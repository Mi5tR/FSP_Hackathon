"""Жизненный цикл попытки тестирования и правила смены грейда."""

from __future__ import annotations

import random
import secrets
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.catalog import GRADE_CODES
from app.core.config import settings
from app.core.skills import SKILL_TITLES
from app.models.entities import (
    Assessment,
    AssessmentItem,
    AssessmentStatus,
    CandidateProfile,
    utcnow,
)
from app.services.testing import cat
from app.services.testing.item_bank import BANK_BY_ID, families_for
from app.services.testing.skill_profile import SKILL_PRIOR_SD, display_level, skill_estimates


def _responses(a: Assessment) -> list[cat.Response]:
    return [cat.Response(BANK_BY_ID[i.family_id], bool(i.is_correct)) for i in a.items if i.is_correct is not None]


def _pool(a: Assessment):
    return cat.pool_for(skill=a.skill) if a.kind == "skill" else cat.pool_for(a.specialization)


def _estimate(db: Session, a: Assessment) -> cat.Estimate:
    if a.kind == "skill":
        cand = db.get(CandidateProfile, a.candidate_id)
        return cat.estimate(_responses(a), a.claimed_grade, prior_sd=SKILL_PRIOR_SD,
                            prior_mean=cand.theta if cand.theta is not None else 0.0)
    return cat.estimate(_responses(a), a.claimed_grade)


def _recently_seen(db: Session, candidate_id: int, exclude_id: int | None = None) -> set[str]:
    rows = db.execute(
        select(AssessmentItem.family_id)
        .join(Assessment)
        .where(Assessment.candidate_id == candidate_id, Assessment.id != (exclude_id or -1))
        .order_by(AssessmentItem.id.desc())
        .limit(30)
    ).scalars()
    return set(rows)


def _no_active(db: Session, cand: CandidateProfile) -> None:
    active = db.scalar(select(Assessment).where(
        Assessment.candidate_id == cand.id, Assessment.status == AssessmentStatus.in_progress))
    if active:
        raise HTTPException(409, f"Уже есть незавершённая попытка #{active.id}")


UPGRADE_OFFER_DAYS = 30


def upgrade_offered(db: Session, cand: CandidateProfile, claimed: str) -> bool:
    """Уверенно сдавшему тест система сама предлагает тест на грейд выше. Такая попытка
    не ждёт кулдауна: это продолжение той же проверки, а не «прыжки» по грейдам.
    Повышение — только отдельным тестом, автоматического повышения нет."""
    last = db.scalar(select(Assessment).where(
        Assessment.candidate_id == cand.id, Assessment.kind == "grade",
        Assessment.status == AssessmentStatus.finished).order_by(Assessment.finished_at.desc()))
    if not last or last.outcome != "upgrade_eligible" or not last.finished_at:
        return False
    nxt = cat.next_grade(last.claimed_grade)
    return claimed == nxt and utcnow() - last.finished_at <= timedelta(days=UPGRADE_OFFER_DAYS)


def check_can_start(db: Session, cand: CandidateProfile, spec: str, claimed: str) -> None:
    """Правила:
    * без текущего грейда — можно тестироваться сразу, в т.ч. на уровень ниже после неудачи;
    * повторить тот же уровень после неудачи — через SAME_LEVEL_RETRY_DAYS;
    * смена уже подтверждённого грейда (вверх или вниз) — не чаще GRADE_CHANGE_COOLDOWN_DAYS.
    """
    _no_active(db, cand)
    now = utcnow()
    if cand.grade and cand.grade_confirmed and claimed != cand.grade and cand.grade_assigned_at:
        allowed = cand.grade_assigned_at + timedelta(days=settings.grade_change_cooldown_days)
        if now < allowed and not upgrade_offered(db, cand, claimed):
            raise HTTPException(429, f"Сменить грейд можно не раньше {allowed:%d.%m.%Y}")
    last_fail = db.scalar(
        select(Assessment)
        .where(Assessment.candidate_id == cand.id, Assessment.kind == "grade", Assessment.specialization == spec,
               Assessment.claimed_grade == claimed, Assessment.outcome == "not_confirmed")
        .order_by(Assessment.finished_at.desc())
    )
    if last_fail and last_fail.finished_at:
        allowed = last_fail.finished_at + timedelta(days=settings.same_level_retry_days)
        if now < allowed:
            raise HTTPException(429, f"Повторить тест на этот уровень можно с {allowed:%d.%m.%Y}. "
                                     f"Тест на уровень ниже доступен сразу.")


