"""Компьютерное адаптивное тестирование (CAT) на модели IRT 2PL.

P(верно | theta) = 1 / (1 + exp(-a * (theta - b)))

* Оценка theta — EAP по сетке с нормальным априорным распределением,
  центрированным на заявленном грейде (кандидат сам выбирает предполагаемый грейд).
* Следующее задание — максимум информации Фишера в текущей оценке,
  но случайно из top-K (randomesque exposure control): разные кандидаты одного
  уровня получают разные семейства, банк не «выгорает» за неделю.
* Решение о грейде — по апостериорной вероятности P(theta >= порог грейда),
  а не по сырому числу правильных ответов. Это даёт стабильность при повторе.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import numpy as np

from app.core.catalog import GRADE_CODES, GRADES
from app.services.testing.item_bank import BANK, ItemFamily, families_for

GRID = np.linspace(-4, 4, 161)
# Априорное среднее — середина полосы заявленного грейда (см. catalog.GRADES)
GRADE_PRIOR_MEAN = {"intern": -1.5, "junior": -0.75, "junior_plus": -0.25, "middle": 0.25,
                    "middle_plus": 0.75, "senior": 1.5}
THRESHOLDS = {g["code"]: g["theta_min"] for g in GRADES}

# Полосы грейдов шириной 0.5 требуют точности SE ≈ 0.3; тест при этом укладывается в 20 минут
MIN_ITEMS = 12
MAX_ITEMS = 22
TARGET_SE = 0.30
TIME_LIMIT_MIN = 20
MAX_FAMILY_USES = 2  # семейство может встретиться повторно, но с другим вариантом
TOP_K = 4
MIN_PER_SKILL = 2
SKILL_BALANCE_BOOST = 1.3
# Короткая проверка одного навыка (заявленного в резюме): не меняет грейд, уточняет профиль навыков
SKILL_MIN_ITEMS = 4
SKILL_MAX_ITEMS = 6
CONFIRM_P = 0.5   # медиана апостериорного распределения не ниже порога: несмещённое решение для полос 0.5 (см. валидацию)
UPGRADE_P = 0.8   # уверенность, нужная для предложения повысить грейд


def p_correct(theta, a: float, b: float):
    return 1.0 / (1.0 + np.exp(-a * (theta - b)))


def fisher_info(theta: float, a: float, b: float) -> float:
    p = float(p_correct(theta, a, b))
    return a * a * p * (1 - p)


@dataclass
class Response:
    family: ItemFamily
    correct: bool


@dataclass
class Estimate:
    theta: float
    se: float
    posterior: np.ndarray

    def prob_at_least(self, threshold: float) -> float:
        return float(self.posterior[GRID >= threshold].sum())


def estimate(responses: list[Response], claimed_grade: str, prior_sd: float = 1.2,
             prior_mean: float | None = None) -> Estimate:
    mu = prior_mean if prior_mean is not None else GRADE_PRIOR_MEAN.get(claimed_grade, 0.0)
    log_post = -0.5 * ((GRID - mu) / prior_sd) ** 2
    for r in responses:
        p = p_correct(GRID, r.family.a_score, r.family.b)
        log_post += np.log(p if r.correct else 1 - p)
    post = np.exp(log_post - log_post.max())
    post /= post.sum()
    theta = float((GRID * post).sum())
    se = float(math.sqrt(((GRID - theta) ** 2 * post).sum()))
    return Estimate(theta, se, post)


def select_next(
    pool_families: list[ItemFamily],
    est: Estimate,
    used: list[str] | set[str],
    recently_seen: set[str],
    rng: random.Random,
    last_skills: list[str] | None = None,
    focus_skills: list[str] | None = None,
) -> ItemFamily | None:
    uses = {fid: list(used).count(fid) for fid in set(used)}
    pool = [f for f in pool_families if uses.get(f.id, 0) < min(MAX_FAMILY_USES, f.max_uses)]
    if not pool:
        return None
    # Сначала ещё не показанные в этой попытке семейства
    unseen = [f for f in pool if f.id not in uses]
    pool = unseen or pool
    # Семейства, которые кандидат видел в недавних попытках, понижаем в приоритете,
    # чтобы повторная попытка не превращалась в проверку памяти.
    fresh = [f for f in pool if f.id not in recently_seen] or pool
    # Балансировка содержания: не более двух заданий подряд на один навык
    if last_skills and len(last_skills) >= 2 and last_skills[-1] == last_skills[-2]:
        fresh = [f for f in fresh if f.skill != last_skills[-1]] or fresh
    boost = set(focus_skills or [])
    # Балансировка по навыкам: пока по навыку меньше MIN_PER_SKILL заданий, его семейства
    # получают приоритет — иначе профиль навыков строится по одному ответу
    seen_skills = list(last_skills or [])

    def priority(f: ItemFamily) -> float:
        p = fisher_info(est.theta, f.a_score, f.b)
        if f.skill in boost:
            p *= 1.6
        # Знаниевые семейства с малым числом формулировок не продвигаем: это ослабило бы защиту от утечки
        if seen_skills.count(f.skill) < MIN_PER_SKILL and f.max_uses > 1:
            p *= SKILL_BALANCE_BOOST
        return p

    ranked = sorted(fresh, key=priority, reverse=True)
    return rng.choice(ranked[: min(TOP_K, len(ranked))])


def should_stop(n_answered: int, est: Estimate, bank_left: int, kind: str = "grade") -> bool:
    lo, hi = (SKILL_MIN_ITEMS, SKILL_MAX_ITEMS) if kind == "skill" else (MIN_ITEMS, MAX_ITEMS)
    if bank_left == 0 or n_answered >= hi:
        return True
    return n_answered >= lo and est.se <= TARGET_SE


def next_grade(grade: str) -> str | None:
    i = GRADE_CODES.index(grade)
    return GRADE_CODES[i + 1] if i + 1 < len(GRADE_CODES) else None


@dataclass
class Verdict:
    outcome: str  # confirmed | upgrade_eligible | not_confirmed
    grade: str | None  # подтверждённый грейд (None, если заявленный не подтверждён)
    suggested_grade: str | None
    p_claimed: float
    explanation: str


def decide(est: Estimate, claimed: str) -> Verdict:
    p_claimed = est.prob_at_least(THRESHOLDS[claimed])
    # Самый высокий грейд, который подтверждается с достаточной уверенностью
    suggested = GRADE_CODES[0]
    for g in GRADE_CODES:
        if est.prob_at_least(THRESHOLDS[g]) >= CONFIRM_P:
            suggested = g
    if p_claimed >= CONFIRM_P:
        nxt = next_grade(claimed)
        if nxt and est.prob_at_least(THRESHOLDS[nxt]) >= UPGRADE_P:
            return Verdict("upgrade_eligible", claimed, nxt, p_claimed,
                           f"Грейд подтверждён уверенно (P={p_claimed:.2f}). Можно пройти тест на {nxt}.")
        return Verdict("confirmed", claimed, None, p_claimed, f"Грейд подтверждён (P={p_claimed:.2f}).")
    return Verdict("not_confirmed", None, suggested if suggested != claimed else None, p_claimed,
                   f"Заявленный грейд не подтверждён (P={p_claimed:.2f}). Грейд не понижается автоматически: "
                   f"можно пройти тест на уровень ниже ({suggested}).")


def pool_for(spec: str | None = None, skill: str | None = None) -> list[ItemFamily]:
    if skill:
        return [f for f in BANK if f.skill == skill]
    return families_for(spec)


def bank_left(pool_families: list[ItemFamily], used: list[str]) -> int:
    return sum(max(0, min(MAX_FAMILY_USES, f.max_uses) - used.count(f.id)) for f in pool_families)


def testable_skills() -> set[str]:
    return {f.skill for f in BANK}


def testable_root(skill: str) -> str | None:
    """Ближайший навык (сам или предок), для которого в банке есть задания."""
    from app.core.skills import ancestors

    bank = testable_skills()
    return next((s for s in [skill, *ancestors(skill)] if s in bank), None)


def blueprint(spec: str, grade: str, skills: list[str], seed: int = 0) -> dict:
    """Как формируется тест под описание вакансии: какие семейства и в какой пропорции.

    Категорийный тест одинаков по структуре для всех кандидатов категории (это даёт
    сопоставимость); вакансия лишь смещает приоритет семейств на требуемый стек.
    Сложность выравнивается через IRT, поэтому кандидаты по-прежнему сравнимы.
    Требования вида «FastAPI» проверяются через ближайший тестируемый навык («Python»).
    """
    theta0 = GRADE_PRIOR_MEAN[grade]
    mapped = {s: testable_root(s) for s in skills}
    focus = {r for r in mapped.values() if r}
    rows = []
    for f in families_for(spec):
        info = fisher_info(theta0, f.a, f.b)
        boost = 1.6 if f.skill in focus else 1.0
        rows.append((f, info * boost, f.skill in focus))
    total = sum(r[1] for r in rows) or 1
    rng = random.Random(seed)
    out = []
    for f, w, rel in sorted(rows, key=lambda r: -r[1]):
        v = f.render(rng.randrange(2**31))
        out.append({
            "family_id": f.id, "title": f.title, "skill": f.skill, "vacancy_skill": rel,
            "difficulty_b": f.b, "discrimination_a": f.a, "share": round(w / total, 3),
            "sample": {"prompt": v.prompt, "code": v.code, "options": v.options},
        })
    in_spec = {f.skill for f in families_for(spec)}
    return {"specialization": spec, "grade": grade, "start_theta": theta0,
            "min_items": MIN_ITEMS, "max_items": MAX_ITEMS,
            "skills_covered": sorted(s for s, r in mapped.items() if r in in_spec),
            "skills_via": {s: r for s, r in mapped.items() if r and r != s},
            "skills_not_in_bank": sorted(s for s, r in mapped.items() if r not in in_spec),
            "families": out}
