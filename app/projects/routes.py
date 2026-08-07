import re
from datetime import datetime, timezone
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from app.decorators import verified_required
from app.extensions import db
from app.forms import CreateProjectForm
from app.models import Project
from app.services.media_download import validate_media_url
from app.services.project_worker import start_background_upload
from app.services.quotas import check_dub_quota, dub_quota_remaining, record_dub_usage
from app.services.speechlab import SpeechLabClient
from app.utils.dub_params import (
    SAMPLE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    build_dub_form_data,
    build_voice_options_json,
    extract_user_voice_prompt,
    parse_voice_options,
    save_upload_file,
    validate_sample_file,
    validate_video_file,
)
from app.utils.status import ACTIVE_STATUSES, is_active, status_label

projects_bp = Blueprint("projects", __name__, url_prefix="/projects")


def _populate_language_choices(form):
    langs = current_app.config["LANGUAGES"]
    form.source_language.choices = langs
    form.target_language.choices = [l for l in langs if l[0] != "auto"]


def _collect_uploads(form, project_name):
    """Collect local file and/or video_url. Returns (file_paths, payload, voice_options, video_url, session_dir, original_filename, err)."""
    video = request.files.get("video")
    has_file = bool(video and video.filename)
    video_url = (getattr(form, "video_url", None) and form.video_url.data or "").strip()
    if not video_url:
        video_url = (request.form.get("video_url") or "").strip()

    if has_file and video_url:
        return None, None, None, None, None, None, "Укажите либо файл, либо ссылку — не оба сразу."
    if not has_file and not video_url:
        return None, None, None, None, None, None, "Загрузите файл или вставьте ссылку на медиа."

    if video_url:
        if not current_app.config.get("YTDLP_ENABLED", True):
            return None, None, None, None, None, None, "Загрузка по ссылке отключена на сервере."
        url_err = validate_media_url(video_url)
        if url_err:
            return None, None, None, None, None, None, url_err

    upload_root = Path(current_app.config["UPLOAD_FOLDER"])
    user_dir = upload_root / str(current_user.id)
    session_dir = user_dir / "pending" / re.sub(r"[^a-zA-Z0-9_-]", "_", project_name)
    session_dir.mkdir(parents=True, exist_ok=True)

    file_paths = {}
    original_filename = None

    if has_file:
        err = validate_video_file(
            video.filename, current_app.config["SPEECHLAB_MAX_UPLOAD_MB"], video
        )
        if err:
            return None, None, None, None, None, None, err
        video_path, err = save_upload_file(
            video,
            session_dir,
            "video",
            VIDEO_EXTENSIONS,
            current_app.config["SPEECHLAB_MAX_UPLOAD_MB"],
        )
        if err:
            return None, None, None, None, None, None, err
        file_paths["video"] = video_path
        original_filename = video.filename
        video_url = None
    else:
        original_filename = video_url[:200]

    sample_meta = {}
    max_sample = current_app.config["VOICE_SAMPLE_MAX_MB"]

    for field, key in (("voice_sample_male", "male"), ("voice_sample_female", "female")):
        sample = request.files.get(field)
        if sample and sample.filename:
            serr = validate_sample_file(sample.filename, max_sample, sample)
            if serr:
                return None, None, None, None, None, None, serr
            spath, serr = save_upload_file(
                sample, session_dir, field, SAMPLE_EXTENSIONS, max_sample
            )
            if serr:
                return None, None, None, None, None, None, serr
            file_paths[field] = spath
            sample_meta[key] = sample.filename

    payload = build_dub_form_data(form, request.form)
    formdata = request.form.to_dict()
    if video_url:
        formdata["video_url"] = video_url
    voice_options = build_voice_options_json(formdata, sample_meta)

    return file_paths, payload, voice_options, video_url, str(session_dir), original_filename, None


def _apply_project_fields(project, form, voice_options, original_filename):
    project.source_language = form.source_language.data
    project.target_language = form.target_language.data
    project.voice_gender = form.voice_gender.data or None
    project.voice_age = form.voice_age.data
    project.voice_prompt = form.voice_prompt.data or None
    project.voice_options = voice_options
    project.original_filename = original_filename
    project.error_message = None
    project.finished_at = None


