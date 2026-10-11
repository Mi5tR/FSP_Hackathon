from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.common import (
    REVEALED_STATUSES,
    build_card,
    contacts_revealed,
    expire_if_needed,
    invitation_out,
    invitation_ttl,
    pdf_response,
    update_microtask_evidence,
)
from app.api.messaging import list_messages, post_message
from app.api.schemas import (
    AtsConnectIn,
    MessageIn,
    MessageOut,
    ApplicationOut,
    ApplicationStatusIn,
    CompanyIn,
    CompanyOut,
    BlockOut,
    ErrorOut,
    FlagOut,
    Grade,
    InvitationIn,
    InvitationOut,
    MatchesOut,
    MatchOut,
    MicroTaskIn,
    MicroTaskOut,
    NeedIn,
    NeedOut,
    NeedParseIn,
    RateIn,
    RequirementResultOut,
    ScoringIn,
    ShortlistIn,
    Spec,
    SubmissionOut,
)
from app.core.config import settings
from app.core.db import get_db
from app.core.security import require_employer
from app.models.entities import (
    Application,
    ApplicationStatus,
    Assessment,
    CandidateProfile,
    Company,
    HiringNeed,
    Invitation,
    InvitationStatus,
    MicroTask,
    MicroTaskSubmission,
    ShortlistEntry,
    User,
    utcnow,
)
from app.core.skills import SKILL_BY_CODE
from app.services.matching.ranking import (
    BLOCK_TITLES,
    HARD_FILTER_TITLES,
    MatchResult,
    NeedQuery,
    ScoringConfig,
    group_categories,
    rank_detailed,
    score_candidate,
)
from app.services.matching.text_parser import parse_need
from app.services.testing.cat import blueprint

router = APIRouter(prefix="/employer", tags=["employer"])


def company(user: User = Depends(require_employer)) -> Company:
    return user.company


def _own_need(db: Session, co: Company, nid: int) -> HiringNeed:
    n = db.get(HiringNeed, nid)
    if not n or n.company_id != co.id:
        raise HTTPException(404, "Потребность не найдена")
    return n


def _visible_candidates(db: Session) -> list[CandidateProfile]:
    q = (select(CandidateProfile)
         .options(selectinload(CandidateProfile.achievements))
         .where(CandidateProfile.grade.is_not(None), CandidateProfile.consent_publication_at.is_not(None),
                CandidateProfile.open_to_offers.is_(True)))
    # is_visible учитывает согласие представителя для 15–17 лет и выбор кандидата скрыть неподтверждённый грейд
    return [c for c in db.scalars(q) if c.is_visible]


def _new_count(db: Session, n: HiringNeed) -> int:
    """Сколько кандидатов появилось в категории потребности (та же специализация, грейд ±1)
    после последнего просмотра подборки — для уведомления «новые кандидаты»."""
    from app.core.catalog import GRADE_CODES

    if not n.seen_at:
        return 0
    i = GRADE_CODES.index(n.grade)
    grades = GRADE_CODES[max(0, i - 1): i + 2]
    rows = db.scalars(select(CandidateProfile).where(
        CandidateProfile.specialization == n.specialization, CandidateProfile.grade.in_(grades),
        CandidateProfile.category_at > n.seen_at))
    return sum(1 for c in rows if c.is_visible)


def _need_out(db: Session, n: HiringNeed) -> NeedOut:
    out = NeedOut.model_validate(n)
    out.new_candidates = _new_count(db, n)
    return out


# ------------------------------------------------------------------ компания
@router.get("/company", response_model=CompanyOut)
def get_company(co: Company = Depends(company)):
    return co


@router.get("/trust")
def get_trust(co: Company = Depends(company), db: Session = Depends(get_db)):
    """Сводка доверия к компании так, как её видит кандидат, и текущий лимит приглашений."""
    from app.services.trust import check_can_invite, company_trust

    sent, limit = check_can_invite(db, co)
    return {**company_trust(db, co), "sent_today": sent}


@router.put("/company", response_model=CompanyOut)
def update_company(body: CompanyIn, co: Company = Depends(company), db: Session = Depends(get_db)):
    for k, v in body.model_dump().items():
        setattr(co, k, v)
    db.commit()
    return co


