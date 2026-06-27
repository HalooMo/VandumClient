import json
import re
from pathlib import Path

VIDEO_EXTENSIONS = {"mp4", "mkv", "mov", "avi", "webm", "wav", "mp3", "m4a"}
SAMPLE_EXTENSIONS = {"mp3", "wav"}
AGE_GROUPS = ("child", "teenager", "mature", "elderly")

MULTIPART_FILE_FIELDS = ("video", "voice_sample_male", "voice_sample_female")

TEXT_FIELDS = (
    "project_name",
    "source_language",
    "target_language",
    "voice_prompt",
    "voice_design_template",
    "voice_design_prompt",
    "voice_gender",
    "gender",
    "voice_age",
    "voice_design_temperature",
    "voice_design_by_key",
    "dub_volume_percent",
    "original_audio_ratio",
    "voice_sample_male_ages",
    "voice_sample_female_ages",
    "voice_sample_male_ref_text",
    "voice_sample_female_ref_text",
    "voice_clone_samples",
    "silero_speaker",
    "silero_all_replicas",
    "silero_age_groups",
    "silero_voices",
)

SILERO_SPEAKERS = frozenset({"aidar", "baya", "eugene", "kseniya", "xenia"})
RU_TARGET_LANGUAGES = frozenset({"ru", "russian"})


def _clean_text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _truthy_form_value(value):
    return str(value).strip().lower() in ("1", "true", "yes", "on", "y")


def _normalize_ages(raw):
    if not raw:
        return None
    parts = [p.strip() for p in str(raw).replace(" ", "").split(",") if p.strip()]
    valid = [p for p in parts if p in AGE_GROUPS]
    return ",".join(valid) if valid else None


def _is_ru_target(target_language):
    if not target_language:
        return False
    return str(target_language).strip().lower() in RU_TARGET_LANGUAGES


def _strip_silero_if_not_ru(data):
    target = data.get("target_language")
    if _is_ru_target(target):
        return data
    for key in ("silero_speaker", "silero_all_replicas", "silero_age_groups", "silero_voices"):
        data.pop(key, None)
    return data


def build_dub_form_data(form=None, formdata=None):
    """Build SpeechLab multipart fields from WTForms + request form."""
    data = {}
    source = formdata or {}

    if form:
        mapping = {
            "project_name": form.project_name.data,
            "source_language": form.source_language.data,
            "target_language": form.target_language.data,
            "voice_gender": form.voice_gender.data,
            "voice_age": form.voice_age.data,
            "voice_prompt": form.voice_prompt.data,
            "dub_volume_percent": form.dub_volume_percent.data,
            "original_audio_ratio": form.original_audio_ratio.data,
            "voice_sample_male_ref_text": getattr(form, "voice_sample_male_ref_text", None)
            and form.voice_sample_male_ref_text.data,
            "voice_sample_female_ref_text": getattr(form, "voice_sample_female_ref_text", None)
            and form.voice_sample_female_ref_text.data,
            "silero_speaker": getattr(form, "silero_speaker", None) and form.silero_speaker.data,
        }
        for key, value in mapping.items():
            cleaned = _clean_text(value)
            if cleaned is not None:
                data[key] = cleaned
        if form.voice_age.data is not None:
            data["voice_age"] = str(form.voice_age.data)
        temp_field = getattr(form, "voice_design_temperature", None)
        if temp_field is not None and temp_field.data is not None:
            data["voice_design_temperature"] = str(temp_field.data)
        silero_all = getattr(form, "silero_all_replicas", None)
        if silero_all is not None and silero_all.data:
            data["silero_all_replicas"] = "true"

    for key in TEXT_FIELDS:
        if key in data:
            continue
        value = source.get(key)
        cleaned = _clean_text(value)
        if cleaned is not None:
            if key in ("voice_sample_male_ages", "voice_sample_female_ages"):
                cleaned = _normalize_ages(cleaned)
                if cleaned:
                    data[key] = cleaned
            elif key == "dub_volume_percent":
                data[key] = str(cleaned)
            elif key == "voice_age":
                data[key] = str(cleaned)
            elif key == "silero_all_replicas":
                if _truthy_form_value(cleaned):
                    data[key] = "true"
            elif key == "silero_speaker":
                if str(cleaned).lower() in SILERO_SPEAKERS:
                    data[key] = str(cleaned).lower()
            elif key == "silero_age_groups":
                cleaned = _normalize_ages(cleaned)
                if cleaned:
                    data[key] = cleaned
            else:
                data[key] = cleaned

    if data.get("voice_prompt") and not data.get("voice_design_template"):
        data["voice_design_template"] = data["voice_prompt"]

    return _strip_silero_if_not_ru(data)


def collect_multipart_files(request_files):
    """Collect video and voice sample files from Flask request.files."""
    files = {}
    for field in MULTIPART_FILE_FIELDS:
        uploaded = request_files.get(field)
        if uploaded and uploaded.filename:
            files[field] = (
                uploaded.filename,
                uploaded.stream,
                uploaded.content_type or "application/octet-stream",
            )
    return files or None


def collect_multipart_files_from_paths(file_paths):
    """Build requests-compatible files dict from saved paths on disk."""
    files = {}
    for field, path in file_paths.items():
        path = Path(path)
        if not path.exists():
            continue
        mime = "audio/wav" if path.suffix.lower() == ".wav" else "audio/mpeg"
        if field == "video":
            mime = "application/octet-stream"
        files[field] = (path.name, open(path, "rb"), mime)
    return files


