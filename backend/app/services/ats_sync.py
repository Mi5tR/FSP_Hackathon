"""Синхронизация событий платформы с ATS работодателя (см. app/integrations/ats.py)."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.ats import STAGE_TO_STATUS, STATUS_TO_STAGE, client_for
from app.models.entities import AtsConnection, AtsEvent, HiringNeed, Invitation, InvitationStatus, utcnow

log = logging.getLogger(__name__)


def connection(db: Session, company_id: int) -> AtsConnection | None:
    return db.scalar(select(AtsConnection).where(AtsConnection.company_id == company_id))


def _event(db: Session, company_id: int, direction: str, event: str, payload: dict, status: str = "ok") -> None:
    db.add(AtsEvent(company_id=company_id, direction=direction, event=event, payload=payload, status=status))


def push_candidate(db: Session, company_id: int, candidate, need: HiringNeed | None, source: str) -> None:
    """Контакты раскрыты (принято приглашение или отклик) — кандидат уходит в ATS."""
    conn = connection(db, company_id)
    if not conn:
        return
    data = {"full_name": candidate.full_name, "email": candidate.contact_email, "phone": candidate.phone,
            "summary": f"ФСП Карьера: {candidate.specialization} / {candidate.grade}; источник — {source}"}
    try:
        client = client_for(conn)
        applicant_id = client.create_applicant(data)
        client.add_to_vacancy(applicant_id, need.ats_external_id if need else None, STATUS_TO_STAGE["accepted"])
        _event(db, company_id, "out", "applicant.created",
               {"applicant_id": applicant_id, "candidate_id": candidate.id, "source": source,
                "vacancy": need.ats_external_id if need else None})
    except Exception as e:  # ATS недоступна — основной сценарий не ломается, событие видно в журнале
        log.warning("ATS push failed: %s", e)
        _event(db, company_id, "out", "applicant.created", {"candidate_id": candidate.id, "error": str(e)}, "error")


def push_status(db: Session, inv: Invitation) -> None:
    conn = connection(db, inv.company_id)
    if not conn:
        return
    _event(db, inv.company_id, "out", "applicant.stage",
           {"candidate_id": inv.candidate_id, "invitation_id": inv.id,
            "stage": STATUS_TO_STAGE.get(inv.status.value, inv.status.value)})


def handle_webhook(db: Session, conn: AtsConnection, payload: dict) -> dict:
    """Вебхук ATS: {"invitation_id": 12, "stage": "Оффер"} → статус приглашения.
    Переходы только вперёд по воронке: accepted → offer → hired, отказ — из любого активного."""
    stage = str(payload.get("stage", "")).strip().lower()
    status = STAGE_TO_STATUS.get(stage)
    inv = db.get(Invitation, int(payload.get("invitation_id") or 0))
    if not status or not inv or inv.company_id != conn.company_id:
        _event(db, conn.company_id, "in", "stage.ignored", payload, "ignored")
        return {"applied": False}
    allowed = {"offer": {InvitationStatus.accepted}, "hired": {InvitationStatus.accepted, InvitationStatus.offer},
               "declined": {InvitationStatus.accepted, InvitationStatus.offer}}
    if inv.status not in allowed[status]:
        _event(db, conn.company_id, "in", "stage.ignored", {**payload, "reason": f"статус {inv.status.value}"}, "ignored")
        return {"applied": False}
    inv.status = InvitationStatus(status)
    if status == "offer":
        inv.offer_at = utcnow()
    elif status == "hired":
        inv.hired_at = utcnow()
    _event(db, conn.company_id, "in", "stage.applied", {**payload, "status": status})
    return {"applied": True, "status": status}


def import_vacancies(db: Session, conn: AtsConnection) -> list[HiringNeed]:
    """Вакансии работодателя из его ATS становятся черновиками потребностей (не публикуются автоматически)."""
    from app.services.matching.text_parser import parse_need

    created = []
    for v in client_for(conn).list_vacancies():
        if db.scalar(select(HiringNeed).where(HiringNeed.company_id == conn.company_id,
                                              HiringNeed.ats_external_id == v["id"])):
            continue
        p = parse_need(f"{v['position']}. {v['body']}")
        n = HiringNeed(company_id=conn.company_id, title=v["position"], description=v["body"],
                       specialization=p["specialization"] or "backend", grade=p["grade"] or "middle",
                       skills=p["skills"],
                       requirements=[{k: r[k] for k in ("skill", "importance", "level")} for r in p["requirements"]],
                       work_format=p["work_format"], salary_from=p["salary_from"] or 100_000,
                       salary_to=p["salary_to"] or p["salary_from"] or 150_000, is_published=False,
                       ats_external_id=v["id"])
        db.add(n)
        created.append(n)
    _event(db, conn.company_id, "in", "vacancies.imported", {"count": len(created)})
    return created
