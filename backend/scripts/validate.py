"""Процедура валидации решения на синтетических данных с известной «истиной».

Запуск:  python -m scripts.validate  (из каталога backend)
Результат: docs/02-validation.md + вывод в консоль.

Идея: раз эталонной разметки нет, мы генерируем популяцию кандидатов с
*известной* истинной способностью, специализацией и навыками, прогоняем их
через реальный код тестирования и подбора и сравниваем результат с истиной.

Блоки:
 1. Точность грейда: совпадение итогового грейда с истинным.
 2. Согласованность (test-retest): два независимых прохождения → тот же грейд?
 3. Дискриминативность: точечно-бисериальная корреляция по семействам.
 4. Устойчивость к утечке: атака «слитый ответ-ключ» против фиксированного теста.
 5. Робастность к ошибке калибровки: параметры a, b «врут» на ±0.3.
 6. Подбор: precision@10 и nDCG@10 против keyword-бейзлайна, в т.ч. на «приукрашенных» резюме.
"""

from __future__ import annotations

import json
import math
import random
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.catalog import GRADE_CODES, SPECIALIZATIONS  # noqa: E402
from app.models.entities import CandidateProfile, FspAchievement, SurveyAnswer, utcnow  # noqa: E402
from app.services.matching.ranking import NeedQuery, keyword_baseline_score, rank, score_candidate  # noqa: E402
from app.services.testing.skill_profile import display_level, skill_estimates  # noqa: E402
from app.core.skills import GRADE_DEFAULT_LEVEL, LEVELS  # noqa: E402
from app.services.matching.ranking import LEVEL_TOLERANCE  # noqa: E402
from app.services.testing import cat  # noqa: E402
from app.services.testing.item_bank import BANK, families_for  # noqa: E402

RNG = random.Random(2026)
SPEC_SKILLS = {s["code"]: s["skills"] for s in SPECIALIZATIONS}
# Уровень по навыку: +0.5, если кандидат им владеет, −1.0, если нет. Сдвиги центрируются
# по навыкам специализации, поэтому θ остаётся средним уровнем и грейд не смещается,
# а отсутствие конкретного навыка заметно в ответах на задания этого навыка.
OWN_EFFECT, MISSING_EFFECT = 0.5, -1.0


def true_grade(theta: float) -> str:
    g = GRADE_CODES[0]
    for code in GRADE_CODES:
        if theta >= cat.THRESHOLDS[code]:
            g = code
    return g


@dataclass
class Simulee:
    theta: float
    spec: str
    skills: set[str]

    def __post_init__(self):
        tested = sorted({f.skill for f in families_for(self.spec)})
        raw = {k: OWN_EFFECT if k in self.skills else MISSING_EFFECT for k in tested}
        mean = sum(raw.values()) / len(raw)
        self.delta = {k: v - mean for k, v in raw.items()}

    def answers(self, fam, rng: random.Random, param_noise: dict | None = None) -> bool:
        a, b = fam.a, fam.b
        if param_noise:  # «истинные» параметры отличаются от тех, что знает система
            a, b = a + param_noise[fam.id][0], b + param_noise[fam.id][1]
        th = self.theta + self.delta.get(fam.skill, 0.0)
        return rng.random() < float(cat.p_correct(th, max(a, 0.3), b))


def run_cat(s: Simulee, claimed: str, seed: int, param_noise=None, recently_seen=frozenset()):
    rng = random.Random(seed)
    responses: list[cat.Response] = []
    used: list[str] = []
    skills: list[str] = []
    while True:
        est = cat.estimate(responses, claimed)
        pool = cat.pool_for(s.spec)
        if cat.should_stop(len(responses), est, cat.bank_left(pool, used)):
            break
        fam = cat.select_next(pool, est, used, set(recently_seen), rng, skills)
        if fam is None:
            break
        used.append(fam.id)
        skills.append(fam.skill)
        responses.append(cat.Response(fam, s.answers(fam, rng, param_noise)))
    est = cat.estimate(responses, claimed)
    return est, cat.decide(est, claimed), responses


def placement(s: Simulee, claimed: str, seed: int, param_noise=None) -> tuple[str | None, int, list]:
    """Путь кандидата по правилам ТЗ: заявил грейд → не подтвердил → пробует уровнем ниже.
    Если подтвердил уверенно — пробует уровнем выше. Возвращает итоговый грейд и число заданий."""
    g = claimed
    total_items = 0
    confirmed = None
    log = []
    tried = set()
    while g and g not in tried:
        tried.add(g)
        est, v, resp = run_cat(s, g, seed + len(tried) * 7919, param_noise)
        total_items += len(resp)
        log.append((g, v.outcome))
        if v.grade:
            confirmed = v.grade
            if v.outcome == "upgrade_eligible" and v.suggested_grade not in tried:
                g = v.suggested_grade
                continue
            break
        idx = GRADE_CODES.index(g)
        g = GRADE_CODES[idx - 1] if idx > 0 else None
    return confirmed, total_items, log


