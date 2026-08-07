"""Download media by URL via yt-dlp with size/SSRF guards."""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from pathlib import Path
from urllib.parse import urlparse

from app.utils.dub_params import VIDEO_EXTENSIONS

logger = logging.getLogger(__name__)

_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")


class MediaDownloadError(Exception):
    """User-facing download failure."""


def _clean_url(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def validate_media_url(raw_url: str | None) -> str | None:
    """Return an error message if URL is invalid; otherwise None."""
    url = _clean_url(raw_url)
    if not url:
        return "Укажите ссылку на медиа"
    if len(url) > 2048:
        return "Ссылка слишком длинная"
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return "Ссылка должна начинаться с http:// или https://"
    if not parsed.hostname:
        return "Некорректная ссылка"
    host = parsed.hostname.lower()
    if host in ("localhost", "metadata.google.internal"):
        return "Этот хост недоступен для скачивания"
    try:
        _assert_public_host(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except MediaDownloadError as exc:
        return str(exc)
    return None


def _assert_public_host(hostname: str, port: int) -> None:
    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise MediaDownloadError(f"Не удалось разрешить хост: {hostname}") from exc

    if not infos:
        raise MediaDownloadError(f"Не удалось разрешить хост: {hostname}")

    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise MediaDownloadError("Ссылки на внутренние адреса запрещены")


def _duration_filter(max_duration_sec: int):
    def match_filter(info, *, incomplete):  # noqa: ARG001
        if not max_duration_sec:
            return None
        duration = info.get("duration")
        if duration is not None and float(duration) > max_duration_sec:
            minutes = max_duration_sec // 60
            return f"Ролик длиннее {minutes} мин — слишком большой для дубляжа"
        return None

    return match_filter


def _find_downloaded_file(dest_dir: Path) -> Path | None:
    candidates = []
    for path in dest_dir.iterdir():
        if not path.is_file():
            continue
        ext = path.suffix.lower().lstrip(".")
        if ext in VIDEO_EXTENSIONS:
            candidates.append(path)
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def download_media_url(
    url: str,
    dest_dir: Path | str,
    *,
    max_mb: int,
    timeout_sec: int = 600,
    max_duration_sec: int = 3600,
) -> tuple[Path, str]:
    """
    Download media with yt-dlp into dest_dir.

    Returns (file_path, display_name).
    Raises MediaDownloadError on failure.
    """
    err = validate_media_url(url)
    if err:
        raise MediaDownloadError(err)

    try:
        import yt_dlp
    except ImportError as exc:
        raise MediaDownloadError(
            "yt-dlp не установлен на сервере. Установите: pip install yt-dlp"
        ) from exc

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Clear previous video.* leftovers in this session dir
    for old in dest_dir.glob("video.*"):
        try:
            old.unlink(missing_ok=True)
        except OSError:
            pass

    max_bytes = max(1, int(max_mb)) * 1024 * 1024
    outtmpl = str(dest_dir / "video.%(ext)s")

    ydl_opts = {
        "outtmpl": outtmpl,
        "format": (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best[ext=m4a]/"
            "best[ext=webm]/best[ext=mp3]/best/best"
        ),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": min(60, max(10, timeout_sec // 10)),
        "retries": 2,
        "fragment_retries": 2,
        "max_filesize": max_bytes,
        "restrictfilenames": True,
        "overwrites": True,
        "match_filter": _duration_filter(max_duration_sec) if max_duration_sec else None,
    }

    display_name = "video.mp4"
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Soft deadline: yt-dlp has no global timeout; rely on socket_timeout + max_filesize
            info = ydl.extract_info(url, download=True)
            if isinstance(info, dict):
                title = (info.get("title") or "").strip()
                ext = (info.get("ext") or "mp4").strip().lstrip(".")
                if title:
                    safe = _SAFE_NAME_RE.sub("_", title)[:80].strip("._") or "video"
                    display_name = f"{safe}.{ext}"
                elif ext:
                    display_name = f"video.{ext}"
    except MediaDownloadError:
        raise
    except Exception as exc:
        msg = str(exc).strip() or exc.__class__.__name__
        if "File is larger than max-filesize" in msg or "max_filesize" in msg.lower():
            raise MediaDownloadError(f"Файл слишком большой (макс. {max_mb} МБ)") from exc
        if "Unsupported URL" in msg:
            raise MediaDownloadError("Эта ссылка не поддерживается") from exc
        logger.warning("yt-dlp failed for %s: %s", url[:120], msg)
        raise MediaDownloadError(f"Не удалось скачать медиа: {msg[:300]}") from exc

    path = _find_downloaded_file(dest_dir)
    if not path or not path.exists():
        raise MediaDownloadError("Скачивание завершилось, но файл не найден")

    size = path.stat().st_size
    if size <= 0:
        path.unlink(missing_ok=True)
        raise MediaDownloadError("Скачанный файл пустой")
    if size > max_bytes:
        path.unlink(missing_ok=True)
        raise MediaDownloadError(f"Файл слишком большой (макс. {max_mb} МБ)")

    ext = path.suffix.lower().lstrip(".")
    if ext not in VIDEO_EXTENSIONS:
        path.unlink(missing_ok=True)
        raise MediaDownloadError(f"Неподдерживаемый формат после скачивания: .{ext}")

    return path, display_name
