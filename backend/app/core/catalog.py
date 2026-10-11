"""Справочник специализаций, грейдов и навыков (MVP-набор основных направлений).

Грейд — уровень навыков, подтверждённый тестом (не стаж). Стаж остаётся атрибутом профиля.
Промежуточные грейды Junior+ и Middle+ делят шкалу способности на полосы по 0.5:
работодатель точнее находит «сильного джуна» или «почти сеньора», а смена грейда
по-прежнему ограничена кулдауном.
"""

GRADES = [
    # theta_min — нижняя граница латентной способности (шкала IRT) для грейда
    {"code": "intern", "title": "Intern", "experience": "стажёр, без коммерческого опыта", "theta_min": -99.0},
    {"code": "junior", "title": "Junior", "experience": "базовые задачи под присмотром", "theta_min": -1.0},
    {"code": "junior_plus", "title": "Junior+", "experience": "типовые задачи самостоятельно", "theta_min": -0.5},
    {"code": "middle", "title": "Middle", "experience": "самостоятельно ведёт задачи", "theta_min": 0.0},
    {"code": "middle_plus", "title": "Middle+", "experience": "сложные задачи, ревью коллег", "theta_min": 0.5},
    {"code": "senior", "title": "Senior", "experience": "архитектура и наставничество", "theta_min": 1.0},
]
GRADE_CODES = [g["code"] for g in GRADES]
GRADE_TITLES = {g["code"]: g["title"] for g in GRADES}
# Базовая ступень для промежуточных грейдов (Junior+ → Junior): используется в объяснениях и валидации
GRADE_BASE = {"intern": "intern", "junior": "junior", "junior_plus": "junior", "middle": "middle",
              "middle_plus": "middle", "senior": "senior"}

SPECIALIZATIONS = [
    {"code": "backend", "title": "Backend-разработчик", "industry": "development",
     "skills": ["python", "java", "go", "sql", "http", "algorithms", "concurrency", "system_design"]},
    {"code": "frontend", "title": "Frontend-разработчик", "industry": "development",
     "skills": ["javascript", "typescript", "react", "css", "http", "algorithms", "browser"]},
    {"code": "mobile", "title": "Мобильный разработчик", "industry": "development",
     "skills": ["kotlin", "android", "swift", "mobile_ui", "concurrency", "http", "algorithms"]},
    {"code": "data", "title": "Data Scientist / ML-инженер", "industry": "data",
     "skills": ["python", "sql", "statistics", "ml", "algorithms"]},
    {"code": "analyst", "title": "Аналитик (системный и продуктовый)", "industry": "analytics",
     "skills": ["sql", "product_metrics", "ab_testing", "statistics", "requirements", "bpmn", "data_modeling"]},
    {"code": "qa", "title": "QA-инженер", "industry": "quality",
     "skills": ["testing", "sql", "http", "python"]},
    {"code": "devops", "title": "DevOps-инженер", "industry": "infrastructure",
     "skills": ["linux", "docker", "networking", "ci_cd", "python"]},
    {"code": "security", "title": "Специалист по ИБ", "industry": "security",
     "skills": ["web_security", "cryptography", "incident_response", "linux", "networking", "http"]},
]
SPEC_CODES = [s["code"] for s in SPECIALIZATIONS]
SPEC_TITLES = {s["code"]: s["title"] for s in SPECIALIZATIONS}
# «Отрасль» в терминах постановщиков — ИТ-направление, а не индустрия бизнеса
INDUSTRIES = {
    "development": "Разработка ПО",
    "data": "Данные и ML",
    "analytics": "Аналитика",
    "quality": "Обеспечение качества",
    "infrastructure": "Инфраструктура и эксплуатация",
    "security": "Информационная безопасность",
}

# Смежные специализации: частичное совпадение при подборе
ADJACENT_SPECS = {
    "backend": {"devops": 0.4, "data": 0.3, "mobile": 0.2},
    "frontend": {"backend": 0.2, "mobile": 0.3},
    "mobile": {"frontend": 0.3, "backend": 0.2},
    "data": {"backend": 0.3, "analyst": 0.4},
    "analyst": {"data": 0.4, "qa": 0.2},
    "qa": {"backend": 0.2, "frontend": 0.2, "analyst": 0.2},
    "devops": {"backend": 0.4, "security": 0.3},
    "security": {"devops": 0.4, "backend": 0.2},
}

# Навыки и их синонимы: app/core/skills.py

SPEC_SYNONYMS = {
    "backend": ["backend", "бэкенд", "бекенд", "серверн"],
    "frontend": ["frontend", "фронтенд", "фронт", "интерфейс"],
    "mobile": ["mobile", "мобильн", "android", "андроид", "ios-разработ", "ios разработ", "flutter"],
    "data": ["data scien", "ml-инженер", "ml engineer", "машинное обучение", "дата-сайентист"],
    "analyst": ["системный аналитик", "бизнес-аналитик", "продуктовый аналитик", "аналитик данных", "analyst"],
    "qa": ["qa", "тестировщик"],
    "devops": ["devops", "sre", "инфраструктур"],
    "security": ["информационной безопасност", "иб-", "специалист по иб", "pentest", "пентест", "security", "soc-аналитик"],
}