def make_population(n: int) -> list[Simulee]:
    pop = []
    for _ in range(n):
        spec = RNG.choice(list(SPEC_SKILLS))
        theta = RNG.gauss(0.0, 1.1)
        pool = SPEC_SKILLS[spec]
        k = max(2, min(len(pool), int(round(len(pool) * (0.45 + 0.12 * theta + RNG.uniform(-0.15, 0.15))))))
        pop.append(Simulee(theta, spec, set(RNG.sample(pool, k))))
    return pop


def claimed_for(s: Simulee) -> str:
    """30% кандидатов завышают грейд на 1, 10% занижают."""
    i = GRADE_CODES.index(true_grade(s.theta))
    r = RNG.random()
    if r < 0.30:
        i = min(i + 1, len(GRADE_CODES) - 1)
    elif r < 0.40:
        i = max(i - 1, 0)
    return GRADE_CODES[i]


def kappa(a: list, b: list) -> float:
    labels = sorted(set(a) | set(b), key=str)
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[l] * cb[l] for l in labels) / n / n
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


# ------------------------------------------------------------------ 1-2-5. Грейд и стабильность
def grade_block(n=1200):
    pop = make_population(n)
    rows = []
    for i, s in enumerate(pop):
        claimed = claimed_for(s)
        g1, items1, _ = placement(s, claimed, seed=10_000 + i)
        g2, _, _ = placement(s, claimed, seed=90_000 + i)
        est, _, _ = run_cat(s, true_grade(s.theta), seed=50_000 + i)
        rows.append((true_grade(s.theta), g1, g2, items1, s.theta, est.theta))
    acc = sum(t == g1 for t, g1, *_ in rows) / n
    cuts = [cat.THRESHOLDS[g] for g in GRADE_CODES[1:]]
    clear = [r for r in rows if min(abs(r[4] - c) for c in cuts) > 0.3]
    acc_clear = sum(t == g1 for t, g1, *_ in clear) / len(clear)
    retest_clear = sum(g1 == g2 for _, g1, g2, *_ in clear) / len(clear)
    within1 = sum(g1 is not None and abs(GRADE_CODES.index(t) - GRADE_CODES.index(g1)) <= 1 for t, g1, *_ in rows) / n
    retest_same = sum(g1 == g2 for _, g1, g2, *_ in rows) / n
    k = kappa([r[1] for r in rows], [r[2] for r in rows])
    rmse = math.sqrt(np.mean([(r[4] - r[5]) ** 2 for r in rows]))
    corr = float(np.corrcoef([r[4] for r in rows], [r[5] for r in rows])[0, 1])
    avg_items = float(np.mean([r[3] for r in rows]))
    over = sum(g1 is not None and GRADE_CODES.index(g1) > GRADE_CODES.index(t) for t, g1, *_ in rows) / n
    confusion = defaultdict(Counter)
    for t, g1, *_ in rows:
        confusion[t][g1 or "—"] += 1

    noise = {f.id: (RNG.uniform(-0.3, 0.3), RNG.uniform(-0.3, 0.3)) for f in BANK}
    acc_noisy = 0
    for i, s in enumerate(pop[:600]):
        g, _, _ = placement(s, claimed_for(s), seed=70_000 + i, param_noise=noise)
        acc_noisy += g == true_grade(s.theta)
    acc_noisy /= 600
    from app.core.catalog import GRADE_BASE
    base_acc = sum(g1 is not None and GRADE_BASE[g1] == GRADE_BASE[t] for t, g1, *_ in rows) / n
    base_retest = sum(g1 is not None and g2 is not None and GRADE_BASE[g1] == GRADE_BASE[g2] for _, g1, g2, *_ in rows) / n
    retest_within1 = sum(g1 is not None and g2 is not None and abs(GRADE_CODES.index(g1) - GRADE_CODES.index(g2)) <= 1
                         for _, g1, g2, *_ in rows) / n
    return dict(base_acc=base_acc, base_retest=base_retest, retest_within1=retest_within1, n=n, acc=acc, acc_clear=acc_clear, retest_clear=retest_clear, n_clear=len(clear), within1=within1, retest=retest_same, kappa=k, rmse=rmse, corr=corr,
                avg_items=avg_items, over=over, confusion=confusion, acc_noisy=acc_noisy)