# ------------------------------------------------------------------ потребности / вакансии
@router.post("/needs/parse")
def parse_need_text(body: NeedParseIn, co: Company = Depends(company)):
    """Разбор свободного описания потребности в структуру (специализация, грейд, стек, вилка)."""
    return parse_need(body.text)


def _need_fields(body: NeedIn) -> dict:
    data = body.model_dump(exclude={"scoring", "requirements", "skills"})
    reqs = [r.model_dump() for r in body.requirements]
    if not reqs and body.skills:
        reqs = [{"skill": s, "importance": "must", "level": None} for s in body.skills]
    unknown = [r["skill"] for r in reqs if r["skill"] not in SKILL_BY_CODE]
    if unknown:
        raise HTTPException(422, f"Неизвестные навыки: {', '.join(unknown)}. Список: GET /api/catalog")
    q = NeedQuery.build(body.specialization, body.grade, requirements=reqs)
    data["requirements"] = [r.__dict__ for r in q.requirements]
    data["skills"] = q.skills
    data["scoring"] = ScoringConfig.from_dict(body.scoring.model_dump(exclude_none=True)).to_dict()
    return data


@router.get("/scoring/defaults")
def scoring_defaults():
    """Настройки скоринга по умолчанию и описание параметров для интерфейса."""
    return {
        "defaults": ScoringConfig().to_dict(),
        "blocks": BLOCK_TITLES,
        "hard_filters": HARD_FILTER_TITLES,
        "help": {
            "strictness": "1 — сильные стороны компенсируют слабые (обычная сумма); 0 — геометрическое среднее; "
                          "отрицательные значения — итог стремится к самому слабому блоку",
            "fsp_bonus": "какую долю разрыва до 100% закрывает сильный профиль ФСП; отсутствие ФСП не штрафуется",
            "must_threshold": "покрытие обязательного навыка ниже порога считается провалом",
            "must_penalty": "множитель итогового балла за каждый проваленный обязательный навык (1 — без штрафа)",
            "confidence_weight": "насколько сильно уверенность в данных влияет на порядок выдачи",
            "min_confidence": "ниже этой уверенности по обязательному навыку показывается флаг «мало данных»",
            "unverified_penalty": "множитель за каждый обязательный навык без прямого подтверждения "
                                  "(только резюме или косвенный тест)",
            "nice_weight": "вес желательного навыка относительно обязательного",
        },
    }


@router.post("/needs", response_model=NeedOut, status_code=201)
def create_need(body: NeedIn, co: Company = Depends(company), db: Session = Depends(get_db)):
    n = HiringNeed(company_id=co.id, seen_at=utcnow(), **_need_fields(body))
    db.add(n)
    db.commit()
    return _need_out(db, n)


@router.get("/needs", response_model=list[NeedOut])
def list_needs(co: Company = Depends(company), db: Session = Depends(get_db)):
    rows = db.scalars(select(HiringNeed).where(HiringNeed.company_id == co.id).order_by(HiringNeed.id.desc()))
    return [_need_out(db, n) for n in rows]


@router.post("/needs/{nid}/seen", response_model=NeedOut)
def mark_need_seen(nid: int, co: Company = Depends(company), db: Session = Depends(get_db)):
    """Подборка просмотрена: следующие новые кандидаты категории будут отмечены как «новые»."""
    n = _own_need(db, co, nid)
    n.seen_at = utcnow()
    db.commit()
    return _need_out(db, n)


@router.put("/needs/{nid}", response_model=NeedOut)
def update_need(nid: int, body: NeedIn, co: Company = Depends(company), db: Session = Depends(get_db)):
    n = _own_need(db, co, nid)
    for k, v in _need_fields(body).items():
        setattr(n, k, v)
    db.commit()
    return _need_out(db, n)


@router.put("/needs/{nid}/scoring", response_model=NeedOut)
def update_need_scoring(nid: int, body: ScoringIn, co: Company = Depends(company), db: Session = Depends(get_db)):
    """Сохраняет настройки скоринга. Шорт-лист и приглашения при этом не теряются."""
    n = _own_need(db, co, nid)
    merged = {**(n.scoring or {}), **body.model_dump(exclude_none=True)}
    n.scoring = ScoringConfig.from_dict(merged).to_dict()
    db.commit()
    return _need_out(db, n)


