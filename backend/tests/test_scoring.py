"""Свойства модели релевантности, на которые опирается механика подбора."""

from app.core.skills import transfer
from app.models.entities import CandidateProfile, FspAchievement, utcnow
from app.services.matching.ranking import NeedQuery, power_mean, rank_detailed, score_candidate
from app.services.matching.text_parser import parse_need


def cand(cid=1, profile=None, declared=(), salary=200_000, fsp=False, fmt="any", grade="middle", theta=0.6):
    c = CandidateProfile(id=cid, specialization="backend", grade=grade, theta=theta, theta_se=0.3,
                         skill_profile=profile or {}, microtask_evidence={}, declared_skills=list(declared),
                         salary_expectation=salary, work_format=fmt, last_activity_at=utcnow(), privacy={})
    if fsp:
        c.achievements.append(FspAchievement(event_name="Чемпионат ФСП", discipline="продуктовое", level="federal",
                                             event_date="2025-05-01", place=1, skills=["python"]))
    return c


STRONG = {"theta": 1.5, "se": 0.3, "n": 6, "correct": 6}
WEAK = {"theta": -1.5, "se": 0.35, "n": 6, "correct": 0}


def need(**scoring):
    return NeedQuery.build("backend", "middle", requirements=[
        {"skill": "python", "importance": "must"}, {"skill": "sql", "importance": "must"}],
        salary_from=200_000, salary_to=300_000, scoring=scoring)


def test_power_mean_limits():
    assert abs(power_mean([1.0, 0.0], [1, 1], 1) - 0.5) < 1e-9
    geo = power_mean([1.0, 0.0], [1, 1], 0)
    strict = power_mean([1.0, 0.0], [1, 1], -2)
    assert geo < 0.5 and strict < geo  # чем строже, тем меньше компенсация


def test_strong_skill_does_not_compensate_failed_must():
    good = score_candidate(cand(1, {"python": STRONG, "sql": STRONG}), need())
    one_gap = score_candidate(cand(2, {"python": STRONG, "sql": WEAK}), need())
    assert good.score > 0.6
    assert one_gap.score < good.score * 0.6
    assert any(f.severity == "bad" and "SQL" in f.text for f in one_gap.flags)


def test_failed_test_overrides_resume_claim():
    r = score_candidate(cand(1, {"python": STRONG, "sql": WEAK}, declared=["sql", "postgresql"]), need())
    sql = next(x for x in r.requirements if x.skill == "sql")
    assert sql.coverage < 0.1 and sql.source == "test"


def test_fsp_is_bonus_only():
    without = score_candidate(cand(1, {"python": STRONG, "sql": STRONG}), need())
    with_fsp = score_candidate(cand(1, {"python": STRONG, "sql": STRONG}, fsp=True), need())
    assert with_fsp.score > without.score
    # Даже без бонуса ФСП работает только как дополнительное доказательство навыков: балл не ниже, чем без ФСП
    no_bonus = score_candidate(cand(1, {"python": STRONG, "sql": STRONG}, fsp=True), need(fsp_bonus=0))
    assert without.score <= no_bonus.score < with_fsp.score
    assert "не штрафуется" in next(b for b in without.blocks if b.key == "fsp").reason


def test_soft_vs_hard_salary_filter():
    pricey = cand(1, {"python": STRONG, "sql": STRONG}, salary=450_000)
    soft, excluded = rank_detailed([pricey], need())
    assert len(soft) == 1 and any("вилки" in f.text for f in soft[0].flags)
    hard, excluded = rank_detailed([pricey], need(hard={"salary": True}))
    assert hard == [] and excluded == {"salary": 1}


def test_unverified_must_is_flagged():
    r = score_candidate(cand(1, {"python": STRONG}, declared=["postgresql"]), need())
    sql = next(x for x in r.requirements if x.skill == "sql")
    assert sql.source == "declared" and sql.testable
    assert any("проверку навыка" in f.text for f in r.flags)


def test_skill_graph_transfer():
    assert transfer("fastapi", "python") == 0.8
    assert transfer("python", "fastapi") == 0.5
    assert transfer("django", "fastapi") == 0.35
    assert transfer("postgresql", "sql") == 0.8
    assert transfer("python", "sql") == 0.0


def test_parse_must_and_nice():
    p = parse_need("Middle backend на Python. Глубокое знание PostgreSQL. Будет плюсом Docker и Next.js.")
    reqs = {r["skill"]: r for r in p["requirements"]}
    assert reqs["python"]["importance"] == "must"
    assert reqs["postgresql"]["level"] == "expert"
    assert reqs["docker"]["importance"] == "nice" and reqs["nextjs"]["importance"] == "nice"
    assert "javascript" not in reqs  # «Next.js» не распадается на «js»
