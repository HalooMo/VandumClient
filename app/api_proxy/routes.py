from datetime import datetime, timezone

from flask import Blueprint, Response, current_app, jsonify, request
from flask_limiter.util import get_remote_address

from app.api_proxy.auth import require_api_key
from app.extensions import db, limiter
from app.models import ApiJob
from app.services.quotas import check_dub_quota, dub_quota_remaining
from app.services.speechlab import SpeechLabClient
from app.utils.dub_params import (
    build_dub_form_data,
    collect_multipart_files,
    sanitize_upstream_json,
)

api_proxy_bp = Blueprint("api_proxy", __name__)


def _api_key_identifier():
    from app.api_proxy.auth import _extract_api_key
    key = _extract_api_key()
    if key:
        return f"apikey:{key[:20]}"
    return get_remote_address()


def _api_dub_limit():
    return current_app.config.get("RATELIMIT_API_DUB", "10 per hour")


def _json_error(message, status=400):
    return jsonify({"error": message}), status


def _proxy_response(resp):
    content_type = resp.headers.get("Content-Type", "application/json")
    return Response(resp.content, status=resp.status_code, content_type=content_type)


def _job_owned(user_id, job_id):
    return ApiJob.query.filter_by(user_id=user_id, job_id=job_id).first()


def _register_job(api_key, payload, upstream):
    job = ApiJob(
        user_id=api_key.user_id,
        api_key_id=api_key.id,
        job_id=upstream["id"],
        project_name=upstream.get("project_name") or payload.get("project_name", ""),
        source_language=upstream.get("source_language") or payload.get("source_language"),
        target_language=upstream.get("target_language") or payload.get("target_language"),
        status=upstream.get("status", "queued"),
    )
    db.session.add(job)
    db.session.commit()
    return job


def _sync_job_record(record, upstream):
    record.status = upstream.get("status", record.status)
    if upstream.get("error"):
        record.error_message = upstream["error"]
    if upstream.get("status") == "done":
        record.finished_at = datetime.now(timezone.utc)
    db.session.commit()


@api_proxy_bp.route("/health")
def health():
    from app.utils.security import is_production

    try:
        data = SpeechLabClient().health(timeout=5)
        public = {"status": data.get("status", "unknown"), "proxy": "vandum-client"}
        if not is_production():
            public["upstream"] = data
        return jsonify(public)
    except Exception as exc:
        body = {"status": "offline", "proxy": "vandum-client"}
        if not is_production():
            body["error"] = str(exc)
        return jsonify(body), 503


@api_proxy_bp.route("/api/v1/dub", methods=["POST"])
@require_api_key
@limiter.limit(_api_dub_limit, key_func=_api_key_identifier, exempt_when=lambda: not current_app.config.get("RATELIMIT_ENABLED", True))
def create_dub(api_key):
    if not check_dub_quota(api_key.user_id):
        remaining, limit = dub_quota_remaining(api_key.user_id)
        return jsonify({
            "error": f"Дневной лимит задач ({limit}) исчерпан. Попробуйте завтра.",
            "quota_remaining": remaining,
        }), 429

    client = SpeechLabClient()
    payload = {}

    if request.content_type and "multipart/form-data" in request.content_type:
        payload = build_dub_form_data(formdata=request.form)
        files = collect_multipart_files(request.files)
        resp = client.create_dub(payload, files=files)
    elif request.is_json:
        payload = sanitize_upstream_json(request.get_json(silent=True) or {})
        resp = client.create_dub_json(payload)
    else:
        payload = build_dub_form_data(formdata=request.form)
        resp = client.create_dub(payload)

    if resp.status_code in (200, 202):
        try:
            upstream = resp.json()
            _register_job(api_key, payload, upstream)
        except Exception:
            pass

    return _proxy_response(resp)


@api_proxy_bp.route("/api/v1/jobs")
@require_api_key
def list_jobs(api_key):
    records = (
        ApiJob.query.filter_by(user_id=api_key.user_id)
        .order_by(ApiJob.created_at.desc())
        .limit(50)
        .all()
    )
    client = SpeechLabClient()
    jobs = []
    for record in records:
        try:
            resp = client.get_job(record.job_id)
            if resp.status_code == 200:
                upstream = resp.json()
                _sync_job_record(record, upstream)
                jobs.append(upstream)
            else:
                jobs.append(_job_snapshot(record))
        except Exception:
            jobs.append(_job_snapshot(record))
    return jsonify(jobs)


def _job_snapshot(record):
    return {
        "id": record.job_id,
        "status": record.status,
        "project_name": record.project_name,
        "source_language": record.source_language,
        "target_language": record.target_language,
        "error": record.error_message,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "finished_at": record.finished_at.isoformat() if record.finished_at else None,
    }


@api_proxy_bp.route("/api/v1/jobs/<job_id>")
@require_api_key
def get_job(api_key, job_id):
    record = _job_owned(api_key.user_id, job_id)
    if not record:
        return _json_error("Задача не найдена", 404)

    try:
        resp = SpeechLabClient().get_job(job_id)
        if resp.status_code == 200:
            _sync_job_record(record, resp.json())
        return _proxy_response(resp)
    except Exception as exc:
        return jsonify({"error": str(exc), "status": record.status}), 502


@api_proxy_bp.route("/api/v1/jobs/<job_id>/download")
@require_api_key
def download_job(api_key, job_id):
    record = _job_owned(api_key.user_id, job_id)
    if not record:
        return _json_error("Задача не найдена", 404)

    try:
        resp = SpeechLabClient().download_job(job_id)

        if resp.status_code != 200:
            return _proxy_response(resp)

        def generate():
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    yield chunk

        headers = {}
        cd = resp.headers.get("Content-Disposition")
        if cd:
            headers["Content-Disposition"] = cd
        else:
            headers["Content-Disposition"] = f'attachment; filename="{record.project_name}_dubbed.mp4"'

        return Response(
            generate(),
            status=200,
            mimetype=resp.headers.get("Content-Type", "video/mp4"),
            headers=headers,
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502
