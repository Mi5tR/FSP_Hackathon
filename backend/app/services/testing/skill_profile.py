"""Профиль навыков: оценка способности по каждому навыку с мерой неопределённости.

На один навык в тесте приходится 1–4 задания, поэтому «доля верных» очень шумная.
Вместо неё для каждого навыка считается апостериорная оценка θ_навык с априорным
распределением, центрированным на общей способности кандидата θ (частичное
объединение, partial pooling): мало заданий — оценка близка к общему уровню и
неопределённость высокая; много заданий — оценка опирается на ответы по навыку.
"""

from __future__ import annotations

import math

import numpy as np

from app.services.testing.cat import GRID, Response, p_correct

SKILL_PRIOR_SD = 1.2  # насколько навык может отличаться от общего уровня


def skill_estimates(responses: list[Response], theta_global: float) -> dict[str, dict]:
    by_skill: dict[str, list[Response]] = {}
    for r in responses:
        by_skill.setdefault(r.family.skill, []).append(r)
    out = {}
    for skill, rs in by_skill.items():
        log_post = -0.5 * ((GRID - theta_global) / SKILL_PRIOR_SD) ** 2
        for r in rs:
            p = p_correct(GRID, r.family.a_score, r.family.b)
            log_post += np.log(p if r.correct else 1 - p)
        post = np.exp(log_post - log_post.max())
        post /= post.sum()
        theta = float((GRID * post).sum())
        se = float(math.sqrt(((GRID - theta) ** 2 * post).sum()))
        out[skill] = {"theta": round(theta, 3), "se": round(se, 3), "n": len(rs),
                      "correct": sum(r.correct for r in rs)}
    return out


def display_level(theta: float) -> float:
    """Уровень навыка для отображения, от 0 до 1 (0.5 — уверенный уровень)."""
    return round(1 / (1 + math.exp(-1.2 * theta)), 2)


def confidence(se: float) -> float:
    """1 — оценка точная, 0 — ответов по навыку нет (SE равна априорной)."""
    return round(max(0.0, min(1.0, 1 - se / SKILL_PRIOR_SD)), 3)


def prob_at_least(theta: float, se: float, threshold: float) -> float:
    """P(θ_навык ≥ порог) в нормальном приближении апостериорного распределения."""
    z = (theta - threshold) / max(se, 1e-6)
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))
