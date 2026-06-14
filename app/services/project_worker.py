import logging
import threading
from pathlib import Path

from app.extensions import db
from app.models import Project
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


def _upload_project(app, project_id, file_paths, payload):
    """Upload video and optional voice samples to SpeechLab in background."""
    with app.app_context():
        project = db.session.get(Project, project_id)
        if not project:
            return

        files = None
        try:
            files = collect_multipart_files_from_paths(file_paths)
            if "video" not in files:
                project.status = "error"
                project.error_message = "Видеофайл не найден"
                db.session.commit()
                return

            client = SpeechLabClient()
            resp = client.create_dub(payload, files=files)
            _apply_response(project, resp)
        except Exception as exc:
            logger.exception("Background upload failed for project %s", project_id)
            project.status = "error"
            project.error_message = str(exc)
        finally:
            close_file_handles(files)
            db.session.commit()
            for path in file_paths.values():
                try:
                    Path(path).unlink(missing_ok=True)
                except Exception:
                    pass


def start_background_upload(app, project_id, file_paths, payload):
    thread = threading.Thread(
        target=_upload_project,
        args=(app, project_id, file_paths, payload),
        daemon=True,
    )
    thread.start()
