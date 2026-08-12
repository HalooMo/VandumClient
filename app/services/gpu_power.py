"""Selectel OpenStack shelve/unshelve for the SpeechLab GPU server."""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

_wake_lock = threading.Lock()
_idle_lock = threading.Lock()
_idle_timer: threading.Timer | None = None
_idle_generation = 0

SHELVED_STATUSES = frozenset({"SHELVED_OFFLOADED", "SHELVED"})
OFF_STATUSES = frozenset({"SHUTOFF", "STOPPED"})


class GpuPowerError(RuntimeError):
    """OpenStack / wake-sleep failures."""


def _cfg(key: str, default: str = "") -> str:
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            val = current_app.config.get(key)
            if val is not None and val != "":
                return str(val)
    except Exception:
        pass
    return os.environ.get(key, default)


def _cfg_bool(key: str, default: bool = False) -> bool:
    raw = _cfg(key, "true" if default else "false")
    return str(raw).lower() in ("1", "true", "yes")


def _cfg_int(key: str, default: int) -> int:
    try:
        return int(_cfg(key, str(default)))
    except (TypeError, ValueError):
        return default


def is_enabled() -> bool:
    return _cfg_bool("GPU_POWER_ENABLED", False)


class GpuPowerClient:
    """Minimal Keystone + Nova client for one project/region/server."""

    def __init__(self):
        self.auth_url = _cfg("OS_AUTH_URL", "https://cloud.api.selcloud.ru/identity/v3").rstrip("/")
        self.username = _cfg("OS_USERNAME")
        self.password = _cfg("OS_PASSWORD")
        self.user_domain = _cfg("OS_USER_DOMAIN_NAME")
        self.project_id = _cfg("OS_PROJECT_ID")
        self.region = _cfg("OS_REGION_NAME")
        self.server_id = _cfg("GPU_SERVER_ID")
        self.speechlab_base = _cfg("SPEECHLAB_BASE_URL", "https://app.vandum.ru").rstrip("/")
        self.wake_timeout = _cfg_int("GPU_WAKE_TIMEOUT_SEC", 300)
        self.shelve_timeout = _cfg_int("GPU_SHELVE_TIMEOUT_SEC", 300)
        self.health_poll = _cfg_int("GPU_HEALTH_POLL_SEC", 5)
        self.status_poll = _cfg_int("GPU_STATUS_POLL_SEC", 5)
        self._token: str | None = None
        self._compute: str | None = None
        self._missing = [
            name
            for name, val in (
                ("OS_AUTH_URL", self.auth_url),
                ("OS_USERNAME", self.username),
                ("OS_PASSWORD", self.password),
                ("OS_USER_DOMAIN_NAME", self.user_domain),
                ("OS_PROJECT_ID", self.project_id),
                ("OS_REGION_NAME", self.region),
                ("GPU_SERVER_ID", self.server_id),
            )
            if not val
        ]

    def require_configured(self) -> None:
        if self._missing:
            raise GpuPowerError(
                "GPU power не настроен. Задайте в .env: " + ", ".join(self._missing)
            )

    def authenticate(self) -> None:
        self.require_configured()
        payload = {
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": self.username,
                            "domain": {"name": self.user_domain},
                            "password": self.password,
                        }
                    },
                },
                "scope": {"project": {"id": self.project_id}},
            }
        }
        r = requests.post(f"{self.auth_url}/auth/tokens", json=payload, timeout=30)
        if r.status_code not in (200, 201):
            raise GpuPowerError(f"Keystone auth failed: HTTP {r.status_code}")
        self._token = r.headers.get("X-Subject-Token")
        if not self._token:
            raise GpuPowerError("Keystone auth failed: no X-Subject-Token")
        catalog = r.json().get("token", {}).get("catalog", [])
        compute = None
        for svc in catalog:
            if svc.get("type") != "compute":
                continue
            for ep in svc.get("endpoints", []):
                if ep.get("interface") != "public":
                    continue
                reg = ep.get("region") or ep.get("region_id")
                if reg == self.region:
                    compute = ep["url"].rstrip("/")
                    break
            if compute:
                break
        if not compute:
            raise GpuPowerError(f"Compute endpoint not found for region {self.region}")
        self._compute = compute

    def _ensure_auth(self) -> None:
        if not self._token or not self._compute:
            self.authenticate()

    def _headers(self) -> dict[str, str]:
        self._ensure_auth()
        return {"X-Auth-Token": self._token, "Content-Type": "application/json"}

    def _url(self, path: str) -> str:
        self._ensure_auth()
        base = self._compute.rstrip("/")
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{base}{path}"

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        timeout = kwargs.pop("timeout", 60)
        url = self._url(path)
        headers = self._headers()
        r = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
        if r.status_code == 401:
            self.authenticate()
            url = self._url(path)
            headers = self._headers()
            r = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
        return r

    def server_show(self) -> dict[str, Any]:
        r = self._request("GET", f"/servers/{self.server_id}", timeout=30)
        if r.status_code != 200:
            raise GpuPowerError(f"server show failed: HTTP {r.status_code} {(r.text or '')[:300]}")
        return r.json()["server"]

    def _action(self, body: dict) -> None:
        r = self._request("POST", f"/servers/{self.server_id}/action", json=body, timeout=60)
        if r.status_code not in (202, 204):
            raise GpuPowerError(f"server action failed: HTTP {r.status_code} {(r.text or '')[:300]}")

    def unshelve(self) -> dict[str, Any]:
        srv = self.server_show()
        status = srv.get("status")
        if status == "ACTIVE" and not srv.get("OS-EXT-STS:task_state"):
            return srv
        if status in SHELVED_STATUSES:
            logger.info("Unshelving GPU server %s (was %s)", self.server_id, status)
            self._action({"unshelve": None})
        elif status in OFF_STATUSES:
            logger.info("Starting GPU server %s (was %s)", self.server_id, status)
            self._action({"os-start": None})
        elif status == "ACTIVE":
            return srv
        else:
            task = srv.get("OS-EXT-STS:task_state")
            if task in ("unshelving", "spawning", "powering-on"):
                return srv
            raise GpuPowerError(f"Cannot wake server in status={status} task={task}")
        return self.wait_active()

    def shelve(self) -> dict[str, Any]:
        srv = self.server_show()
        status = srv.get("status")
        if status in SHELVED_STATUSES and not srv.get("OS-EXT-STS:task_state"):
            return srv
        if status != "ACTIVE" and status not in SHELVED_STATUSES:
            task = srv.get("OS-EXT-STS:task_state")
            if task in ("shelving", "shelving_image_pending_upload", "shelving_image_uploading"):
                return self.wait_shelved()
            raise GpuPowerError(f"Cannot shelve server in status={status} task={task}")
        logger.info("Shelving GPU server %s (was %s)", self.server_id, status)
        self._action({"shelve": None})
        return self.wait_shelved()

    def wait_active(self, timeout: int | None = None) -> dict[str, Any]:
        deadline = time.time() + (timeout if timeout is not None else self.wake_timeout)
        last = None
        while time.time() < deadline:
            srv = self.server_show()
            status = srv.get("status")
            task = srv.get("OS-EXT-STS:task_state")
            line = f"{status}/{task}"
            if line != last:
                logger.info("GPU server %s: status=%s task=%s", self.server_id, status, task)
                last = line
            if status == "ACTIVE" and not task:
                return srv
            if status == "ERROR":
                raise GpuPowerError(f"Server entered ERROR: {srv.get('fault')}")
            time.sleep(self.status_poll)
        raise GpuPowerError(f"Timeout waiting for ACTIVE ({timeout or self.wake_timeout}s)")

    def wait_shelved(self, timeout: int | None = None) -> dict[str, Any]:
        deadline = time.time() + (timeout if timeout is not None else self.shelve_timeout)
        last = None
        while time.time() < deadline:
            srv = self.server_show()
            status = srv.get("status")
            task = srv.get("OS-EXT-STS:task_state")
            line = f"{status}/{task}"
            if line != last:
                logger.info("GPU server %s: status=%s task=%s", self.server_id, status, task)
                last = line
            if status in SHELVED_STATUSES and not task:
                return srv
            if status == "ERROR":
                raise GpuPowerError(f"Server entered ERROR: {srv.get('fault')}")
            time.sleep(self.status_poll)
        raise GpuPowerError(f"Timeout waiting for SHELVED ({timeout or self.shelve_timeout}s)")

    def check_health(self, timeout: int = 5) -> tuple[bool, int | None, str]:
        url = f"{self.speechlab_base}/health"
        try:
            r = requests.get(url, timeout=timeout)
            return True, r.status_code, (r.text or "")[:300]
        except Exception as exc:
            return False, None, f"{type(exc).__name__}: {exc}"

    def wait_health(self, timeout: int | None = None) -> None:
        deadline = time.time() + (timeout if timeout is not None else self.wake_timeout)
        while time.time() < deadline:
            ok, code, detail = self.check_health()
            if ok and code == 200:
                logger.info("SpeechLab health OK at %s", self.speechlab_base)
                return
            logger.debug("SpeechLab health not ready: code=%s detail=%s", code, detail)
            time.sleep(self.health_poll)
        raise GpuPowerError(
            f"Timeout waiting for {self.speechlab_base}/health ({timeout or self.wake_timeout}s)"
        )

    def ensure_awake(self) -> dict[str, Any]:
        """Unshelve if needed and wait until SpeechLab /health returns 200."""
        ok, code, _ = self.check_health(timeout=3)
        if ok and code == 200:
            srv = self.server_show()
            return {"already_up": True, "server": srv}

        with _wake_lock:
            ok, code, _ = self.check_health(timeout=3)
            if ok and code == 200:
                return {"already_up": True, "server": self.server_show()}

            t0 = time.time()
            srv = self.unshelve()
            remaining = max(30, self.wake_timeout - int(time.time() - t0))
            self.wait_health(timeout=remaining)
            return {
                "already_up": False,
                "elapsed_sec": round(time.time() - t0, 1),
                "server": srv,
            }