def _match_out(db: Session, co: Company, r: MatchResult, shortlisted: bool = False, inv_status: str | None = None,
               seen_at=None) -> MatchOut:
    return MatchOut(candidate=build_card(db, r.candidate, co.id, seen_at), score=r.score, percent=r.percent,
                    probability=r.probability, confidence=r.confidence,
                    blocks=[BlockOut(**b.__dict__) for b in r.blocks],
                    requirements=[RequirementResultOut(**x.__dict__) for x in r.requirements],
                    flags=[FlagOut(**f.__dict__) for f in r.flags],
                    shortlisted=shortlisted, invitation_status=inv_status)


def _matches(db: Session, co: Company, q: NeedQuery, need_id: int | None, *, require_fsp: bool,
             skills_filter: list[str], grade_filter: str | None, spec_filter: str | None,
             limit: int, offset: int, seen_at=None) -> MatchesOut:
    cands = _visible_candidates(db)
    results, excluded = rank_detailed(cands, q)
    categories = group_categories(results)
    if seen_at:
        for g in categories:
            g["new"] = sum(1 for r in results if r.category == (g["specialization"], g["grade"])
                           and r.candidate.category_at and r.candidate.category_at > seen_at)
    # Уточнение поверх подборки: фильтры сужают список, но категории и шорт-лист сохраняются
    if require_fsp:
        results = [r for r in results if r.candidate.achievements]
    if grade_filter:
        results = [r for r in results if r.candidate.grade == grade_filter]
    if spec_filter:
        results = [r for r in results if r.candidate.specialization == spec_filter]
    if skills_filter:
        results = [r for r in results if set(skills_filter) <= set(r.candidate.verified_skills or {}) | set(r.candidate.declared_skills or [])]
    shortlisted = set(db.scalars(select(ShortlistEntry.candidate_id).where(ShortlistEntry.need_id == need_id))) if need_id else set()
    inv_status = {i.candidate_id: i.status.value for i in db.scalars(select(Invitation).where(Invitation.company_id == co.id))}
    page = results[offset: offset + limit]
    return MatchesOut(
        need_id=need_id, categories=categories, total=len(results), excluded=excluded,
        excluded_titles=HARD_FILTER_TITLES, scoring=q.config.to_dict(),
        items=[_match_out(db, co, r, r.candidate.id in shortlisted, inv_status.get(r.candidate.id), seen_at) for r in page],
    )


@router.get("/needs/{nid}/matches", response_model=MatchesOut)
def need_matches(
    nid: int,
    require_fsp: bool = False,
    skills: list[str] = Query(default=[]),
    grade: Grade | None = None,
    specialization: Spec | None = None,
    limit: int = Query(20, le=100),
    offset: int = 0,
    co: Company = Depends(company),
    db: Session = Depends(get_db),
):
    n = _own_need(db, co, nid)
    q = NeedQuery.from_need(n)
    return _matches(db, co, q, nid, require_fsp=require_fsp, skills_filter=skills, grade_filter=grade,
                    spec_filter=specialization, limit=limit, offset=offset, seen_at=n.seen_at)


@router.get("/candidates", response_model=MatchesOut)
def search_bank(
    specialization: Spec,
    grade: Grade,
    skills: list[str] = Query(default=[]),
    require_fsp: bool = False,
    salary_to: int = 10_000_000,
    limit: int = Query(20, le=100),
    offset: int = 0,
    co: Company = Depends(company),
    db: Session = Depends(get_db),
):
    """Поиск по всему банку кандидатов без создания потребности."""
    q = NeedQuery.build(specialization, grade, skills=[s for s in skills if s in SKILL_BY_CODE], salary_to=salary_to)
    return _matches(db, co, q, None, require_fsp=require_fsp, skills_filter=[], grade_filter=None,
                    spec_filter=None, limit=limit, offset=offset)


