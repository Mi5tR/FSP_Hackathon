"""Вход через ФСП ID (Keycloak, OpenID Connect, Authorization Code Flow).

Боевых доступов к Keycloak ФСП на хакатоне нет, поэтому по умолчанию работает MockFspIdProvider:
он повторяет протокол (state, одноразовый короткоживущий code, обмен code на claims), но экран
входа рисует наш фронтенд (/fsp-id/login), а «Keycloak» — это подписанный JWT-код.

Переключение на реальный ФСП ID — только переменные окружения, код вызова не меняется:
    FSP_OIDC_ISSUER=https://id.fsp-russia.com/realms/fsp
    FSP_OIDC_CLIENT_ID=fsp-career
    FSP_OIDC_CLIENT_SECRET=...

Схема потока: docs/06-fsp-integration.md.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import time
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

import httpx
import jwt

from app.core.config import settings


@dataclass
class FspIdClaims:
    sub: str            # ФСП ID участника — ключ привязки, подменить его кандидат не может
    email: str
    name: str
    consent: bool       # согласие на передачу профиля и достижений, данное на экране ФСП ID


class FspIdProvider(Protocol):
    mode: str

    def authorize_url(self, state: str, redirect_uri: str) -> str: ...

    def exchange_code(self, code: str, state: str) -> FspIdClaims: ...


class FspIdError(Exception):
    pass


# ------------------------------------------------------------------ имитация

MOCK_PASSWORD = "demo12345"
_used_codes: dict[str, float] = {}  # jti -> exp: код одноразовый, как в Keycloak


class MockFspIdProvider:
    mode = "mock"

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        return "/fsp-id/login?" + urlencode({"state": state, "redirect_uri": redirect_uri})

    def issue_code(self, login: str, password: str, state: str, redirect_uri: str, consent: bool) -> str:
        """Экран входа имитированного ФСП ID: логин — ФСП ID (FSP-123456) или email участника."""
        login = login.strip()
        if password != MOCK_PASSWORD:
            raise FspIdError("Неверный логин или пароль ФСП ID (в демо пароль demo12345)")
        if login.upper().startswith("FSP-") and login[4:].isdigit() and len(login) >= 8:
            sub, email = login.upper(), f"{login.lower()}@fsp-id.demo"
        elif "@" in login:
            digits = str(int(hashlib.sha256(login.lower().encode()).hexdigest(), 16) % 900000 + 100001)
            sub, email = f"FSP-{digits}", login.lower()
        else:
            raise FspIdError("Логин ФСП ID — email или идентификатор вида FSP-123456")
        now = int(time.time())
        payload = {"sub": sub, "email": email, "name": "Участник ФСП", "consent": consent, "state": state,
                   "redirect_uri": redirect_uri, "aud": "fsp-mock-code", "iat": now, "exp": now + 120,
                   "jti": secrets.token_urlsafe(12)}
        return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

    def exchange_code(self, code: str, state: str) -> FspIdClaims:
        try:
            p = jwt.decode(code, settings.jwt_secret, algorithms=["HS256"], audience="fsp-mock-code")
        except jwt.PyJWTError:
            raise FspIdError("Код авторизации недействителен или истёк")
        if p["state"] != state:
            raise FspIdError("state не совпадает: возможна CSRF-атака")
        now = time.time()
        for k in [k for k, exp in _used_codes.items() if exp < now]:
            _used_codes.pop(k, None)
        if p["jti"] in _used_codes:
            raise FspIdError("Код авторизации уже использован")
        _used_codes[p["jti"]] = p["exp"]
        return FspIdClaims(sub=p["sub"], email=p["email"], name=p["name"], consent=bool(p["consent"]))


# ------------------------------------------------------------------ реальный Keycloak (скелет)

class KeycloakOidcProvider:
    """Скелет интеграции с Keycloak ФСП ID: discovery, обмен кода, проверка id_token по JWKS."""
    mode = "keycloak"

    def __init__(self, issuer: str, client_id: str, client_secret: str, redirect_uri: str):
        self.issuer = issuer.rstrip("/")
        self.client_id, self.client_secret, self.redirect_uri = client_id, client_secret, redirect_uri
        self._conf: dict | None = None

    def _discovery(self) -> dict:
        if self._conf is None:
            r = httpx.get(f"{self.issuer}/.well-known/openid-configuration", timeout=5)
            r.raise_for_status()
            self._conf = r.json()
        return self._conf

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        q = {"client_id": self.client_id, "response_type": "code", "scope": "openid email profile",
             "redirect_uri": redirect_uri or self.redirect_uri, "state": state}
        return self._discovery()["authorization_endpoint"] + "?" + urlencode(q)

    def exchange_code(self, code: str, state: str) -> FspIdClaims:
        conf = self._discovery()
        r = httpx.post(conf["token_endpoint"], timeout=5, data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri,
            "client_id": self.client_id, "client_secret": self.client_secret})
        if r.status_code != 200:
            raise FspIdError("ФСП ID отклонил код авторизации")
        id_token = r.json()["id_token"]
        key = jwt.PyJWKClient(conf["jwks_uri"]).get_signing_key_from_jwt(id_token)
        p = jwt.decode(id_token, key.key, algorithms=["RS256"], audience=self.client_id, issuer=self.issuer)
        # Согласие на передачу данных даётся на consent-экране Keycloak (client scope «fsp-achievements»)
        return FspIdClaims(sub=p["sub"], email=p.get("email", ""), name=p.get("name", ""), consent=True)


def get_fsp_id_provider() -> FspIdProvider:
    issuer = os.getenv("FSP_OIDC_ISSUER")
    if issuer:
        return KeycloakOidcProvider(issuer, os.getenv("FSP_OIDC_CLIENT_ID", "fsp-career"),
                                    os.getenv("FSP_OIDC_CLIENT_SECRET", ""),
                                    f"{settings.frontend_url}/auth/fsp-callback")
    return MOCK


MOCK = MockFspIdProvider()