GRADE_SYNONYMS = {
    "intern": ["стажёр", "стажер", "intern", "без опыта"],
    "junior": ["junior", "джун", "младший", "до года"],
    "junior_plus": ["junior+", "junior plus", "сильный джун"],
    "middle": ["middle", "мидл", "миддл"],
    "middle_plus": ["middle+", "middle plus", "сильный мидл"],
    "senior": ["senior", "сеньор", "синьор", "ведущий", "lead", "старший"],
}

# Релевантность дисциплин ФСП специализации (идея постановщиков: ИБ-специалисту
# соревнование по ИБ релевантнее робототехники). Все дисциплины равнозначны по престижу —
# коэффициент отражает только профильность, а не «важность» соревнования.
FSP_DISCIPLINE_RELEVANCE = {
    "продуктовое программирование": {"backend": 1.0, "frontend": 1.0, "mobile": 1.0, "qa": 0.9, "devops": 0.9,
                                     "analyst": 0.9, "data": 0.8, "security": 0.7},
    "алгоритмическое программирование": {"backend": 1.0, "data": 1.0, "frontend": 0.8, "mobile": 0.8,
                                         "security": 0.8, "devops": 0.7, "qa": 0.7, "analyst": 0.7},
    "программирование систем ИИ": {"data": 1.0, "backend": 0.8, "analyst": 0.8},
    "информационная безопасность": {"security": 1.0, "devops": 0.9, "backend": 0.8},
    "программирование робототехники": {"backend": 0.7, "data": 0.7, "mobile": 0.6},
    "программирование БАС": {"backend": 0.7, "data": 0.7, "mobile": 0.6},
}
FSP_RELEVANCE_DEFAULT = 0.6


def discipline_relevance(discipline: str | None, spec: str | None) -> float:
    if not spec or not discipline:
        return 1.0
    return FSP_DISCIPLINE_RELEVANCE.get((discipline or "").strip(), {}).get(spec or "", FSP_RELEVANCE_DEFAULT)


# Опросник самооценки по специализации (шаг 1 обязательного пути). Ответы 0–3:
# 0 — не делал, 1 — делал с помощью, 2 — делаю самостоятельно, 3 — учу других / отвечаю за решение.
# Опросник не присваивает грейд: он даёт подсказку, на какой грейд претендовать (ML-модель grade_hint),
# и показывает, какие разделы теста будут приоритетными.
SURVEY_SCALE = ["не делал", "с помощью", "самостоятельно", "учу других"]
SURVEY = {
    "backend": ["Проектировал REST/gRPC API и версионирование", "Писал сложные SQL-запросы и индексы под нагрузку",
                "Работал с очередями и асинхронной обработкой", "Профилировал и ускорял сервис под нагрузкой",
                "Разбивал монолит или проектировал микросервисы", "Проводил код-ревью и отвечал за архитектуру"],
    "frontend": ["Верстал адаптивные интерфейсы по макетам", "Писал SPA на React/Vue с роутингом и состоянием",
                 "Оптимизировал рендеринг и размер бандла", "Создавал или поддерживал дизайн-систему",
                 "Настраивал SSR/SSG и SEO", "Проводил код-ревью и задавал фронтенд-архитектуру"],
    "mobile": ["Публиковал приложение в RuStore / Google Play / App Store", "Работал с жизненным циклом экранов и навигацией",
               "Писал асинхронный код на корутинах / async-await", "Оптимизировал плавность списков и анимаций",
               "Настраивал офлайн-режим и синхронизацию", "Отвечал за архитектуру мобильного приложения"],
    "data": ["Готовил данные и признаки в pandas/SQL", "Обучал и валидировал классические ML-модели",
             "Проводил и интерпретировал A/B-тесты", "Обучал нейросети (PyTorch и др.)",
             "Выводил модели в прод и мониторил дрейф", "Отвечал за ML-направление или ревьюил модели коллег"],
    "analyst": ["Собирал и формализовал требования (user story, use case)", "Писал SQL-запросы для отчётов",
                "Моделировал процессы в BPMN / UML", "Считал продуктовые метрики и воронки",
                "Проектировал A/B-тесты и делал выводы", "Отвечал за аналитику продукта или команды"],
    "qa": ["Писал тест-кейсы и чек-листы", "Тестировал API (Postman, curl)", "Писал автотесты (pytest, Selenium)",
           "Проводил нагрузочное тестирование", "Настраивал тесты в CI", "Выстраивал процесс тестирования в команде"],
    "devops": ["Администрировал Linux-серверы", "Собирал Docker-образы и compose", "Настраивал CI/CD-пайплайны",
               "Работал с Kubernetes в проде", "Настраивал мониторинг и алертинг", "Отвечал за инфраструктуру и дежурства"],
    "security": ["Проводил анализ защищённости веб-приложений", "Разбирал журналы и инциденты (SIEM)",
                 "Настраивал сетевые экраны и сегментацию", "Работал с криптографией и PKI",
                 "Участвовал в CTF или bug bounty", "Отвечал за процессы ИБ в компании"],
}
