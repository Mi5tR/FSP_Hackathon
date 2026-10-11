"""Демо-данные: работодатели, вакансии из текстовых описаний и база кандидатов,
прошедших симулированное адаптивное тестирование.

Запуск: python -m app.seed.demo   (идемпотентно: при наличии демо-аккаунтов ничего не делает)

Демо-аккаунты (пароль у всех demo12345):
  candidate@demo.ru  — кандидат без теста (пройти путь с нуля)
  cand3@demo.ru      — кандидат с категорией, достижениями ФСП и приглашениями
  employer@demo.ru   — работодатель «Цифровой Банк» с вакансиями, приглашениями и подключённой ATS
"""

from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy import select

from app.core.catalog import GRADE_CODES, SPECIALIZATIONS
from app.core.db import Base, SessionLocal, engine, ensure_columns
from app.core.security import hash_password
from app.integrations.ats import new_webhook_secret
from app.integrations.fsp import MockFspClient
from app.models.entities import (
    Assessment,
    AssessmentStatus,
    AtsConnection,
    AtsEvent,
    CandidateProfile,
    Company,
    Complaint,
    FspAchievement,
    HiringNeed,
    Invitation,
    InvitationStatus,
    Message,
    MicroTask,
    Role,
    SurveyAnswer,
    User,
    utcnow,
)
from app.services.matching.ranking import NeedQuery, score_candidate
from app.services.matching.text_parser import parse_need
from app.services.testing import cat
from app.services.testing.skill_profile import display_level, skill_estimates

PASSWORD = "demo12345"
RNG = random.Random(42)
N_CANDIDATES = 500

FIRST = ["Алексей", "Мария", "Иван", "Анна", "Дмитрий", "Екатерина", "Сергей", "Ольга", "Никита", "Дарья",
         "Артём", "Полина", "Михаил", "Софья", "Егор", "Алина", "Кирилл", "Виктория", "Тимур", "Ксения",
         "Роман", "Вероника", "Глеб", "Ульяна", "Максим", "Елизавета", "Арсений", "Маргарита"]
LAST = ["Иванов", "Смирнов", "Кузнецов", "Попов", "Васильев", "Петров", "Соколов", "Михайлов", "Новиков",
        "Фёдоров", "Морозов", "Волков", "Алексеев", "Лебедев", "Семёнов", "Егоров", "Павлов", "Козлов",
        "Орлов", "Зайцев", "Белов", "Голубев", "Виноградов", "Богданов"]
CITIES = ["Москва", "Санкт-Петербург", "Казань", "Новосибирск", "Екатеринбург", "Нижний Новгород", "Томск",
          "Самара", "Краснодар", "Иннополис"]
SALARY = {"intern": 60_000, "junior": 100_000, "junior_plus": 140_000, "middle": 210_000, "middle_plus": 280_000,
          "senior": 380_000}
SPEC_WEIGHTS = {"backend": 0.22, "frontend": 0.16, "mobile": 0.1, "data": 0.12, "analyst": 0.12, "qa": 0.1,
                "devops": 0.1, "security": 0.08}
ABOUT = {
    "backend": ["Пишу сервисы на Python и Go, люблю чистые API.", "Делал платёжные интеграции и очереди.",
                "Интересен highload и распределённые системы."],
    "frontend": ["Делаю быстрые интерфейсы на React.", "Собирал дизайн-систему для трёх продуктов.",
                 "Люблю доступность и аккуратную вёрстку."],
    "mobile": ["Пишу на Kotlin и Jetpack Compose.", "Выпустил два приложения в RuStore.", "iOS и Android, SwiftUI."],
    "data": ["Строю рекомендательные модели.", "Классический ML и A/B-тесты.", "Компьютерное зрение и PyTorch."],
    "analyst": ["Собираю требования и рисую BPMN.", "Продуктовая аналитика: воронки, когорты, A/B.",
                "SQL, дашборды в DataLens, метрики продукта."],
    "qa": ["Автоматизирую тесты на pytest.", "Тестирую API и мобильные приложения.", "Выстраивал регресс с нуля."],
    "devops": ["Kubernetes в проде, GitLab CI.", "Настраивал мониторинг и алертинг.", "Linux, сети, Terraform."],
    "security": ["Участвую в CTF, разбираю веб-уязвимости.", "Работал в SOC: SIEM и реагирование.",
                 "Анализ защищённости веб-приложений."],
}

