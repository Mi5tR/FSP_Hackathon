"""Сквозной сценарий из п. 3.3 ТЗ: регистрация → опрос → тест → категория →
поиск работодателем → приглашение → принятие → раскрытие контактов."""

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["DEV_MODE"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.entities import AssessmentItem  # noqa: E402


def _signup(client, email, role):
    r = client.post("/api/auth/register", json={"email": email, "password": "password123", "role": role,
                                                "consent_processing": True})
    assert r.status_code == 201, r.text
    r = client.post("/api/auth/verify-email", json={"token": r.json()["dev_verify_token"]})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _pass_test(client, h, strong=True):
    r = client.post("/api/candidate/assessments", json={}, headers=h)
    assert r.status_code == 201, r.text
    step = r.json()
    db = SessionLocal()
    while step["item"]:
        item = db.get(AssessmentItem, step["item"]["item_id"])
        db.refresh(item)
        option = item.correct_option if strong else (item.correct_option + 1) % 4
        r = client.post(f"/api/candidate/assessments/{step['assessment']['id']}/answer",
                        json={"item_id": item.id, "option": option}, headers=h)
        assert r.status_code == 200, r.text
        step = r.json()
    db.close()
    return step["assessment"]


def test_full_reverse_hiring_flow():
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        ch = _signup(client, "cand@example.com", "candidate")
        client.put("/api/candidate/profile", json={"full_name": "Иван Петров", "phone": "+79990001122",
                                                    "declared_skills": ["python", "sql", "docker"],
                                                    "salary_expectation": 250000}, headers=ch)
        r = client.post("/api/candidate/survey", json={"industry": "development", "specialization": "backend",
                                                       "claimed_grade": "middle"}, headers=ch)
        assert r.status_code == 201
        result = _pass_test(client, ch, strong=True)
        assert result["status"] == "finished"
        assert result["outcome"] in ("confirmed", "upgrade_eligible")
        assert result["result_grade"] == "middle"

        # Кулдаун: сразу сменить грейд нельзя
        r = client.post("/api/candidate/assessments", json={"claimed_grade": "senior"}, headers=ch)
        assert r.status_code == 429

        # Пока нет согласия на публикацию, работодатель кандидата не видит
        eh = _signup(client, "hr@example.com", "employer")
        client.put("/api/employer/company", json={"name": "ТехКомпания", "industry": "fintech"}, headers=eh)
        r = client.post("/api/employer/needs", json={"title": "Backend Python", "specialization": "backend",
                                                     "grade": "middle", "skills": ["python", "sql"],
                                                     "salary_from": 200000, "salary_to": 300000}, headers=eh)
        need_id = r.json()["id"]
        assert client.get(f"/api/employer/needs/{need_id}/matches", headers=eh).json()["total"] == 0

        client.put("/api/candidate/privacy", json={"consent_publication": True}, headers=ch)
        r = client.post("/api/candidate/fsp/link", json={"fsp_id": "FSP-12345"}, headers=ch)
        assert r.status_code == 200 and r.json()["fsp_id"] == "FSP-12345"

        m = client.get(f"/api/employer/needs/{need_id}/matches", headers=eh).json()
        assert m["total"] == 1
        card = m["items"][0]["candidate"]
        assert card["contacts"] is None and card["display_name"].startswith("Кандидат #")
        assert any("Категория совпадает" in b["reason"] for b in m["items"][0]["blocks"])

        # Приглашение без вилки отклоняется валидацией
        bad = client.post("/api/employer/invitations", json={"candidate_id": card["id"], "position_title": "Dev",
                                                             "message": "Приглашаем на интервью", "contact_method": "tg"},
                          headers=eh)
        assert bad.status_code == 422
        r = client.post("/api/employer/invitations", json={
            "candidate_id": card["id"], "need_id": need_id, "position_title": "Backend-разработчик",
            "message": "Нам понравился ваш результат теста по SQL", "salary_from": 220000, "salary_to": 280000,
            "contact_method": "telegram @hr_tech"}, headers=eh)
        assert r.status_code == 201, r.text
        inv_id = r.json()["id"]
        assert r.json()["candidate_contacts"] is None

        inv = client.get(f"/api/candidate/invitations/{inv_id}", headers=ch).json()
        assert inv["status"] == "viewed" and inv["salary_from"] == 220000
        assert client.post(f"/api/candidate/invitations/{inv_id}/accept", headers=ch).json()["status"] == "accepted"

        invs = client.get("/api/employer/invitations", headers=eh).json()
        assert invs[0]["status"] == "accepted"
        assert invs[0]["candidate_contacts"]["phone"] == "+79990001122"

        # Роли разграничены
        assert client.get("/api/employer/needs", headers=ch).status_code == 403
        assert client.get("/api/candidate/profile", headers=eh).status_code == 403


def test_candidate_without_fsp_and_weak_result():
    with TestClient(app) as client:
        h = _signup(client, "weak@example.com", "candidate")
        client.post("/api/candidate/survey", json={"industry": "development", "specialization": "frontend",
                                                   "claimed_grade": "senior"}, headers=h)
        result = _pass_test(client, h, strong=False)
        assert result["outcome"] == "not_confirmed"
        assert result["result_grade"] is None
        # Не понижаем принудительно, но тест на уровень ниже доступен сразу
        r = client.post("/api/candidate/assessments", json={"claimed_grade": "middle"}, headers=h)
        assert r.status_code == 201
        prof = client.get("/api/candidate/profile", headers=h).json()
        assert prof["achievements"] == [] and prof["fsp_id"] is None


def test_resume_skill_check():
    with TestClient(app) as client:
        h = _signup(client, "skills@example.com", "candidate")
        client.put("/api/candidate/profile", json={"declared_skills": ["python", "react", "kubernetes"]}, headers=h)
        client.post("/api/candidate/survey", json={"industry": "development", "specialization": "backend",
                                                   "claimed_grade": "junior"}, headers=h)
        _pass_test(client, h, strong=True)
        checks = {c["skill"]: c for c in client.get("/api/candidate/skill-checks", headers=h).json()}
        assert checks["react"]["status"] == "testable"
        assert checks["kubernetes"]["status"] == "not_testable"
        r = client.post("/api/candidate/skill-checks", json={"skill": "react"}, headers=h)
        assert r.status_code == 201, r.text
        step = r.json()
        db = SessionLocal()
        while step["item"]:
            item = db.get(AssessmentItem, step["item"]["item_id"])
            db.refresh(item)
            step = client.post(f"/api/candidate/assessments/{step['assessment']['id']}/answer",
                               json={"item_id": item.id, "option": item.correct_option}, headers=h).json()
        db.close()
        assert step["assessment"]["kind"] == "skill" and step["assessment"]["result_grade"] is None
        checks = {c["skill"]: c for c in client.get("/api/candidate/skill-checks", headers=h).json()}
        assert checks["react"]["status"] == "verified"
        assert client.post("/api/candidate/skill-checks", json={"skill": "react"}, headers=h).status_code == 429
        prof = client.get("/api/candidate/profile", headers=h).json()
        assert prof["grade"] == "junior"  # проверка навыка грейд не меняет
