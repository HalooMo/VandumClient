# Полный гайд: деплой Dpunk с нуля на VPS

Цель: сайт **https://dpunk.online** на чистом Ubuntu-сервере  
(без Docker): **Python + Gunicorn + PostgreSQL + Nginx + systemd + Let's Encrypt**.

Типичные пути/имена (как у вас раньше):

| Что | Значение |
|-----|----------|
| Сервер | `161.104.16.64` (ваш IP) |
| Домен | `dpunk.online` + `www.dpunk.online` |
| Код | `/opt/vandumclient` |
| Linux-пользователь | `vandum` |
| systemd | `vandumclient.service` |
| Gunicorn | `127.0.0.1:8001` |
| Postgres | user/db `dpunk` |
| Репозиторий | `https://github.com/HalooMo/VandumClient.git` |

---

## 0. С вашего ПК (Windows) — код на GitHub

Перед установкой на сервер убедитесь, что свежий код запушен:

```powershell
cd C:\Users\salim\Projects\VandumClient
git status
git push origin main
```

Если push ещё не делали после правок безопасности — сделайте сейчас.

Подключение к серверу:

```powershell
ssh root@161.104.16.64
```

(или ваш логин, если не root)

---

## 1. DNS (панель домена)

Только **A**-записи на IP сервера:

```
dpunk.online      A    161.104.16.64
www.dpunk.online  A    161.104.16.64
```

**Удалите AAAA (IPv6)**, если IPv6 на VPS не настроен — иначе Let's Encrypt часто даёт 404.

Проверка с сервера через 5–15 минут:

```bash
dig +short dpunk.online A
dig +short www.dpunk.online A
dig +short dpunk.online AAAA   # должно быть пусто
curl -4 ifconfig.me            # должен совпасть с A-записью
```

---

## 2. Базовые пакеты

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip python3-dev \
  postgresql postgresql-contrib libpq-dev \
  nginx certbot python3-certbot-nginx \
  git ffmpeg curl
```

`ffmpeg` нужен для yt-dlp (YouTube video+audio).

Проверка Python:

```bash
python3 --version   # нужен 3.10+
```

---

## 3. Пользователь и каталог

```bash
sudo adduser --disabled-password --gecos "" vandum
sudo mkdir -p /opt/vandumclient
sudo chown vandum:vandum /opt/vandumclient
```

Если пользователь уже есть — шаг с `adduser` можно пропустить.

---

## 4. PostgreSQL

```bash
sudo -u postgres psql
```

В консоли `psql` (пароль придумайте свой и сохраните):

```sql
CREATE USER dpunk WITH PASSWORD 'СИЛЬНЫЙ_ПАРОЛЬ_БД';
CREATE DATABASE dpunk OWNER dpunk;
GRANT ALL PRIVILEGES ON DATABASE dpunk TO dpunk;
\q
```

Для Postgres 15+ иногда нужно ещё:

```bash
sudo -u postgres psql -d dpunk -c "GRANT ALL ON SCHEMA public TO dpunk;"
```

Проверка:

```bash
psql "postgresql://dpunk:СИЛЬНЫЙ_ПАРОЛЬ_БД@localhost:5432/dpunk" -c '\conninfo'
```

---

## 5. Код из GitHub

```bash
sudo -u vandum git clone https://github.com/HalooMo/VandumClient.git /opt/vandumclient
cd /opt/vandumclient

sudo -u vandum python3 -m venv .venv
sudo -u vandum .venv/bin/pip install --upgrade pip
sudo -u vandum .venv/bin/pip install -r requirements.txt
```

Если каталог уже не пустой:

```bash
cd /opt/vandumclient
sudo -u vandum git remote -v
sudo -u vandum git fetch origin
sudo -u vandum git reset --hard origin/main
sudo -u vandum .venv/bin/pip install -r requirements.txt
```

---

## 6. Файл `.env` (критично)

```bash
sudo -u vandum cp /opt/vandumclient/.env.example /opt/vandumclient/.env
sudo -u vandum nano /opt/vandumclient/.env
```

Минимальный рабочий пример (подставьте свои секреты):

```env
SECRET_KEY=сгенерируйте_длинную_случайную_строку_32+_символов
FLASK_ENV=production