COMPANIES = [
    {"email": "employer@demo.ru", "name": "Цифровой Банк", "industry": "Финтех", "inn": "7725123450",
     "website": "https://demo.ru", "ats": True,
     "description": "Разрабатываем мобильный банк и платёжную платформу для 5 млн клиентов."},
    {"email": "hr@retail.demo.ru", "name": "РитейлТех", "industry": "E-commerce", "inn": "1655123453",
     "website": "https://retail.demo.ru",
     "description": "Маркетплейс и логистика: рекомендательные системы, высоконагруженный бэкенд."},
    {"email": "hr@gov.demo.ru", "name": "ГосЦифра", "industry": "GovTech",
     "description": "Цифровые сервисы для жителей города."},
    {"email": "hr@mobilab.demo.ru", "name": "МобиЛаб", "industry": "Мобильная разработка", "inn": "7707083893",
     "website": "https://mobilab.demo.ru", "description": "Студия мобильных приложений для банков и ритейла."},
    {"email": "hr@datapulse.demo.ru", "name": "ДатаПульс", "industry": "Аналитика", "inn": "7736050003",
     "website": "https://datapulse.demo.ru", "description": "Продуктовая аналитика и BI для онлайн-сервисов."},
    {"email": "hr@cybershield.demo.ru", "name": "КиберЩит", "industry": "Информационная безопасность",
     "inn": "7702070139", "website": "https://cybershield.demo.ru",
     "description": "SOC и анализ защищённости для финансовых организаций."},
    {"email": "hr@cloudops.demo.ru", "name": "ОблакоОпс", "industry": "Облачная инфраструктура",
     "description": "Облачная платформа и managed Kubernetes."},
    {"email": "hr@uchikod.demo.ru", "name": "Учи.Код", "industry": "EdTech", "inn": "7710140679",
     "description": "Онлайн-школа программирования для школьников."},
    {"email": "hr@gruztech.demo.ru", "name": "ГрузТех", "industry": "Логистика",
     "description": "Сервисы для грузоперевозок и складов."},
    # Компания с поведением «сборщика резюме»: на неё пожаловались кандидаты, и система приостановила приглашения
    {"email": "start.career.hr@mail.demo.ru", "name": "Карьерный Старт Плюс", "industry": "Кадровое агентство",
     "description": "Подбор персонала. Обучение перед трудоустройством.", "shady": True},
]

