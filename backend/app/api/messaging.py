"""Переписка по приглашению. Доступна обеим сторонам, пока приглашение не отозвано и не отклонено:
контакты при этом не раскрываются — это безопасный канал до принятия приглашения."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import MessageOut
from app.models.entities import Invitation, InvitationStatus, Message, utcnow

CLOSED = (InvitationStatus.declined, InvitationStatus.withdrawn, InvitationStatus.expired)


def list_messages(db: Session, inv: Invitation, reader: str) -> list[MessageOut]:
    rows = list(db.scalars(select(Message).where(Message.invitation_id == inv.id).order_by(Message.id)))
    changed = False
    for m in rows:
        if m.sender != reader and m.read_at is None:
            m.read_at = utcnow()
            changed = True
    if changed:
        db.commit()
    return [MessageOut.model_validate(m) for m in rows]


def post_message(db: Session, inv: Invitation, sender: str, text: str) -> MessageOut:
    if inv.status in CLOSED:
        raise HTTPException(409, "Переписка закрыта: приглашение отклонено, отозвано или истекло")
    m = Message(invitation_id=inv.id, sender=sender, text=text.strip())
    db.add(m)
    db.commit()
    return MessageOut.model_validate(m)
