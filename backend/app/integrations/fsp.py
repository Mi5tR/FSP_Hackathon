"""Интеграция с реестром ФСП.

Контракт, который мы предлагаем ФСП (реального API на хакатоне нет):

    GET /participants/{fsp_id}                -> профиль участника (ФИО, регион)
    GET /participants/{fsp_id}/achievements   -> список результатов соревнований

В проде fsp_id приходит как `sub` из токена ФСП ID (Keycloak, OIDC), поэтому
кандидат не может привязать чужой ID. В MVP используется MockFspClient
с синтетическим реестром; HttpFspClient — заготовка под реальный API.
"""

from __future__ import annotations

import hashlib
import os
import random
from dataclasses import asdict, dataclass, field
from typing import Protocol

import httpx


@dataclass
class FspAchievementDTO:
    event_name: str
    discipline: str
    level: str
    event_date: str
    place: int | None
    participants: int | None
    role_in_team: str | None
    skills: list[str] = field(default_factory=list)
    source_url: str | None = None


@dataclass
class FspParticipantDTO:
    fsp_id: str
    full_name: str
    region: str
    achievements: list[FspAchievementDTO]
    sport_rank: str | None = None  # спортивный разряд по спортивному программированию

    def to_dict(self) -> dict:
        return asdict(self)


class FspRegistryClient(Protocol):
    def get_participant(self, fsp_id: str) -> FspParticipantDTO | None: ...


_EVENTS = [
    ("Чемпионат России по спортивному программированию", "продуктовое программирование", "federal", ["python", "react", "system_design"]),
    ("Кубок России по спортивному программированию", "алгоритмическое программирование", "federal", ["algorithms"]),
    ("Всероссийский хакатон «Лидеры цифровой трансформации»", "продуктовое программирование", "federal", ["python", "ml", "http"]),
    ("Региональные соревнования по программированию", "алгоритмическое программирование", "regional", ["algorithms"]),
    ("Чемпионат по программированию систем ИИ", "программирование систем ИИ", "federal", ["ml", "python", "statistics"]),
    ("Соревнования по информационной безопасности (CTF)", "информационная безопасность", "regional", ["linux", "networking"]),
    ("Международная олимпиада ICPC (региональный этап)", "алгоритмическое программирование", "international", ["algorithms"]),
    ("Чемпионат России по программированию робототехники", "программирование робототехники", "federal", ["python", "algorithms"]),
    ("Кубок по программированию беспилотных авиационных систем", "программирование БАС", "federal", ["python", "concurrency"]),
    ("Хакатон по мобильной разработке", "продуктовое программирование", "regional", ["kotlin", "android", "swift"]),
    ("Чемпионат по продуктовой аналитике и данным", "продуктовое программирование", "regional", ["sql", "product_metrics"]),
]
_RANKS = [None, None, "3 разряд", "2 разряд", "1 разряд", "КМС", "МС"]
_ROLES = ["капитан", "backend", "frontend", "ML", "аналитик", None]


class MockFspClient:
    """Детерминированный синтетический реестр: одинаковый fsp_id всегда даёт
    одинаковые данные. ID, оканчивающиеся на '0', — участники без истории
    (проверка обязательного сценария «нет истории ФСП»)."""

    def get_participant(self, fsp_id: str) -> FspParticipantDTO | None:
        if not fsp_id.upper().startswith("FSP-") or len(fsp_id) < 6:
            return None
        rng = random.Random(int(hashlib.sha256(fsp_id.encode()).hexdigest(), 16) % 2**32)
        if fsp_id.endswith("0"):
            return FspParticipantDTO(fsp_id, "Участник ФСП", "Москва", [], None)
        ach = []
        for _ in range(rng.randint(1, 4)):
            name, disc, level, skills = rng.choice(_EVENTS)
            participants = rng.choice([40, 80, 150, 300, 600])
            place = rng.choice([1, 2, 3, 5, 8, 12, 25, None])
            year = rng.choice([2023, 2024, 2025, 2026])
            ach.append(FspAchievementDTO(
                event_name=f"{name} {year}", discipline=disc, level=level,
                event_date=f"{year}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                place=place, participants=participants, role_in_team=rng.choice(_ROLES),
                skills=skills, source_url=f"https://fsp-russia.com/results/{rng.randint(1000, 9999)}",
            ))
        best = min((a.place for a in ach if a.place), default=None)
        rank = _RANKS[min(len(_RANKS) - 1, len(ach) + (2 if best == 1 else 1 if best and best <= 3 else 0))]
        return FspParticipantDTO(fsp_id, "Участник ФСП", rng.choice(["Москва", "Казань", "Новосибирск", "Екатеринбург"]),
                                 ach, rank)


class HttpFspClient:
    def __init__(self, base_url: str, token: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}

    def get_participant(self, fsp_id: str) -> FspParticipantDTO | None:
        with httpx.Client(timeout=5) as client:
            r = client.get(f"{self.base_url}/participants/{fsp_id}", headers=self.headers)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            p = r.json()
            a = client.get(f"{self.base_url}/participants/{fsp_id}/achievements", headers=self.headers)
            a.raise_for_status()
            return FspParticipantDTO(fsp_id, p.get("full_name", ""), p.get("region", ""),
                                     [FspAchievementDTO(**x) for x in a.json()], p.get("sport_rank"))


def get_fsp_client() -> FspRegistryClient:
    url = os.getenv("FSP_API_URL")
    return HttpFspClient(url, os.getenv("FSP_API_TOKEN")) if url else MockFspClient()
