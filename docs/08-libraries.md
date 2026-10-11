# Библиотеки и версии

Версии бэкенда закреплены в `backend/requirements.txt`, фронтенда — в `frontend/package-lock.json`
(сборка в Docker идёт через `npm ci`, то есть ровно по lock-файлу).

## Среда

| Компонент | Версия | Где задана |
|---|---|---|
| Python | 3.13 (образ `python:3.13-slim`) | `backend/Dockerfile` |
| Node.js | 24 (образ `node:24-alpine`) | `frontend/Dockerfile` |
| PostgreSQL | 16 (образ `postgres:16-alpine`) | `docker-compose.yml` |
| nginx | 1.27 (образ `nginx:1.27-alpine`) | `frontend/Dockerfile` |
| Mailpit | 1.21 (образ `axllent/mailpit:v1.21`) | `docker-compose.yml` |

## Бэкенд

| Пакет | Версия | Зачем |
|---|---|---|
| fastapi | 0.128.0 | HTTP API и OpenAPI |
| uvicorn[standard] | 0.40.0 | ASGI-сервер |
| SQLAlchemy | 2.0.48 | ORM |
| psycopg[binary] | 3.2.9 | драйвер PostgreSQL |
| pydantic | 2.12.5 | схемы и валидация |
| email-validator | 2.2.0 | проверка email |
| PyJWT | 2.10.1 | JWT, OIDC-код имитации, проверка id_token Keycloak по JWKS |
| bcrypt | 4.3.0 | хэши паролей |
| python-multipart | 0.0.20 | загрузка PDF-резюме |
| pypdf | 5.4.0 | извлечение текста из PDF |
| fpdf2 | 2.8.9 | генерация стандартизированного PDF-профиля |
| numpy | 2.4.1 | IRT/CAT, калибровка, валидация |
| httpx | 0.28.1 | клиенты реестра ФСП, Keycloak и Huntflow |
| scikit-learn | 1.7.2 | TF-IDF, логистическая регрессия: специализация по тексту, нечёткие навыки, подсказка грейда |
| pytest | 8.3.5 | тесты |

## Фронтенд

| Пакет | Версия (lock) | Зачем |
|---|---|---|
| react, react-dom | 19.3.0 | интерфейс |
| react-router-dom | 7.18.4 | маршрутизация, переходы через View Transitions API |
| typescript | 6.0.3 | типизация |
| vite | 8.3.2 | сборка и dev-сервер |
| @vitejs/plugin-react | 6.1.1 | JSX и fast refresh |
| oxlint | 1.86.0 | линтер |
| @types/react, @types/react-dom | 19.3.0 | типы |
| @types/node | 24.19.1 | типы конфигурации Vite |

Для PDF-профиля шрифт JetBrains Mono (SIL OFL 1.1) лежит в `backend/app/assets/fonts` вместе с лицензией.
В веб-интерфейсе шрифты подключаются из Google Fonts: **JetBrains Mono** — фирменный шрифт ФСП по брендбуку (SIL Open Font License 1.1),
**Inter** — основной текст. Иконки — inline SVG без внешних библиотек. Анимации и тёмная тема написаны на чистом
CSS (без UI-фреймворков) и учитывают `prefers-reduced-motion`.

## Модели и внешние сервисы

| Модель | Библиотека | Обучение | Где используется |
|---|---|---|---|
| Классификатор специализации (TF-IDF char 3–5 + LogisticRegression) | scikit-learn 1.7.2 | при старте, на синтетическом корпусе резюме, < 1 с | подсказка в опросе, разбор PDF-резюме и описания вакансии |
| Нечёткое распознавание навыков (TF-IDF char 2–4, ближайший сосед) | scikit-learn 1.7.2 | словарь навыков и транслит-синонимов | разбор резюме и вакансии: «Постгрес» → PostgreSQL |
| Подсказка грейда (мультиклассовая LogisticRegression) | scikit-learn 1.7.2 | синтетическая популяция с известным уровнем | экран выбора грейда |
| Калибровка процента (изотоническая регрессия) | numpy | скрипт валидации, `calibration.json` | поле `probability` в подборке |

Внешние LLM в рабочем контуре не используются: персональные данные никуда не передаются, GPU не требуется.
Генерация заданий — параметрические шаблоны с программно вычисляемым ответом. Huntflow API v2 вызывается только
при подключённом токене работодателя; без токена работает демонстрационный клиент без сети.
