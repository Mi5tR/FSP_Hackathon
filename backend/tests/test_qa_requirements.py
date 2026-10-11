"""Требования из сессии вопросов и ответов с постановщиками (qa-summary-fsp-2026.md):
неподтверждённый грейд не прячется, все соревнования ФСП равнозначны, вход через ФСП ID,
переписка, отзыв контактов, автопроверка заданий, несовершеннолетние, метка доверия, честность теста."""

import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ["DEV_MODE"] = "1"

from types import SimpleNamespace  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.core.inn import inn_valid  # noqa: E402
from app.main import app  # noqa: E402
from app.services.matching.ranking import fsp_strength  # noqa: E402
from tests.test_e2e import _pass_test, _signup  # noqa: E402


def _employer(client, email):
    h = _signup(client, email, "employer")
    client.put("/api/employer/company", json={"name": "Тест Компания", "inn": "7725123450"}, headers=h)
    return h


def _candidate(client, email, strong):
    h = _signup(client, email, "candidate")
    client.put("/api/candidate/profile", json={"full_name": "Тест Кандидат", "phone": "+7900"}, headers=h)
    client.post("/api/candidate/survey", json={"industry": "development", "specialization": "backend",
                                               "claimed_grade": "senior"}, headers=h)
    res = _pass_test(client, h, strong=strong)
    client.put("/api/candidate/privacy", json={"consent_publication": True}, headers=h)
    return h, res


def test_unconfirmed_grade_stays_visible_but_lower():
    with TestClient(app) as client:
        weak_h, res = _candidate(client, "weak@qa.ru", strong=False)
        assert res["outcome"] == "not_confirmed"
        prof = client.get("/api/candidate/profile", headers=weak_h).json()
        assert prof["grade"] == "senior" and prof["grade_confirmed"] is False and prof["is_visible"]
        # Кулдаун не сжигается: тест на уровень ниже доступен сразу
        assert client.post("/api/candidate/assessments", json={"claimed_grade": "middle"}, headers=weak_h).status_code == 201

        _candidate(client, "strong@qa.ru", strong=True)
        eh = _employer(client, "hr@qa.ru")
        r = client.get("/api/employer/candidates", params={"specialization": "backend", "grade": "senior"}, headers=eh)
        items = r.json()["items"]
        flags = {i["candidate"]["id"]: i["candidate"]["grade_confirmed"] for i in items}
        assert False in flags.values(), "неподтверждённый кандидат должен остаться в выдаче"
        senior = [i for i in items if i["candidate"]["grade"] == "senior"]
        confirmed_first = [i["candidate"]["grade_confirmed"] for i in senior]
        assert confirmed_first == sorted(confirmed_first, reverse=True), "подтверждённые выше неподтверждённых"


def _ach(level, place, date="2026-01-10"):
    return SimpleNamespace(level=level, place=place, event_date=date, skills=[], event_name="Соревнование")


def test_fsp_levels_are_equal_and_participation_capped():
    regional = fsp_strength(SimpleNamespace(achievements=[_ach("regional", 1)]))[0]
    federal = fsp_strength(SimpleNamespace(achievements=[_ach("international", 1)]))[0]
    assert regional == federal, "уровень мероприятия не должен влиять"
    many_online = fsp_strength(SimpleNamespace(achievements=[_ach("regional", None) for _ in range(20)]))[0]
    one_win = fsp_strength(SimpleNamespace(achievements=[_ach("regional", 1)]))[0]
    assert many_online < one_win, "набить профиль одними участиями нельзя"
    old = fsp_strength(SimpleNamespace(achievements=[_ach("regional", 1, "2020-01-01")]))[0]
    assert old < one_win, "свежий результат весит больше"


def test_fsp_id_login_and_link():
    with TestClient(app) as client:
        cfg = client.get("/api/auth/fsp-id/config", params={"state": "s" * 16, "redirect_uri": "/auth/fsp-callback"}).json()
        assert cfg["mode"] == "mock"
        bad = client.post("/api/auth/fsp-id/mock-authorize", json={"login": "FSP-555123", "password": "x",
                                                                    "state": "s" * 16, "redirect_uri": "/cb"})
        assert bad.status_code == 401
        code = client.post("/api/auth/fsp-id/mock-authorize", json={"login": "FSP-555123", "password": "demo12345",
                                                                     "state": "s" * 16, "redirect_uri": "/cb"}).json()["code"]
        assert client.post("/api/auth/fsp-id/callback", json={"code": code, "state": "другой" * 3}).status_code == 400
        tok = client.post("/api/auth/fsp-id/callback", json={"code": code, "state": "s" * 16})
        assert tok.status_code == 200 and tok.json()["role"] == "candidate"
        # Код одноразовый
        assert client.post("/api/auth/fsp-id/callback", json={"code": code, "state": "s" * 16}).status_code == 400
        h = {"Authorization": f"Bearer {tok.json()['access_token']}"}
        prof = client.get("/api/candidate/profile", headers=h).json()
        assert prof["fsp_id"] == "FSP-555123" and prof["achievements"]