# Вакансии задаются свободным текстом — система сама извлекает специализацию, грейд, стек и вилку
VACANCY_TEXTS = [
    (0, "Backend-разработчик (Middle)",
     "Ищем middle backend-разработчика на Python (FastAPI) в команду платежей. Уверенный PostgreSQL и REST API. "
     "Опыт с asyncio. Будет плюсом: Docker, Kafka, понимание микросервисной архитектуры. "
     "Гибридный формат. Зарплата от 230 000 до 320 000 руб."),
    (0, "Senior Backend / архитектор",
     "Senior бэкенд-разработчик в команду антифрода. Глубокое знание system design и highload, многопоточность, SQL. "
     "Желательно знание Go. Удалённо. Вилка 380 000 – 520 000."),
    (0, "Android-разработчик (Middle+)",
     "Middle+ Android-разработчик в мобильный банк: Kotlin, корутины, Jetpack Compose, REST API. "
     "Будет плюсом опыт публикации в RuStore. Гибрид. 280 000 – 360 000 руб."),
    (1, "Frontend-разработчик (Junior)",
     "Junior фронтенд-разработчик: JavaScript, вёрстка HTML/CSS, React. Будет плюсом TypeScript. "
     "Опыт до года. Оплата 90 000 – 140 000."),
    (1, "ML-инженер рекомендаций",
     "Middle Data Scientist / ML-инженер: машинное обучение, статистика, A/B-тесты, Python, SQL. "
     "Желательно PyTorch. Зарплата 250 000 – 340 000."),
    (1, "Frontend-разработчик (Middle+)",
     "Middle+ фронтенд: React, TypeScript, производительность рендеринга, Next.js. Удалённо. 270 000 – 340 000 руб."),
    (2, "DevOps-инженер",
     "DevOps middle: Linux, Docker, Kubernetes, сети. CI/CD на GitLab. Будет плюсом Nginx. 220 000 – 300 000 руб."),
    (2, "QA-инженер (Junior)",
     "Тестировщик junior: ручное и автотестирование, базовый SQL, REST API. Желательно pytest. "
     "100 000 – 140 000."),
    (3, "iOS / Android разработчик (Junior+)",
     "Мобильный разработчик junior+: Swift или Kotlin, жизненный цикл экранов, работа с REST API. "
     "Офис в Казани или гибрид. 130 000 – 170 000 руб."),
    (4, "Продуктовый аналитик (Middle)",
     "Продуктовый аналитик middle: SQL, продуктовые метрики, воронки и когорты, A/B-тесты. "
     "Будет плюсом BPMN и сбор требований. Удалённо. 200 000 – 260 000 руб."),
    (4, "Системный аналитик (Junior+)",
     "Системный аналитик junior+: сбор требований, BPMN, UML, базовый SQL. 140 000 – 180 000 руб."),
    (5, "Специалист по ИБ / пентестер (Middle)",
     "Специалист по информационной безопасности middle: анализ защищённости веб-приложений, OWASP, Linux, сети. "
     "Желательно участие в CTF. 230 000 – 300 000 руб."),
    (5, "Аналитик SOC (Junior)",
     "Аналитик SOC junior: разбор инцидентов в SIEM, сети, Linux. Обучим процессам. 110 000 – 150 000 руб."),
    (6, "SRE / DevOps (Senior)",
     "Senior SRE: Kubernetes, глубокое знание сетей и Linux, CI/CD, мониторинг. Удалённо. 380 000 – 480 000 руб."),
    (7, "Python-разработчик (Junior)",
     "Junior Python-разработчик для платформы курсов: Python, SQL, REST. Будет плюсом Django. 90 000 – 130 000 руб."),
    (8, "Backend-разработчик Go (Middle+)",
     "Middle+ бэкенд на Go: микросервисы, Kafka, PostgreSQL. Гибрид. 290 000 – 370 000 руб."),
]

# Задания с эталоном проверяет система (answer_type="exact"), открытые — работодатель
EXACT_TASKS = [
    (0, "backend", "middle", ["algorithms"], "Сложность сортировки слиянием",
     "Какова асимптотическая сложность сортировки слиянием в худшем случае? Ответ в нотации O-большое.",
     "O(n log n)|n log n|nlogn|o(nlogn)"),
    (1, "frontend", "junior", ["javascript"], "Результат выражения",
     "Что вернёт выражение typeof null в JavaScript? Ответ одним словом.", "object|\"object\""),
    (4, "analyst", "middle", ["product_metrics"], "Конверсия в покупку",
     "Из 2 400 посетителей 96 оформили заказ. Какова конверсия в процентах? Ответ числом без знака процента.",
     "4|4.0|4,0"),
    (5, "security", "junior", ["networking"], "Порт SSH",
     "Какой TCP-порт по умолчанию использует SSH? Ответ числом.", "22"),
    (3, "mobile", "junior_plus", ["kotlin"], "Elvis-оператор",
     "Как называется оператор ?: в Kotlin? Ответ одним-двумя словами.", "элвис|elvis|elvis operator|элвис-оператор"),
]

MICRO_TASKS = [
    (0, "backend", "middle", ["http", "system_design"], "Идемпотентность платежа",
     "Клиент повторно отправил запрос на списание из-за таймаута. Как спроектировать API, чтобы деньги не списались "
     "дважды? Опишите подход в 5–10 предложениях."),
    (1, "frontend", "junior", ["react", "browser"], "Медленный список товаров",
     "Список из 5000 карточек товаров тормозит при прокрутке. Какие 2–3 шага вы бы предприняли первыми и почему?"),
    (3, "mobile", "middle", ["mobile_ui", "android"], "Офлайн-режим корзины",
     "Пользователь добавляет товары в корзину без сети. Как синхронизировать корзину с сервером, когда сеть появится, "
     "и не потерять изменения с другого устройства?"),
    (4, "analyst", "middle", ["product_metrics", "ab_testing"], "Упала конверсия",
     "Конверсия в оплату упала на 15% за неделю. Опишите план, как найти причину: какие срезы и метрики проверите первыми?"),
    (5, "security", "middle", ["web_security"], "Подозрительные входы",
     "В логах видно 3 000 неудачных входов в разные аккаунты с одного /24-диапазона за час. Ваши действия?"),
    (6, "devops", "middle", ["kubernetes", "ci_cd"], "Откат релиза",
     "После выкладки выросла доля 5xx. Как организовать быстрый откат и что добавить в пайплайн, чтобы это не повторилось?"),
    (2, "qa", "junior", ["testing"], "Тест-кейсы для формы входа",
     "Перечислите 6–8 проверок для формы входа по email и паролю, включая негативные."),
    (1, "data", "middle", ["ml", "statistics"], "Дисбаланс классов",
     "В задаче антифрода 0,5% положительных примеров. Как обучать и оценивать модель? Какие метрики выберете?"),
]