def _start_project(form, existing=None):
    if not check_dub_quota(current_user.id):
        _, limit = dub_quota_remaining(current_user.id)
        return None, f"Дневной лимит задач ({limit}) исчерпан. Попробуйте завтра."

    (
        file_paths,
        payload,
        voice_options,
        video_url,
        session_dir,
        original_filename,
        err,
    ) = _collect_uploads(form, form.project_name.data)
    if err:
        return None, err

    if existing:
        existing.job_id = None
        existing.status = "uploading"
        _apply_project_fields(existing, form, voice_options, original_filename)
        project = existing
    else:
        project = Project(
            user_id=current_user.id,
            project_name=form.project_name.data,
            source_language=form.source_language.data,
            target_language=form.target_language.data,
            status="uploading",
            voice_gender=form.voice_gender.data or None,
            voice_age=form.voice_age.data,
            voice_prompt=form.voice_prompt.data or None,
            voice_options=voice_options,
            original_filename=original_filename,
        )
        db.session.add(project)

    record_dub_usage(current_user.id, source="web")
    db.session.commit()

    start_background_upload(
        current_app._get_current_object(),
        project.id,
        file_paths,
        payload,
        video_url=video_url,
        session_dir=session_dir,
    )
    return project, None


@projects_bp.route("/")
@login_required
def list_projects():
    projects = (
        Project.query.filter_by(user_id=current_user.id)
        .order_by(Project.created_at.desc())
        .all()
    )
    active = [p for p in projects if is_active(p.status)]
    completed = [p for p in projects if not is_active(p.status)]
    return render_template(
        "projects/list.html",
        projects=projects,
        active_projects=active,
        completed_projects=completed,
    )


@projects_bp.route("/create", methods=["GET", "POST"])
@login_required
@verified_required
def create():
    form = CreateProjectForm()
    _populate_language_choices(form)

    if form.validate_on_submit():
        existing = Project.query.filter_by(
            user_id=current_user.id,
            project_name=form.project_name.data,
        ).first()
        if existing and is_active(existing.status):
            flash("Проект с таким именем уже обрабатывается.", "error")
            return render_template("projects/create.html", form=form)

        project, err = _start_project(form, existing=existing)
        if err:
            flash(err, "error")
            return render_template("projects/create.html", form=form)

        flash("Проект запущен! Отслеживайте статус на странице проекта.", "success")
        return redirect(url_for("projects.detail", project_id=project.id))

    return render_template("projects/create.html", form=form)


@projects_bp.route("/status-batch")
@login_required
def status_batch():
    projects = (
        Project.query.filter_by(user_id=current_user.id)
        .filter(Project.status.in_(list(ACTIVE_STATUSES)))
        .all()
    )

    client = SpeechLabClient()
    results = []

    for project in projects:
        if project.job_id:
            try:
                resp = client.get_job(project.job_id)
                if resp.status_code == 200:
                    data = resp.json()
                    project.status = data.get("status", project.status)
                    if data.get("error"):
                        project.error_message = data["error"]
                    if data.get("status") == "done":
                        project.finished_at = datetime.now(timezone.utc)
            except Exception:
                pass

        results.append({
            "id": project.id,
            "status": project.status,
            "status_label": status_label(project.status),
            "error": project.error_message,
        })

    db.session.commit()
    return jsonify({"projects": results})


