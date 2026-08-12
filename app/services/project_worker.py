import logging
import threading
from pathlib import Path

from app.extensions import db
from app.models import Project
from app.services.gpu_power import GpuPowerError, ensure_gpu_awake, schedule_gpu_idle_shelve
from app.services.media_download import MediaDownloadError, download_media_url
from app.services.speechlab import SpeechLabClient
from app.utils.dub_params import close_file_handles, collect_multipart_files_from_paths


logger = logging.getLogger(__name__)


def _apply_response(project, resp):
    if resp.status_code == 503:
        body = resp.json()
        project.status = "error"
        project.error_message = f"Сервер занят (задача {body.get('active_job_id')})"
    elif resp.status_code == 413:
        project.status = "error"
        project.error_message = "Файл слишком большой"
    elif resp.status_code not in (200, 202):
        try:
            project.error_message = resp.json().get("error", resp.text)
        except Exception:
            project.error_message = resp.text[:500]
        project.status = "error"
    else:
        job = resp.json()
        project.job_id = job["id"]
        project.status = job.get("status", "queued")
        project.error_message = None


def _resolve_video_path(app, project, file_paths, video_url, session_dir):
    """Ensure file_paths contains a local video path (download via yt-dlp if needed)."""
    if file_paths.get("video"):
        return file_paths

    if not video_url:
        raise MediaDownloadError("Видеофайл не найден")

    if not app.config.get("YTDLP_ENABLED", True):
        raise MediaDownloadError("Загрузка по ссылке отключена на сервере")

    dest = Path(session_dir) if session_dir else None
    if not dest:
        raise MediaDownloadError("Нет каталога для скачивания")

    path, display_name = download_media_url(
        video_url,
        dest,
        max_mb=app.config["SPEECHLAB_MAX_UPLOAD_MB"],
        timeout_sec=app.config.get("YTDLP_TIMEOUT_SEC", 600),
        max_duration_sec=app.config.get("YTDLP_MAX_DURATION_SEC", 3600),
    )
    file_paths["video"] = path
    if display_name:
        project.original_filename = display_name
    return file_paths


def _upload_project(app, project_id, file_paths, payload, video_url=None, session_dir=None):
    """Download (optional) then upload video and voice samples to SpeechLab."""
    with app.app_context():
        project = db.session.get(Project, project_id)
        if not project:
            return

        files = None
        paths = dict(file_paths or {})
        try:
            paths = _resolve_video_path(app, project, paths, video_url, session_dir)
            db.session.commit()

            files = collect_multipart_files_from_paths(paths)
            if "video" not in files:
                project.status = "error"
                project.error_message = "Видеофайл не найден"
                db.session.commit()
                return

            ensure_gpu_awake()
            client = SpeechLabClient()
            resp = client.create_dub(payload, files=files)
            _apply_response(project, resp)
            if project.status in ("error", "done"):
                schedule_gpu_idle_shelve()
        except MediaDownloadError as exc:
            logger.warning("Media download failed for project %s: %s", project_id, exc)
            project.status = "error"
            project.error_message = str(exc)
            schedule_gpu_idle_shelve()
        except GpuPowerError as exc:
            logger.warning("GPU wake failed for project %s: %s", project_id, exc)
            project.status = "error"
            project.error_message = f"Сервер просыпается / недоступен: {exc}"
            schedule_gpu_idle_shelve()
        except Exception as exc:
            logger.exception("Background upload failed for project %s", project_id)
            project.status = "error"
            project.error_message = str(exc)
            schedule_gpu_idle_shelve()
        finally:
            close_file_handles(files)
            db.session.commit()
            for path in paths.values():
                try:
                    Path(path).unlink(missing_ok=True)
                except Exception:
                    pass


def start_background_upload(app, project_id, file_paths, payload, video_url=None, session_dir=None):
    thread = threading.Thread(
        target=_upload_project,
        args=(app, project_id, file_paths, payload),
        kwargs={"video_url": video_url, "session_dir": session_dir},
        daemon=True,
    )
    thread.start()