# Как навыки банка обычно выглядят в резюме: «Python» → «Python, FastAPI»
SPECIFIC = {
    "python": ["fastapi", "django", "flask"], "sql": ["postgresql", "mysql", "clickhouse"],
    "http": ["rest", "grpc"], "concurrency": ["asyncio"], "system_design": ["microservices", "highload"],
    "javascript": ["typescript", "nodejs"], "react": ["nextjs", "redux"], "css": ["html", "tailwind"],
    "statistics": ["ab_testing"], "ml": ["pytorch", "sklearn"], "testing": ["pytest", "selenium"],
    "linux": ["bash"], "docker": ["kubernetes"], "networking": ["nginx"], "ci_cd": ["gitlab_ci", "github_actions"],
    "product_metrics": ["excel_bi"], "android": ["flutter"],
}


def _specific(skills: set[str]) -> set[str]:
    out = set(skills)
    for s in skills:
        if s in SPECIFIC and RNG.random() < 0.7:
            out.add(RNG.choice(SPECIFIC[s]))
    return out


_HASH: list[str] = []


def _user(db, email: str, role: Role) -> User:
    # bcrypt намеренно медленный: для 500 демо-аккаунтов с одним паролем считаем хеш один раз
    if not _HASH:
        _HASH.append(hash_password(PASSWORD))
    u = User(email=email, password_hash=_HASH[0], role=role, email_verified=True)
    db.add(u)
    db.flush()
    return u


def _simulate_assessment(db, cand: CandidateProfile, spec: str, theta_true: float, skills: set[str]):
    """Прогоняет кандидата через реальный CAT-движок с симулированными ответами."""
    true_idx = sum(theta_true >= cat.THRESHOLDS[g] for g in GRADE_CODES[1:])
    claimed_idx = min(len(GRADE_CODES) - 1, max(0, true_idx + RNG.choice([0, 0, 0, 1, -1])))
    claimed = GRADE_CODES[claimed_idx]
    pool = cat.pool_for(spec)
    all_resp = []
    attempts = 0
    last_claimed, last_est = claimed, None
    while claimed and attempts < 2:
        attempts += 1
        used, resp, last = [], [], []
        while True:
            est = cat.estimate(resp, claimed)
            if cat.should_stop(len(resp), est, cat.bank_left(pool, used)):
                break
            fam = cat.select_next(pool, est, used, set(), RNG, last)
            if fam is None:
                break
            used.append(fam.id)
            last.append(fam.skill)
            th = theta_true + (0.4 if fam.skill in skills else -0.4)
            resp.append(cat.Response(fam, RNG.random() < float(cat.p_correct(th, fam.a, fam.b))))
        all_resp += resp
        est = cat.estimate(resp, claimed)
        v = cat.decide(est, claimed)
        finished = utcnow() - timedelta(days=RNG.randint(1, 60))
        integrity = {"focus_lost": RNG.choice([0, 0, 0, 0, 1, 2, 6]), "copy_attempts": RNG.choice([0, 0, 0, 0, 0, 1, 3]),
                     "fast_answers": RNG.choice([0, 0, 0, 1, 4])}
        db.add(Assessment(candidate_id=cand.id, specialization=spec, claimed_grade=claimed,
                          status=AssessmentStatus.finished, seed=RNG.randrange(2**31), theta=est.theta,
                          theta_se=est.se, outcome=v.outcome, result_grade=v.grade, integrity=integrity,
                          started_at=finished - timedelta(minutes=RNG.randint(9, 19)), finished_at=finished))
        if v.grade:
            cand.specialization, cand.grade = spec, v.grade
            cand.theta, cand.theta_se = est.theta, est.se
            prof = skill_estimates(all_resp, est.theta)
            cand.skill_profile = prof
            cand.verified_skills = {k: display_level(x["theta"]) for k, x in prof.items()}
            cand.grade_assigned_at = finished
            cand.category_at = finished
            return claimed
        last_claimed, last_est = claimed, est
        idx = GRADE_CODES.index(claimed)
        claimed = GRADE_CODES[idx - 1] if idx > 0 else None
    # Грейд не подтвердился: кандидат не выпадает из оборота, а виден с пометкой и ниже подтверждённых
    cand.specialization, cand.grade, cand.grade_confirmed = spec, last_claimed, False
    cand.theta, cand.theta_se = last_est.theta, last_est.se
    cand.category_at = utcnow() - timedelta(days=RNG.randint(1, 60))
    prof = skill_estimates(all_resp, last_est.theta)
    cand.skill_profile = prof
    cand.verified_skills = {k: display_level(x["theta"]) for k, x in prof.items()}
    return None