def start(db: Session, cand: CandidateProfile, spec: str, claimed: str) -> Assessment:
    if claimed not in GRADE_CODES:
        raise HTTPException(422, "Неизвестный грейд")
    if not families_for(spec):
        raise HTTPException(422, "Неизвестная специализация")
    check_can_start(db, cand, spec, claimed)
    a = Assessment(candidate_id=cand.id, specialization=spec, claimed_grade=claimed, kind="grade",
                   seed=secrets.randbelow(2**31), theta=cat.GRADE_PRIOR_MEAN[claimed])
    db.add(a)
    db.commit()
    return a


def start_skill_check(db: Session, cand: CandidateProfile, skill: str) -> Assessment:
    """Короткая проверка навыка, заявленного в резюме. Проверяется ближайший тестируемый
    навык графа (FastAPI → Python). Грейд не меняется, обновляется профиль навыков."""
    root = cat.testable_root(skill)
    if root is None:
        raise HTTPException(422, f"Для навыка «{SKILL_TITLES.get(skill, skill)}» пока нет заданий в банке")
    _no_active(db, cand)
    last = db.scalar(select(Assessment).where(
        Assessment.candidate_id == cand.id, Assessment.kind == "skill", Assessment.skill == root,
        Assessment.status == AssessmentStatus.finished).order_by(Assessment.finished_at.desc()))
    if last and last.finished_at:
        allowed = last.finished_at + timedelta(days=settings.skill_retest_days)
        if utcnow() < allowed:
            raise HTTPException(429, f"Повторная проверка навыка возможна с {allowed:%d.%m.%Y}")
    a = Assessment(candidate_id=cand.id, specialization=cand.specialization or "backend",
                   claimed_grade=cand.grade or "junior", kind="skill", skill=root,
                   seed=secrets.randbelow(2**31), theta=cand.theta or 0.0, theta_se=SKILL_PRIOR_SD)
    db.add(a)
    db.commit()
    return a


def current_item(a: Assessment) -> AssessmentItem | None:
    return next((i for i in a.items if i.answered_option is None), None)


def next_item(db: Session, a: Assessment) -> AssessmentItem | None:
    """Возвращает текущее неотвеченное задание либо выбирает новое; None — тест окончен."""
    if a.status != AssessmentStatus.in_progress:
        return None
    pending = current_item(a)
    if pending:
        return pending
    responses = _responses(a)
    est = _estimate(db, a)
    used = [i.family_id for i in a.items]
    pool = _pool(a)
    # Общий лимит времени теста: по истечении тест завершается по уже данным ответам
    timed_out = a.kind == "grade" and utcnow() - a.started_at > timedelta(minutes=cat.TIME_LIMIT_MIN)
    if timed_out or cat.should_stop(len(responses), est, cat.bank_left(pool, used), a.kind):
        finish(db, a)
        return None
    # RNG детерминирован от seed попытки и номера шага: попытку можно воспроизвести при аудите
    rng = random.Random(a.seed * 1000 + len(a.items))
    fam = cat.select_next(pool, est, used, _recently_seen(db, a.candidate_id, a.id), rng,
                          [BANK_BY_ID[i.family_id].skill for i in a.items])
    if fam is None:
        finish(db, a)
        return None
    variant_seed = rng.randrange(2**31)
    variant = fam.render(variant_seed)
    item = AssessmentItem(assessment_id=a.id, family_id=fam.id, variant_seed=variant_seed,
                          correct_option=variant.correct)
    db.add(item)
    db.commit()
    db.refresh(a)
    return item


FAST_ANSWER_S = 3  # быстрее — подозрительно для задания с кодом: сигнал, а не автоматический штраф