@router.get("/candidates/{cid}", responses={404: {"model": ErrorOut}})
def candidate_card(cid: int, need_id: int | None = None, co: Company = Depends(company), db: Session = Depends(get_db)):
    c = db.get(CandidateProfile, cid)
    if not c or not c.is_visible:
        raise HTTPException(404, "Кандидат не найден или скрыл профиль")
    card = build_card(db, c, co.id)
    out = {"candidate": card}
    if need_id:
        n = _own_need(db, co, need_id)
        out["match"] = _match_out(db, co, score_candidate(c, NeedQuery.from_need(n)))
    return out


@router.get("/candidates/{cid}/pdf", response_class=Response, responses={200: {"content": {"application/pdf": {}}}})
def candidate_pdf(cid: int, co: Company = Depends(company), db: Session = Depends(get_db)):
    """Стандартизированный PDF-профиль кандидата. Пока кандидат не дал согласия — обезличенная версия."""
    c = db.get(CandidateProfile, cid)
    if not c or not c.is_visible:
        raise HTTPException(404, "Кандидат не найден или скрыл профиль")
    from app.services.profile_pdf import build_profile_pdf
    history = list(db.scalars(select(Assessment).where(Assessment.candidate_id == c.id).order_by(Assessment.id.desc())))
    anonymous = not contacts_revealed(db, co.id, c.id)
    return pdf_response(build_profile_pdf(c, history, anonymous=anonymous), f"candidate-{c.id}.pdf")


@router.get("/needs/{nid}/test-blueprint")
def need_test_blueprint(nid: int, seed: int = 0, co: Company = Depends(company), db: Session = Depends(get_db)):
    """Показывает, как система формирует тест для кандидатов под эту вакансию:
    состав семейств, их доли и пример сгенерированного варианта каждого (без ответа)."""
    n = _own_need(db, co, nid)
    return blueprint(n.specialization, n.grade, n.skills, seed)


@router.get("/micro-tasks")
def my_micro_tasks(co: Company = Depends(company), db: Session = Depends(get_db)):
    tasks = db.scalars(select(MicroTask).where(MicroTask.company_id == co.id).order_by(MicroTask.id.desc()))
    out = []
    for t in tasks:
        n = db.scalar(select(func.count()).select_from(MicroTaskSubmission).where(MicroTaskSubmission.task_id == t.id))
        out.append({**MicroTaskOut(id=t.id, company_name=co.name, specialization=t.specialization, grade=t.grade,
                                   title=t.title, body=t.body, skills=t.skills, created_at=t.created_at,
                                   answer_type=t.answer_type or "open").model_dump(),
                    "submissions": n, "reference_answer": t.reference_answer})
    return out


# ------------------------------------------------------------------ шорт-лист
@router.post("/needs/{nid}/shortlist", status_code=201)
def add_to_shortlist(nid: int, body: ShortlistIn, co: Company = Depends(company), db: Session = Depends(get_db)):
    _own_need(db, co, nid)
    if not db.scalar(select(ShortlistEntry).where(ShortlistEntry.need_id == nid, ShortlistEntry.candidate_id == body.candidate_id)):
        db.add(ShortlistEntry(need_id=nid, candidate_id=body.candidate_id, note=body.note))
        db.commit()
    return {"ok": True}


@router.delete("/needs/{nid}/shortlist/{cid}")
def remove_from_shortlist(nid: int, cid: int, co: Company = Depends(company), db: Session = Depends(get_db)):
    _own_need(db, co, nid)
    e = db.scalar(select(ShortlistEntry).where(ShortlistEntry.need_id == nid, ShortlistEntry.candidate_id == cid))
    if e:
        db.delete(e)
        db.commit()
    return {"ok": True}


@router.get("/needs/{nid}/shortlist", response_model=list[MatchOut])
def get_shortlist(nid: int, co: Company = Depends(company), db: Session = Depends(get_db)):
    n = _own_need(db, co, nid)
    q = NeedQuery.from_need(n)
    inv_status = {i.candidate_id: i.status.value for i in db.scalars(select(Invitation).where(Invitation.company_id == co.id))}
    out = []
    for e in db.scalars(select(ShortlistEntry).where(ShortlistEntry.need_id == nid)):
        c = db.get(CandidateProfile, e.candidate_id)
        out.append(_match_out(db, co, score_candidate(c, q), True, inv_status.get(c.id)))
    return sorted(out, key=lambda m: -m.score)


