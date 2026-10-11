# API

Полная спецификация — OpenAPI 3: после запуска откройте Swagger `http://localhost:8000/docs` (в Docker также
`http://localhost:8080/docs`) или файл [openapi.json](openapi.json) в этом каталоге. Схемы запросов и ответов
описаны в `backend/app/api/schemas.py`.

**Общее.** Все пути начинаются с `/api`. Авторизация — заголовок `Authorization: Bearer <JWT>`. Ошибки
возвращаются как `{"detail": "текст"}`: 401 — нет или недействителен токен, 403 — email не подтверждён,
404 — объект не найден или не принадлежит пользователю, 409 — конфликт состояния, 422 — ошибка данных,
429 — сработал кулдаун или лимит приглашений.

## Аутентификация

| Метод | Путь | Назначение |
|---|---|---|
| POST | `/auth/register` | Регистрация по email. Согласие на обработку ПДн (152-ФЗ) обязательно |
| POST | `/auth/verify-email` | Подтверждение email по токену из письма |
| POST | `/auth/login` | Вход по email и паролю |
| GET | `/auth/me` | Текущий пользователь |
| POST | `/auth/demo` | Только `DEV_MODE`: новый чистый аккаунт соискателя или работодателя для проверки жюри |
| GET | `/auth/fsp-id/config` | Куда отправить пользователя для входа через ФСП ID (mock или Keycloak) |
| POST | `/auth/fsp-id/mock-authorize` | Экран входа имитированного ФСП ID → одноразовый `code` |
| POST | `/auth/fsp-id/callback` | Обмен `code` на профиль ФСП ID: вход, регистрация или привязка + импорт достижений |