# ------------------------------------------------------------------ 3. Дискриминативность
def discrimination_block(n=1500):
    pop = make_population(n)
    per_family = defaultdict(list)  # family -> [(correct, total_score)]
    for i, s in enumerate(pop):
        _, _, resp = run_cat(s, true_grade(s.theta), seed=30_000 + i)
        for r in resp:
            per_family[r.family.id].append((int(r.correct), s.theta))
    out = []
    for fam in BANK:
        data = per_family.get(fam.id, [])
        if len(data) < 30:
            continue
        x = np.array([d[0] for d in data])
        y = np.array([d[1] for d in data])
        rpb = float(np.corrcoef(x, y)[0, 1]) if x.std() > 0 else 0.0
        out.append((fam.id, len(data), float(x.mean()), rpb))
    # Разделение слабых и сильных: средний θ̂ у нижнего и верхнего квартилей истинного θ
    return out


# ------------------------------------------------------------------ 4. Утечка
def leakage_block(n_leak_sources=200, n_attackers=300):
    """Атакующий собирает ответы из n_leak_sources прохождений (тексты заданий + верные ответы)
    и в своей попытке подставляет слитый ответ, если видит точно такое же задание."""
    leaked = {}
    for i in range(n_leak_sources):
        spec = RNG.choice(list(SPEC_SKILLS))
        s = Simulee(RNG.gauss(0, 1), spec, set(SPEC_SKILLS[spec]))
        _, _, resp = run_cat(s, "middle", seed=200_000 + i)
        # Восстанавливаем конкретные варианты, которые видел источник утечки
        rng = random.Random(200_000 + i)
        for r in resp:
            v = r.family.render(rng.randrange(2**31))
            # Ключ — текст задания: атакующий узнает его и при другом порядке вариантов
            leaked[(r.family.id, v.prompt, v.code)] = v.options[v.correct]

    def attack(use_key: bool):
        hits = total = 0
        passed = []
        for i in range(n_attackers):
            spec = RNG.choice(list(SPEC_SKILLS))
            s = Simulee(-0.8, spec, set())  # слабый кандидат пытается «пролезть» на middle
            rng = random.Random(500_000 + i)
            responses, used, skills = [], [], []
            while True:
                est = cat.estimate(responses, "middle")
                pool = cat.pool_for(spec)
                if cat.should_stop(len(responses), est, cat.bank_left(pool, used)):
                    break
                fam = cat.select_next(pool, est, used, set(), rng, skills)
                used.append(fam.id)
                skills.append(fam.skill)
                v = fam.render(rng.randrange(2**31))
                total += 1
                if use_key and (fam.id, v.prompt, v.code) in leaked:
                    hits += 1
                    correct = True
                else:
                    correct = s.answers(fam, rng)
                responses.append(cat.Response(fam, correct))
            passed.append(cat.decide(cat.estimate(responses, "middle"), "middle").grade is not None)
        return hits / max(total, 1), sum(passed) / len(passed)

    hit_rate, attacker_pass = attack(True)
    _, no_key_pass = attack(False)

    # Базовая линия: фиксированный тест из 12 заданий, одинаковый для всех — ключ сливается целиком
    fixed_pass_with_leak = 1.0

    variants = {}
    for fam in BANK:
        seen = {(v.prompt, v.code) for v in (fam.render(sd) for sd in range(2000))}
        variants[fam.id] = len(seen)

    # Экспозиция: доля прохождений, в которых встречается семейство
    exposure = Counter()
    n_exp = 600
    for i in range(n_exp):
        s = Simulee(RNG.gauss(0, 1), "backend", set(SPEC_SKILLS["backend"]))
        _, _, resp = run_cat(s, "middle", seed=800_000 + i)
        for fid in {r.family.id for r in resp}:
            exposure[fid] += 1
    max_exp = max(exposure.values()) / n_exp
    low_variety = {k: v for k, v in variants.items() if v < 50}
    return dict(hit_rate=hit_rate, attacker_pass=attacker_pass, no_key_pass=no_key_pass,
                fixed_pass=fixed_pass_with_leak, variants=variants, max_exposure=max_exp, low_variety=low_variety,
                backend_pool=len(families_for("backend")))