# ------------------------------------------------------------------ приглашения
@router.post("/invitations", response_model=InvitationOut, status_code=201,
             responses={404: {"model": ErrorOut}, 409: {"model": ErrorOut}, 429: {"model": ErrorOut}})
def send_invitation(body: InvitationIn, co: Company = Depends(company), db: Session = Depends(get_db)):
    if not co.name:
        raise HTTPException(409, "Заполните профиль компании: название обязательно")
    if co.moderation_status == "review":
        raise HTTPException(403, "Приглашения приостановлены: на компанию поступили жалобы кандидатов, идёт проверка")
    c = db.get(CandidateProfile, body.candidate_id)
    if not c or not c.is_visible:
        raise HTTPException(404, "Кандидат не найден или скрыл профиль")
    from app.services.trust import check_can_invite, salary_flag

    sent, limit = check_can_invite(db, co)
    # Лимит делает приглашение «дорогим»: работодатель выбирает адресно, а не рассылает всем.
    # Он зависит от доверия к компании: новым компаниям меньше, проверенным больше.
    if sent >= limit:
        raise HTTPException(429, f"Лимит {limit} приглашений в сутки исчерпан (зависит от уровня доверия к компании)")
    # Одному кандидату можно предложить несколько разных позиций, но не дублировать одну и ту же
    dup = db.scalar(select(Invitation).where(
        Invitation.company_id == co.id, Invitation.candidate_id == c.id,
        Invitation.status.in_([InvitationStatus.sent, InvitationStatus.viewed]),
        (Invitation.need_id == body.need_id) if body.need_id else (Invitation.position_title == body.position_title)))
    if dup:
        raise HTTPException(409, "Кандидату уже отправлено активное приглашение на эту позицию")
    if (c.privacy or {}).get("hide_below_expectation") and c.salary_expectation and body.salary_to < c.salary_expectation:
        raise HTTPException(422, "Вилка ниже зарплатных ожиданий кандидата: он попросил не присылать такие предложения")
    snapshot = {}
    if body.need_id:
        n = _own_need(db, co, body.need_id)
        r = score_candidate(c, NeedQuery.from_need(n))
        snapshot = r.snapshot()
    inv = Invitation(company_id=co.id, candidate_id=c.id, need_id=body.need_id, position_title=body.position_title,
                     message=body.message, salary_from=body.salary_from, salary_to=body.salary_to,
                     contact_method=body.contact_method, match_snapshot=snapshot, expires_at=invitation_ttl(),
                     salary_flag=salary_flag(db, c.specialization, c.grade, body.salary_to))
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return invitation_out(db, inv, for_employer=True)


def _own_inv(db: Session, co: Company, iid: int) -> Invitation:
    inv = db.get(Invitation, iid)
    if not inv or inv.company_id != co.id:
        raise HTTPException(404, "Приглашение не найдено")
    expire_if_needed(inv)
    return inv


@router.get("/invitations/{iid}/messages", response_model=list[MessageOut])
def invitation_messages(iid: int, co: Company = Depends(company), db: Session = Depends(get_db)):
    return list_messages(db, _own_inv(db, co, iid), reader="employer")


@router.post("/invitations/{iid}/messages", response_model=MessageOut, status_code=201,
             responses={409: {"model": ErrorOut}})
def send_message(iid: int, body: MessageIn, co: Company = Depends(company), db: Session = Depends(get_db)):
    return post_message(db, _own_inv(db, co, iid), "employer", body.text)


@router.get("/invitations", response_model=list[InvitationOut])
def list_invitations(co: Company = Depends(company), db: Session = Depends(get_db)):
    rows = list(db.scalars(select(Invitation).where(Invitation.company_id == co.id).order_by(Invitation.id.desc())))
    for inv in rows:
        expire_if_needed(inv)
    db.commit()
    return [invitation_out(db, i, for_employer=True) for i in rows]