def answer(db: Session, a: Assessment, item_id: int, option: int,
           focus_lost: int = 0, copy_attempts: int = 0) -> AssessmentItem:
    item = current_item(a)
    if item is None or item.id != item_id:
        raise HTTPException(409, "Это задание уже не активно")
    elapsed = (utcnow() - item.presented_at).total_seconds()
    limit = BANK_BY_ID[item.family_id].time_limit_s
    item.answered_option = option
    item.response_ms = int(elapsed * 1000)
    # Ответ после истечения лимита (+10 с на сеть) засчитывается как неверный
    item.is_correct = option == item.correct_option and elapsed <= limit + 10
    # Прокторинг «лайт»: копим сигналы, работодатель видит сводку. На оценку θ они не влияют,
    # чтобы случайный уход с вкладки не стоил грейда.
    i = dict(a.integrity or {})
    i["focus_lost"] = i.get("focus_lost", 0) + focus_lost
    i["copy_attempts"] = i.get("copy_attempts", 0) + copy_attempts
    i["fast_answers"] = i.get("fast_answers", 0) + (elapsed < FAST_ANSWER_S and limit >= 30)
    a.integrity = i
    est = _estimate(db, a)
    a.theta, a.theta_se = est.theta, est.se
    db.commit()
    return item


def recompute_skill_profile(db: Session, cand: CandidateProfile) -> None:
    """Профиль навыков строится по ответам из всех завершённых попыток кандидата."""
    rows = db.scalars(select(Assessment).where(
        Assessment.candidate_id == cand.id, Assessment.status == AssessmentStatus.finished))
    responses = [r for a in rows for r in _responses(a)]
    theta = cand.theta if cand.theta is not None else 0.0
    prof = skill_estimates(responses, theta)
    cand.skill_profile = prof
    cand.verified_skills = {k: display_level(v["theta"]) for k, v in prof.items()}


def finish(db: Session, a: Assessment) -> None:
    est = _estimate(db, a)
    a.theta, a.theta_se = est.theta, est.se
    a.status = AssessmentStatus.finished
    a.finished_at = utcnow()
    cand = db.get(CandidateProfile, a.candidate_id)
    if a.kind == "skill":
        a.outcome = "skill_checked"
    else:
        verdict = cat.decide(est, a.claimed_grade)
        a.outcome = verdict.outcome
        a.result_grade = verdict.grade
        if verdict.grade:
            changed = (cand.grade != verdict.grade or cand.specialization != a.specialization
                       or not cand.grade_confirmed)
            cand.specialization = a.specialization
            cand.grade = verdict.grade
            cand.grade_confirmed = True
            cand.theta, cand.theta_se = est.theta, est.se
            if changed or cand.grade_assigned_at is None:
                cand.grade_assigned_at = utcnow()
                cand.category_at = utcnow()
        elif not (cand.grade and cand.grade_confirmed):
            # Подтверждённого грейда нет: кандидат не выпадает из оборота, а остаётся в выдаче
            # с заявленным грейдом и статусом «не подтверждён» (ниже подтверждённых в своей категории).
            # Кулдаун смены грейда не запускается: тест на уровень ниже доступен сразу.
            cand.specialization = a.specialization
            cand.grade = a.claimed_grade
            cand.grade_confirmed = False
            cand.theta, cand.theta_se = est.theta, est.se
            cand.grade_assigned_at = None
            cand.category_at = utcnow()
    db.flush()
    recompute_skill_profile(db, cand)
    cand.last_activity_at = utcnow()
    db.commit()


def summary(db: Session, a: Assessment) -> dict:
    est = _estimate(db, a)
    verdict = cat.decide(est, a.claimed_grade) if a.status == AssessmentStatus.finished and a.kind == "grade" else None
    skills = skill_estimates(_responses(a), est.theta)
    explanation = verdict.explanation if verdict else None
    if a.kind == "skill" and a.status == AssessmentStatus.finished:
        lvl = display_level(est.theta)
        explanation = (f"Навык «{SKILL_TITLES.get(a.skill, a.skill)}» проверен: уровень {lvl:.0%}. "
                       "Теперь он учитывается в подборе как подтверждённый, а не только заявленный.")
    return {
        "id": a.id,
        "kind": a.kind,
        "skill": a.skill,
        "specialization": a.specialization,
        "claimed_grade": a.claimed_grade,
        "status": a.status.value,
        "answered": len([i for i in a.items if i.answered_option is not None]),
        "max_items": cat.SKILL_MAX_ITEMS if a.kind == "skill" else cat.MAX_ITEMS,
        "theta": round(a.theta, 2),
        "theta_se": round(a.theta_se, 2),
        "outcome": a.outcome,
        "result_grade": a.result_grade,
        "suggested_grade": verdict.suggested_grade if verdict else None,
        "explanation": explanation,
        "skills": {k: display_level(v["theta"]) for k, v in skills.items()},
        "started_at": a.started_at,
        "finished_at": a.finished_at,
        "integrity": a.integrity or {},
    }