DATABASE_URL=postgresql://dpunk:СИЛЬНЫЙ_ПАРОЛЬ_БД@localhost:5432/dpunk

# ВАЖНО: это URL inference SpeechLab, НЕ https://dpunk.online
SPEECHLAB_BASE_URL=https://app.vandum.ru
SPEECHLAB_API_KEY=ваш_ключ_speechlab
SPEECHLAB_MAX_UPLOAD_MB=150

YTDLP_ENABLED=true
YTDLP_TIMEOUT_SEC=600
YTDLP_MAX_DURATION_SEC=3600

APP_URL=https://dpunk.online

ADMIN_EMAIL=admin@dpunk.online
ADMIN_PASSWORD=сильный_пароль_админа
ADMIN_RESET_PASSWORD=true

MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=ваш@gmail.com
MAIL_PASSWORD=app-password-gmail
MAIL_DEFAULT_SENDER=Dpunk <noreply@dpunk.online>

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

MAX_DUB_JOBS_PER_DAY=20
```

Сгенерировать `SECRET_KEY`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Права:

```bash
sudo chmod 600 /opt/vandumclient/.env
sudo chown vandum:vandum /opt/vandumclient/.env
```

### Важные правила `.env`

1. **`SPEECHLAB_BASE_URL` не должен быть `https://dpunk.online`** — иначе сайт будет стучаться сам в себя и зависать.
2. При `FLASK_ENV=production` слабые `SECRET_KEY` / `ADMIN_PASSWORD` (типа `admin123`) — **приложение не стартует**.
3. После первого успешного входа админа поставьте `ADMIN_RESET_PASSWORD=false`.
4. Google OAuth: в консоли Google добавьте  
   `https://dpunk.online/auth/google/callback`

Проверка импорта приложения от пользователя `vandum`:

```bash
cd /opt/vandumclient
sudo -u vandum bash -c 'set -a; source .env; set +a; .venv/bin/python -c "from app import create_app; create_app(); print(\"OK\")"'
```

Если видите ошибку про SECRET_KEY / ADMIN_PASSWORD — поправьте `.env`.

---

## 7. systemd

```bash
sudo nano /etc/systemd/system/vandumclient.service
```

Содержимое:

```ini
[Unit]
Description=Dpunk Web Client
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=vandum
Group=vandum
WorkingDirectory=/opt/vandumclient
EnvironmentFile=/opt/vandumclient/.env
ExecStart=/opt/vandumclient/.venv/bin/gunicorn \
  --bind 127.0.0.1:8001 \
  --workers 2 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile - \
  "app:create_app()"
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Запуск:

```bash
sudo systemctl daemon-reload
sudo systemctl enable vandumclient
sudo systemctl restart vandumclient
sudo systemctl status vandumclient --no-pager
```

Логи при ошибке:

```bash
sudo journalctl -u vandumclient -n 80 --no-pager
```

Проверка локально на сервере:

```bash
curl -s http://127.0.0.1:8001/health
```

Ожидается JSON со `"status"`.

---

## 8. Nginx (HTTP → потом HTTPS)

```bash
sudo nano /etc/nginx/sites-available/dpunk
```

Сначала **только HTTP** (для certbot):

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name dpunk.online www.dpunk.online;

    client_max_body_size 160m;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
```