def ensure_gpu_awake() -> dict[str, Any] | None:
    """No-op unless GPU_POWER_ENABLED. Raises GpuPowerError on failure."""
    if not is_enabled():
        return None
    cancel_gpu_idle_shelve()
    client = GpuPowerClient()
    result = client.ensure_awake()
    logger.info(
        "GPU awake: already_up=%s elapsed=%s status=%s",
        result.get("already_up"),
        result.get("elapsed_sec"),
        (result.get("server") or {}).get("status"),
    )
    return result


def cancel_gpu_idle_shelve() -> None:
    """Cancel a pending idle shelve (new job / wake / download)."""
    global _idle_timer, _idle_generation
    with _idle_lock:
        _idle_generation += 1
        if _idle_timer is not None:
            _idle_timer.cancel()
            _idle_timer = None
            logger.debug("GPU idle shelve cancelled")


def schedule_gpu_idle_shelve() -> None:
    """After jobs finish: shelve GPU if still idle for GPU_IDLE_SEC (default 60)."""
    global _idle_timer, _idle_generation
    if not is_enabled():
        return

    idle_sec = max(1, _cfg_int("GPU_IDLE_SEC", 60))
    app = None
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            app = current_app._get_current_object()
    except Exception:
        app = None

    with _idle_lock:
        _idle_generation += 1
        gen = _idle_generation
        if _idle_timer is not None:
            _idle_timer.cancel()

        def _fire():
            _try_idle_shelve(gen, app)

        _idle_timer = threading.Timer(idle_sec, _fire)
        _idle_timer.daemon = True
        _idle_timer.start()
        logger.info("GPU idle shelve scheduled in %ss (gen=%s)", idle_sec, gen)