# ------------------------------------------------------------------ 6. Подбор
NEEDS = [
    ("backend", "middle", ["python", "sql", "http"], ["concurrency"], 200_000, 300_000),
    ("backend", "senior", ["system_design", "concurrency", "sql"], ["algorithms"], 350_000, 500_000),
    ("frontend", "junior", ["javascript", "css"], ["react"], 90_000, 150_000),
    ("frontend", "middle", ["react", "javascript"], ["http"], 180_000, 260_000),
    ("data", "middle", ["ml", "statistics", "python"], ["sql"], 220_000, 320_000),
    ("qa", "junior", ["testing", "sql"], ["http"], 80_000, 130_000),
    ("devops", "middle", ["linux", "networking"], ["ci_cd", "docker"], 230_000, 330_000),
    ("mobile", "middle_plus", ["kotlin", "android"], ["concurrency"], 270_000, 360_000),
    ("analyst", "junior_plus", ["sql", "requirements"], ["bpmn"], 130_000, 180_000),
    ("analyst", "middle", ["product_metrics", "sql"], ["ab_testing"], 200_000, 270_000),
    ("security", "middle", ["web_security", "networking"], ["cryptography"], 220_000, 300_000),
    ("backend", "junior_plus", ["python", "sql"], ["http"], 120_000, 170_000),
]
EXPECTED_SALARY = {"intern": 60_000, "junior": 100_000, "junior_plus": 140_000, "middle": 210_000,
                   "middle_plus": 280_000, "senior": 380_000}

# Варианты агрегации для абляции: что даёт каждый механизм по отдельности
CONFIGS = [
    ("sum", "Взвешенная сумма (прошлая версия)", {"strictness": 1, "must_penalty": 1, "must_threshold": 0.4}),
    ("geo", "Геометрическое среднее", {"must_penalty": 1}),
    ("geo_must04", "+ штраф за must-have, порог 0.4", {"must_threshold": 0.4}),
    ("default", "+ порог must-have 0.5 (по умолчанию)", {}),
    ("conf", "+ сортировка с учётом уверенности (α = 0.5)", {"confidence_weight": 0.5}),
    ("strict", "Строгий режим (p = −1)", {"strictness": -1}),
    ("verified", "Строгий + обязательные только подтверждённые", {"strictness": -1, "unverified_penalty": 0.5}),
]


def make_query(spec, grade, must, nice, s_from, s_to, scoring=None) -> NeedQuery:
    reqs = [{"skill": x, "importance": "must"} for x in must] + [{"skill": x, "importance": "nice"} for x in nice]
    return NeedQuery.build(spec, grade, requirements=reqs, salary_from=s_from, salary_to=s_to, scoring=scoring or {})


SKILL_CHECK_PROB = 0.5  # доля навыков из резюме, которые кандидат проверяет мини-тестом


def run_skill_check(s: Simulee, skill: str, theta_prior: float, seed: int) -> list:
    """Мини-тест по одному навыку, как в продукте (POST /candidate/skill-checks)."""
    rng = random.Random(seed)
    pool = cat.pool_for(skill=skill)
    responses, used = [], []
    while True:
        est = cat.estimate(responses, "middle", prior_sd=1.2, prior_mean=theta_prior)
        if cat.should_stop(len(responses), est, cat.bank_left(pool, used), "skill"):
            break
        fam = cat.select_next(pool, est, used, set(), rng, [])
        if fam is None:
            break
        used.append(fam.id)
        responses.append(cat.Response(fam, s.answers(fam, rng)))
    return responses


def build_candidate(i: int, s: Simulee) -> tuple[CandidateProfile, Simulee]:
    claimed = claimed_for(s)
    grade, _, _ = placement(s, claimed, seed=1_000_000 + i)
    est, _, resp = run_cat(s, grade or claimed, seed=2_000_000 + i)
    inflater = RNG.random() < 0.3
    declared = set(s.skills)
    if inflater:  # приукрашенное резюме: «весь стек» специализации и завышенный грейд
        declared |= set(SPEC_SKILLS[s.spec])
        claimed = GRADE_CODES[min(GRADE_CODES.index(claimed) + 1, len(GRADE_CODES) - 1)]
    testable = cat.testable_skills()
    for k, skill in enumerate(sorted(declared)):
        if skill in testable and RNG.random() < SKILL_CHECK_PROB:
            resp = resp + run_skill_check(s, skill, est.theta, seed=3_000_000 + i * 50 + k)
    prof = skill_estimates(resp, est.theta)
    c = CandidateProfile(id=i, full_name=f"sim{i}", declared_skills=sorted(declared),
                         specialization=s.spec if grade else None, grade=grade,
                         theta=est.theta, theta_se=est.se, skill_profile=prof,
                         verified_skills={k: display_level(v["theta"]) for k, v in prof.items()},
                         microtask_evidence={},
                         salary_expectation=int(EXPECTED_SALARY[true_grade(s.theta)] * RNG.uniform(0.85, 1.2)),
                         work_format="any", last_activity_at=utcnow(), privacy={})
    c.survey = SurveyAnswer(industry="x", specialization=s.spec, claimed_grade=claimed)
    if RNG.random() < 0.25:  # участники ФСП чуть сильнее в среднем (самоотбор)
        place = 1 if s.theta > 1 else 3 if s.theta > 0.3 else 12
        c.achievements.append(FspAchievement(event_name="Чемпионат ФСП", discipline="продуктовое", level="federal",
                                             event_date="2025-05-01", place=place, skills=list(s.skills)[:2]))
    return c, s


