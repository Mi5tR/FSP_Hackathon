"""ML и NLP для разбора резюме и подсказок (scikit-learn, без GPU и без внешних API).

Где применяется и почему именно так:

1. **Классификатор специализации по тексту** (TF-IDF символьных n-грамм + логистическая
   регрессия). Резюме пишут как угодно: «бэкендер», «серверная часть», «Kotlin, Jetpack».
   Модель даёт распределение вероятностей по специализациям — в опросе это подсказка, какую
   специализацию выбрать. Категорию модель не присваивает: её даёт только тест.
2. **Нечёткое распознавание навыков** (ближайший сосед по символьным n-граммам). Словарь
   регулярных выражений ловит точные написания; модель добавляет опечатки и транслит
   («Постгрес», «Кубернетес», «Djnago»). Найденное так помечается «распознано по сходству».
3. **Подсказка грейда** (мультиклассовая логистическая регрессия по признакам профиля:
   стаж, ширина стека, призовые места ФСП, опросник самооценки). Обучена на синтетической
   популяции, где истинный уровень известен. Это только подсказка: грейд выбирает кандидат,
   подтверждает тест.

Модели маленькие (обучение < 2 с при первом обращении), обучаются детерминированно
и кэшируются в памяти процесса. Персональные данные никуда не передаются.
"""

from __future__ import annotations

import random
import re
from functools import lru_cache

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline

from app.core.catalog import GRADE_CODES, GRADES, SPEC_SYNONYMS, SPEC_TITLES, SPECIALIZATIONS
from app.core.skills import SKILL_TITLES, SKILLS, find_skills

# Разговорные и транслитерированные написания навыков — словарь для нечёткого поиска
ALIASES = {
    "python": ["питон", "пайтон"], "postgresql": ["постгрес", "postgres", "постгря"], "react": ["реакт", "reactjs"],
    "kubernetes": ["кубернетес", "кубер"], "javascript": ["джаваскрипт", "яваскрипт"], "typescript": ["тайпскрипт"],
    "docker": ["докер"], "kotlin": ["котлин"], "django": ["джанго"], "java": ["джава"], "golang": [],
    "go": ["голанг"], "clickhouse": ["кликхаус"], "kafka": ["кафка"], "redis": ["редис"], "linux": ["линукс"],
    "swift": ["свифт"], "android": ["андроид"], "flutter": ["флаттер"], "nginx": ["энджинкс"], "fastapi": ["фастапи"],
    "selenium": ["селениум"], "pytorch": ["пайторч"], "sklearn": ["сайкит"], "vue": ["вью", "vuejs"],
    "excel_bi": ["эксель", "powerbi"], "bpmn": ["бпмн"], "graphql": [],
}
_WORD = re.compile(r"[a-zа-яё][a-zа-яё0-9+#.\-]{2,}", re.I)


def _skill_names() -> list[tuple[str, str]]:
    out = []
    for s in SKILLS:
        out.append((s.code, s.title.lower()))
        out.append((s.code, s.code.replace("_", " ")))
        for a in ALIASES.get(s.code, []):
            out.append((s.code, a))
    return out


@lru_cache(maxsize=1)
def _skill_index():
    names = _skill_names()
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
    m = vec.fit_transform([n for _, n in names])
    return vec, m, names


def fuzzy_skills(text: str, threshold: float = 0.62) -> dict[str, str]:
    """Навыки, найденные по сходству написания: {код: слово из текста}. Точные совпадения
    словаря сюда не попадают — их уже нашёл find_skills."""
    exact = set(find_skills(text))
    words = {w.lower().strip(".-") for w in _WORD.findall(text)}
    words = [w for w in words if len(w) >= 4 and not find_skills(w)]
    if not words:
        return {}
    vec, m, names = _skill_index()
    sims = (vec.transform(words) @ m.T).toarray()
    out: dict[str, str] = {}
    for i, w in enumerate(words):
        j = int(sims[i].argmax())
        code = names[j][0]
        if sims[i, j] >= threshold and code not in exact and code not in out:
            out[code] = w
    return out


# ------------------------------------------------------------------ классификатор специализации

_ROLE_PHRASES = {
    "backend": ["разработка серверной части", "проектирование API", "микросервисы", "бэкенд-разработчик", "интеграции с платёжными системами"],
    "frontend": ["вёрстка интерфейсов", "SPA", "фронтенд-разработчик", "UI-компоненты", "дизайн-система"],
    "mobile": ["мобильное приложение", "android-разработчик", "ios-разработчик", "публикация в сторах", "Jetpack Compose"],
    "data": ["машинное обучение", "обучение моделей", "data scientist", "feature engineering", "рекомендательные системы"],
    "analyst": ["сбор требований", "системный аналитик", "продуктовая аналитика", "BPMN-схемы", "дашборды и метрики"],
    "qa": ["тестирование", "тест-кейсы", "автотесты", "регрессионное тестирование", "баг-репорты"],
    "devops": ["CI/CD", "инфраструктура", "мониторинг", "SRE", "администрирование серверов"],
    "security": ["анализ защищённости", "пентест", "SOC", "реагирование на инциденты", "CTF"],
}
_NOISE = ["git", "agile", "scrum", "jira", "английский B2", "командная работа", "коммуникабельность", "ответственность"]


