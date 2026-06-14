STATUS_LABELS = {
    "uploading": "Выполняется",
    "pending": "Выполняется",
    "queued": "Выполняется",
    "running": "Выполняется",
    "done": "Готово",
    "error": "Ошибка",
}

DETAIL_STATUS_LABELS = {
    "uploading": "Загрузка файла",
    "pending": "Ожидание",
    "queued": "В очереди",
    "running": "Выполняется",
    "done": "Готово",
    "error": "Ошибка",
}

ACTIVE_STATUSES = {"uploading", "pending", "queued", "running"}


def status_label(status, detail=False):
    labels = DETAIL_STATUS_LABELS if detail else STATUS_LABELS
    return labels.get(status, status)


def is_active(status):
    return status in ACTIVE_STATUSES
