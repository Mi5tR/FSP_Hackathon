"""Граф навыков: иерархия «родитель → потомок», связи между близкими навыками
и правила частичного зачёта.

Зачем: работодатель пишет «FastAPI», кандидат подтвердил тестом «Python».
Это не полное совпадение, но и не ноль. Коэффициенты переноса делают такие
случаи явными и объяснимыми.

Синонимы задаются регулярными выражениями (без учёта регистра, «ё» → «е»).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

# Коэффициенты переноса подтверждения между навыками
CHILD_TO_PARENT = 0.8   # знает FastAPI → почти наверняка знает Python
PARENT_TO_CHILD = 0.5   # знает Python → FastAPI освоит, но это не подтверждено
SIBLING = 0.35          # Django и FastAPI: общий родитель


@dataclass(frozen=True)
class Skill:
    code: str
    title: str
    patterns: tuple[str, ...]
    parent: str | None = None
    related: dict[str, float] = field(default_factory=dict)


_W = r"(?<![a-zа-я0-9])"   # левая граница слова
_E = r"(?![a-zа-я0-9])"    # правая граница слова


def w(token: str) -> str:
    """Токен как отдельное слово (для латиницы и коротких аббревиатур)."""
    return _W + token + _E


SKILLS: list[Skill] = [
    # --- языки и платформы бэкенда
    Skill("python", "Python", (w("python"), "питон")),
    Skill("fastapi", "FastAPI", (w("fastapi"),), "python"),
    Skill("django", "Django", (w("django"),), "python"),
    Skill("flask", "Flask", (w("flask"),), "python"),
    Skill("java", "Java", (w("java"),), related={"kotlin": 0.6}),
    Skill("spring", "Spring", (w("spring"), "spring boot"), "java"),
    Skill("kotlin", "Kotlin", (w("kotlin"),), related={"java": 0.6}),
    Skill("go", "Go", (w("golang"), w("go")),),
    # --- данные и хранение
    Skill("sql", "SQL", (w("sql"), "базы данных", "баз данных", w("субд"))),
    Skill("postgresql", "PostgreSQL", (w("postgres(?:ql)?"),), "sql"),
    Skill("mysql", "MySQL", (w("mysql"),), "sql"),
    Skill("clickhouse", "ClickHouse", (w("clickhouse"),), "sql"),
    Skill("redis", "Redis", (w("redis"),), related={"system_design": 0.3}),
    Skill("kafka", "Kafka", (w("kafka"), "rabbitmq", "брокер(?:ы)? сообщений"), related={"system_design": 0.4}),
    # --- взаимодействие и архитектура
    Skill("http", "HTTP / API", (w("http"), w("api"), "веб-сервис")),
    Skill("rest", "REST", (w("rest"), "restful"), "http"),
    Skill("grpc", "gRPC", (w("grpc"),), "http"),
    Skill("concurrency", "Конкурентность", ("многопоточ", w("concurrency"), "параллел", "конкурентн")),
    Skill("asyncio", "asyncio / async", (w("asyncio"), w("async"), "асинхрон"), "concurrency", {"python": 0.3}),
    Skill("system_design", "Системный дизайн", ("system design", "архитектур", "проектирование систем")),
    Skill("microservices", "Микросервисы", ("микросервис", "microservice"), "system_design"),
    Skill("highload", "Highload", (w("highload"), "высоконагруж", "high-load"), "system_design"),
    Skill("algorithms", "Алгоритмы", ("алгоритм", w("algorithms?"), "структур[аы] данных", "олимпиад")),
    # --- фронтенд
    Skill("javascript", "JavaScript", (w("javascript"), w("js"), w("ecmascript"))),
    Skill("typescript", "TypeScript", (w("typescript"), w("ts")), "javascript"),
    Skill("nodejs", "Node.js", (w("node(?:\\.js|js)?"),), "javascript"),
    Skill("react", "React", (w("react"),), related={"javascript": 0.5}),
    Skill("nextjs", "Next.js", (w("next\\.?js"),), "react"),
    Skill("redux", "Redux", (w("redux"),), "react"),
    Skill("vue", "Vue", (w("vue(?:\\.js)?"),), related={"react": 0.4, "javascript": 0.5}),
    Skill("css", "CSS / вёрстка", (w("css"), "верстк", w("sass"), w("scss"))),
    Skill("html", "HTML", (w("html5?"),), "css"),
    Skill("tailwind", "Tailwind", (w("tailwind"),), "css"),
    Skill("browser", "Браузер и DOM", ("браузер", w("browser"), w("dom"), "web api")),
    # --- данные и ML
    Skill("statistics", "Статистика", ("статистик", w("statistics"))),
    Skill("ab_testing", "A/B-тесты", ("a/b", "ab-тест", "а/б"), "statistics"),
    Skill("ml", "Машинное обучение", ("machine learning", w("ml"), "машинн(?:ое|ого) обучени", "нейросет")),
    Skill("pytorch", "PyTorch", (w("pytorch"), w("torch")), "ml"),
    Skill("sklearn", "scikit-learn", (w("sklearn"), "scikit"), "ml"),
    # --- качество
    Skill("testing", "Тестирование", ("тестирован", w("testing"), w("qa"), "автотест")),
    Skill("pytest", "pytest", (w("pytest"),), "testing", {"python": 0.4}),
    Skill("selenium", "Selenium / UI-автотесты", (w("selenium"), w("playwright"), w("cypress")), "testing"),
    # --- инфраструктура
    Skill("linux", "Linux", (w("linux"), w("unix"))),
    Skill("bash", "Bash", (w("bash"), w("shell")), "linux"),
    Skill("docker", "Docker", (w("docker"), "контейнер")),
    Skill("kubernetes", "Kubernetes", (w("kubernetes"), w("k8s")), "docker"),
    Skill("networking", "Сети", (w("сети"), "сетев", w("network(?:ing)?"), w("tcp"), w("dns"))),
    Skill("nginx", "Nginx", (w("nginx"),), "networking"),
    Skill("ci_cd", "CI/CD", ("ci/cd", w("ci"), "непрерывн(?:ая|ой) интеграц")),
    Skill("gitlab_ci", "GitLab CI", (w("gitlab"),), "ci_cd"),
    Skill("github_actions", "GitHub Actions", ("github actions",), "ci_cd"),
    Skill("jenkins", "Jenkins", (w("jenkins"),), "ci_cd"),
    # --- мобильная разработка
    Skill("android", "Android SDK", (w("android"), "андроид", w("jetpack"), w("compose")), related={"kotlin": 0.5}),
    Skill("swift", "Swift / iOS", (w("swift"), w("ios"), w("swiftui"), w("uikit"))),
    Skill("flutter", "Flutter", (w("flutter"), w("dart")), related={"mobile_ui": 0.4}),
    Skill("mobile_ui", "Мобильный UI и производительность", ("мобильн(?:ый|ого|ые) интерфейс", w("dp"), "жизненн(?:ый|ого) цикл",
                                                           w("fps"), "lifecycle")),
    # --- аналитика
    Skill("product_metrics", "Продуктовые метрики", ("продуктов(?:ые|ых) метрик", "конверси", "воронк", w("retention"),
                                                     w("arpu"), w("ltv"), w("dau"), w("mau"), "юнит-экономик")),
    Skill("requirements", "Требования и ТЗ", ("требовани", "техническ(?:ое|ого) задани", w("тз"), "user stor",
                                              "use case", "юзкейс")),
    Skill("bpmn", "BPMN / моделирование процессов", (w("bpmn"), "бизнес-процесс", "моделирование процесс")),
    Skill("data_modeling", "Моделирование данных (ER, UML)", (w("uml"), w("er"), "er-диаграм", "модел(?:ь|ирование) данных",
                                                              "нормализац")),
    Skill("excel_bi", "Excel / BI", (w("excel"), w("power bi"), w("tableau"), w("datalens"), w("superset"))),
    # --- информационная безопасность
    Skill("web_security", "Безопасность веб-приложений", (w("owasp"), "уязвимост", w("xss"), "sql-инъекц", w("csrf"),
                                                          "пентест", w("pentest"), w("burp"))),
    Skill("cryptography", "Криптография", ("криптограф", "шифрован", w("tls"), w("pki"), "хеш-функц")),
    Skill("incident_response", "Мониторинг и реагирование (SOC)", (w("soc"), w("siem"), "инцидент", "реагировани",
                                                                   w("ids"), w("ips"))),
]
SKILL_BY_CODE = {s.code: s for s in SKILLS}
SKILL_TITLES = {s.code: s.title for s in SKILLS}

# Уровни требований и соответствующие пороги на шкале способности (та же шкала, что у грейдов)
LEVELS = {"basic": -1.0, "confident": 0.0, "expert": 1.0}
LEVEL_TITLES = {"basic": "базовый", "confident": "уверенный", "expert": "экспертный"}
GRADE_DEFAULT_LEVEL = {"intern": "basic", "junior": "basic", "junior_plus": "basic", "middle": "confident",
                       "middle_plus": "confident", "senior": "expert"}


def ancestors(code: str) -> list[str]:
    out = []
    cur = SKILL_BY_CODE.get(code)
    while cur and cur.parent:
        out.append(cur.parent)
        cur = SKILL_BY_CODE.get(cur.parent)
    return out


@lru_cache(maxsize=4096)
def transfer(evidence: str, required: str) -> float:
    """Какую долю подтверждения навыка `evidence` можно засчитать в навык `required`."""
    if evidence == required:
        return 1.0
    best = 0.0
    up_e, up_r = ancestors(evidence), ancestors(required)
    # evidence — потомок required (FastAPI → Python): по CHILD_TO_PARENT за каждый уровень
    if required in up_e:
        best = max(best, CHILD_TO_PARENT ** (up_e.index(required) + 1))
    # evidence — предок required (Python → FastAPI)
    if evidence in up_r:
        best = max(best, PARENT_TO_CHILD ** (up_r.index(evidence) + 1))
    # общий родитель
    if up_e and up_r and up_e[0] == up_r[0]:
        best = max(best, SIBLING)
    # явные связи (в обе стороны)
    for a, b in ((evidence, required), (required, evidence)):
        s = SKILL_BY_CODE.get(a)
        if s and b in s.related:
            best = max(best, s.related[b])
    return round(best, 3)


def _norm(text: str) -> str:
    return " " + re.sub(r"\s+", " ", text.lower().replace("ё", "е")) + " "


@lru_cache(maxsize=1)
def _compiled() -> list[tuple[str, re.Pattern]]:
    return [(s.code, re.compile(p.replace("ё", "е"))) for s in SKILLS for p in s.patterns]


def find_skills(text: str) -> dict[str, list[tuple[int, int]]]:
    """Находит навыки в тексте. Перекрывающиеся совпадения разрешаются в пользу более
    длинного: в «PostgreSQL» найдётся postgresql, а не ещё и sql."""
    t = _norm(text)
    spans = []
    for code, rx in _compiled():
        for m in rx.finditer(t):
            spans.append((m.start(), m.end(), code))
    spans.sort(key=lambda s: (-(s[1] - s[0]), s[0]))
    taken: list[tuple[int, int]] = []
    out: dict[str, list[tuple[int, int]]] = {}
    for start, end, code in spans:
        if any(start < e and s < end for s, e in taken):
            continue
        taken.append((start, end))
        out.setdefault(code, []).append((start, end))
    return out


def tree() -> list[dict]:
    """Справочник для UI: навыки с родителями."""
    return [{"code": s.code, "title": s.title, "parent": s.parent} for s in SKILLS]
