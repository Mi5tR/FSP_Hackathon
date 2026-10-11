import logging
import smtplib
from email.message import EmailMessage

import secrets

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    DemoLoginIn,
    ErrorOut,
    FspIdAuthorizeIn,
    FspIdCallbackIn,
    LoginIn,
    MeOut,
    RegisterIn,
    RegisterOut,
    TokenOut,
    VerifyIn,
)
from app.core.config import settings
from app.core.db import get_db
from app.core.security import create_access_token, get_current_user, hash_password, new_token, verify_password
from app.integrations.fsp import get_fsp_client
from app.integrations.fsp_id import MOCK, FspIdError, get_fsp_id_provider
from app.models.entities import CandidateProfile, Company, FspAchievement, Role, User, utcnow

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger("fsp.auth")


def _send_verification(email: str, token: str) -> None:
    link = f"{settings.frontend_url}/verify?token={token}"
    if not settings.smtp_host:
        log.warning("Ссылка подтверждения для %s: %s", email, link)
        return
    msg = EmailMessage()
    msg["Subject"] = "Подтверждение email — ФСП Карьера"
    msg["From"] = "no-reply@fsp-talent.local"
    msg["To"] = email
    msg.set_content(f"Подтвердите адрес: {link}")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as s:
        s.send_message(msg)


@router.post("/register", response_model=RegisterOut, status_code=201, responses={409: {"model": ErrorOut}, 422: {"model": ErrorOut}})
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if not body.consent_processing:
        raise HTTPException(422, "Нужно согласие на обработку персональных данных")
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "Пользователь с таким email уже существует")
    token = new_token()
    user = User(email=body.email.lower(), password_hash=hash_password(body.password),
                role=Role(body.role), verify_token=token)
    db.add(user)
    db.flush()
    if user.role == Role.candidate:
        db.add(CandidateProfile(user_id=user.id, contact_email=user.email, consent_processing_at=utcnow()))
    else:
        db.add(Company(user_id=user.id, contact_email=user.email))
    db.commit()
    _send_verification(user.email, token)
    return RegisterOut(id=user.id, email=user.email, message="Письмо с подтверждением отправлено",
                       dev_verify_token=token if settings.dev_mode else None)


@router.post("/verify-email", response_model=TokenOut, responses={404: {"model": ErrorOut}})
def verify_email(body: VerifyIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.verify_token == body.token))
    if not user:
        raise HTTPException(404, "Ссылка недействительна")
    user.email_verified = True
    user.verify_token = None
    db.commit()
    return TokenOut(access_token=create_access_token(user), role=user.role.value)


@router.post("/login", response_model=TokenOut, responses={401: {"model": ErrorOut}, 403: {"model": ErrorOut}})
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Неверный email или пароль")
    if not user.email_verified:
        raise HTTPException(403, "Подтвердите email")
    return TokenOut(access_token=create_access_token(user), role=user.role.value)


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    return MeOut(id=user.id, email=user.email, role=user.role.value, email_verified=user.email_verified)


# ------------------------------------------------------------------ быстрый вход для проверки
@router.post("/demo", response_model=TokenOut, responses={404: {"model": ErrorOut}})
def demo_login(body: DemoLoginIn, db: Session = Depends(get_db)):
    """Только в DEV_MODE: создаёт новый чистый аккаунт, чтобы жюри прошло путь само, без регистрации и почты."""
    if not settings.dev_mode:
        raise HTTPException(404, "Демо-вход выключен")
    tag = secrets.token_hex(3)
    user = User(email=f"jury-{body.role}-{tag}@demo.ru", password_hash=hash_password(secrets.token_urlsafe(16)),
                role=Role(body.role), email_verified=True)
    db.add(user)
    db.flush()
    if user.role == Role.candidate:
        db.add(CandidateProfile(user_id=user.id, full_name=f"Эксперт {tag.upper()}", contact_email=user.email,
                                consent_processing_at=utcnow()))
    else:
        db.add(Company(user_id=user.id, name=f"Компания эксперта {tag.upper()}", industry="ИТ",
                       contact_email=user.email))
    db.commit()
    return TokenOut(access_token=create_access_token(user), role=user.role.value)


