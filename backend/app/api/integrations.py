"""Входящие вебхуки внешних систем (ATS работодателя)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.entities import AtsConnection
from app.services.ats_sync import handle_webhook

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.post("/huntflow/webhook/{secret}")
def huntflow_webhook(secret: str, payload: dict, db: Session = Depends(get_db)):
    """Смена этапа кандидата в Huntflow → статус приглашения на платформе.

    Пример тела: `{"invitation_id": 12, "stage": "Оффер"}`. Секрет в пути выдаётся при подключении
    ATS и идентифицирует компанию; чужие приглашения обновить нельзя.
    """
    conn = db.scalar(select(AtsConnection).where(AtsConnection.webhook_secret == secret))
    if not conn:
        raise HTTPException(404, "Неизвестный вебхук")
    res = handle_webhook(db, conn, payload)
    db.commit()
    return res
