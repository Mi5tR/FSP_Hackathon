"""Защита от фиктивных вакансий и недобросовестных работодателей.

Верификация компании на этапе MVP не обязательна (п. 2.2.4 ТЗ), поэтому защита строится
не на «входном фильтре», а на поведении: каждое действие работодателя оставляет след,
который видит кандидат, и превышение порогов автоматически ограничивает компанию.

Сигналы доверия (каждый объясним кандидату):
* ИНН прошёл проверку контрольной суммы — добровольная метка;
* домен корпоративной почты совпадает с сайтом компании;
* возраст аккаунта: новые компании получают меньший лимит приглашений;
* доля принятых приглашений и доля ответов в переписке после принятия (нет «гостинга»);
* офферы и выходы на работу — компания реально нанимает;
* жалобы кандидатов: 3 жалобы от разных людей за 30 дней — приглашения приостанавливаются до проверки;
* вилка-приманка: зарплата заметно выше рынка категории помечается для кандидата.
"""

from __future__ import annotations

import statistics
from datetime import timedelta
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.inn import inn_valid
from app.models.entities import (
    CandidateProfile,
    Company,
    Complaint,
    Invitation,
    InvitationStatus,
    Message,
    utcnow,
)

DAILY_LIMIT = {"high": 60, "medium": 40, "new": 15, "low": 15, "review": 0}
COMPLAINTS_TO_REVIEW = 3
COMPLAINT_WINDOW_DAYS = 30
NEW_COMPANY_DAYS = 7
BAIT_FACTOR = 1.8   # вилка «до» выше медианных ожиданий категории в 1.8 раза и больше
COMPLAINT_REASONS = {
    "fake": "Вакансии нет: похоже на сбор резюме или данных",
    "payment": "Просят оплату, обучение за деньги или личные данные сверх нужного",
    "conditions": "Условия в переписке не совпадают с приглашением",
    "spam": "Массовая рассылка, не про мой профиль",
    "rude": "Некорректное общение",
    "other": "Другое",
}