@projects_bp.route("/<int:project_id>/edit", methods=["GET", "POST"])
@login_required
@verified_required
def edit(project_id):
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first_or_404()
    if is_active(project.status):
        flash("Проект ещё обрабатывается. Дождитесь завершения.", "warning")
        return redirect(url_for("projects.detail", project_id=project.id))

    form = CreateProjectForm()
    _populate_language_choices(form)
    opts = parse_voice_options(project.voice_options)

    if request.method == "GET":
        form.project_name.data = project.project_name
        form.source_language.data = project.source_language
        form.target_language.data = project.target_language
        form.voice_gender.data = project.voice_gender or ""
        form.voice_age.data = project.voice_age
        form.voice_prompt.data = extract_user_voice_prompt(project.voice_prompt) or project.voice_prompt or ""
        temp = opts.get("voice_design_temperature")
        if temp is not None:
            try:
                form.voice_design_temperature.data = float(temp)
            except (TypeError, ValueError):
                pass
        form.voice_sample_male_ref_text.data = opts.get("voice_sample_male_ref_text", "")
        form.voice_sample_female_ref_text.data = opts.get("voice_sample_female_ref_text", "")
        form.silero_speaker.data = opts.get("silero_speaker", "")
        form.silero_all_replicas.data = str(opts.get("silero_all_replicas", "")).lower() in ("1", "true", "yes")
        if opts.get("cast_mode") == "speakers":
            form.cast_mode.data = "speakers"
            form.cast_voice.data = ""
        elif opts.get("cast_voice"):
            form.cast_mode.data = "voice"
            form.cast_voice.data = opts.get("cast_voice", "")
        else:
            form.cast_mode.data = ""
            form.cast_voice.data = ""

    if form.validate_on_submit():
        if form.project_name.data != project.project_name:
            flash("Нельзя изменить имя существующего проекта.", "error")
            return render_template("projects/edit.html", form=form, project=project, voice_opts=opts)

        updated, err = _start_project(form, existing=project)
        if err:
            flash(err, "error")
            return render_template("projects/edit.html", form=form, project=project, voice_opts=opts)

        flash("Проект перезапущен с новыми настройками.", "success")
        return redirect(url_for("projects.detail", project_id=updated.id))

    return render_template("projects/edit.html", form=form, project=project, voice_opts=opts)


@projects_bp.route("/<int:project_id>")
@login_required
def detail(project_id):
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first_or_404()
    return render_template(
        "projects/detail.html",
        project=project,
        voice_opts=parse_voice_options(project.voice_options),
    )


@projects_bp.route("/<int:project_id>/status")
@login_required
def status_api(project_id):
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first_or_404()

    if project.status == "uploading" or not project.job_id:
        return jsonify({
            "status": project.status,
            "status_label": status_label(project.status),
            "error": project.error_message,
        })

    try:
        client = SpeechLabClient()
        resp = client.get_job(project.job_id)
        if resp.status_code == 200:
            data = resp.json()
            project.status = data.get("status", project.status)
            if data.get("error"):
                project.error_message = data["error"]
            if data.get("status") == "done":
                project.finished_at = datetime.now(timezone.utc)
            db.session.commit()
            data["status_label"] = status_label(project.status)
            return jsonify(data)
    except Exception as e:
        return jsonify({
            "status": project.status,
            "status_label": status_label(project.status),
            "error": str(e),
        })

    return jsonify({
        "status": project.status,
        "status_label": status_label(project.status),
    })


@projects_bp.route("/<int:project_id>/download")
@login_required
@verified_required
def download(project_id):
    return _proxy_result_media(project_id, disposition="attachment")


@projects_bp.route("/<int:project_id>/stream")
@login_required
@verified_required
def stream(project_id):
    """Inline MP4 stream for in-browser player (supports Range when upstream does)."""
    return _proxy_result_media(project_id, disposition="inline")


def _proxy_result_media(project_id, disposition="attachment"):
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first_or_404()
    if project.status != "done" or not project.job_id:
        if disposition == "inline":
            return Response("Результат ещё не готов", status=404)
        flash("Результат ещё не готов.", "warning")
        return redirect(url_for("projects.detail", project_id=project.id))

    try:
        extra = {}
        range_header = request.headers.get("Range")
        if range_header:
            extra["Range"] = range_header

        client = SpeechLabClient()
        resp = client.download_job(project.job_id, extra_headers=extra or None)
        if resp.status_code not in (200, 206):
            if disposition == "inline":
                return Response("Не удалось загрузить видео", status=502)
            flash("Не удалось скачать файл.", "error")
            return redirect(url_for("projects.detail", project_id=project.id))

        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", project.project_name or "project")[:64]
        filename = f"{safe_name}_dubbed.mp4"

        def generate():
            try:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        yield chunk
            finally:
                resp.close()

        headers = {
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "Cache-Control": "private, max-age=3600",
        }
        for key in ("Content-Length", "Content-Range", "Accept-Ranges"):
            val = resp.headers.get(key)
            if val:
                headers[key] = val

        return Response(
            generate(),
            status=resp.status_code,
            mimetype=resp.headers.get("Content-Type", "video/mp4"),
            headers=headers,
        )
    except Exception as e:
        if disposition == "inline":
            return Response(str(e), status=502)
        flash(f"Ошибка скачивания: {e}", "error")
        return redirect(url_for("projects.detail", project_id=project.id))