def test_chat_revoke_contacts_and_exact_task():
    with TestClient(app) as client:
        ch, _ = _candidate(client, "chat@qa.ru", strong=True)
        cid = client.get("/api/candidate/profile", headers=ch).json()["id"]
        eh = _employer(client, "chat-hr@qa.ru")
        inv = client.post("/api/employer/invitations", json={
            "candidate_id": cid, "position_title": "Backend", "message": "Приглашаем на собеседование", "salary_from": 300000,
            "salary_to": 400000, "contact_method": "telegram @hr"}, headers=eh).json()
        assert client.post(f"/api/employer/invitations/{inv['id']}/messages", json={"text": "Вопрос?"}, headers=eh).status_code == 201
        assert client.get("/api/candidate/invitations", headers=ch).json()[0]["unread"] == 1
        msgs = client.get(f"/api/candidate/invitations/{inv['id']}/messages", headers=ch).json()
        assert msgs[0]["text"] == "Вопрос?"
        client.post(f"/api/candidate/invitations/{inv['id']}/accept", json={}, headers=ch)
        assert client.get("/api/employer/invitations", headers=eh).json()[0]["candidate_contacts"]
        client.post(f"/api/candidate/invitations/{inv['id']}/revoke-contacts", json={}, headers=ch)
        assert client.get("/api/employer/invitations", headers=eh).json()[0]["candidate_contacts"] is None
        card = client.get(f"/api/employer/candidates/{cid}", headers=eh).json()["candidate"]
        assert card["contacts"] is None and card["display_name"].startswith("Кандидат #")

        # Задание с эталоном проверяет система
        prof = client.get("/api/candidate/profile", headers=ch).json()
        t = client.post("/api/employer/micro-tasks", json={
            "specialization": "backend", "grade": prof["grade"], "skills": ["algorithms"], "title": "Сложность",
            "body": "Сложность сортировки слиянием в худшем случае?", "answer_type": "exact",
            "reference_answer": "O(n log n)|n log n"}, headers=eh).json()
        r = client.post(f"/api/candidate/micro-tasks/{t['id']}/answer", json={"answer": " o(N log N) "}, headers=ch)
        assert r.json()["result"] == "correct"
        sub = client.get(f"/api/employer/micro-tasks/{t['id']}/submissions", headers=eh).json()[0]
        assert sub["auto_checked"] and sub["employer_rating"] == 5


def test_minor_needs_guardian_consent_and_inn_badge():
    with TestClient(app) as client:
        h, _ = _candidate(client, "teen@qa.ru", strong=True)
        client.put("/api/candidate/profile", json={"birth_date": "2010-01-01"}, headers=h)
        r = client.put("/api/candidate/privacy", json={"consent_publication": True}, headers=h)
        assert r.status_code == 422
        assert client.get("/api/candidate/profile", headers=h).json()["is_visible"] is False
        client.put("/api/candidate/profile", json={"guardian_name": "Мама", "guardian_contact": "+7",
                                                   "guardian_consent": True}, headers=h)
        assert client.put("/api/candidate/privacy", json={"consent_publication": True}, headers=h).status_code == 200
        assert client.get("/api/candidate/profile", headers=h).json()["is_visible"] is True
    assert inn_valid("7725123450") and not inn_valid("7725123451")


def test_integrity_signals_and_demo_login():
    with TestClient(app) as client:
        tok = client.post("/api/auth/demo", json={"role": "candidate"}).json()
        h = {"Authorization": f"Bearer {tok['access_token']}"}
        client.post("/api/candidate/survey", json={"industry": "development", "specialization": "qa",
                                                   "claimed_grade": "junior"}, headers=h)
        step = client.post("/api/candidate/assessments", json={}, headers=h).json()
        r = client.post(f"/api/candidate/assessments/{step['assessment']['id']}/answer",
                        json={"item_id": step["item"]["item_id"], "option": 0, "focus_lost": 2, "copy_attempts": 1},
                        headers=h).json()
        assert r["assessment"]["integrity"]["focus_lost"] == 2
        hint = client.get("/api/candidate/grade-hint", headers=h).json()
        assert hint["grade"] in ("intern", "junior", "middle", "senior") and hint["note"]


def test_standardized_pdf_profile():
    with TestClient(app) as client:
        h, _ = _candidate(client, "pdf@qa.ru", strong=True)
        r = client.get("/api/candidate/profile/pdf", headers=h)
        assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content[:4] == b"%PDF"
        cid = client.get("/api/candidate/profile", headers=h).json()["id"]
        eh = _employer(client, "pdf-hr@qa.ru")
        r = client.get(f"/api/employer/candidates/{cid}/pdf", headers=eh)
        assert r.status_code == 200 and r.content[:4] == b"%PDF"
