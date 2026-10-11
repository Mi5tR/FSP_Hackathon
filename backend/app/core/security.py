import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.models.entities import Role, User

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def new_token() -> str:
    return secrets.token_urlsafe(32)


def create_access_token(user: User) -> str:
    # Claims mirror Keycloak's access token layout (sub, email, realm_access.roles)
    # so swapping our issuer for FSP ID Keycloak only changes key verification.
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "realm_access": {"roles": [user.role.value]},
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_ttl_minutes),
        "iss": "fsp-talent",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется авторизация")
    try:
        payload = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Недействительный токен")
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Пользователь не найден")
    if not user.email_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Подтвердите email")
    return user


def require_role(role: Role):
    def dep(user: User = Depends(get_current_user)) -> User:
        if user.role != role:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав")
        return user

    return dep


require_candidate = require_role(Role.candidate)
require_employer = require_role(Role.employer)