def _local_jobs_busy() -> bool:
    from app.models import ApiJob, Project
    from app.utils.status import ACTIVE_STATUSES

    if Project.query.filter(Project.status.in_(tuple(ACTIVE_STATUSES))).count():
        return True
    if ApiJob.query.filter(ApiJob.status.in_(tuple(ACTIVE_STATUSES))).count():
        return True
    return False


def _upstream_busy(client: GpuPowerClient) -> bool:
    try:
        r = requests.get(f"{client.speechlab_base}/health", timeout=5)
        if r.status_code != 200:
            return True
        data = r.json() if r.content else {}
    except Exception:
        return True
    return bool(data.get("active_job"))


def _try_idle_shelve(gen: int, app) -> None:
    with _idle_lock:
        if gen != _idle_generation:
            return

    def _run():
        if not is_enabled():
            return
        if _local_jobs_busy():
            logger.info("GPU idle shelve deferred: local jobs still active")
            schedule_gpu_idle_shelve()
            return
        client = GpuPowerClient()
        try:
            srv = client.server_show()
        except GpuPowerError as exc:
            logger.warning("GPU idle shelve: status check failed: %s", exc)
            return
        status = srv.get("status")
        if status in SHELVED_STATUSES:
            logger.info("GPU already shelved, skip idle shelve")
            return
        if _upstream_busy(client):
            logger.info("GPU idle shelve deferred: upstream active_job")
            schedule_gpu_idle_shelve()
            return
        try:
            with _wake_lock:
                with _idle_lock:
                    if gen != _idle_generation:
                        return
                if _local_jobs_busy() or _upstream_busy(client):
                    schedule_gpu_idle_shelve()
                    return
                logger.info("GPU idle timeout reached — shelving server %s", client.server_id)
                client.shelve()
        except GpuPowerError as exc:
            logger.warning("GPU idle shelve failed: %s", exc)

    if app is not None:
        with app.app_context():
            _run()
    else:
        _run()
