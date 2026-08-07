# Деплой Dpunk (VandumClient) на VPS

Краткий чеклист для production без Docker (REG / любой Linux VPS).

## 1. Перед выкладкой

- [ ] В `.env` заданы **сильные** `SECRET_KEY` (≥24 символов) и `ADMIN_PASSWORD` (не `admin123`)
- [ ] `FLASK_ENV=production`
- [ ] `APP_URL=https://ваш-домен` (https)
- [ ] `DATABASE_URL=postgresql://...` (локальный Postgres)
- [ ] `SPEECHLAB_BASE_URL` = реальный inference-сервер (**не** URL этого же сайта)
- [ ] `SPEECHLAB_API_KEY` заполнен
- [ ] `SPEECHLAB_MAX_UPLOAD_MB=150` (или нужный лимит)
- [ ] SMTP / Google OAuth по необходимости
- [ ] `.env` **не** коммитится в git

## 2. Установка на сервере

```bash
sudo mkdir -p /opt/vandumclient
sudo git clone https://github.com/HalooMo/VandumClient.git /opt/vandumclient
# или: git pull в существующем каталоге

cd /opt/vandumclient
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# YouTube / URL-загрузка:
sudo apt-get update && sudo apt-get install -y ffmpeg
# yt-dlp уже в requirements.txt

cp .env.example .env
nano .env   # заполнить секреты
```

При `FLASK_ENV=production` приложение **не стартует** со слабыми `SECRET_KEY` / `ADMIN_PASSWORD`.

## 3. systemd (пример)

```ini
[Unit]
Description=Dpunk web
After=network.target postgresql.service

[Service]
User=vandum
Group=vandum
WorkingDirectory=/opt/vandumclient
EnvironmentFile=/opt/vandumclient/.env
ExecStart=/opt/vandumclient/.venv/bin/gunicorn -b 127.0.0.1:8001 -w 2 --timeout 120 "app:create_app()"
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vandumclient
sudo systemctl restart vandumclient
```

`timeout` gunicorn ≥ 120 — API `video_url` может качать до ~3 мин.

## 4. nginx

Проксируйте на `127.0.0.1:8001`, `client_max_body_size` ≥ лимита upload (например `160m`), HTTPS (Let's Encrypt).

## 5. После обновления кода

```bash
sudo -u vandum git -C /opt/vandumclient pull
sudo -u vandum /opt/vandumclient/.venv/bin/pip install -r /opt/vandumclient/requirements.txt
sudo systemctl restart vandumclient
```

Схема БД: `create_all` + лёгкие `ALTER` при старте (в т.ч. `dub_usage`, `key_hash` VARCHAR(255)).

## 6. Проверка

```bash
curl -s https://ваш-домен/health
curl -s -H "X-API-Key: dpk_..." https://ваш-домен/api/v1/cast-voices
```

Логин админом, создать тестовый проект (файл и/или URL).

## 7. Безопасность (уже в коде)

- Квоты считаются на **каждый** запуск (в т.ч. restart) через таблицу `dub_usage`
- yt-dlp: блок private/CGNAT IP; API — макс. 2 параллельных URL-скачивания
- Production не принимает placeholder-секреты
- Код верификации email на экране только при `DEV_SHOW_VERIFY_CODE=true`
- Logout / resend verification — POST + CSRF

## 8. GitHub

```bash
git status
git add -A
git commit -m "..."
git push origin main
```

Не пушьте `.env`, ключи, дампы БД, содержимое `uploads/`.