def _synthetic_resume(rng: random.Random, spec: dict) -> str:
    code = spec["code"]
    own = [SKILL_TITLES.get(s, s) for s in spec["skills"]]
    children = [s.title for s in SKILLS if s.parent in spec["skills"]]
    other = [s.title for s in SKILLS if s.code not in spec["skills"]]
    parts = rng.sample(own, k=min(len(own), rng.randint(2, 5)))
    parts += rng.sample(children, k=min(len(children), rng.randint(0, 3)))
    parts += rng.sample(other, k=rng.randint(0, 3))          # шум: смежные технологии из других направлений
    parts += rng.sample(_ROLE_PHRASES[code], k=rng.randint(1, 3))
    parts += rng.sample(_NOISE, k=rng.randint(0, 3))
    if rng.random() < 0.5:
        parts.append(rng.choice(SPEC_SYNONYMS[code]))
    rng.shuffle(parts)
    return ", ".join(parts)


def synthetic_corpus(n_per_spec: int = 160, seed: int = 7) -> tuple[list[str], list[str]]:
    rng = random.Random(seed)
    xs, ys = [], []
    for spec in SPECIALIZATIONS:
        for _ in range(n_per_spec):
            xs.append(_synthetic_resume(rng, spec))
            ys.append(spec["code"])
    return xs, ys


@lru_cache(maxsize=1)
def spec_model():
    xs, ys = synthetic_corpus()
    model = make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=2),
        LogisticRegression(C=4.0, max_iter=2000),
    )
    model.fit(xs, ys)
    return model


def predict_specialization(text: str, top: int = 3) -> list[dict]:
    if not text or len(text.strip()) < 3:
        return []
    model = spec_model()
    probs = model.predict_proba([text])[0]
    order = np.argsort(-probs)[:top]
    return [{"specialization": str(model.classes_[i]), "title": SPEC_TITLES[str(model.classes_[i])],
             "probability": round(float(probs[i]), 3)} for i in order]


# ------------------------------------------------------------------ подсказка грейда

_THRESHOLDS = [g["theta_min"] for g in GRADES][1:]


def _grade_index(theta: float) -> int:
    return sum(theta >= t for t in _THRESHOLDS)


def _features(years: float, n_skills: int, prizes: int, survey_mean: float | None) -> list[float]:
    has_survey = 0.0 if survey_mean is None else 1.0
    return [min(years, 15) / 5, min(n_skills, 15) / 10, min(prizes, 5) / 3, (survey_mean or 0) / 3, has_survey]


def synthetic_population(n: int = 4000, seed: int = 11):
    """Та же генеративная модель, что у демо-данных: стаж, ширина стека и самооценка
    зависят от истинного уровня с шумом; призовые места ФСП — слабый сигнал."""
    rng = random.Random(seed)
    X, y = [], []
    for _ in range(n):
        theta = rng.gauss(0.1, 1.0)
        years = max(0.0, 2.2 + 1.6 * theta + rng.uniform(-1.2, 1.2))
        n_skills = max(1, round(5 + 1.5 * theta + rng.gauss(0, 1.5)))
        prizes = int(rng.random() < 0.15 + 0.08 * max(theta, 0)) * rng.randint(1, 2)
        survey = None if rng.random() < 0.3 else min(3.0, max(0.0, 1.4 + 0.6 * theta + rng.gauss(0, 0.45)))
        X.append(_features(years, n_skills, prizes, survey))
        y.append(_grade_index(theta))
    return np.array(X), np.array(y)


@lru_cache(maxsize=1)
def grade_model():
    X, y = synthetic_population()
    m = LogisticRegression(C=2.0, max_iter=3000)
    m.fit(X, y)
    return m


def predict_grade(years: float, n_skills: int, prizes: int, survey_mean: float | None) -> dict:
    m = grade_model()
    probs = m.predict_proba([_features(years, n_skills, prizes, survey_mean)])[0]
    dist = {GRADE_CODES[int(c)]: round(float(p), 3) for c, p in zip(m.classes_, probs)}
    best = max(dist, key=dist.get)
    return {"grade": best, "probability": dist[best], "distribution": dist}