def true_skill_ok(s: Simulee, skill: str, level: str) -> bool:
    """Истинное владение навыком на требуемом уровне: истинная способность по навыку
    (общий θ плюс сдвиг навыка) не ниже порога уровня с тем же допуском, что в скоринге."""
    if skill in s.delta:
        return s.theta + s.delta[skill] >= LEVELS[level] - LEVEL_TOLERANCE
    return skill in s.skills


def relevant(s: Simulee, c: CandidateProfile, need) -> float:
    """Эталонная релевантность (0/1/2) по ИСТИННЫМ свойствам кандидата."""
    spec, grade, must, nice, _, s_to = need
    if s.spec != spec:
        return 0.0
    gd = abs(GRADE_CODES.index(true_grade(s.theta)) - GRADE_CODES.index(grade))
    if gd > 1:
        return 0.0
    level = GRADE_DEFAULT_LEVEL[grade]
    must_cover = sum(true_skill_ok(s, x, level) for x in must) / len(must)
    budget_ok = c.salary_expectation <= s_to * 1.1
    if gd == 0 and must_cover == 1 and budget_ok:
        return 2.0
    if (gd == 0 and must_cover >= 0.5) or (gd == 1 and must_cover == 1 and budget_ok):
        return 1.0
    return 0.0


def must_failed_truth(s: Simulee, need) -> bool:
    level = GRADE_DEFAULT_LEVEL[need[1]]
    return not all(true_skill_ok(s, x, level) for x in need[2])


def ndcg(rels: list[float], ideal: list[float], k=10) -> float:
    dcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rels[:k]))
    idcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(sorted(ideal, reverse=True)[:k]))
    return dcg / idcg if idcg else 0.0


def isotonic(xs: list[float], ys: list[float]) -> list[tuple[float, float]]:
    """Изотоническая регрессия (pool adjacent violators): монотонная ступенчатая функция балл → вероятность."""
    pts = sorted(zip(xs, ys))
    blocks = [[x, x, y, 1] for x, y in pts]  # [x_min, x_max, сумма y, n]
    merged: list[list] = []
    for b in blocks:
        merged.append(b)
        while len(merged) > 1 and merged[-2][2] / merged[-2][3] >= merged[-1][2] / merged[-1][3]:
            b2 = merged.pop()
            b1 = merged.pop()
            merged.append([b1[0], b2[1], b1[2] + b2[2], b1[3] + b2[3]])
    return [(round(b[1], 4), round(b[2] / b[3], 3)) for b in merged]


def apply_bins(bins, x):
    for upper, p in bins:
        if x <= upper:
            return p
    return bins[-1][1]


def ece(pred: list[float], obs: list[int], n_bins=10) -> tuple[float, list]:
    """Ожидаемая ошибка калибровки и таблица надёжности по 10 корзинам."""
    rows = []
    total = 0.0
    for k in range(n_bins):
        lo, hi = k / n_bins, (k + 1) / n_bins
        idx = [i for i, p in enumerate(pred) if lo <= p < hi or (k == n_bins - 1 and p == 1.0)]
        if not idx:
            continue
        mp = float(np.mean([pred[i] for i in idx]))
        mo = float(np.mean([obs[i] for i in idx]))
        rows.append((f"{lo:.1f}–{hi:.1f}", len(idx), mp, mo))
        total += len(idx) / len(pred) * abs(mp - mo)
    return total, rows


