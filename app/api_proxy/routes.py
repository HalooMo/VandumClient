from datetime import datetime, timezone
import re
import tempfile
import threading

from flask import Blueprint, Response, current_app, jsonify, request
from flask_limiter.util import get_remote_address

from app.api_proxy.auth import require_api_key
from app.extensions import db, limiter
from app.models import ApiJob
from app.services.media_download import MediaDownloadError, download_media_url, validate_media_url
from app.services.quotas import check_dub_quota, dub_quota_remaining, record_dub_usage
from app.services.speechlab import SpeechLabClient
from app.utils.dub_params import (
    build_dub_form_data,
    close_file_handles,
    collect_multipart_files,
    collect_multipart_files_from_paths,
    sanitize_upstream_json,
    validate_video_file,
)

api_proxy_bp = Blueprint("api_proxy", __name__)

_YTDLP_API_SLOTS = threading.Semaphore(2)


def _safe_download_filename(project_name):
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", (project_name or "project"))[:64]
    return f"{safe or 'project'}_dubbed.mp4"


def _api_download_by_url(video_url, dest_dir):
    """Download with concurrency cap and capped timeout (API request path)."""
    if not _YTDLP_API_SLOTS.acquire(blocking=False):
        raise MediaDownloadError("Сервер занят скачиванием по URL. Повторите через минуту.")
    try:
        timeout = min(int(current_app.config.get("YTDLP_TIMEOUT_SEC", 600)), 180)
        return download_media_url(
            video_url,
            dest_dir,
            max_mb=current_app.config["SPEECHLAB_MAX_UPLOAD_MB"],
            timeout_sec=timeout,
            max_duration_sec=current_app.config.get("YTDLP_MAX_DURATION_SEC", 3600),
        )
    finally:
        _YTDLP_API_SLOTS.release()


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
    record_dub_usage(api_key.user_id, source="api")
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
        public = {"status": data.get("status", "unknown"), "proxy": "dpunk-client"}
        if not is_production():
            public["upstream"] = data
        return jsonify(public)
    except Exception as exc:
        body = {"status": "offline", "proxy": "dpunk-client"}
        if not is_production():
            body["error"] = str(exc)
        return jsonify(body), 503


@api_proxy_bp.route("/api/v1/cast-voices")
@require_api_key
def cast_voices(api_key):
    try:
        resp = SpeechLabClient().list_cast_voices()
        return _proxy_response(resp)
    except Exception as exc:
        return _json_error(str(exc), 502)


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
    files = None
    downloaded_paths = {}
    temp_dir = None

    try:
        if request.content_type and "multipart/form-data" in request.content_type:
            video = request.files.get("video")
            video_url = (request.form.get("video_url") or "").strip()
            if video and video.filename and video_url:
                return _json_error("Укажите либо video, либо video_url — не оба сразу.", 400)
            if video and video.filename:
                size_err = validate_video_file(
                    video.filename,
                    current_app.config["SPEECHLAB_MAX_UPLOAD_MB"],
                    video,
                )
                if size_err:
                    return _json_error(size_err, 413)
            payload = build_dub_form_data(formdata=request.form)
            files = collect_multipart_files(request.files) or {}
            if video_url and "video" not in files:
                err = validate_media_url(video_url)
                if err:
                    return _json_error(err, 400)
                if not current_app.config.get("YTDLP_ENABLED", True):
                    return _json_error("Загрузка по ссылке отключена на сервере.", 503)
                temp_dir = tempfile.TemporaryDirectory(prefix="dpunk_ytdlp_")
                try:
                    path, _ = _api_download_by_url(video_url, temp_dir.name)
                except MediaDownloadError as exc:
                    return _json_error(str(exc), 400)
                downloaded_paths["video"] = path
                video_files = collect_multipart_files_from_paths(downloaded_paths) or {}
                files = {**files, **video_files}
            resp = client.create_dub(payload, files=files or None)
        elif request.is_json:
            raw = request.get_json(silent=True) or {}
            video_url = (raw.get("video_url") or "").strip() if isinstance(raw, dict) else ""
            payload = sanitize_upstream_json(raw)
            payload.pop("video_url", None)
            if video_url:
                if payload.get("video_path"):
                    return _json_error("Укажите либо video_path, либо video_url.", 400)
                err = validate_media_url(video_url)
                if err:
                    return _json_error(err, 400)
                if not current_app.config.get("YTDLP_ENABLED", True):
                    return _json_error("Загрузка по ссылке отключена на сервере.", 503)
                temp_dir = tempfile.TemporaryDirectory(prefix="dpunk_ytdlp_")
                try:
                    path, _ = _api_download_by_url(video_url, temp_dir.name)
                except MediaDownloadError as exc:
                    return _json_error(str(exc), 400)
                downloaded_paths["video"] = path
                files = collect_multipart_files_from_paths(downloaded_paths)
                resp = client.create_dub(payload, files=files)
            else:
                resp = client.create_dub_json(payload)
        else:
            video_url = (request.form.get("video_url") or "").strip()
            payload = build_dub_form_data(formdata=request.form)
            if video_url:
                err = validate_media_url(video_url)
                if err:
                    return _json_error(err, 400)
                if not current_app.config.get("YTDLP_ENABLED", True):
                    return _json_error("Загрузка по ссылке отключена на сервере.", 503)
                temp_dir = tempfile.TemporaryDirectory(prefix="dpunk_ytdlp_")
                try:
                    path, _ = _api_download_by_url(video_url, temp_dir.name)
                except MediaDownloadError as exc:
                    return _json_error(str(exc), 400)
                downloaded_paths["video"] = path
                files = collect_multipart_files_from_paths(downloaded_paths)
                resp = client.create_dub(payload, files=files)
            else:
                resp = client.create_dub(payload)

        if resp.status_code in (200, 202):
            try:
                upstream = resp.json()
                _register_job(api_key, payload, upstream)
            except Exception:
                current_app.logger.exception("Failed to register API job locally")

        return _proxy_response(resp)
    finally:
        close_file_handles(files)
        if temp_dir is not None:
            temp_dir.cleanup()


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
            try:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        yield chunk
            finally:
                resp.close()

        headers = {}
        cd = resp.headers.get("Content-Disposition")
        if cd and "\n" not in cd and "\r" not in cd:
            headers["Content-Disposition"] = cd
        else:
            headers["Content-Disposition"] = (
                f'attachment; filename="{_safe_download_filename(record.project_name)}"'
            )

        return Response(
            generate(),
            status=200,
            mimetype=resp.headers.get("Content-Type", "video/mp4"),
            headers=headers,
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502