## Публичные

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/catalog` | ИТ-направления, 8 специализаций, 6 грейдов, навыки, опросник самооценки |
| GET | `/stats` | Обезличенные итоговые цифры платформы для главной страницы |
| GET | `/catalog/item-bank` | Состав банка семейств заданий (без ответов) |
| GET | `/vacancies` | Опубликованные вакансии работодателей платформы (кроме приостановленных компаний) |
| POST | `/integrations/huntflow/webhook/{secret}` | Вебхук Huntflow о смене этапа: `{"invitation_id": 12, "stage": "Оффер"}` |
| GET | `/health` | Проверка живости |

## Кандидат (`/candidate`)

| Метод | Путь | Назначение |
|---|---|---|
| GET, PUT | `/profile` | Профиль. Дата рождения и согласие законного представителя для 15–17 лет |
| GET | `/profile/pdf` | Стандартизированный PDF-профиль (категория, навыки, ФСП, история тестов) |
| GET | `/grade-hint` | ML-подсказка грейда (распределение по ступеням) и вероятные специализации по тексту профиля. Только подсказка |
| PUT | `/privacy` | Приватность и согласие на публикацию; `show_unconfirmed` — показывать ли профиль до подтверждения грейда; `hide_below_expectation` — не принимать вилки ниже ожиданий |
| POST | `/resume/parse` | Распознавание полей из PDF-резюме, без сохранения; навыки по сходству написания и ML-специализация |
| POST | `/survey` | Опрос: ИТ-направление, специализация, заявленный грейд, ответы самооценки `answers.self` |
| GET, POST | `/assessments` | История попыток / старт теста на грейд (кулдауны → 429) |
| GET | `/assessments/{id}` | Текущее задание и сводка |
| POST | `/assessments/{id}/answer` | Ответ + сигналы честности (`focus_lost`, `copy_attempts`) |
| GET, POST | `/skill-checks` | Навыки из резюме и короткая проверка навыка (грейд не меняет) |
| POST, DELETE | `/fsp/link` | Прямая привязка и отвязка ФСП ID (основной путь — OIDC-callback) |
| GET | `/invitations`, `/invitations/{id}` | Приглашения со снимком соответствия, доверием к работодателю (`company_trust`), флагами вилки |
| POST | `/invitations/{id}/complaint` | Жалоба на приглашение; 3 жалобы за 30 дней приостанавливают компанию |
| POST | `/invitations/{id}/accept`, `/decline` | Ответ на приглашение |
| POST | `/invitations/{id}/revoke-contacts`, `/restore-contacts` | Отзыв и возврат доступа к контактам |
| GET, POST | `/invitations/{id}/messages` | Переписка по приглашению |
| POST | `/vacancies/{id}/apply`, GET `/applications` | Отклик на вакансию (вспомогательный путь) |
| GET | `/micro-tasks` | Задания работодателей для своей категории (и соседних ступеней); `recommended` — адресное задание для кандидата |
| GET | `/badges` | Счётчики для меню: новые приглашения и сообщения, новые задания |
| POST | `/micro-tasks/{id}/answer` | Ответ. Для задания с эталоном сразу возвращается `result: correct / wrong` |

## Работодатель (`/employer`)

| Метод | Путь | Назначение |
|---|---|---|
| GET, PUT | `/company` | Профиль компании; `inn_valid` — добровольная метка доверия (контрольная сумма ИНН) |
| GET | `/trust` | Доверие к компании так, как его видит кандидат, и суточный лимит приглашений |
| GET, PUT, DELETE | `/ats` | Подключение Huntflow (без токена — демо-режим), URL вебхука, журнал синхронизации |
| POST | `/ats/import-vacancies` | Импорт вакансий из ATS черновиками потребностей |
| GET | `/badges` | Счётчики для меню: непрочитанные сообщения, новые кандидаты, новые отклики |
| POST | `/needs/parse` | Разбор свободного описания потребности |
| GET, POST, PUT | `/needs`, `/needs/{id}` | Потребности (с флагом `is_published` — открытая вакансия); `new_candidates` — новые в категории |
| POST | `/needs/{id}/seen` | Подборка просмотрена: следующие новые кандидаты будут отмечены |
| GET | `/scoring/defaults`, PUT `/needs/{id}/scoring` | Настройки модели релевантности |
| GET | `/needs/{id}/matches` | Объяснимая подборка: категории, блоки, требования, флаги, отсеянные фильтрами |
| GET | `/candidates`, `/candidates/{id}` | Поиск по банку и карточка кандидата |
| GET | `/candidates/{id}/pdf` | PDF-профиль кандидата: обезличенный, пока контакты не раскрыты |
| GET | `/needs/{id}/test-blueprint` | Как тестируются кандидаты под эту потребность |
| GET, POST, DELETE | `/needs/{id}/shortlist[/{cid}]` | Шорт-лист |
| GET, POST | `/invitations` | Адресные приглашения: суточный лимит по доверию, несколько позиций одному кандидату без дублей |
| POST | `/invitations/{id}/withdraw` | Отзыв приглашения |
| POST | `/invitations/{id}/offer`, `/hired` | Оффер после принятия и выход на работу |
| GET, POST | `/invitations/{id}/messages` | Переписка |
| GET, PATCH | `/needs/{id}/applications`, `/applications/{id}` | Отклики |
| GET, POST | `/micro-tasks` | Регулярные задания: `answer_type = open / exact`, `reference_answer` для автопроверки |
| GET | `/micro-tasks/{id}/submissions` | Ответы (`auto_checked` — проверено системой) |
| POST | `/micro-tasks/submissions/{id}/rate` | Оценка открытого ответа 1–5 |

## Пример: сквозной сценарий

```bash
# кандидат без регистрации (DEV_MODE)
TOKEN=$(curl -s -X POST localhost:8000/api/auth/demo -H 'content-type: application/json' \
  -d '{"role":"candidate"}' | jq -r .access_token)
curl -s -X POST localhost:8000/api/candidate/survey -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"industry":"development","specialization":"backend","claimed_grade":"middle"}'
curl -s -X POST localhost:8000/api/candidate/assessments -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d '{}'
```