def matching_block(n=900):
    pop = make_population(n)
    built = [build_candidate(i, s) for i, s in enumerate(pop)]
    truth = {c.id: s for c, s in built}
    cands = [c for c, _ in built]
    names = [k for k, _, _ in CONFIGS] + ["baseline", "oracle"]
    res = {k: defaultdict(list) for k in names}
    for need in NEEDS:
        rels_all = [relevant(truth[c.id], c, need) for c in cands]
        tops = {}
        for key, _, scoring in CONFIGS:
            tops[key] = [r.candidate for r in rank(cands, make_query(*need, scoring=scoring))][:10]
        q0 = make_query(*need)
        oracle = sorted(range(len(cands)), key=lambda i: (-rels_all[i], must_failed_truth(truth[cands[i].id], need)))
        tops["oracle"] = [cands[i] for i in oracle[:10]]
        tops["baseline"] = sorted(cands, key=lambda c: -keyword_baseline_score(c, q0))[:10]
        for key, top in tops.items():
            rels = [relevant(truth[c.id], c, need) for c in top]
            res[key]["p@10"].append(sum(r > 0 for r in rels) / 10)
            res[key]["strict_p@10"].append(sum(r == 2 for r in rels) / 10)
            res[key]["ndcg@10"].append(ndcg(rels, rels_all))
            res[key]["must_fail@10"].append(sum(must_failed_truth(truth[c.id], need) for c in top) / 10)
            res[key]["inflated@10"].append(sum(
                GRADE_CODES.index(c.survey.claimed_grade) > GRADE_CODES.index(true_grade(truth[c.id].theta)) for c in top))
    summary = {k: {m: float(np.mean(v)) for m, v in d.items()} for k, d in res.items()}

    # Стресс-тест компенсации: «блестящие» кандидаты, которые не знают одного обязательного навыка
    comp = {k: [] for k in names if k != "oracle"}
    comp_checked = {k: [] for k in names if k != "oracle"}
    comp_unchecked = {k: [] for k in names if k != "oracle"}
    for ni, need in enumerate(NEEDS):
        spec, grade, must = need[0], need[1], need[2]
        adv = []
        for j in range(30):
            sim = Simulee(cat.THRESHOLDS[grade] + 1.0 if grade != "intern" else 0.0, spec, set(SPEC_SKILLS[spec]))
            gap = must[j % len(must)]
            if gap in sim.delta:
                sim.delta = {k: (0.3 if k != gap else -2.5) for k in sim.delta}
            else:
                sim.skills.discard(gap)
            c, _ = build_candidate(50_000 + ni * 100 + j, sim)
            c.achievements = [FspAchievement(event_name="Чемпионат России ФСП", discipline="продуктовое",
                                             level="federal", event_date="2025-05-01", place=1,
                                             skills=[k for k in must if k != gap][:1])]
            c.declared_skills = sorted(set(c.declared_skills) | set(must))  # в резюме навык, конечно, указан
            c.salary_expectation = need[4]
            adv.append(c)
        adv_ids = {c.id for c in adv}
        # «Проверял навык» — по навыку-пробелу есть хотя бы 4 ответа (мини-тест пройден)
        checked = {c.id for c, j in zip(adv, range(30)) if c.skill_profile.get(must[j % len(must)], {}).get("n", 0) >= 4}
        pool = cands + adv
        tops = {key: [r.candidate for r in rank(pool, make_query(*need, scoring=scoring))][:10]
                for key, _, scoring in CONFIGS}
        q0 = make_query(*need)
        tops["baseline"] = sorted(pool, key=lambda c: -keyword_baseline_score(c, q0))[:10]
        for key, top in tops.items():
            ids = {c.id for c in top}
            comp[key].append(len(ids & adv_ids) / 10)
            comp_checked[key].append(len(ids & checked) / max(1, len(checked)))
            comp_unchecked[key].append(len(ids & (adv_ids - checked)) / max(1, len(adv_ids - checked)))
    for k, v in comp.items():
        summary[k]["compensation@10"] = float(np.mean(v))
        summary[k]["comp_checked"] = float(np.mean(comp_checked[k]))
        summary[k]["comp_unchecked"] = float(np.mean(comp_unchecked[k]))

    # Калибровка процента: учим на половине кандидатов, проверяем на другой половине
    pairs = []
    for need in NEEDS:
        q = make_query(*need)
        for c in cands:
            if not c.grade:
                continue
            r = score_candidate(c, q)
            if r.role_fit > 0:
                pairs.append((c.id % 2, r.score, int(relevant(truth[c.id], c, need) > 0)))
    train = [(x, y) for part, x, y in pairs if part == 0]
    test = [(x, y) for part, x, y in pairs if part == 1]
    bins = isotonic([x for x, _ in train], [y for _, y in train])
    raw_ece, raw_rows = ece([x for x, _ in test], [y for _, y in test])
    cal_ece, cal_rows = ece([apply_bins(bins, x) for x, _ in test], [y for _, y in test])
    full_bins = isotonic([x for _, x, _ in pairs], [y for _, _, y in pairs])
    out = Path(__file__).resolve().parents[1] / "app" / "services" / "matching" / "calibration.json"
    out.write_text(json.dumps({"source": "scripts/validate.py (синтетика)", "bins": full_bins}, ensure_ascii=False),
                   encoding="utf-8")
    return {"summary": summary, "raw_ece": raw_ece, "cal_ece": cal_ece, "raw_rows": raw_rows,
            "cal_rows": cal_rows, "n_pairs": len(pairs), "n": n}


