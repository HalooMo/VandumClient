# Dpunk — Web Client for AI Dubbing

Клиентское веб-приложение для сервиса AI-дубляжа SpeechLab (https://app.vandum.ru).

## Возможности

- Футуристичный современный UI
- Регистрация / вход по email с подтверждением почты
- Авторизация через Google OAuth
- Создание проектов дубляжа (загрузка видео, настройка голоса)
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
  services/   — SpeechLab API client, email, analytics
templates/    — Jinja2 шаблоны
static/       — CSS, JS
```

## API интеграция

Приложение проксирует запросы к inference API от имени сервера.
Пользователи не видят системный API-ключ — он хранится в переменных окружения.

Эндпоинты:
- `POST /api/v1/dub` — создать задачу
- `GET /api/v1/jobs/<id>` — статус
- `GET /api/v1/jobs/<id>/download` — скачать результат
