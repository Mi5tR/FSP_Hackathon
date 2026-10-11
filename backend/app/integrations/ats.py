"""Интеграция с ATS работодателя (Huntflow API v2).

Зачем: платформа должна встраиваться в существующий процесс найма, а не требовать
ручного дублирования. Синхронизация двусторонняя:

* платформа → ATS: когда контакты кандидата раскрыты (принято приглашение или отклик),
  кандидат создаётся в Huntflow и добавляется на вакансию; смена статуса (оффер, выход,
  отказ) передаётся этапом подбора;
* ATS → платформа: вебхук Huntflow о смене этапа («Оффер», «Вышел на работу», «Отказ»)
  обновляет статус приглашения, и кандидат видит актуальный статус у себя;
* вакансии из ATS импортируются как черновики потребностей (своих, а не чужих площадок).

В MVP работает MockHuntflowClient (детерминированные ID, без сети). HuntflowClient —
клиент для настоящего Huntflow по публичной документации https://api.huntflow.ru/v2/docs.
Персональные данные уходят в ATS только после раскрытия контактов — те же правила
видимости, что и в интерфейсе.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Protocol

import httpx

# Этапы Huntflow, которые мы сопоставляем статусам приглашения
STATUS_TO_STAGE = {"accepted": "Новые", "offer": "Оффер", "hired": "Вышел на работу", "declined": "Отказ"}
STAGE_TO_STATUS = {"offer": "offer", "оффер": "offer", "hired": "hired", "вышел на работу": "hired",
                   "trash": "declined", "отказ": "declined"}


class AtsClient(Protocol):
    def create_applicant(self, data: dict) -> str: ...
    def add_to_vacancy(self, applicant_id: str, vacancy_id: str | None, stage: str) -> None: ...
    def list_vacancies(self) -> list[dict]: ...


class MockHuntflowClient:
    """Имитация Huntflow: возвращает стабильные ID и пару вакансий для импорта."""

    def __init__(self, account_id: str):
        self.account_id = account_id

    def create_applicant(self, data: dict) -> str:
        return "hf-" + hashlib.sha1(f"{self.account_id}:{data.get('email')}".encode()).hexdigest()[:10]

    def add_to_vacancy(self, applicant_id: str, vacancy_id: str | None, stage: str) -> None:
        return None

    def list_vacancies(self) -> list[dict]:
        return [
            {"id": "hf-vac-101", "position": "Python-разработчик (Middle+)",
             "body": "Middle+ backend на Python, FastAPI, PostgreSQL, Kafka. Удалённо. 300 000 – 380 000 руб."},
            {"id": "hf-vac-102", "position": "Продуктовый аналитик",
             "body": "Продуктовый аналитик middle: SQL, продуктовые метрики, A/B-тесты, воронки. 200 000 – 260 000 руб."},
        ]


class HuntflowClient:
    BASE = "https://api.huntflow.ru/v2"

    def __init__(self, account_id: str, token: str):
        self.account_id = account_id
        self.headers = {"Authorization": f"Bearer {token}"}

    def _url(self, path: str) -> str:
        return f"{self.BASE}/accounts/{self.account_id}{path}"

    def create_applicant(self, data: dict) -> str:
        parts = (data.get("full_name") or "").split()
        body = {"last_name": parts[0] if parts else "", "first_name": parts[1] if len(parts) > 1 else "",
                "email": data.get("email"), "phone": data.get("phone"),
                "externals": [{"auth_type": "NATIVE", "data": {"body": data.get("summary", "")}}]}
        r = httpx.post(self._url("/applicants"), json=body, headers=self.headers, timeout=10)
        r.raise_for_status()
        return str(r.json()["id"])

    def add_to_vacancy(self, applicant_id: str, vacancy_id: str | None, stage: str) -> None:
        if not vacancy_id:
            return
        r = httpx.post(self._url(f"/applicants/{applicant_id}/vacancy"),
                       json={"vacancy": int(vacancy_id), "status": stage}, headers=self.headers, timeout=10)
        r.raise_for_status()

    def list_vacancies(self) -> list[dict]:
        r = httpx.get(self._url("/vacancies"), headers=self.headers, timeout=10)
        r.raise_for_status()
        return [{"id": str(v["id"]), "position": v["position"], "body": v.get("body") or ""} for v in r.json()["items"]]


def client_for(conn) -> AtsClient:
    if conn.mode == "live" and conn.token:
        return HuntflowClient(conn.account_id, conn.token)
    return MockHuntflowClient(conn.account_id)


def new_webhook_secret() -> str:
    return secrets.token_urlsafe(24)