# ------------------------------------------------------------------ ФСП ID (OIDC)
_optional_bearer = HTTPBearer(auto_error=False)


def _optional_user(creds: HTTPAuthorizationCredentials | None, db: Session) -> User | None:
    if creds is None:
        return None
    try:
        payload = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return db.get(User, int(payload["sub"]))


@router.get("/fsp-id/config")
def fsp_id_config(state: str, redirect_uri: str):
    """Куда отправить пользователя для входа: имитация ФСП ID (mock) или реальный Keycloak."""
    p = get_fsp_id_provider()
    return {"mode": p.mode, "authorize_url": p.authorize_url(state, redirect_uri)}


@router.post("/fsp-id/mock-authorize", responses={401: {"model": ErrorOut}})
def fsp_id_mock_authorize(body: FspIdAuthorizeIn):
    """Экран входа имитированного ФСП ID. Возвращает одноразовый code, как Keycloak в redirect_uri."""
    try:
        code = MOCK.issue_code(body.login, body.password, body.state, body.redirect_uri, consent=True)
    except FspIdError as e:
        raise HTTPException(401, str(e))
    return {"code": code, "state": body.state, "redirect_uri": body.redirect_uri}


def _import_achievements(c: CandidateProfile, fsp_id: str) -> None:
    participant = get_fsp_client().get_participant(fsp_id)
    c.fsp_id = fsp_id
    c.fsp_linked_at = utcnow()
    c.fsp_rank = participant.sport_rank
    c.achievements.clear()
    for a in participant.achievements if participant else []:
        c.achievements.append(FspAchievement(**a.__dict__))


@router.post("/fsp-id/callback", response_model=TokenOut, responses={400: {"model": ErrorOut}, 409: {"model": ErrorOut}})
def fsp_id_callback(body: FspIdCallbackIn, db: Session = Depends(get_db),
                    creds: HTTPAuthorizationCredentials | None = Depends(_optional_bearer)):
    """Обмен code на профиль ФСП ID.
    * Пользователь уже вошёл как кандидат — ФСП ID привязывается к его профилю (sub из токена, подменить нельзя).
    * Иначе — вход: по привязанному ФСП ID, по email или создание нового кандидата.
    В обоих случаях достижения подтягиваются из реестра ФСП."""
    try:
        claims = get_fsp_id_provider().exchange_code(body.code, body.state)
    except FspIdError as e:
        raise HTTPException(400, str(e))
    owner = db.scalar(select(CandidateProfile).where(CandidateProfile.fsp_id == claims.sub))
    current = _optional_user(creds, db)

    if current is not None:
        if current.role != Role.candidate:
            raise HTTPException(409, "ФСП ID привязывается только к профилю соискателя")
        if owner and owner.user_id != current.id:
            raise HTTPException(409, "Этот ФСП ID уже привязан к другому профилю")
        _import_achievements(current.candidate, claims.sub)
        db.commit()
        return TokenOut(access_token=create_access_token(current), role=current.role.value)

    if owner:
        user = owner.user
    else:
        user = db.scalar(select(User).where(User.email == claims.email.lower()))
        if user and user.role != Role.candidate:
            raise HTTPException(409, "Этот email зарегистрирован как работодатель")
        if user is None:
            if not claims.consent:
                raise HTTPException(400, "Нужно согласие на передачу данных из ФСП ID")
            user = User(email=claims.email.lower(), password_hash=hash_password(secrets.token_urlsafe(16)),
                        role=Role.candidate, email_verified=True)
            db.add(user)
            db.flush()
            # Согласие на обработку ПДн (152-ФЗ) дано на экране ФСП ID при передаче профиля
            db.add(CandidateProfile(user_id=user.id, full_name=claims.name, contact_email=user.email,
                                    consent_processing_at=utcnow()))
            db.flush()
            db.refresh(user)
        user.email_verified = True  # email подтверждён на стороне ФСП ID
        _import_achievements(user.candidate, claims.sub)
    db.commit()
    return TokenOut(access_token=create_access_token(user), role=user.role.value)
