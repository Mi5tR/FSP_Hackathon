"""Общие правила видимости данных для обеих ролей."""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import AchievementOut, CandidateCard, InvitationOut
from app.core.config import settings
from app.core.inn import inn_valid
from app.models.entities import (
    Application,
    Assessment,
    AssessmentStatus,
    CandidateProfile,
    HiringNeed,
    Invitation,
    InvitationStatus,
    Message,
    MicroTask,
    MicroTaskSubmission,
    utcnow,
)


# Статусы, при которых кандидат уже дал согласие на контакт (принял приглашение и дальше по воронке)
REVEALED_STATUSES = (InvitationStatus.accepted, InvitationStatus.offer, InvitationStatus.hired)


def contacts_revealed(db: Session, company_id: int, candidate_id: int) -> bool:
    """Контакты раскрываются только если кандидат принял приглашение этой компании
    или сам откликнулся на её вакансию (п. 2.2.2 ТЗ)."""
    accepted = db.scalar(select(Invitation.id).where(
        Invitation.company_id == company_id, Invitation.candidate_id == candidate_id,
        Invitation.status.in_(REVEALED_STATUSES), Invitation.contacts_revoked_at.is_(None)))
    if accepted:
        return True
    applied = db.scalar(select(Application.id).join(HiringNeed).where(
        HiringNeed.company_id == company_id, Application.candidate_id == candidate_id))
    return bool(applied)


def candidate_contacts(c: CandidateProfile) -> dict:
    return {"full_name": c.full_name, "email": c.contact_email, "phone": c.phone, "telegram": c.telegram}


def integrity_summary(db: Session, candidate_id: int) -> dict:
    """Сводка честности по последнему завершённому тесту на грейд: видна работодателю как сигнал, не как приговор."""
    a = db.scalar(select(Assessment).where(
        Assessment.candidate_id == candidate_id, Assessment.kind == "grade",
        Assessment.status == AssessmentStatus.finished).order_by(Assessment.finished_at.desc()))
    if not a:
        return {}
    i = a.integrity or {}
    focus, copies, fast = i.get("focus_lost", 0), i.get("copy_attempts", 0), i.get("fast_answers", 0)
    level = "ok" if focus + copies <= 1 and fast <= 2 else "warn" if focus + copies <= 5 else "bad"
    return {"focus_lost": focus, "copy_attempts": copies, "fast_answers": fast, "level": level}


def build_card(db: Session, c: CandidateProfile, company_id: int, seen_at=None) -> CandidateCard:
    revealed = contacts_revealed(db, company_id, c.id)
    p = c.privacy or {}
    show_fsp = p.get("show_fsp", True)
    return CandidateCard(
        id=c.id,
        display_name=c.full_name if revealed and c.full_name else f"Кандидат #{c.id}",
        specialization=c.specialization or "",
        grade=c.grade or "",
        grade_confirmed=c.grade_confirmed is not False,
        minor_age=c.age if c.age is not None and c.age < 18 else None,
        integrity=integrity_summary(db, c.id),
        theta=round(c.theta, 2) if c.theta is not None else None,
        verified_skills=c.verified_skills or {},
        declared_skills=c.declared_skills or [],
        experience_years=c.experience_years if p.get("show_experience", True) else None,
        city=c.city if p.get("show_city", True) else None,
        about=c.about if p.get("show_about", True) else None,
        work_format=c.work_format,
        has_fsp=bool(c.achievements) and show_fsp,
        fsp_rank=c.fsp_rank if show_fsp else None,
        is_new=bool(seen_at and c.category_at and c.category_at > seen_at),
        achievements=[AchievementOut.model_validate(a) for a in c.achievements] if show_fsp else [],
        last_activity_at=c.last_activity_at,
        contacts_revealed=revealed,
        contacts=candidate_contacts(c) if revealed else None,
    )


def expire_if_needed(inv: Invitation) -> None:
    if inv.status in (InvitationStatus.sent, InvitationStatus.viewed) and inv.expires_at < utcnow():
        inv.status = InvitationStatus.expired