def email_domain(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.rsplit("@", 1)[1].lower()


def site_domain(url: str | None) -> str | None:
    if not url:
        return None
    host = urlparse(url if "://" in url else f"https://{url}").hostname or ""
    return host.lower().removeprefix("www.") or None


def domain_match(co: Company) -> bool:
    site = site_domain(co.website)
    emails = {email_domain(co.contact_email), email_domain(co.user.email if co.user else None)} - {None}
    return bool(site) and any(d == site or d.endswith("." + site) for d in emails)


def market_median(db: Session, spec: str, grade: str) -> int | None:
    vals = [v for v in db.scalars(select(CandidateProfile.salary_expectation).where(
        CandidateProfile.specialization == spec, CandidateProfile.grade == grade,
        CandidateProfile.salary_expectation.is_not(None)))]
    return int(statistics.median(vals)) if len(vals) >= 5 else None


def salary_flag(db: Session, spec: str | None, grade: str | None, salary_to: int) -> str | None:
    if not spec or not grade:
        return None
    med = market_median(db, spec, grade)
    if med and salary_to >= med * BAIT_FACTOR:
        return "above_market"
    return None


def complaints_recent(db: Session, company_id: int) -> int:
    since = utcnow() - timedelta(days=COMPLAINT_WINDOW_DAYS)
    return db.scalar(select(func.count(func.distinct(Complaint.candidate_id))).where(
        Complaint.company_id == company_id, Complaint.created_at >= since)) or 0


def company_trust(db: Session, co: Company) -> dict:
    """Сводка доверия к работодателю: видна кандидату в приглашении и самому работодателю."""
    now = utcnow()
    since = now - timedelta(days=90)
    rows = dict(db.execute(select(Invitation.status, func.count()).where(
        Invitation.company_id == co.id, Invitation.created_at >= since).group_by(Invitation.status)).all())
    total = sum(rows.values())
    accepted_like = sum(rows.get(s, 0) for s in (InvitationStatus.accepted, InvitationStatus.offer, InvitationStatus.hired))
    offers = rows.get(InvitationStatus.offer, 0) + rows.get(InvitationStatus.hired, 0)
    hires = rows.get(InvitationStatus.hired, 0)
    # Ответил ли работодатель в переписке по принятым приглашениям (защита от «гостинга»)
    accepted_ids = list(db.scalars(select(Invitation.id).where(
        Invitation.company_id == co.id, Invitation.created_at >= since,
        Invitation.status.in_([InvitationStatus.accepted, InvitationStatus.offer, InvitationStatus.hired]))))
    replied = 0
    if accepted_ids:
        replied = db.scalar(select(func.count(func.distinct(Message.invitation_id))).where(
            Message.invitation_id.in_(accepted_ids), Message.sender == "employer")) or 0
    complaints = complaints_recent(db, co.id)
    age_days = (now - co.created_at).days if co.created_at else 999
    signals = []
    score = 50
    if inn_valid(co.inn):
        score += 15
        signals.append({"ok": True, "text": "ИНН прошёл проверку контрольной суммы"})
    else:
        signals.append({"ok": False, "text": "ИНН не указан или не прошёл проверку"})
    if domain_match(co):
        score += 10
        signals.append({"ok": True, "text": f"Почта на домене сайта ({site_domain(co.website)})"})
    if age_days < NEW_COMPANY_DAYS:
        score -= 10
        signals.append({"ok": False, "text": f"Новая компания на платформе ({age_days} дн.)"})
    acc_rate = accepted_like / total if total else None
    if acc_rate is not None and total >= 3:
        score += round((acc_rate - 0.3) * 30)
        signals.append({"ok": acc_rate >= 0.25, "text": f"Принято приглашений: {acc_rate:.0%} из {total} за 90 дней"})
    reply_rate = replied / len(accepted_ids) if accepted_ids else None
    if reply_rate is not None:
        score += round((reply_rate - 0.5) * 20)
        signals.append({"ok": reply_rate >= 0.5, "text": f"Отвечает после принятия приглашения: {reply_rate:.0%}"})
    if offers:
        score += min(10, offers * 3)
        signals.append({"ok": True, "text": f"Офферов: {offers}, выходов на работу: {hires}"})
    if complaints:
        score -= complaints * 15
        signals.append({"ok": False, "text": f"Жалоб кандидатов за 30 дней: {complaints}"})
    score = max(0, min(100, score))
    if co.moderation_status == "review":
        level = "review"
    elif age_days < NEW_COMPANY_DAYS:
        level = "new"
    else:
        level = "high" if score >= 75 else "medium" if score >= 45 else "low"
    return {
        "score": score, "level": level, "signals": signals,
        "daily_limit": DAILY_LIMIT[level], "complaints_30d": complaints,
        "invitations_90d": total, "acceptance_rate": round(acc_rate, 2) if acc_rate is not None else None,
        "reply_rate": round(reply_rate, 2) if reply_rate is not None else None,
        "offers_90d": offers, "hires_90d": hires,
        "moderation_status": co.moderation_status,
    }


def check_can_invite(db: Session, co: Company) -> tuple[int, int]:
    """Возвращает (отправлено за сутки, лимит). Лимит зависит от уровня доверия:
    приглашение «дорогое», поэтому работодатель выбирает адресно, а не рассылает всем."""
    trust = company_trust(db, co)
    since = utcnow() - timedelta(days=1)
    sent = db.scalar(select(func.count()).select_from(Invitation).where(
        Invitation.company_id == co.id, Invitation.created_at >= since)) or 0
    return sent, trust["daily_limit"]


def register_complaint(db: Session, inv: Invitation, reason: str, text: str) -> dict:
    exists = db.scalar(select(Complaint).where(Complaint.invitation_id == inv.id, Complaint.candidate_id == inv.candidate_id))
    if not exists:
        db.add(Complaint(invitation_id=inv.id, company_id=inv.company_id, candidate_id=inv.candidate_id,
                         reason=reason, text=text))
        db.flush()
    n = complaints_recent(db, inv.company_id)
    co = db.get(Company, inv.company_id)
    paused = False
    if n >= COMPLAINTS_TO_REVIEW and co.moderation_status != "review":
        co.moderation_status = "review"
        paused = True
    return {"complaints_30d": n, "company_paused": paused or co.moderation_status == "review"}
