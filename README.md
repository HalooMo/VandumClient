# Dpunk — быстрый AI-дубляж

Веб-клиент для закадрового дубляжа: загрузили файл — получили MP4. Акцент на скорости и простоте.

## Возможности

- Футуристичный современный UI
- Регистрация / вход по email с подтверждением почты
- Авторизация через Google OAuth
- Создание проектов дубляжа (файл или ссылка YouTube/др. через yt-dlp, настройка голоса)
- Отслеживание статуса задач в реальном времени
- Скачивание готового MP4
- Админ-панель управления пользователями
- Дэшборд аналитики (графики по дням / месяцам / годам)

## Быстрый старт (локально)

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env        # заполните переменные
python run.py
```

Откройте http://localhost:5000

## Деплой через Docker

```bash
cp .env.example .env
# Заполните .env (SECRET_KEY, SPEECHLAB_API_KEY, MAIL_*, GOOGLE_*)
docker compose up -d --build
```

Приложение будет доступно на порту **8000**.

## Переменные окружения

| Переменная | Описание |
|---|---|
| `SECRET_KEY` | Секрет Flask (обязательно сменить) |
| `DATABASE_URL` | PostgreSQL URI (в Docker: `postgresql://dpunk:dpunk@db:5432/dpunk`) |
| `SPEECHLAB_BASE_URL` | URL API сервера (по умолчанию `https://app.vandum.ru`) |
| `SPEECHLAB_API_KEY` | API-ключ inference-сервера |
| `MAIL_*` | SMTP для отправки писем подтверждения |
| `GOOGLE_CLIENT_ID/SECRET` | Google OAuth credentials |
| `APP_URL` | Публичный URL приложения (для OAuth и email ссылок) |
| `ADMIN_EMAIL/PASSWORD` | Первый администратор (создаётся автоматически) |
| `YTDLP_ENABLED` | Разрешить загрузку медиа по URL (`true`/`false`) |
| `YTDLP_TIMEOUT_SEC` | Таймаут сокетов/ожидания скачивания (сек) |
| `YTDLP_MAX_DURATION_SEC` | Макс. длина ролика в секундах (0 = без лимита) |
| `SPEECHLAB_MAX_UPLOAD_MB` | Лимит размера файла после скачивания / upload |
| `GPU_POWER_ENABLED` | Авто-unshelve GPU перед dub (`true`/`false`) |
| `GPU_SERVER_ID` | UUID облачного сервера SpeechLab в Selectel |
| `OS_*` | Креды OpenStack (сервисный пользователь Selectel) |

### URL через yt-dlp

На шаге 1 визарда можно выбрать **Ссылка** вместо файла. Dpunk скачивает медиа через `yt-dlp`, затем отправляет файл в SpeechLab как обычно.

На сервере нужно:

```bash
pip install -r requirements.txt
# для склейки video+audio с YouTube:
sudo apt install -y ffmpeg
```

API: поле `video_url` в multipart или JSON (`POST /api/v1/dub`) вместо `video` / `video_path`.

## Деплой

См. подробный чеклист: [DEPLOY.md](DEPLOY.md).

Кратко на VPS: `git pull` → `pip install -r requirements.txt` → `ffmpeg` для yt-dlp → сильный `.env` → `systemctl restart vandumclient`.

## Google OAuth

1. Создайте проект в [Google Cloud Console](https://console.cloud.google.com/)
2. Credentials → OAuth 2.0 Client ID → Web application
3. Authorized redirect URI: `https://app.vandum.ru/auth/google/callback`
4. Скопируйте Client ID и Secret в `.env`

## Структура

```
app/
  auth/       — авторизация, Google OAuth, email verify
  main/       — главная, о сервисе
  projects/   — создание и управление проектами
  admin/      — админ-панель
  dashboard/  — аналитика
  services/   — SpeechLab API client, GPU power, email, analytics
scripts/      — CLI: gpu_power.py (status / unshelve / shelve)
templates/    — Jinja2 шаблоны
static/       — CSS, JS
```

## GPU power (Selectel)

Если inference-сервер в Selectel замораживается (`shelve`), включите `GPU_POWER_ENABLED=true` и заполните `GPU_SERVER_ID` + `OS_*`. Перед отправкой задачи в SpeechLab клиент сделает unshelve и дождётся `/health`. После завершения всех задач и простоя `GPU_IDLE_SEC` (по умолчанию 60 с) сервер автоматически замораживается.

Вручную:

```bash
python scripts/gpu_power.py status
python scripts/gpu_power.py unshelve   # разморозить + ждать /health
python scripts/gpu_power.py shelve     # заморозить (экономия GPU)
```

## API интеграция

Приложение проксирует запросы к inference API от имени сервера.
Пользователи не видят системный API-ключ — он хранится в переменных окружения.

Эндпоинты:
- `POST /api/v1/dub` — создать задачу
- `GET /api/v1/jobs/<id>` — статус
- `GET /api/v1/jobs/<id>/download` — скачать результат