```bash
sudo mkdir -p /var/www/certbot
sudo ln -sf /etc/nginx/sites-available/dpunk /etc/nginx/sites-enabled/dpunk
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

Проверка с вашего ПК или сервера:

```bash
curl -I http://dpunk.online/
```

---

## 9. HTTPS (Let's Encrypt)

```bash
sudo certbot --nginx -d dpunk.online -d www.dpunk.online
```

Если 404 на challenge:

1. Проверьте DNS A / отсутствие AAAA (раздел 1).
2. Убедитесь, что `location /.well-known/` есть и nginx перезагружен.
3. Попробуйте webroot:

```bash
sudo certbot certonly --webroot -w /var/www/certbot -d dpunk.online -d www.dpunk.online
```

После успешного сертификата nginx обычно сам допишет SSL.  
Итоговый HTTPS-прокси должен по-прежнему слать на `127.0.0.1:8001` с `X-Forwarded-Proto`.

Пример финального куска (certbot часто делает сам):

```nginx
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name dpunk.online www.dpunk.online;

    # ssl_certificate ... (пропишет certbot)

    client_max_body_size 160m;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}

server {
    listen 80;
    server_name dpunk.online www.dpunk.online;
    return 301 https://$host$request_uri;
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
curl -s https://dpunk.online/health
```

---

## 10. Файрвол (если ufw включён)

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status
```

---

## 11. Первый вход и проверки

1. Откройте https://dpunk.online  
2. Войдите админом из `.env` (`ADMIN_EMAIL` / `ADMIN_PASSWORD`)  
3. Создайте тестовый проект (файл или ссылка YouTube)  
4. API (если ключ уже есть):

```bash
curl -s -H "X-API-Key: dpk_ВАШ_КЛЮЧ" https://dpunk.online/api/v1/cast-voices
```

После успешного деплоя в `.env`:

```env
ADMIN_RESET_PASSWORD=false
```

и:

```bash
sudo systemctl restart vandumclient
```

---

## 12. Обновление кода в будущем

С ПК:

```powershell
git push origin main
```

На сервере:

```bash
sudo -u vandum git -C /opt/vandumclient pull
sudo -u vandum /opt/vandumclient/.venv/bin/pip install -r /opt/vandumclient/requirements.txt
sudo systemctl restart vandumclient
sudo systemctl status vandumclient --no-pager
```

---

## Частые поломки

| Симптом | Что проверить |
|---------|----------------|
| `Failed to load environment files` | Есть ли `/opt/vandumclient/.env`, путь в `EnvironmentFile=` |
| Сервис падает сразу | `journalctl -u vandumclient -n 80` — часто слабый SECRET_KEY/ADMIN_PASSWORD |
| 502 Bad Gateway | `systemctl status vandumclient`, `curl 127.0.0.1:8001/health` |
| Дубляж 401 | `SPEECHLAB_API_KEY` и что `SPEECHLAB_BASE_URL` — не сам сайт |
| Сайт «висит» на /health | `SPEECHLAB_BASE_URL` случайно = `https://dpunk.online` |
| Certbot 404 | AAAA в DNS, nginx `acme-challenge`, IP A-записи |
| Upload слишком большой | `client_max_body_size` в nginx + `SPEECHLAB_MAX_UPLOAD_MB` |
| YouTube не качается | `ffmpeg` установлен, `YTDLP_ENABLED=true` |

---

## Быстрый чеклист «с нуля»

1. [ ] DNS A → IP сервера, без AAAA  
2. [ ] `apt` пакеты + ffmpeg  
3. [ ] user `vandum`, каталог `/opt/vandumclient`  
4. [ ] Postgres user/db `dpunk`  
5. [ ] `git clone` + venv + `pip install -r requirements.txt`  
6. [ ] `.env` с сильными секретами и правильным SpeechLab URL  
7. [ ] systemd `vandumclient` → порт 8001  
8. [ ] nginx → proxy на 8001, `client_max_body_size 160m`  
9. [ ] certbot HTTPS  
10. [ ] логин админом, тест дубляжа  

Готово: сервис снова на **https://dpunk.online**.
