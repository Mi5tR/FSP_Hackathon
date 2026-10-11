"""Расширенная механика: воронка до оффера, защита от недобросовестных работодателей,
интеграция с ATS, ожидания по зарплате, промежуточные грейды, ML-подсказки."""

import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ["DEV_MODE"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.catalog import GRADE_CODES  # noqa: E402
from app.main import app  # noqa: E402
from app.services.ml import fuzzy_skills, predict_specialization  # noqa: E402
from app.services.matching.text_parser import parse_need  # noqa: E402
from app.services.testing.item_bank import BANK, families_for  # noqa: E402
from tests.test_e2e import _pass_test, _signup  # noqa: E402


def _employer(client, email, name="Тест Компания"):
    h = _signup(client, email, "employer")
    client.put("/api/employer/company", json={"name": name, "inn": "7725123450"}, headers=h)
    return h


def _candidate(client, email, grade="middle", strong=True, spec="backend"):
    h = _signup(client, email, "candidate")
    client.put("/api/candidate/profile", json={"full_name": "Кандидат Тестов", "phone": "+7900",
                                               "salary_expectation": 250_000}, headers=h)
    client.post("/api/candidate/survey", json={"industry": "development", "specialization": spec,
                                               "claimed_grade": grade}, headers=h)
    res = _pass_test(client, h, strong=strong)
    client.put("/api/candidate/privacy", json={"consent_publication": True}, headers=h)
    cid = client.get("/api/candidate/profile", headers=h).json()["id"]
    return h, cid, res


def _invite(client, eh, cid, title="Backend", sal=(200_000, 300_000)):
    return client.post("/api/employer/invitations", json={
        "candidate_id": cid, "position_title": title, "message": "Приглашаем на собеседование в команду",
        "salary_from": sal[0], "salary_to": sal[1], "contact_method": "telegram @hr"}, headers=eh)


def test_offer_and_hired_after_acceptance():
    with TestClient(app) as client:
        ch, cid, _ = _candidate(client, "offer@ext.ru")
        eh = _employer(client, "hr-offer@ext.ru")
        inv = _invite(client, eh, cid).json()
        assert client.post(f"/api/employer/invitations/{inv['id']}/offer", headers=eh).status_code == 409, \
            "оффер возможен только после принятия"
        client.post(f"/api/candidate/invitations/{inv['id']}/accept", headers=ch)
        r = client.post(f"/api/employer/invitations/{inv['id']}/offer", headers=eh)
        assert r.status_code == 200 and r.json()["status"] == "offer" and r.json()["candidate_contacts"]
        mine = client.get("/api/candidate/invitations", headers=ch).json()
        assert mine[0]["status"] == "offer" and mine[0]["company_trust"]["signals"]
        assert client.post(f"/api/employer/invitations/{inv['id']}/hired", headers=eh).json()["status"] == "hired"


def test_several_positions_for_one_candidate_but_no_duplicates():
    with TestClient(app) as client:
        _, cid, _ = _candidate(client, "multi@ext.ru")
        eh = _employer(client, "hr-multi@ext.ru")
        assert _invite(client, eh, cid, "Backend").status_code == 201
        assert _invite(client, eh, cid, "Backend").status_code == 409
        assert _invite(client, eh, cid, "Tech Lead платформы").status_code == 201


def test_hide_offers_below_expectation():
    with TestClient(app) as client:
        ch, cid, _ = _candidate(client, "exp@ext.ru")
        client.put("/api/candidate/privacy", json={"consent_publication": True, "hide_below_expectation": True},
                   headers=ch)
        eh = _employer(client, "hr-exp@ext.ru")
        assert _invite(client, eh, cid, sal=(100_000, 150_000)).status_code == 422
        assert _invite(client, eh, cid, sal=(220_000, 280_000)).status_code == 201


def test_complaints_pause_company():
    with TestClient(app) as client:
        eh = _employer(client, "hr-shady@ext.ru", "Сомнительная")
        for k in range(3):
            ch, cid, _ = _candidate(client, f"victim{k}@ext.ru")
            inv = _invite(client, eh, cid).json()
            r = client.post(f"/api/candidate/invitations/{inv['id']}/complaint", json={"reason": "payment"}, headers=ch)
            assert r.status_code == 200
        assert r.json()["company_paused"] is True
        _, cid, _ = _candidate(client, "victim9@ext.ru")
        assert _invite(client, eh, cid).status_code == 403
        assert client.get("/api/employer/trust", headers=eh).json()["level"] == "review"


def test_ats_push_and_webhook():
    with TestClient(app) as client:
        ch, cid, _ = _candidate(client, "ats@ext.ru")
        eh = _employer(client, "hr-ats@ext.ru")
        conn = client.put("/api/employer/ats", json={"account_id": "acc-1"}, headers=eh).json()
        assert conn["connected"] and conn["mode"] == "mock"
        inv = _invite(client, eh, cid).json()
        client.post(f"/api/candidate/invitations/{inv['id']}/accept", headers=ch)
        events = client.get("/api/employer/ats", headers=eh).json()["events"]
        assert any(e["event"] == "applicant.created" for e in events), "контакты раскрыты — кандидат ушёл в ATS"
        r = client.post(conn["webhook_url"], json={"invitation_id": inv["id"], "stage": "Оффер"})
        assert r.json() == {"applied": True, "status": "offer"}
        assert client.post("/api/integrations/huntflow/webhook/wrong", json={}).status_code == 404
        imported = client.post("/api/employer/ats/import-vacancies", headers=eh).json()["imported"]
        assert imported == 2


def test_badges_and_recommended_task():
    with TestClient(app) as client:
        ch, cid, _ = _candidate(client, "badge@ext.ru")
        eh = _employer(client, "hr-badge@ext.ru")
        client.post("/api/employer/micro-tasks", json={"specialization": "backend", "grade": "middle",
                                                       "skills": ["sql"], "title": "Индексы",
                                                       "body": "Как ускорить запрос с фильтром по двум полям?"}, headers=eh)
        _invite(client, eh, cid)
        b = client.get("/api/candidate/badges", headers=ch).json()
        assert b["invitations"] >= 1
        tasks = client.get("/api/candidate/micro-tasks", headers=ch).json()
        if tasks:
            assert tasks[0]["recommended"] and tasks[0]["recommended_reason"]


def test_grade_ladder_and_item_bank():
    assert GRADE_CODES == ["intern", "junior", "junior_plus", "middle", "middle_plus", "senior"]
    for spec in ("mobile", "analyst", "security"):
        assert len(families_for(spec)) >= 10
    for f in BANK:
        for seed in range(50):
            v = f.render(seed)
            assert len(set(v.options)) == 4 and 0 <= v.correct < 4
    assert parse_need("Ищем Middle+ разработчика на Go")["grade"] == "middle_plus"


def test_ml_helpers():
    assert predict_specialization("Kotlin, Jetpack Compose, корутины, RuStore")[0]["specialization"] == "mobile"
    assert {"postgresql", "kubernetes"} <= set(fuzzy_skills("Постгрес и Кубернетес"))