@router.post("/invitations/{iid}/withdraw", response_model=InvitationOut)
def withdraw_invitation(iid: int, co: Company = Depends(company), db: Session = Depends(get_db)):
    inv = db.get(Invitation, iid)
    if not inv or inv.company_id != co.id:
        raise HTTPException(404, "Приглашение не найдено")
    if inv.status not in (InvitationStatus.sent, InvitationStatus.viewed):
        raise HTTPException(409, "Приглашение уже закрыто")
    inv.status = InvitationStatus.withdrawn
    db.commit()
    return invitation_out(db, inv, for_employer=True)


def _advance(db: Session, co: Company, iid: int, to: InvitationStatus, allowed: tuple) -> InvitationOut:
    inv = _own_inv(db, co, iid)
    if inv.status not in allowed:
        raise HTTPException(409, f"Из статуса «{inv.status.value}» нельзя перейти в «{to.value}»")
    inv.status = to
    if to == InvitationStatus.offer:
        inv.offer_at = utcnow()
    elif to == InvitationStatus.hired:
        inv.hired_at = utcnow()
    from app.services.ats_sync import push_status
    push_status(db, inv)
    db.commit()
    return invitation_out(db, inv, for_employer=True)


@router.post("/invitations/{iid}/offer", response_model=InvitationOut, responses={409: {"model": ErrorOut}})
def make_offer(iid: int, co: Company = Depends(company), db: Session = Depends(get_db)):
    """После принятия приглашения и собеседований работодатель фиксирует оффер — кандидат видит это у себя."""
    return _advance(db, co, iid, InvitationStatus.offer, (InvitationStatus.accepted,))


@router.post("/invitations/{iid}/hired", response_model=InvitationOut, responses={409: {"model": ErrorOut}})
def mark_hired(iid: int, co: Company = Depends(company), db: Session = Depends(get_db)):
    """Кандидат вышел на работу: сигнал доверия к компании и закрытие воронки."""
    return _advance(db, co, iid, InvitationStatus.hired, (InvitationStatus.accepted, InvitationStatus.offer))


@router.get("/badges")
def badges(co: Company = Depends(company), db: Session = Depends(get_db)):
    """Счётчики для меню: непрочитанные сообщения, новые кандидаты в категориях потребностей, новые отклики."""
    from app.models.entities import Message

    inv_ids = list(db.scalars(select(Invitation.id).where(Invitation.company_id == co.id)))
    unread = db.scalar(select(func.count()).select_from(Message).where(
        Message.invitation_id.in_(inv_ids or [-1]), Message.sender == "candidate", Message.read_at.is_(None))) or 0
    needs = list(db.scalars(select(HiringNeed).where(HiringNeed.company_id == co.id)))
    new_cands = sum(_new_count(db, n) for n in needs)
    apps = db.scalar(select(func.count()).select_from(Application).where(
        Application.need_id.in_([n.id for n in needs] or [-1]), Application.status == ApplicationStatus.sent)) or 0
    return {"invitations": unread, "needs": new_cands + apps, "new_candidates": new_cands, "applications": apps}


# ------------------------------------------------------------------ ATS (Huntflow)
def _ats_out(db: Session, co: Company) -> dict:
    from app.models.entities import AtsEvent
    from app.services.ats_sync import connection

    conn = connection(db, co.id)
    events = db.scalars(select(AtsEvent).where(AtsEvent.company_id == co.id).order_by(AtsEvent.id.desc()).limit(15))
    return {
        "connected": bool(conn), "provider": conn.provider if conn else None,
        "account_id": conn.account_id if conn else None, "mode": conn.mode if conn else None,
        "webhook_url": f"/api/integrations/huntflow/webhook/{conn.webhook_secret}" if conn else None,
        "events": [{"id": e.id, "direction": e.direction, "event": e.event, "payload": e.payload,
                    "status": e.status, "created_at": e.created_at} for e in events],
    }


@router.get("/ats")
def ats_status(co: Company = Depends(company), db: Session = Depends(get_db)):
    return _ats_out(db, co)


@router.put("/ats")
def ats_connect(body: AtsConnectIn, co: Company = Depends(company), db: Session = Depends(get_db)):
    """Подключение Huntflow. Без токена — демонстрационный режим (без сети), с токеном — рабочий API Huntflow."""
    from app.integrations.ats import new_webhook_secret
    from app.models.entities import AtsConnection
    from app.services.ats_sync import connection

    conn = connection(db, co.id) or AtsConnection(company_id=co.id, webhook_secret=new_webhook_secret())
    conn.provider, conn.account_id, conn.token = body.provider, body.account_id, body.token
    conn.mode = "live" if body.token else "mock"
    db.add(conn)
    db.commit()
    return _ats_out(db, co)