def _candidate(db, i: int, fsp: MockFspClient, spec: str | None = None, theta: float | None = None,
               with_fsp: bool | None = None) -> CandidateProfile:
    spec_skills = {s["code"]: s["skills"] for s in SPECIALIZATIONS}
    spec = spec or RNG.choices(list(SPEC_WEIGHTS), weights=list(SPEC_WEIGHTS.values()))[0]
    theta = theta if theta is not None else RNG.gauss(0.1, 1.0)
    pool = spec_skills[spec]
    k = max(2, min(len(pool), round(len(pool) * (0.5 + 0.12 * theta + RNG.uniform(-0.15, 0.15)))))
    skills = set(RNG.sample(pool, k))
    first, last = RNG.choice(FIRST), RNG.choice(LAST)
    if first[-1] in "аяь" and first not in ("Никита",):
        last = last + "а" if not last.endswith("ий") else last[:-2] + "ая"
    u = _user(db, f"cand{i}@demo.ru", Role.candidate)
    cand = CandidateProfile(
        user_id=u.id, full_name=f"{first} {last}", contact_email=f"cand{i}@demo.ru",
        phone=f"+7 9{RNG.randint(10, 99)} {RNG.randint(100, 999)}-{RNG.randint(10, 99)}-{RNG.randint(10, 99)}",
        telegram=f"@cand_{i}", city=RNG.choice(CITIES),
        experience_years=round(max(0.0, 2.2 + 1.6 * theta + RNG.uniform(-1, 1)), 1),
        # Резюме часто шире реальных навыков и пишется конкретными технологиями
        declared_skills=sorted(_specific(skills | set(RNG.sample(pool, min(len(pool), 2))))),
        work_format=RNG.choice(["remote", "hybrid", "office", "any", "any"]),
        about=RNG.choice(ABOUT[spec]),
        consent_processing_at=utcnow(), consent_publication_at=utcnow(),
        last_activity_at=utcnow() - timedelta(days=RNG.randint(0, 120)),
    )
    db.add(cand)
    db.flush()
    claimed = _simulate_assessment(db, cand, spec, theta, skills)
    db.add(SurveyAnswer(candidate_id=cand.id, industry=next(s["industry"] for s in SPECIALIZATIONS if s["code"] == spec),
                        specialization=spec, claimed_grade=claimed or cand.grade or "junior",
                        answers={"self": {str(q): max(0, min(3, round(1.4 + 0.6 * theta + RNG.gauss(0, 0.5))))
                                          for q in range(6)}}))
    if cand.grade:
        cand.salary_expectation = int(SALARY[cand.grade] * RNG.uniform(0.85, 1.25) // 5000 * 5000)
    if with_fsp if with_fsp is not None else RNG.random() < 0.3:
        fsp_id = f"FSP-{100000 + i * 7 + RNG.randint(1, 6)}"  # оканчивается не на 0 — есть история
        participant = fsp.get_participant(fsp_id)
        cand.fsp_id = fsp_id
        cand.fsp_linked_at = utcnow()
        cand.fsp_rank = participant.sport_rank
        for a in participant.achievements:
            cand.achievements.append(FspAchievement(**a.__dict__))
    return cand


def _invite(db, co: Company, cand: CandidateProfile, need: HiringNeed | None, status: InvitationStatus,
            days_ago: int, messages: list[tuple[str, str]] = ()) -> Invitation:
    created = utcnow() - timedelta(days=days_ago)
    sal_from = need.salary_from if need else SALARY.get(cand.grade, 150_000)
    sal_to = need.salary_to if need else int(sal_from * 1.3)
    snap = score_candidate(cand, NeedQuery.from_need(need)).snapshot() if need else {}
    inv = Invitation(company_id=co.id, candidate_id=cand.id, need_id=need.id if need else None,
                     position_title=need.title if need else "Разработчик в продуктовую команду",
                     message=f"Здравствуйте! Нам понравился ваш профиль в категории — приглашаем обсудить позицию в «{co.name}».",
                     salary_from=sal_from, salary_to=sal_to, contact_method="Telegram рекрутера @hr_" + str(co.id),
                     status=status, match_snapshot=snap, created_at=created, expires_at=created + timedelta(days=14))
    if status != InvitationStatus.sent:
        inv.viewed_at = created + timedelta(hours=3)
    if status in (InvitationStatus.accepted, InvitationStatus.offer, InvitationStatus.hired, InvitationStatus.declined):
        inv.responded_at = created + timedelta(hours=6)
    if status in (InvitationStatus.offer, InvitationStatus.hired):
        inv.offer_at = created + timedelta(days=5)
    if status == InvitationStatus.hired:
        inv.hired_at = created + timedelta(days=12)
    if status == InvitationStatus.declined:
        inv.decline_reason = RNG.choice(["salary", "stack", "not_looking"])
    db.add(inv)
    db.flush()
    for k, (who, text) in enumerate(messages):
        db.add(Message(invitation_id=inv.id, sender=who, text=text, created_at=created + timedelta(hours=8 + k),
                       read_at=created + timedelta(hours=9 + k)))
    return inv


def run(n_candidates: int = N_CANDIDATES) -> None:
    Base.metadata.create_all(engine)
    ensure_columns()
    db = SessionLocal()
    if db.scalar(select(User).where(User.email == "employer@demo.ru")):
        print("Демо-данные уже загружены")
        return

    companies = []
    for c in COMPANIES:
        u = _user(db, c["email"], Role.employer)
        co = Company(user_id=u.id, name=c["name"], industry=c["industry"], description=c["description"],
                     contact_email=c["email"], inn=c.get("inn"), website=c.get("website"),
                     created_at=utcnow() - timedelta(days=3 if c.get("shady") else RNG.randint(60, 400)))
        db.add(co)
        db.flush()
        companies.append(co)

    needs = []
    for ci, title, text in VACANCY_TEXTS:
        p = parse_need(text)
        n = HiringNeed(company_id=companies[ci].id, title=title, description=text,
                       specialization=p["specialization"], grade=p["grade"] or "middle", skills=p["skills"],
                       requirements=[{k: r[k] for k in ("skill", "importance", "level")} for r in p["requirements"]],
                       work_format=p["work_format"],
                       salary_from=p["salary_from"], salary_to=p["salary_to"] or p["salary_from"],
                       is_published=True, seen_at=utcnow() - timedelta(days=3),
                       ats_external_id=f"hf-vac-{len(needs) + 1}" if COMPANIES[ci].get("ats") else None)
        db.add(n)
        needs.append(n)
    db.flush()

    for ci, spec, grade, skills, title, body in MICRO_TASKS:
        db.add(MicroTask(company_id=companies[ci].id, specialization=spec, grade=grade, skills=skills,
                         title=title, body=body))
    for ci, spec, grade, skills, title, body, ref in EXACT_TASKS:
        db.add(MicroTask(company_id=companies[ci].id, specialization=spec, grade=grade, skills=skills,
                         title=title, body=body, answer_type="exact", reference_answer=ref))

    # Пустой кандидат для живого демо сквозного пути
    u = _user(db, "candidate@demo.ru", Role.candidate)
    db.add(CandidateProfile(user_id=u.id, full_name="Демо Кандидат", contact_email="candidate@demo.ru",
                            consent_processing_at=utcnow()))

    fsp = MockFspClient()
    cands = []
    for i in range(n_candidates):
        if i == 3:
            # Витринный кандидат: backend middle с историей ФСП — получает приглашения в демо
            cand = _candidate(db, i, fsp, spec="backend", theta=0.35, with_fsp=True)
        else:
            cand = _candidate(db, i, fsp)
        if i == 7:
            # Несовершеннолетний участник ФСП: 16 лет, согласие законного представителя получено
            cand.birth_date = f"{utcnow().year - 16}-03-15"
            cand.guardian_name, cand.guardian_contact = "Родитель Демо", "+7 900 000-00-00"
            cand.guardian_consent_at = utcnow()
        if i % 37 == 5 and cand.grade_confirmed is False:
            cand.privacy = {**(cand.privacy or {}), "show_unconfirmed": False}
        if i % 11 == 0:
            # Свежие кандидаты в категориях — уведомление «новые кандидаты» у работодателей
            cand.category_at = utcnow() - timedelta(days=RNG.randint(0, 5))
        cands.append(cand)
    db.flush()

    # История взаимодействий: даёт реальные сигналы доверия (принятия, ответы, офферы)
    bank, retail, shady = companies[0], companies[1], companies[-1]
    showcase = cands[3]
    _invite(db, bank, showcase, needs[0], InvitationStatus.sent, 1)
    _invite(db, retail, showcase, None, InvitationStatus.accepted, 6,
            [("employer", "Спасибо, что приняли приглашение! Удобно созвониться в четверг в 15:00?"),
             ("candidate", "Добрый день! Да, четверг подходит.")])
    by_spec: dict[str, list[CandidateProfile]] = {}
    for c in cands[10:]:
        if c.grade and c.is_visible:
            by_spec.setdefault(c.specialization, []).append(c)
    plan = [(InvitationStatus.hired, 40), (InvitationStatus.offer, 12), (InvitationStatus.accepted, 8),
            (InvitationStatus.accepted, 4), (InvitationStatus.declined, 20), (InvitationStatus.viewed, 2),
            (InvitationStatus.sent, 1)]
    for co_i, need_i in ((0, 0), (0, 2), (1, 3), (4, 9), (5, 11), (3, 8)):
        co, need = companies[co_i], needs[need_i]
        pool = by_spec.get(need.specialization, [])[:len(plan)]
        for (st, days), cand in zip(plan, pool):
            msgs = [("employer", "Здравствуйте! Расскажу подробнее о команде — когда удобно созвониться?"),
                    ("candidate", "Добрый день, завтра после 16:00.")]
            _invite(db, co, cand, need, st, days, msgs if st in (InvitationStatus.accepted, InvitationStatus.offer,
                                                                InvitationStatus.hired) else [])
    # «Сборщик резюме»: массовые приглашения с вилкой-приманкой и три жалобы — компания приостановлена
    for k, cand in enumerate(by_spec.get("backend", [])[20:24]):
        inv = _invite(db, shady, cand, None, InvitationStatus.declined if k < 3 else InvitationStatus.viewed, 2)
        inv.salary_from, inv.salary_to, inv.salary_flag = 400_000, 900_000, "above_market"
        inv.message = "Срочно! Доход до 900 000. Для старта нужно пройти платное обучение."
        if k < 3:
            db.add(Complaint(invitation_id=inv.id, company_id=shady.id, candidate_id=cand.id,
                             reason=["payment", "fake", "spam"][k], text="Просили оплатить курс перед собеседованием"))
    shady.moderation_status = "review"

    # ATS Huntflow у «Цифрового Банка» в демонстрационном режиме
    db.add(AtsConnection(company_id=bank.id, provider="huntflow", account_id="demo-bank", token="",
                         webhook_secret=new_webhook_secret(), mode="mock"))
    db.add(AtsEvent(company_id=bank.id, direction="in", event="vacancies.imported", payload={"count": 3}))
    db.commit()
    print(f"Загружено: {len(companies)} компаний, {len(VACANCY_TEXTS)} вакансий, {n_candidates} кандидатов")
    db.close()


if __name__ == "__main__":
    run()
