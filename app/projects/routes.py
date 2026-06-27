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
from app.services.project_worker import start_background_upload
from app.services.quotas import check_dub_quota, dub_quota_remaining
from app.services.speechlab import SpeechLabClient
from app.utils.dub_params import (
    SAMPLE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    build_dub_form_data,
    build_voice_options_json,
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
    video = request.files.get("video")
    if not video or not video.filename:
        return None, None, None, "Загрузите видео или аудио файл."

    err = validate_video_file(video.filename, current_app.config["SPEECHLAB_MAX_UPLOAD_MB"], video)
    if err:
        return None, None, None, err

    upload_root = Path(current_app.config["UPLOAD_FOLDER"])
    user_dir = upload_root / str(current_user.id)
    session_dir = user_dir / "pending" / re.sub(r"[^a-zA-Z0-9_-]", "_", project_name)
    session_dir.mkdir(parents=True, exist_ok=True)

    video_path, err = save_upload_file(
        video, session_dir, "video", VIDEO_EXTENSIONS, current_app.config["SPEECHLAB_MAX_UPLOAD_MB"]
    )
    if err:
        return None, None, None, err

    file_paths = {"video": video_path}
    sample_meta = {}
    max_sample = current_app.config["VOICE_SAMPLE_MAX_MB"]

    for field, key in (("voice_sample_male", "male"), ("voice_sample_female", "female")):
        sample = request.files.get(field)
        if sample and sample.filename:
            serr = validate_sample_file(sample.filename, max_sample, sample)
            if serr:
                return None, None, None, serr
            spath, serr = save_upload_file(
                sample, session_dir, field, SAMPLE_EXTENSIONS, max_sample
            )
            if serr:
                return None, None, None, serr
            file_paths[field] = spath
            sample_meta[key] = sample.filename

    payload = build_dub_form_data(form, request.form)
    voice_options = build_voice_options_json(request.form, sample_meta)

    return file_paths, payload, voice_options, None


def _apply_project_fields(project, form, voice_options):
    project.source_language = form.source_language.data
    project.target_language = form.target_language.data
    project.voice_gender = form.voice_gender.data or None
    project.voice_age = form.voice_age.data
    project.voice_prompt = form.voice_prompt.data or None
    project.voice_options = voice_options
    project.original_filename = request.files.get("video").filename
    project.error_message = None
    project.finished_at = None


def _start_project(form, existing=None):
    if not check_dub_quota(current_user.id):
        _, limit = dub_quota_remaining(current_user.id)
        return None, f"Дневной лимит задач ({limit}) исчерпан. Попробуйте завтра."

    file_paths, payload, voice_options, err = _collect_uploads(form, form.project_name.data)
    if err:
        return None, err

    if existing:
        existing.job_id = None
        existing.status = "uploading"
        _apply_project_fields(existing, form, voice_options)
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
            original_filename=request.files.get("video").filename,
        )
        db.session.add(project)

    db.session.commit()

    start_background_upload(
        current_app._get_current_object(),
        project.id,
        file_paths,
        payload,
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
        form.voice_prompt.data = project.voice_prompt or ""
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
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first_or_404()
    if project.status != "done" or not project.job_id:
        flash("Результат ещё не готов.", "warning")
        return redirect(url_for("projects.detail", project_id=project.id))

    try:
        client = SpeechLabClient()
        resp = client.download_job(project.job_id)
        if resp.status_code != 200:
            flash("Не удалось скачать файл.", "error")
            return redirect(url_for("projects.detail", project_id=project.id))

        filename = f"{project.project_name}_dubbed.mp4"

        def generate():
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    yield chunk

        return Response(
            generate(),
            mimetype="video/mp4",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        flash(f"Ошибка скачивания: {e}", "error")
        return redirect(url_for("projects.detail", project_id=project.id))
