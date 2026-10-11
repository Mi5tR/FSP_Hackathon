# Развёртывание на сервере

Нужен Linux-сервер с Docker и Docker Compose. Хватит 2 ГБ памяти.

## Первый запуск

```bash
git clone <репозиторий> fsp-hackathon
cd fsp-hackathon
export JWT_SECRET="$(openssl rand -hex 32)"
docker compose up -d --build
```

После запуска:

| Адрес | Что там |
|---|---|
| `http://<сервер>:8080` | приложение |
| `http://<сервер>:8000/docs` | Swagger |
| `http://<сервер>:8025` | Mailpit: перехваченные письма подтверждения email |

Демо-данные загружаются автоматически при старте бэкенда, если их ещё нет: 500 кандидатов, 10 компаний (одна из них
приостановлена по жалобам — для демонстрации антифрода), 16 вакансий, задания и приглашения в разных статусах.
Пароль у демо-аккаунтов: `demo12345`.

## Переменные окружения бэкенда

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `JWT_SECRET` | `change-me-in-prod` | секрет подписи токенов, **обязательно поменять** |
| `DEV_MODE` | `1` | `1` — токен подтверждения email возвращается в ответе регистрации (удобно для демо) |
| `DATABASE_URL` | Postgres из compose | строка подключения SQLAlchemy |
| `SMTP_HOST`, `SMTP_PORT` | `mail`, `1025` | почтовый сервер (в compose — Mailpit) |
| `FRONTEND_URL` | `http://localhost:8080` | адрес фронтенда для ссылки в письме; поменять на публичный |
| `CORS_ORIGINS` | localhost | разрешённые источники через запятую; добавить публичный адрес |
| `FSP_API_URL`, `FSP_API_TOKEN` | не заданы | реальный API реестра ФСП; без них работает mock |
| `GRADE_CHANGE_COOLDOWN_DAYS` | `90` | как часто можно менять подтверждённый грейд |
| `INVITATION_TTL_DAYS` | `14` | срок жизни приглашения |
| `FRONTEND_PORT` | `8080` | внешний порт фронтенда в compose (если 8080 занят — например, `FRONTEND_PORT=8090`) |

Для публичного адреса задайте `FRONTEND_URL` и `CORS_ORIGINS` в `docker-compose.yml` или в файле `.env` рядом с ним.

## Обновление

```bash
git pull
docker compose up -d --build
```

Миграций пока нет: схема создаётся при старте. Если модели данных менялись, пересоздайте базу. Это удалит все данные,
демо-данные загрузятся заново.

```bash
docker compose down -v
docker compose up -d --build
```

## Проверка

```bash
curl http://localhost:8000/api/health        # {"status":"ok"}
docker compose logs -f backend
```
