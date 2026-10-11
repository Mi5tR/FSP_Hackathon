"""Подбор и ранжирование кандидатов под потребность работодателя.

Модель релевантности — три уровня:

1. **Требования.** Для каждого навыка из потребности считается покрытие от 0 до 1:
   вероятность, что кандидат владеет навыком на требуемом уровне. Доказательства
   берутся из нескольких источников с разным доверием (тест > регулярные задания >
   ФСП > резюме) и переносятся по графу навыков (FastAPI → Python и т.п.).
2. **Блоки.** Роль, стек, уровень, подтверждённость, условия, актуальность — каждый
   от 0 до 1 со своим объяснением. ФСП — отдельный блок-бонус.
3. **Итог.** Взвешенное степенное среднее блоков с параметром строгости p
   (p = 1 — обычная взвешенная сумма, p = 0 — геометрическое среднее, p < 0 — ближе
   к минимуму): чем строже, тем меньше сильный блок компенсирует слабый. Поверх —
   ограничение при провале обязательного навыка и бонус ФСП, который не может
   понизить балл. Сортировка — по баллу, умноженному на уверенность в степени α.

Все параметры настраиваются в потребности работодателя (ScoringConfig).
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from app.core.catalog import ADJACENT_SPECS, GRADE_CODES, GRADE_TITLES, SPEC_TITLES, discipline_relevance
from app.core.skills import (
    CHILD_TO_PARENT,
    GRADE_DEFAULT_LEVEL,
    LEVEL_TITLES,
    LEVELS,
    SKILL_TITLES,
    ancestors,
    transfer,
)
from app.models.entities import CandidateProfile, utcnow
from app.services.testing.cat import THRESHOLDS
from app.services.testing.skill_profile import confidence as se_confidence
from app.services.testing.skill_profile import prob_at_least

BLOCKS = ["role", "stack", "level", "verification", "conditions", "freshness"]
BLOCK_TITLES = {
    "role": "Роль", "stack": "Стек", "level": "Уровень", "verification": "Подтверждённость",
    "conditions": "Условия", "freshness": "Актуальность", "fsp": "ФСП (бонус)",
}
# Доверие к источнику доказательства и уверенность, которую он даёт
SOURCE_TRUST = {"test": 1.0, "microtask": 0.8, "fsp": 0.7, "declared": 0.3}
SOURCE_TITLES = {"test": "тест", "microtask": "задания работодателей", "fsp": "ФСП", "declared": "резюме"}
CORROBORATED = 0.9  # тест по навыку-родителю подкрепляет заявленный в резюме навык-потомок
LEVEL_TOLERANCE = 0.25   # допуск при сравнении с порогом уровня
FLOOR = 0.03             # нижняя граница блока для степенного среднего с p ≤ 0
PLACE_FACTOR = ((1, 1.0), (3, 0.9), (10, 0.75))
# Все соревнования ФСП равнозначны (рекомендация постановщиков): уровень мероприятия не взвешивается.
# Учитываются число стартов и результативность: победа > призовое место > топ-10 > участие.
FSP_RESULT = ((1, 1.0), (3, 0.85), (10, 0.55))
FSP_PARTICIPATION = 0.2          # вклад одного старта без высокого места
FSP_PARTICIPATION_CAP = 0.5      # суммарный потолок «явок»: профиль нельзя набить одними онлайн-участиями
FSP_YEARLY_DECAY = 0.15          # свежий результат весит больше: −15% за год, но не ниже 50%
# Заявленный, но не подтверждённый тестом грейд: кандидат остаётся в выдаче, но ниже подтверждённых
UNCONFIRMED_GRADE_PENALTY = 0.6


# ------------------------------------------------------------------ настройки

@dataclass
class HardFilters:
    """Жёсткие фильтры: кандидат, не прошедший фильтр, исключается из выдачи
    (по умолчанию всё мягкое — кандидат остаётся, но получает флаг)."""
    must_skills: bool = False
    salary: bool = False
    work_format: bool = False
    exact_grade: bool = False
    fsp_only: bool = False


@dataclass
class ScoringConfig:
    weights: dict[str, float] = field(default_factory=lambda: {
        "role": 0.25, "stack": 0.30, "level": 0.15, "verification": 0.10, "conditions": 0.12, "freshness": 0.08})
    strictness: float = 0.0       # p степенного среднего, от -3 (строго) до 1 (компенсаторно)
    fsp_bonus: float = 0.15       # доля «оставшегося до 100%», которую закрывает сильный ФСП-профиль
    nice_weight: float = 0.5      # вес желательного навыка относительно обязательного
    # Значения по умолчанию выбраны по валидации (docs/02-validation.md, раздел 6)
    must_threshold: float = 0.5   # покрытие — вероятность владения; ниже 0.5 «скорее нет» — провал
    must_penalty: float = 0.6     # множитель итога за каждый проваленный обязательный навык
    min_confidence: float = 0.25  # ниже — флаг «мало данных» (без штрафа)
    unverified_penalty: float = 0.85  # множитель за каждый слабо подтверждённый обязательный навык
    confidence_weight: float = 0.0  # α: насколько уверенность влияет на порядок выдачи (0 — не влияет)
    hard: HardFilters = field(default_factory=HardFilters)

    @classmethod
    def from_dict(cls, d: dict | None) -> "ScoringConfig":
        cfg = cls()
        d = d or {}
        for k, v in (d.get("weights") or {}).items():
            if k in cfg.weights and isinstance(v, (int, float)):
                cfg.weights[k] = max(0.0, float(v))
        clamp = lambda v, lo, hi: max(lo, min(hi, float(v)))
        for name, lo, hi in (("strictness", -3, 1), ("fsp_bonus", 0, 0.5), ("nice_weight", 0, 1),
                             ("must_threshold", 0, 1), ("must_penalty", 0, 1),
                             ("min_confidence", 0, 1), ("unverified_penalty", 0, 1), ("confidence_weight", 0, 2)):
            if name in d and d[name] is not None:
                setattr(cfg, name, clamp(d[name], lo, hi))
        for k, v in (d.get("hard") or {}).items():
            if hasattr(cfg.hard, k):
                setattr(cfg.hard, k, bool(v))
        if sum(cfg.weights.values()) == 0:
            cfg.weights = cls().weights
        return cfg

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Requirement:
    skill: str
    importance: str = "must"   # must | nice
    level: str = "confident"   # basic | confident | expert


@dataclass
class NeedQuery:
    specialization: str
    grade: str
    requirements: list[Requirement]
    salary_from: int
    salary_to: int
    work_format: str = "any"
    config: ScoringConfig = field(default_factory=ScoringConfig)

    @property
    def skills(self) -> list[str]:
        return [r.skill for r in self.requirements]

    @classmethod
    def build(cls, specialization: str, grade: str, skills: list[str] | None = None,
              requirements: list[dict] | None = None, salary_from: int = 0, salary_to: int = 10_000_000,
              work_format: str = "any", scoring: dict | None = None) -> "NeedQuery":
        if requirements:
            reqs = [Requirement(r["skill"], r.get("importance", "must"), r.get("level") or GRADE_DEFAULT_LEVEL[grade])
                    for r in requirements]
        else:
            reqs = [Requirement(s, "must", GRADE_DEFAULT_LEVEL[grade]) for s in (skills or [])]
        return cls(specialization, grade, reqs, salary_from, salary_to, work_format, ScoringConfig.from_dict(scoring))

    @classmethod
    def from_need(cls, n, scoring_override: dict | None = None) -> "NeedQuery":
        return cls.build(n.specialization, n.grade, n.skills, n.requirements, n.salary_from, n.salary_to,
                         n.work_format, scoring_override if scoring_override is not None else n.scoring)


# ------------------------------------------------------------------ результаты

@dataclass
class Block:
    key: str
    title: str
    score: float
    weight: float
    reason: str


@dataclass
class ReqResult:
    skill: str
    title: str
    importance: str
    level: str
    coverage: float
    confidence: float
    source: str | None
    reason: str
    testable: bool = False
    # ok — закрыт; failed — тест показал низкий уровень или данных нет; unverified — только косвенные данные
    status: str = "ok"


@dataclass
class Flag:
    severity: str  # bad | warn | info
    text: str


@dataclass
class MatchResult:
    candidate: CandidateProfile
    score: float          # итоговая релевантность 0..1
    sort_key: float
    confidence: float
    blocks: list[Block] = field(default_factory=list)
    requirements: list[ReqResult] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)
    probability: float | None = None
    excluded_by: list[str] = field(default_factory=list)
    role_fit: float = 0.0

    @property
    def category(self) -> tuple[str, str]:
        return self.candidate.specialization, self.candidate.grade

    @property
    def percent(self) -> int:
        return round(self.score * 100)

    def snapshot(self) -> dict:
        """Снимок для приглашения: кандидат видит, почему его выбрали."""
        return {
            "score": self.score, "percent": self.percent, "confidence": self.confidence,
            "probability": self.probability,
            "blocks": [asdict(b) for b in self.blocks],
            "requirements": [asdict(r) for r in self.requirements],
            "flags": [asdict(f) for f in self.flags],
        }


# ------------------------------------------------------------------ математика

def power_mean(values: list[float], weights: list[float], p: float) -> float:
    """Взвешенное степенное среднее. p=1 — арифметическое, p→0 — геометрическое,
    p→−∞ — минимум. При p ≤ 0 значения ограничиваются снизу FLOOR, чтобы ноль
    одного блока давал сильный, но конечный штраф."""
    pairs = [(v, w) for v, w in zip(values, weights) if w > 0]
    if not pairs:
        return 0.0
    total_w = sum(w for _, w in pairs)
    if abs(p) < 1e-6:
        return math.exp(sum(w * math.log(max(v, FLOOR)) for v, w in pairs) / total_w)
    if p < 0:
        pairs = [(max(v, FLOOR), w) for v, w in pairs]
    return (sum(w * v ** p for v, w in pairs) / total_w) ** (1 / p)


_CALIBRATION_FILE = Path(__file__).with_name("calibration.json")
_calibration: list[tuple[float, float]] | None = None


def calibrate(score: float) -> float | None:
    """Оценка вероятности «кандидат релевантен» по откалиброванной ступенчатой функции
    (изотоническая регрессия, строится скриптом валидации)."""
    global _calibration
    if _calibration is None:
        try:
            _calibration = [tuple(x) for x in json.loads(_CALIBRATION_FILE.read_text(encoding="utf-8"))["bins"]]
        except (OSError, ValueError, KeyError):
            _calibration = []
    if not _calibration:
        return None
    for upper, prob in _calibration:
        if score <= upper:
            return prob
    return _calibration[-1][1]


def reload_calibration() -> None:
    global _calibration
    _calibration = None


def _place_factor(place: int | None) -> float:
    for limit, f in PLACE_FACTOR:
        if place and place <= limit:
            return f
    return 0.6


# ------------------------------------------------------------------ требования

def requirement_evidence(c: CandidateProfile, req: Requirement, threshold_ok: float = 0.5) -> ReqResult:
    """Доказательство владения навыком на требуемом уровне из всех источников.

    * Объективное доказательство по самому навыку или его потомку отменяет самоописание:
      провалил тест по SQL — строка «SQL» в резюме не спасает.
    * Подкреплённое заявление: кандидат указал в резюме «PostgreSQL» и прошёл тест по SQL —
      тест по навыку-родителю засчитывается с коэффициентом CORROBORATED, а не PARENT_TO_CHILD.
    """
    from app.services.testing.cat import testable_root

    threshold = LEVELS.get(req.level, 0.0) - LEVEL_TOLERANCE
    title = SKILL_TITLES.get(req.skill, req.skill)
    claimed = any(transfer(d, req.skill) >= CHILD_TO_PARENT for d in (c.declared_skills or []))
    # (покрытие, уверенность, источник, пояснение, вероятность уровня, прямое ли доказательство)
    options: list[tuple[float, float, str, str, float, bool]] = []
    strong_objective = False

    for s, est in (c.skill_profile or {}).items():
        t = transfer(s, req.skill)
        if t == 0:
            continue
        p = prob_at_least(est["theta"], est["se"], threshold)
        conf = se_confidence(est["se"])
        if s == req.skill:
            via = ""
        elif s in ancestors(req.skill) and claimed:
            t = max(t, CORROBORATED)
            via = f" по {SKILL_TITLES.get(s, s)} (подкрепляет заявленный {title})"
        else:
            via = f" через {SKILL_TITLES.get(s, s)}"
        direct = t >= CHILD_TO_PARENT
        options.append((t * p, t * conf, "test", f"тест{via}: {est['n']} зад., P(уровень) = {p:.0%}", p, direct))
        strong_objective |= direct and est["n"] >= 2

    for s, ev in (c.microtask_evidence or {}).items():
        t = transfer(s, req.skill)
        if t:
            conf = t * min(1.0, ev["n"] / 3) * 0.6
            options.append((t * SOURCE_TRUST["microtask"] * ev["score"], conf, "microtask",
                            f"задания работодателей: {ev['n']}, средняя оценка {ev['score'] * 5:.1f}/5",
                            ev["score"], t >= CHILD_TO_PARENT))
            strong_objective |= t >= CHILD_TO_PARENT

    for a in c.achievements or []:
        for s in a.skills or []:
            t = transfer(s, req.skill)
            if t:
                options.append((t * SOURCE_TRUST["fsp"] * _place_factor(a.place), t * 0.5, "fsp",
                                f"ФСП: «{a.event_name}»", 1.0, False))

    if not strong_objective:
        for s in c.declared_skills or []:
            t = transfer(s, req.skill)
            if t:
                options.append((t * SOURCE_TRUST["declared"], t * 0.1, "declared", "только заявлено в резюме",
                                1.0, False))

    testable = testable_root(req.skill) is not None
    if not options:
        return ReqResult(req.skill, title, req.importance, req.level, 0.0, 0.0, None, "нет данных", testable, "failed")
    tests = [o for o in options if o[2] == "test"]
    others = [o for o in options if o[2] != "test"]
    if not tests:
        cov, conf, src, why, p_lvl, direct = max(others, key=lambda o: (o[0], o[1]))
    else:
        # Тест — опорный источник, его вес равен его уверенности. Остальные источники
        # заполняют только неуверенную часть: уверенный провал теста не перекрыть ни ФСП,
        # ни резюме, а при малом числе заданий они честно добавляют информацию.
        t_cov, t_conf, _, t_why, p_lvl, direct = max(tests, key=lambda o: (o[5], o[1], o[0]))
        o_best = max(others, key=lambda o: (o[0], o[1])) if others else None
        o_cov, o_conf = (o_best[0], o_best[1]) if o_best else (0.0, 0.0)
        cov = t_conf * t_cov + (1 - t_conf) * max(t_cov, o_cov)
        conf = t_conf + (1 - t_conf) * o_conf
        src, why = "test", t_why
        if o_best and o_cov > t_cov and (1 - t_conf) * (o_cov - t_cov) > 0.05:
            why += f"; дополнительно {SOURCE_TITLES[o_best[2]]}"
    if cov >= threshold_ok:
        status = "ok"
    elif src in ("test", "microtask") and direct and p_lvl < threshold_ok:
        status = "failed"      # прямая проверка показала, что уровня нет
    else:
        status = "unverified"  # данные косвенные или только заявление — нужна проверка
    return ReqResult(req.skill, title, req.importance, req.level, round(cov, 3), round(conf, 3), src, why,
                     testable, status)


# ------------------------------------------------------------------ блоки

def _role(c: CandidateProfile, q: NeedQuery) -> tuple[Block, float]:
    spec = 1.0 if c.specialization == q.specialization else ADJACENT_SPECS.get(q.specialization, {}).get(c.specialization, 0.0)
    gd = abs(GRADE_CODES.index(c.grade) - GRADE_CODES.index(q.grade))
    # Соседний промежуточный грейд (Middle ↔ Middle+) — близкая категория, через ступень — дальняя
    s = spec * {0: 1.0, 1: 0.6, 2: 0.25}.get(gd, 0.0)
    label = f"{SPEC_TITLES.get(c.specialization, c.specialization)} · {GRADE_TITLES.get(c.grade, c.grade)}"
    if c.grade_confirmed is False:
        label += " (не подтверждён)"
    reason = (f"Категория совпадает: {label}" if s == 1.0 else
              f"Смежная категория: {label}" if s > 0 else f"Категория не совпадает: {label}")
    return Block("role", BLOCK_TITLES["role"], s, q.config.weights["role"], reason), s


def _stack(reqs: list[ReqResult], q: NeedQuery) -> Block:
    w = q.config.weights["stack"]
    if not reqs:
        return Block("stack", BLOCK_TITLES["stack"], 0.5, w, "Требования к стеку не заданы")
    weights = [1.0 if r.importance == "must" else q.config.nice_weight for r in reqs]
    s = power_mean([r.coverage for r in reqs], weights, q.config.strictness)
    must = [r for r in reqs if r.importance == "must"]
    ok = sum(r.coverage >= q.config.must_threshold for r in must)
    reason = f"Покрытие стека {s:.0%}" + (f"; обязательных закрыто {ok} из {len(must)}" if must else "")
    return Block("stack", BLOCK_TITLES["stack"], s, w, reason)


def _level(c: CandidateProfile, q: NeedQuery) -> Block:
    w = q.config.weights["level"]
    if c.theta is None:
        return Block("level", BLOCK_TITLES["level"], 0.0, w, "Нет результата теста")
    margin = c.theta - max(THRESHOLDS[c.grade], -2.5)
    s = 1 / (1 + math.exp(-2.2 * (margin - 0.5)))
    return Block("level", BLOCK_TITLES["level"], s, w,
                 f"Результат теста θ = {c.theta:+.2f}, запас над порогом грейда {margin:+.2f}")


def _verification(c: CandidateProfile, reqs: list[ReqResult], q: NeedQuery) -> Block:
    w = q.config.weights["verification"]
    if not reqs:
        s = se_confidence(c.theta_se or 0.8) if c.theta is not None else 0.0
        return Block("verification", BLOCK_TITLES["verification"], s, w, "Требования не заданы: учитывается точность теста")
    weights = [1.0 if r.importance == "must" else q.config.nice_weight for r in reqs]
    s = sum(r.confidence * wt for r, wt in zip(reqs, weights)) / sum(weights)
    objective = sum(1 for r in reqs if r.source in ("test", "microtask", "fsp"))
    return Block("verification", BLOCK_TITLES["verification"], s, w,
                 f"Объективно подтверждено {objective} из {len(reqs)} требований")


def _conditions(c: CandidateProfile, q: NeedQuery, flags: list[Flag]) -> tuple[Block, dict[str, bool]]:
    fails = {}
    exp = c.salary_expectation
    if not exp:
        sal, sal_txt = 0.8, "ожидания не указаны"
    elif exp <= q.salary_to:
        sal, sal_txt = 1.0, "ожидания в вилке"
    else:
        over = exp / q.salary_to - 1
        sal, sal_txt = max(0.0, 1 - over * 3), f"ожидания выше вилки на ~{over:.0%}"
        fails["salary"] = True
        flags.append(Flag("warn", f"Зарплатные ожидания выше вилки примерно на {over:.0%}"))
    fmt_ok = q.work_format == "any" or c.work_format in ("any", q.work_format)
    fmt = 1.0 if fmt_ok else 0.3
    if not fmt_ok:
        fails["work_format"] = True
        flags.append(Flag("warn", f"Формат работы не совпадает: кандидат выбрал «{c.work_format}»"))
    s = power_mean([sal, fmt], [1.0, 0.6], q.config.strictness)
    reason = f"Зарплата: {sal_txt}; формат: {'совпадает' if fmt_ok else 'не совпадает'}"
    return Block("conditions", BLOCK_TITLES["conditions"], s, q.config.weights["conditions"], reason), fails


def _freshness(c: CandidateProfile, q: NeedQuery, now: datetime) -> Block:
    w = q.config.weights["freshness"]
    if not c.last_activity_at:
        return Block("freshness", BLOCK_TITLES["freshness"], 0.0, w, "Нет активности")
    days = (now - c.last_activity_at).days
    s = 1.0 if days <= 14 else max(0.0, 1 - (days - 14) / 166)
    return Block("freshness", BLOCK_TITLES["freshness"], s, w, f"Профиль актуализирован {days} дн. назад")


def _events(n: int) -> str:
    word = "мероприятие" if n % 10 == 1 and n % 100 != 11 else (
        "мероприятия" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else "мероприятий")
    return f"{n} {word}"


def _fsp_age_factor(event_date: str | None, now: datetime) -> float:
    try:
        d = datetime.strptime((event_date or "")[:10], "%Y-%m-%d")
    except ValueError:
        return 1.0
    years = max(0.0, (now - d).days / 365.25)
    return max(0.5, 1 - FSP_YEARLY_DECAY * years)


def fsp_strength(c: CandidateProfile, relevant_skills: list[str] | None = None,
                 now: datetime | None = None, spec: str | None = None) -> tuple[float, str]:
    if not c.achievements:
        return 0.0, "Нет истории ФСП — не штрафуется, оценка по тесту и заданиям"
    now = now or utcnow()
    results, participation = 0.0, 0.0
    wins = prizes = 0
    best = None
    for a in c.achievements:
        res = next((f for limit, f in FSP_RESULT if a.place and a.place <= limit), None)
        w = (res if res is not None else FSP_PARTICIPATION) * _fsp_age_factor(a.event_date, now)
        if relevant_skills and any(transfer(s, r) >= 0.5 for s in (a.skills or []) for r in relevant_skills):
            w *= 1.25
        # Профильность дисциплины: ИБ-специалисту CTF релевантнее робототехники (все дисциплины равны по престижу)
        w *= discipline_relevance(getattr(a, "discipline", None), spec or getattr(c, "specialization", None))
        if res is None:
            participation += w
        else:
            results += w
        wins += a.place == 1
        prizes += bool(a.place and 2 <= a.place <= 3)
        if best is None or w > best[0]:
            best = (w, a)
    total = results + min(FSP_PARTICIPATION_CAP, participation)
    a = best[1]
    place_txt = f"{a.place} место" if a.place else "участие"
    stats = ", ".join(x for x in (f"побед: {wins}" if wins else "", f"призовых: {prizes}" if prizes else "") if x)
    return 1 - math.exp(-1.2 * total), (f"{_events(len(c.achievements))}" + (f" ({stats})" if stats else "")
                                        + f", лучшее — «{a.event_name}», {place_txt}")


# ------------------------------------------------------------------ итог

def score_candidate(c: CandidateProfile, q: NeedQuery, now: datetime | None = None) -> MatchResult:
    now = now or utcnow()
    cfg = q.config
    flags: list[Flag] = []
    reqs = [requirement_evidence(c, r, cfg.must_threshold) for r in q.requirements]

    role, role_fit = _role(c, q)
    stack = _stack(reqs, q)
    level = _level(c, q)
    verification = _verification(c, reqs, q)
    conditions, cond_fails = _conditions(c, q, flags)
    freshness = _freshness(c, q, now)
    blocks = [role, stack, level, verification, conditions, freshness]

    base = power_mean([b.score for b in blocks], [b.weight for b in blocks], cfg.strictness)

    fsp_s, fsp_reason = fsp_strength(c, q.skills, now, q.specialization)
    # Бонус закрывает часть разрыва до 100% и никогда не уменьшает балл
    total = base + cfg.fsp_bonus * fsp_s * (1 - base)
    blocks.append(Block("fsp", BLOCK_TITLES["fsp"], fsp_s, cfg.fsp_bonus, fsp_reason))

    must_failed = [r for r in reqs if r.importance == "must" and r.status == "failed"]
    for r in must_failed:
        flags.insert(0, Flag("bad", f"Обязательный навык «{r.title}» ({LEVEL_TITLES[r.level]}) не подтверждён: "
                                    f"покрытие {r.coverage:.0%}, {r.reason}"))
    # Каждый проваленный обязательный навык умножает итог на must_penalty: сильные стороны
    # не могут компенсировать отсутствие обязательного навыка
    total *= cfg.must_penalty ** len(must_failed)
    # Обязательный навык без надёжного подтверждения: мягкий штраф и подсказка запросить проверку
    # Обязательный навык без прямого подтверждения: мягкий штраф и подсказка запросить проверку
    weak = [r for r in reqs if r.importance == "must" and r.status == "unverified"]
    total *= cfg.unverified_penalty ** len(weak)
    if c.grade_confirmed is False:
        total *= UNCONFIRMED_GRADE_PENALTY
        flags.insert(0, Flag("warn", f"Грейд «{GRADE_TITLES.get(c.grade, c.grade)}» заявлен, но тестом не подтверждён: "
                                     "кандидат показан ниже подтверждённых в своей категории"))
    for r in reqs:
        hint = "можно запросить у кандидата проверку навыка" if r.testable else "проверка навыка в банке пока недоступна"
        if r in weak:
            flags.append(Flag("warn", f"«{r.title}» не подтверждён напрямую ({r.reason}); {hint}"))
        elif r.importance == "must" and r.status == "ok" and r.confidence < cfg.min_confidence:
            flags.append(Flag("info", f"«{r.title}»: мало заданий по навыку (уверенность {r.confidence:.0%}); {hint}"))
    for r in reqs:
        if r.importance == "nice" and r.status != "ok":
            flags.append(Flag("info", f"Желательный навык «{r.title}» не подтверждён"))


    role_conf = se_confidence(c.theta_se) if c.theta_se is not None else 0.0
    conf = 0.6 * verification.score + 0.4 * role_conf if reqs else role_conf
    sort_key = total * max(conf, 0.05) ** cfg.confidence_weight

    excluded = []
    h = cfg.hard
    if h.must_skills and must_failed:
        excluded.append("must_skills")
    if h.salary and cond_fails.get("salary"):
        excluded.append("salary")
    if h.work_format and cond_fails.get("work_format"):
        excluded.append("work_format")
    if h.exact_grade and c.grade != q.grade:
        excluded.append("exact_grade")
    if h.fsp_only and not c.achievements:
        excluded.append("fsp_only")

    return MatchResult(c, round(total, 4), round(sort_key, 4), round(conf, 3), blocks, reqs, flags,
                       calibrate(total), excluded, role_fit)


HARD_FILTER_TITLES = {
    "must_skills": "не закрыт обязательный навык", "salary": "ожидания выше вилки",
    "work_format": "не совпадает формат работы", "exact_grade": "другой грейд", "fsp_only": "нет истории ФСП",
}


def rank_detailed(cands: list[CandidateProfile], q: NeedQuery) -> tuple[list[MatchResult], dict[str, int]]:
    """Выдача только по присвоенным категориям; кандидаты, отсеянные жёсткими
    фильтрами, считаются, чтобы работодатель видел цену каждого фильтра."""
    results, excluded = [], {}
    for c in cands:
        if not c.grade or not c.specialization:
            continue
        r = score_candidate(c, q)
        if r.role_fit <= 0:
            continue
        if r.excluded_by:
            for k in r.excluded_by:
                excluded[k] = excluded.get(k, 0) + 1
            continue
        results.append(r)
    # Сначала точная категория, внутри — по баллу с учётом уверенности
    # Неподтверждённый грейд — после подтверждённых внутри той же категории
    results.sort(key=lambda r: (-r.role_fit, r.candidate.grade_confirmed is False, -r.sort_key))
    return results, excluded


def rank(cands: list[CandidateProfile], q: NeedQuery) -> list[MatchResult]:
    return rank_detailed(cands, q)[0]


def group_categories(results: list[MatchResult]) -> list[dict]:
    groups: dict[tuple, list[MatchResult]] = {}
    for r in results:
        groups.setdefault(r.category, []).append(r)
    out = []
    for (spec, grade), rs in groups.items():
        out.append({
            "specialization": spec, "grade": grade,
            "title": f"{SPEC_TITLES.get(spec, spec)} · {GRADE_TITLES.get(grade, grade)}",
            "fit": round(rs[0].role_fit, 2), "count": len(rs),
            "with_fsp": sum(1 for r in rs if r.candidate.achievements),
            "unconfirmed": sum(1 for r in rs if r.candidate.grade_confirmed is False),
            "avg_score": round(sum(r.score for r in rs) / len(rs), 3),
            "best_percent": max(r.percent for r in rs),
        })
    out.sort(key=lambda g: (-g["fit"], -g["avg_score"]))
    return out


def keyword_baseline_score(c: CandidateProfile, q: NeedQuery) -> float:
    """Базовая линия «как на обычной площадке»: совпадение ключевых слов резюме
    и самозаявленного грейда. Используется только для сравнения в валидации."""
    declared = set(c.declared_skills or [])
    overlap = len(declared & set(q.skills)) / max(1, len(q.skills))
    spec_ok = 1.0 if c.survey and c.survey.specialization == q.specialization else 0.0
    grade_ok = 1.0 if c.survey and c.survey.claimed_grade == q.grade else 0.0
    return 0.5 * overlap + 0.3 * spec_ok + 0.2 * grade_ok