def close_file_handles(files_dict):
    if not files_dict:
        return
    for entry in files_dict.values():
        if len(entry) >= 2 and hasattr(entry[1], "close"):
            try:
                entry[1].close()
            except Exception:
                pass


def sanitize_upstream_json(data):
    """Remove server-side paths from JSON payloads before proxying upstream."""
    if not isinstance(data, dict):
        return {}
    payload = dict(data)
    payload.pop("video_path", None)

    if not _is_ru_target(payload.get("target_language")):
        for key in ("silero_speaker", "silero_all_replicas", "silero_age_groups", "silero_voices"):
            payload.pop(key, None)

    clones = payload.get("voice_clone_samples")
    if isinstance(clones, list):
        safe_clones = []
        for item in clones:
            if not isinstance(item, dict):
                continue
            safe = {k: v for k, v in item.items() if k != "sample_path"}
            if safe.get("gender"):
                safe_clones.append(safe)
        payload["voice_clone_samples"] = safe_clones
    elif isinstance(clones, str):
        try:
            parsed = json.loads(clones)
            payload["voice_clone_samples"] = sanitize_upstream_json(
                {"voice_clone_samples": parsed}
            ).get("voice_clone_samples", [])
        except json.JSONDecodeError:
            payload.pop("voice_clone_samples", None)

    return payload


def _check_upload_size(uploaded, max_mb):
    if not uploaded:
        return None
    stream = uploaded.stream
    pos = stream.tell()
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(pos)
    if size > max_mb * 1024 * 1024:
        return f"Файл слишком большой (макс. {max_mb} МБ)"
    return None


def _magic_checkers():
    return {
        "mp3": lambda h: h[:3] == b"ID3" or (len(h) >= 2 and h[0] == 0xFF and (h[1] & 0xE0) == 0xE0),
        "wav": lambda h: len(h) >= 12 and h[:4] == b"RIFF" and h[8:12] == b"WAVE",
        "mp4": lambda h: len(h) >= 12 and h[4:8] == b"ftyp",
        "mov": lambda h: len(h) >= 12 and h[4:8] == b"ftyp",
        "m4a": lambda h: len(h) >= 12 and h[4:8] == b"ftyp",
        "webm": lambda h: len(h) >= 4 and h[:4] == b"\x1a\x45\xdf\xa3",
        "mkv": lambda h: len(h) >= 4 and h[:4] == b"\x1a\x45\xdf\xa3",
        "avi": lambda h: len(h) >= 12 and h[:4] == b"RIFF" and h[8:12] == b"AVI ",
    }


def _validate_file_magic(path, ext):
    checker = _magic_checkers().get(ext)
    if not checker:
        return None
    try:
        header = Path(path).read_bytes()[:32]
    except OSError:
        return "Не удалось прочитать загруженный файл"
    if not checker(header):
        return "Содержимое файла не соответствует расширению"
    return None


def validate_video_file(filename, max_mb, uploaded=None):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in VIDEO_EXTENSIONS:
        return f"Неподдерживаемый формат видео. Допустимо: {', '.join(sorted(VIDEO_EXTENSIONS))}"
    if uploaded:
        size_err = _check_upload_size(uploaded, max_mb)
        if size_err:
            return size_err
    return None


def validate_sample_file(filename, max_mb, uploaded=None):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in SAMPLE_EXTENSIONS:
        return "Сэмпл голоса: только MP3 или WAV"
    if uploaded:
        size_err = _check_upload_size(uploaded, max_mb)
        if size_err:
            return size_err
    return None


def save_upload_file(uploaded, dest_dir, basename, allowed_ext, max_mb):
    if not uploaded or not uploaded.filename:
        return None, None

    ext = uploaded.filename.rsplit(".", 1)[-1].lower() if "." in uploaded.filename else ""
    if ext not in allowed_ext:
        return None, f"Неподдерживаемый формат .{ext}"

    size_err = _check_upload_size(uploaded, max_mb)
    if size_err:
        return None, size_err

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", basename)
    dest = dest_dir / f"{safe}.{ext}"
    uploaded.save(dest)

    magic_err = _validate_file_magic(dest, ext)
    if magic_err:
        dest.unlink(missing_ok=True)
        return None, magic_err

    return dest, None


def build_voice_options_json(formdata, sample_meta):
    """Persist voice clone metadata for project detail page."""
    options = {}
    for key in (
        "voice_design_temperature",
        "voice_sample_male_ages",
        "voice_sample_female_ages",
        "voice_sample_male_ref_text",
        "voice_sample_female_ref_text",
        "silero_speaker",
        "silero_all_replicas",
        "silero_age_groups",
    ):
        val = _clean_text(formdata.get(key))
        if key.endswith("_ages"):
            val = _normalize_ages(val)
        if key == "silero_all_replicas":
            val = "true" if val and _truthy_form_value(val) else None
        if val:
            options[key] = val
    if sample_meta.get("male"):
        options["voice_sample_male"] = sample_meta["male"]
    if sample_meta.get("female"):
        options["voice_sample_female"] = sample_meta["female"]
    return json.dumps(options, ensure_ascii=False) if options else None


def parse_voice_options(raw):
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}