@router.delete("/ats")
def ats_disconnect(co: Company = Depends(company), db: Session = Depends(get_db)):
    from app.services.ats_sync import connection

    conn = connection(db, co.id)
    if conn:
        db.delete(conn)
        db.commit()
    return _ats_out(db, co)


@router.post("/ats/import-vacancies")
def ats_import(co: Company = Depends(company), db: Session = Depends(get_db)):
    """Вакансии из ATS работодателя → черновики потребностей (не публикуются автоматически)."""
    from app.services.ats_sync import connection, import_vacancies

    conn = connection(db, co.id)
    if not conn:
        raise HTTPException(409, "ATS не подключена")
    created = import_vacancies(db, conn)
    db.commit()
    return {"imported": len(created), **_ats_out(db, co)}


# ------------------------------------------------------------------ отклики на вакансии
@router.get("/needs/{nid}/applications", response_model=list[ApplicationOut])
def need_applications(nid: int, co: Company = Depends(company), db: Session = Depends(get_db)):
    _own_need(db, co, nid)
    rows = db.scalars(select(Application).where(Application.need_id == nid).order_by(Application.id.desc()))
    return [ApplicationOut(id=a.id, need_id=a.need_id, vacancy_title=a.need.title, company_name=co.name,
                           candidate_id=a.candidate_id, status=a.status.value, cover_note=a.cover_note,
                           created_at=a.created_at, candidate=build_card(db, a.candidate, co.id)) for a in rows]


@router.patch("/applications/{aid}", response_model=ApplicationOut)
def update_application(aid: int, body: ApplicationStatusIn, co: Company = Depends(company), db: Session = Depends(get_db)):
    a = db.get(Application, aid)
    if not a or a.need.company_id != co.id:
        raise HTTPException(404, "Отклик не найден")
    a.status = ApplicationStatus(body.status)
    db.commit()
    return ApplicationOut(id=a.id, need_id=a.need_id, vacancy_title=a.need.title, company_name=co.name,
                          candidate_id=a.candidate_id, status=a.status.value, cover_note=a.cover_note,
                          created_at=a.created_at, candidate=build_card(db, a.candidate, co.id))


# ------------------------------------------------------------------ регулярные задания
@router.post("/micro-tasks", response_model=MicroTaskOut, status_code=201)
def create_micro_task(body: MicroTaskIn, co: Company = Depends(company), db: Session = Depends(get_db)):
    t = MicroTask(company_id=co.id, **body.model_dump())
    db.add(t)
    db.commit()
    return MicroTaskOut(id=t.id, company_name=co.name, specialization=t.specialization, grade=t.grade,
                        title=t.title, body=t.body, skills=t.skills, created_at=t.created_at,
                        answer_type=t.answer_type)


@router.get("/micro-tasks/{tid}/submissions", response_model=list[SubmissionOut])
def task_submissions(tid: int, co: Company = Depends(company), db: Session = Depends(get_db)):
    t = db.get(MicroTask, tid)
    if not t or t.company_id != co.id:
        raise HTTPException(404, "Задание не найдено")
    return [SubmissionOut(id=s.id, candidate_id=s.candidate_id, answer=s.answer, employer_rating=s.employer_rating,
                          auto_checked=bool(s.auto_checked), created_at=s.created_at)
            for s in db.scalars(select(MicroTaskSubmission).where(MicroTaskSubmission.task_id == tid))]


@router.post("/micro-tasks/submissions/{sid}/rate")
def rate_submission(sid: int, body: RateIn, co: Company = Depends(company), db: Session = Depends(get_db)):
    s = db.get(MicroTaskSubmission, sid)
    if not s or db.get(MicroTask, s.task_id).company_id != co.id:
        raise HTTPException(404, "Ответ не найден")
    s.employer_rating = body.rating
    db.flush()
    update_microtask_evidence(db, s.candidate_id)
    db.commit()
    return {"ok": True}