def matching_report(m) -> list[str]:
    s = m["summary"]
    titles = {k: t for k, t, _ in CONFIGS} | {"baseline": "Keyword-бейзлайн (резюме + заявленный грейд)",
                                              "oracle": "Оракул (знает истину — потолок)"}
    lines = ["## 6. Качество подбора", "",
             f"{len(NEEDS)} потребностей (обязательные и желательные навыки) × {m['n']} кандидатов. "
             "Эталон считается по истинным свойствам: релевантен, если совпадает специализация, грейд ±1 "
             "и обязательные навыки истинно освоены на требуемом уровне (уровень по навыку = общий θ + сдвиг навыка).", "",
             "### Сравнение способов агрегации", "",
             "| вариант | p@10 | strict p@10 | nDCG@10 | провален must-have в топ-10 | стресс-тест: доля в топ-10 "
             "| из проверивших навык попали в топ | из не проверивших попали в топ | завысили грейд в топ-10 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for key in [k for k, _, _ in CONFIGS] + ["baseline", "oracle"]:
        x = s[key]
        mark = "**" if key == "default" else ""
        fmt = lambda k: f"{x[k]:.0%}" if k in x else "—"
        lines.append(f"| {mark}{titles[key]}{mark} | {x['p@10']:.2f} | {x['strict_p@10']:.2f} | {x['ndcg@10']:.2f} "
                     f"| {x['must_fail@10']:.0%} | {fmt('compensation@10')} | {fmt('comp_checked')} "
                     f"| {fmt('comp_unchecked')} | {x['inflated@10']:.1f} |")
    lines += ["", "«Провален must-have» — доля кандидатов в топ-10, которые на самом деле не владеют хотя бы одним "
              "обязательным навыком на требуемом уровне.", "",
              "«Стресс-тест компенсации» — в базу для каждой потребности добавлены 30 «блестящих» кандидатов: сильный тест, "
              "1 место ФСП (по другим навыкам), свежий профиль, ожидания в вилке и навык в резюме, но один обязательный навык они на самом деле "
              "не знают. Показана доля таких кандидатов в топ-10: это прямая проверка, компенсируют ли сильные стороны "
              "отсутствие обязательного навыка (идеал — 0%).", "",
              "### Калибровка процента релевантности", "",
              f"Пары «кандидат — потребность»: {m['n_pairs']}. Изотоническая регрессия обучена на половине кандидатов, "
              "проверена на другой половине. ECE — средняя разница между обещанной и фактической долей релевантных.", "",
              f"- Сырой балл как вероятность: ECE = **{m['raw_ece']:.3f}**",
              f"- После калибровки: ECE = **{m['cal_ece']:.3f}**", "",
              "| корзина | пар | обещано | фактически |", "|---|---|---|---|"]
    for name, cnt, mp, mo in m["cal_rows"]:
        lines.append(f"| {name} | {cnt} | {mp:.0%} | {mo:.0%} |")
    lines += ["", "Таблица калибровки сохраняется в `app/services/matching/calibration.json` и используется в выдаче "
              "(поле `probability`). На реальных данных она доучивается по действиям работодателей.", ""]
    return lines


def ml_block():
    """Качество ML-подсказок на отложенной синтетике (другой seed, чем при обучении)."""
    from app.services import ml

    xs, ys = ml.synthetic_corpus(n_per_spec=60, seed=999)
    model = ml.spec_model()
    pred = model.predict(xs)
    spec_acc = float(np.mean([p == y for p, y in zip(pred, ys)]))
    top2 = float(np.mean([y in model.classes_[np.argsort(-pr)[:2]] for pr, y in zip(model.predict_proba(xs), ys)]))
    X, y = ml.synthetic_population(n=2000, seed=4242)
    gm = ml.grade_model()
    gp = gm.predict(X)
    g_acc = float(np.mean(gp == y))
    g_w1 = float(np.mean(np.abs(gp - y) <= 1))
    typos = ["Постгрес", "Кубернетес", "реакт", "докер", "Котлин", "Typscript", "Джанго", "кафка", "линукс", "питон"]
    found = sum(bool(ml.fuzzy_skills(t)) or bool(__import__("app.core.skills", fromlist=["find_skills"]).find_skills(t))
                for t in typos)
    return dict(spec_acc=spec_acc, spec_top2=top2, n_spec=len(xs), grade_acc=g_acc, grade_w1=g_w1, n_grade=len(y),
                typo_found=found, typo_total=len(typos))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print("1-2,5. Грейд и согласованность …")
    g = grade_block()
    print("3. Дискриминативность …")
    d = discrimination_block()
    print("4. Утечка …")
    lk = leakage_block()
    print("6. Подбор …")
    m = matching_block()
    print("7. ML …")
    mlr = ml_block()

    lines = ["# Отчёт валидации (синтетические данные)", "",
             "Сгенерирован `python -m scripts.validate`. Популяция с известной истинной способностью θ, "
             "специализацией и навыками; 30% кандидатов завышают грейд, 30% резюме «приукрашены».", "",
             "## 1. Точность присвоения грейда", "",
             f"- Кандидатов: **{g['n']}**, в среднем заданий на кандидата (с учётом пересдач по правилам): **{g['avg_items']:.1f}**",
             f"- Шкала из 6 грейдов (Intern, Junior, Junior+, Middle, Middle+, Senior) с полосами шириной 0.5 по θ",
             f"- Итоговый грейд совпал с истинным: **{g['acc']:.1%}**, в пределах ±1 ступени: **{g['within1']:.1%}**",
             f"- Совпала базовая ступень (Junior/Junior+ → Junior, Middle/Middle+ → Middle): **{g['base_acc']:.1%}**",
             f"- Без «пограничных» кандидатов (|θ − порог| > 0.3, n = {g['n_clear']}): точность **{g['acc_clear']:.1%}**",
             f"- Завышение (грейд выше истинного): **{g['over']:.1%}**",
             f"- Точность оценки θ: RMSE = **{g['rmse']:.2f}**, корреляция с истиной r = **{g['corr']:.2f}**", "",
             "Матрица ошибок (строки — истинный грейд, столбцы — присвоенный):", "",
             "| истина \\ итог | " + " | ".join(GRADE_CODES + ["—"]) + " |",
             "|---|" + "---|" * (len(GRADE_CODES) + 1)]
    for t in GRADE_CODES:
        lines.append(f"| {t} | " + " | ".join(str(g["confusion"][t][x]) for x in GRADE_CODES + ["—"]) + " |")
    lines += ["", "## 2. Согласованность при повторном прохождении (test-retest)", "",
              f"- Тот же итоговый грейд при независимом повторе с другими заданиями: **{g['retest']:.1%}**",
              f"- Без пограничных кандидатов: **{g['retest_clear']:.1%}**",
              f"- В пределах ±1 ступени: **{g['retest_within1']:.1%}**; та же базовая ступень: **{g['base_retest']:.1%}**",
              f"- Каппа Коэна: **{g['kappa']:.2f}**", "",
              "## 3. Дискриминативность заданий", "",
              "Точечно-бисериальная корреляция ответа с истинной способностью (> 0.3 — хорошо):", "",
              "| семейство | ответов | доля верных | r_pb |", "|---|---|---|---|"]
    for fid, cnt, p, rpb in sorted(d, key=lambda x: -x[3]):
        lines.append(f"| {fid} | {cnt} | {p:.2f} | {rpb:.2f} |")
    lines += ["", "## 4. Устойчивость к распространению заданий", "",
              f"- Атака «слитый ключ»: собраны ответы из 200 прохождений. Доля заданий атакующего, совпавших со слитыми: **{lk['hit_rate']:.2%}**",
              f"- Слабый кандидат (θ = −0.8) с этим ключом подтвердил Middle: **{lk['attacker_pass']:.1%}**; "
              f"без ключа — **{lk['no_key_pass']:.1%}**; при фиксированном тесте с утёкшим ключом — **{lk['fixed_pass']:.0%}**",
              f"- Максимальная экспозиция семейства в пуле Backend ({lk['backend_pool']} семейств): **{lk['max_exposure']:.0%}** прохождений",
              "- Уникальных вариантов на семейство (из 2000 сидов):", ""]
    lines.append(", ".join(f"{k}: {v}" for k, v in lk["variants"].items()))
    lines += ["", "Семейства с < 50 уникальными формулировками (знаниевые, низкая защита от утечки): "
              + (", ".join(lk["low_variety"]) or "нет")]
    lines += ["", f"## 5. Робастность к ошибке калибровки", "",
              f"- Параметры a и b заданий случайно смещены на ±0.3: точность грейда **{g['acc_noisy']:.1%}** (без смещения {g['acc']:.1%})", "",
              ""]
    lines += matching_report(m)
    lines += ["", "## 7. ML и NLP-подсказки (отложенная синтетика)", "",
              f"- Классификатор специализации по тексту резюме (TF-IDF + логистическая регрессия), {mlr['n_spec']} текстов: "
              f"точность **{mlr['spec_acc']:.1%}**, верная в топ-2 **{mlr['spec_top2']:.1%}**",
              f"- Подсказка грейда по профилю и опроснику, {mlr['n_grade']} профилей: точно **{mlr['grade_acc']:.1%}**, "
              f"±1 ступень **{mlr['grade_w1']:.1%}**. Это подсказка до теста; грейд присваивает только тест (раздел 1)",
              f"- Нечёткое распознавание навыков (опечатки, транслит): найдено **{mlr['typo_found']} из {mlr['typo_total']}**", ""]
    out = Path(__file__).resolve().parents[2] / "docs" / "02-validation.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