def company_stats(db: Session, company_id: int) -> dict:
    """Репутация работодателя, видимая кандидату: защищает от «пустых» приглашений."""
    since = utcnow() - timedelta(days=90)
    rows = dict(db.execute(
        select(Invitation.status, func.count()).where(
            Invitation.company_id == company_id, Invitation.created_at >= since)
        .group_by(Invitation.status)).all())
    total = sum(rows.values())
    accepted = rows.get(InvitationStatus.accepted, 0)
    declined = rows.get(InvitationStatus.declined, 0)
    return {
        "invitations_90d": total,
        "accepted_90d": accepted,
        "acceptance_rate": round(accepted / total, 2) if total else None,
        "decline_rate": round(declined / total, 2) if total else None,
    }


def invitation_out(db: Session, inv: Invitation, for_employer: bool) -> InvitationOut:
    other = "candidate" if for_employer else "employer"
    total = db.scalar(select(func.count()).select_from(Message).where(Message.invitation_id == inv.id)) or 0
    unread = db.scalar(select(func.count()).select_from(Message).where(
        Message.invitation_id == inv.id, Message.sender == other, Message.read_at.is_(None))) or 0
    show_contacts = for_employer and inv.status in REVEALED_STATUSES and inv.contacts_revoked_at is None
    from app.models.entities import Complaint
    from app.services.trust import company_trust
    return InvitationOut(
        id=inv.id, company_id=inv.company_id, company_name=inv.company.name, candidate_id=inv.candidate_id,
        need_id=inv.need_id, position_title=inv.position_title, message=inv.message,
        salary_from=inv.salary_from, salary_to=inv.salary_to, contact_method=inv.contact_method,
        status=inv.status.value, decline_reason=inv.decline_reason,
        match=inv.match_snapshot or None, created_at=inv.created_at, viewed_at=inv.viewed_at,
        responded_at=inv.responded_at, expires_at=inv.expires_at,
        company_stats=None if for_employer else company_stats(db, inv.company_id),
        company_trust=None if for_employer else company_trust(db, inv.company),
        company_inn_valid=inn_valid(inv.company.inn),
        salary_flag=inv.salary_flag,
        below_expectation=bool(inv.candidate.salary_expectation and inv.salary_to < inv.candidate.salary_expectation),
        complained=bool(not for_employer and db.scalar(select(Complaint.id).where(Complaint.invitation_id == inv.id))),
        offer_at=inv.offer_at, hired_at=inv.hired_at,
        candidate_contacts=candidate_contacts(inv.candidate) if show_contacts else None,
        contacts_revoked_at=inv.contacts_revoked_at,
        unread=unread, messages_count=total,
    )


def invitation_ttl():
    return utcnow() + timedelta(days=settings.invitation_ttl_days)


def update_microtask_evidence(db: Session, candidate_id: int) -> None:
    """Оценки работодателей за регулярные задания становятся доказательством по навыкам задания."""
    agg: dict[str, list[int]] = {}
    rows = db.execute(select(MicroTaskSubmission, MicroTask).join(MicroTask, MicroTask.id == MicroTaskSubmission.task_id)
                      .where(MicroTaskSubmission.candidate_id == candidate_id,
                             MicroTaskSubmission.employer_rating.is_not(None)))
    for sub, task in rows:
        for skill in task.skills or []:
            agg.setdefault(skill, []).append(sub.employer_rating)
    cand = db.get(CandidateProfile, candidate_id)
    cand.microtask_evidence = {k: {"score": round(sum(v) / len(v) / 5, 3), "n": len(v)} for k, v in agg.items()}
    cand.last_activity_at = utcnow()


def normalize_answer(x: str) -> str:
    return " ".join(x.lower().replace("ё", "е").split()).strip(" .;")


def check_exact(answer: str, reference: str) -> bool:
    """Автопроверка по эталону: допускаются варианты через «|» (например «O(n log n)|n log n»)."""
    a = normalize_answer(answer)
    return any(a == normalize_answer(r) for r in reference.split("|") if r.strip())


def pdf_response(content: bytes, filename: str):
    from fastapi import Response
    return Response(content, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
