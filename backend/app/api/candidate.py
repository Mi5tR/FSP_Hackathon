import io
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.common import (
    REVEALED_STATUSES,
    check_exact,
    expire_if_needed,
    invitation_out,
    pdf_response,
    update_microtask_evidence,
)
from app.api.messaging import list_messages, post_message
from app.api.schemas import (
    ApplicationIn,
    ApplicationOut,
    AnswerIn,
    AssessmentOut,
    AssessmentStartIn,
    ComplaintIn,
    DeclineIn,
    ErrorOut,
    FspLinkIn,
    GradeHintOut,
    InvitationOut,
    ItemOut,
    MicroTaskAnswerIn,
    MicroTaskOut,
    MessageIn,
    MessageOut,
    PrivacyIn,
    ProfileIn,
    ProfileOut,
    StepOut,
    SkillCheckIn,
    SkillCheckOut,
    SurveyIn,
)
from app.core.config import settings
from app.core.db import get_db
from app.core.security import require_candidate
from app.integrations.fsp import get_fsp_client
from app.models.entities import (
    Application,
    Assessment,
    CandidateProfile,
    FspAchievement,
    HiringNeed,
    Invitation,
    InvitationStatus,
    MicroTask,
    MicroTaskSubmission,
    SurveyAnswer,
    User,
    utcnow,
)
from app.services.matching.text_parser import parse_resume
from app.services.profile_pdf import build_profile_pdf
from app.services.testing import service as testing
from app.core.skills import SKILL_BY_CODE, SKILL_TITLES
from app.services.testing.cat import testable_root
from app.services.testing.item_bank import BANK_BY_ID

router = APIRouter(prefix="/candidate", tags=["candidate"])


def me(user: User = Depends(require_candidate)) -> CandidateProfile:
    return user.candidate


def _profile_out(c: CandidateProfile) -> ProfileOut:
    out = ProfileOut.model_validate(c)
    if c.grade_assigned_at:
        out.next_grade_change_at = c.grade_assigned_at + timedelta(days=settings.grade_change_cooldown_days)
    out.is_visible = c.is_visible
    return out


def _with_upgrade(db: Session, c: CandidateProfile) -> ProfileOut:
    out = _profile_out(c)
    from app.services.testing.cat import next_grade

    nxt = next_grade(c.grade) if c.grade and c.grade_confirmed else None
    if nxt and testing.upgrade_offered(db, c, nxt):
        out.upgrade_available = nxt
    return out


# ------------------------------------------------------------------ профиль
@router.get("/profile", response_model=ProfileOut)
def get_profile(c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    return _with_upgrade(db, c)


@router.put("/profile", response_model=ProfileOut, responses={422: {"model": ErrorOut}})
def update_profile(body: ProfileIn, c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    guardian_consent = data.pop("guardian_consent", None)
    if data.get("birth_date"):
        try:
            born = datetime.strptime(data["birth_date"], "%Y-%m-%d")
        except ValueError:
            raise HTTPException(422, "Некорректная дата рождения")
        if born > datetime.now() or born.year < 1940:
            raise HTTPException(422, "Некорректная дата рождения")
    for k, v in data.items():
        setattr(c, k, v)
    if guardian_consent is not None:
        if guardian_consent and not (c.guardian_name and c.guardian_contact):
            raise HTTPException(422, "Укажите ФИО и контакт законного представителя")
        c.guardian_consent_at = utcnow() if guardian_consent else None
    c.last_activity_at = utcnow()
    db.commit()
    return _profile_out(c)


@router.get("/profile/pdf", response_class=Response, responses={200: {"content": {"application/pdf": {}}}})
def profile_pdf(c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    """Стандартизированный PDF-профиль: категория, подтверждённые навыки, достижения ФСП, история тестов."""
    history = list(db.scalars(select(Assessment).where(Assessment.candidate_id == c.id).order_by(Assessment.id.desc())))
    return pdf_response(build_profile_pdf(c, history, anonymous=False), f"fsp-profile-{c.id}.pdf")


@router.get("/grade-hint", response_model=GradeHintOut)
def grade_hint(c: CandidateProfile = Depends(me)):
    """Подсказка, на какой грейд претендовать: ML-модель по стажу, ширине стека, призовым местам ФСП
    и опроснику самооценки, плюс вероятная специализация по тексту профиля.
    Это только подсказка: кандидат выбирает грейд сам, а присваивает его только тест."""
    from app.core.skills import SKILL_TITLES as titles
    from app.services.ml import predict_grade, predict_specialization

    years = c.experience_years or 0
    prizes = [a for a in c.achievements if a.place and a.place <= 3]
    self_scores = ((c.survey.answers or {}).get("self") or {}) if c.survey else {}
    survey_mean = sum(self_scores.values()) / len(self_scores) if self_scores else None
    pred = predict_grade(years, len(c.declared_skills or []), len(prizes), survey_mean)
    reasons = [f"стаж {years:g} г." if years else "стаж не указан",
               f"навыков в резюме: {len(c.declared_skills or [])}"]
    if prizes:
        reasons.append(f"призовые места в соревнованиях ФСП: {len(prizes)}")
    if survey_mean is not None:
        reasons.append(f"самооценка в опроснике {survey_mean:.1f} из 3")
    text = " ".join([c.about or "", " ".join(c.roles or []), " ".join(titles.get(s, s) for s in c.declared_skills or [])])
    return GradeHintOut(grade=pred["grade"], probability=pred["probability"], distribution=pred["distribution"],
                        reasons=reasons, specializations=predict_specialization(text) if text.strip() else [],
                        note="Это подсказка ML-модели, а не оценка: грейд присваивает только тест. "
                             "Если тест не подтвердит уровень, тест на уровень ниже доступен сразу.")


@router.put("/privacy", response_model=ProfileOut)
def update_privacy(body: PrivacyIn, c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    data = body.model_dump()
    consent = data.pop("consent_publication")
    if consent and c.age is not None and c.age < 15:
        raise HTTPException(422, "Публикация профиля доступна с 15 лет")
    if consent and c.age is not None and c.age < 18 and not c.guardian_consent_at:
        raise HTTPException(422, "До 18 лет профиль публикуется только с согласия законного представителя "
                                 "(заполните его в профиле)")
    c.privacy = data
    c.consent_publication_at = utcnow() if consent else None
    db.commit()
    return _profile_out(c)


@router.post("/resume/parse", responses={422: {"model": ErrorOut}})
async def parse_resume_pdf(file: UploadFile = File(...), c: CandidateProfile = Depends(me)):
    """Автораспознавание полей из PDF. Ничего не сохраняет: кандидат проверяет поля и сохраняет профиль сам."""
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(422, "Файл больше 5 МБ")
    try:
        text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(raw)).pages)
    except Exception:
        raise HTTPException(422, "Не удалось прочитать PDF")
    if not text.strip():
        raise HTTPException(422, "В PDF нет текстового слоя (скан). Заполните профиль вручную.")
    return parse_resume(text)


# ------------------------------------------------------------------ опрос и тест
@router.post("/survey", status_code=201)
def submit_survey(body: SurveyIn, c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    if c.survey:
        c.survey.industry, c.survey.specialization = body.industry, body.specialization
        c.survey.claimed_grade, c.survey.answers = body.claimed_grade, body.answers
    else:
        db.add(SurveyAnswer(candidate_id=c.id, **body.model_dump()))
    db.commit()
    return {"ok": True}


def _item_out(item, number: int) -> ItemOut:
    fam = BANK_BY_ID[item.family_id]
    v = fam.render(item.variant_seed)
    return ItemOut(item_id=item.id, number=number, title=fam.title, skill=fam.skill, prompt=v.prompt,
                   code=v.code, options=v.options, time_limit_s=fam.time_limit_s, presented_at=item.presented_at)


def _step(db: Session, a: Assessment) -> StepOut:
    item = testing.next_item(db, a)
    db.refresh(a)
    return StepOut(assessment=AssessmentOut(**testing.summary(db, a)),
                   item=_item_out(item, len(a.items)) if item else None)


def _own_assessment(db: Session, c: CandidateProfile, aid: int) -> Assessment:
    a = db.get(Assessment, aid)
    if not a or a.candidate_id != c.id:
        raise HTTPException(404, "Попытка не найдена")
    return a


@router.post("/assessments", response_model=StepOut, status_code=201, responses={409: {"model": ErrorOut}, 429: {"model": ErrorOut}})
def start_assessment(body: AssessmentStartIn, c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    if not c.survey and not (body.specialization and body.claimed_grade):
        raise HTTPException(422, "Сначала пройдите опрос по специализации")
    spec = body.specialization or c.survey.specialization
    grade = body.claimed_grade or c.survey.claimed_grade
    a = testing.start(db, c, spec, grade)
    return _step(db, a)


@router.get("/assessments", response_model=list[AssessmentOut])
def list_assessments(c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    rows = db.scalars(select(Assessment).where(Assessment.candidate_id == c.id).order_by(Assessment.id.desc()))
    return [AssessmentOut(**testing.summary(db, a)) for a in rows]


@router.get("/assessments/{aid}", response_model=StepOut)
def get_assessment(aid: int, c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    return _step(db, _own_assessment(db, c, aid))


@router.post("/assessments/{aid}/answer", response_model=StepOut, responses={409: {"model": ErrorOut}})
def answer_item(aid: int, body: AnswerIn, c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    a = _own_assessment(db, c, aid)
    testing.answer(db, a, body.item_id, body.option, body.focus_lost, body.copy_attempts)
    return _step(db, a)


@router.get("/skill-checks", response_model=list[SkillCheckOut])
def skill_checks(c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    """Навыки из резюме и их статус. Неподтверждённые навыки можно проверить коротким тестом
    (4–6 заданий): после проверки они учитываются в подборе как подтверждённые."""
    demand: dict[str, int] = {}
    for n in db.scalars(select(HiringNeed).where(HiringNeed.is_published.is_(True))):
        for r in n.requirements or [{"skill": s} for s in n.skills]:
            demand[r["skill"]] = demand.get(r["skill"], 0) + 1
    profile = c.skill_profile or {}
    out = []
    for s in c.declared_skills or []:
        root = testable_root(s) if s in SKILL_BY_CODE else None
        est = profile.get(root) if root else None
        status = "verified" if est and est["n"] >= 2 else "testable" if root else "not_testable"
        out.append(SkillCheckOut(skill=s, title=SKILL_TITLES.get(s, s), status=status,
                                 tested_as=root if root and root != s else None,
                                 level=c.verified_skills.get(root) if est else None,
                                 demanded=demand.get(s, 0)))
    return sorted(out, key=lambda x: (x.status != "testable", -x.demanded))


@router.post("/skill-checks", response_model=StepOut, status_code=201,
             responses={409: {"model": ErrorOut}, 422: {"model": ErrorOut}, 429: {"model": ErrorOut}})
def start_skill_check(body: SkillCheckIn, c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    if body.skill not in SKILL_BY_CODE:
        raise HTTPException(422, "Неизвестный навык")
    a = testing.start_skill_check(db, c, body.skill)
    return _step(db, a)


# ------------------------------------------------------------------ ФСП
@router.post("/fsp/link", response_model=ProfileOut, responses={404: {"model": ErrorOut}, 409: {"model": ErrorOut}})
def link_fsp(body: FspLinkIn, c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    other = db.scalar(select(CandidateProfile).where(CandidateProfile.fsp_id == body.fsp_id, CandidateProfile.id != c.id))
    if other:
        raise HTTPException(409, "Этот ФСП ID уже привязан к другому профилю")
    participant = get_fsp_client().get_participant(body.fsp_id)
    if participant is None:
        raise HTTPException(404, "Участник с таким ФСП ID не найден в реестре")
    c.fsp_id = body.fsp_id
    c.fsp_linked_at = utcnow()
    c.fsp_rank = participant.sport_rank
    c.achievements.clear()
    for a in participant.achievements:
        c.achievements.append(FspAchievement(**a.__dict__))
    db.commit()
    db.refresh(c)
    return _profile_out(c)


@router.delete("/fsp/link", response_model=ProfileOut)
def unlink_fsp(c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    c.fsp_id = None
    c.fsp_linked_at = None
    c.fsp_rank = None
    c.achievements.clear()
    db.commit()
    return _profile_out(c)


# ------------------------------------------------------------------ приглашения
def _own_invitation(db: Session, c: CandidateProfile, iid: int) -> Invitation:
    inv = db.get(Invitation, iid)
    if not inv or inv.candidate_id != c.id:
        raise HTTPException(404, "Приглашение не найдено")
    expire_if_needed(inv)
    return inv


@router.get("/invitations", response_model=list[InvitationOut])
def list_invitations(c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    rows = list(db.scalars(select(Invitation).where(Invitation.candidate_id == c.id).order_by(Invitation.id.desc())))
    for inv in rows:
        expire_if_needed(inv)
    db.commit()
    return [invitation_out(db, i, for_employer=False) for i in rows]


@router.get("/invitations/{iid}", response_model=InvitationOut)
def view_invitation(iid: int, c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    inv = _own_invitation(db, c, iid)
    if inv.status == InvitationStatus.sent:
        inv.status = InvitationStatus.viewed
        inv.viewed_at = utcnow()
    db.commit()
    return invitation_out(db, inv, for_employer=False)


def _respond(db: Session, inv: Invitation, status: InvitationStatus, reason: str | None = None):
    if inv.status not in (InvitationStatus.sent, InvitationStatus.viewed):
        raise HTTPException(409, f"Приглашение уже в статусе {inv.status.value}")
    inv.viewed_at = inv.viewed_at or utcnow()
    inv.status = status
    inv.decline_reason = reason
    inv.responded_at = utcnow()
    db.commit()
    return invitation_out(db, inv, for_employer=False)


@router.post("/invitations/{iid}/accept", response_model=InvitationOut, responses={409: {"model": ErrorOut}})
def accept_invitation(iid: int, c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    inv = _own_invitation(db, c, iid)
    out = _respond(db, inv, InvitationStatus.accepted)
    # Контакты раскрыты — если у работодателя подключена ATS, кандидат уходит туда
    from app.services.ats_sync import push_candidate
    push_candidate(db, inv.company_id, c, db.get(HiringNeed, inv.need_id) if inv.need_id else None, "приглашение принято")
    db.commit()
    return out


@router.post("/invitations/{iid}/complaint", responses={409: {"model": ErrorOut}})
def complain(iid: int, body: ComplaintIn, c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    """Жалоба на приглашение (фиктивная вакансия, просьба об оплате, несоответствие условий).
    Три жалобы разных кандидатов за 30 дней автоматически приостанавливают приглашения компании."""
    from app.services.trust import register_complaint

    inv = _own_invitation(db, c, iid)
    res = register_complaint(db, inv, body.reason, body.text)
    if inv.status in (InvitationStatus.sent, InvitationStatus.viewed):
        inv.status = InvitationStatus.declined
        inv.decline_reason = "company"
        inv.responded_at = utcnow()
    db.commit()
    return {"ok": True, **res}


@router.post("/invitations/{iid}/decline", response_model=InvitationOut, responses={409: {"model": ErrorOut}})
def decline_invitation(iid: int, body: DeclineIn, c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    return _respond(db, _own_invitation(db, c, iid), InvitationStatus.declined, body.reason)


@router.post("/invitations/{iid}/revoke-contacts", response_model=InvitationOut, responses={409: {"model": ErrorOut}})
def revoke_contacts(iid: int, c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    """Отзыв доступа к контактам после принятия приглашения: работодатель снова видит обезличенную карточку."""
    inv = _own_invitation(db, c, iid)
    if inv.status not in REVEALED_STATUSES:
        raise HTTPException(409, "Контакты раскрываются только по принятому приглашению")
    inv.contacts_revoked_at = utcnow()
    db.commit()
    return invitation_out(db, inv, for_employer=False)


@router.post("/invitations/{iid}/restore-contacts", response_model=InvitationOut, responses={409: {"model": ErrorOut}})
def restore_contacts(iid: int, c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    inv = _own_invitation(db, c, iid)
    if inv.status not in REVEALED_STATUSES:
        raise HTTPException(409, "Приглашение не принято")
    inv.contacts_revoked_at = None
    db.commit()
    return invitation_out(db, inv, for_employer=False)


@router.get("/invitations/{iid}/messages", response_model=list[MessageOut])
def invitation_messages(iid: int, c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    return list_messages(db, _own_invitation(db, c, iid), reader="candidate")


@router.post("/invitations/{iid}/messages", response_model=MessageOut, status_code=201,
             responses={409: {"model": ErrorOut}})
def send_message(iid: int, body: MessageIn, c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    return post_message(db, _own_invitation(db, c, iid), "candidate", body.text)


# ------------------------------------------------------------------ отклики
@router.post("/vacancies/{vid}/apply", response_model=ApplicationOut, status_code=201, responses={409: {"model": ErrorOut}})
def apply(vid: int, body: ApplicationIn, c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    need = db.get(HiringNeed, vid)
    if not need or not need.is_published:
        raise HTTPException(404, "Вакансия не найдена")
    if not c.grade:
        raise HTTPException(409, "Откликаться можно после присвоения категории по итогам теста")
    if db.scalar(select(Application).where(Application.need_id == vid, Application.candidate_id == c.id)):
        raise HTTPException(409, "Вы уже откликнулись на эту вакансию")
    app_ = Application(need_id=vid, candidate_id=c.id, cover_note=body.cover_note)
    db.add(app_)
    from app.services.ats_sync import push_candidate
    push_candidate(db, need.company_id, c, need, "отклик на вакансию")
    db.commit()
    return _app_out(app_)


def _app_out(a: Application) -> ApplicationOut:
    return ApplicationOut(id=a.id, need_id=a.need_id, vacancy_title=a.need.title, company_name=a.need.company.name,
                          candidate_id=a.candidate_id, status=a.status.value, cover_note=a.cover_note,
                          created_at=a.created_at)


@router.get("/applications", response_model=list[ApplicationOut])
def my_applications(c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    rows = db.scalars(select(Application).where(Application.candidate_id == c.id).order_by(Application.id.desc()))
    return [_app_out(a) for a in rows]


# ------------------------------------------------------------------ регулярные задания
def _task_pool(db: Session, c: CandidateProfile) -> list[MicroTask]:
    """Задания специализации кандидата для его грейда и соседних (Middle видит задания Middle+ и Junior+)."""
    from app.core.catalog import GRADE_CODES

    if not c.grade or not c.specialization:
        return []
    i = GRADE_CODES.index(c.grade)
    grades = GRADE_CODES[max(0, i - 1): i + 2]
    return list(db.scalars(select(MicroTask).where(MicroTask.specialization == c.specialization,
                                                   MicroTask.grade.in_(grades)).order_by(MicroTask.id.desc()).limit(20)))


def _recommend(c: CandidateProfile, tasks: list[MicroTask], answered: set[int]) -> tuple[int | None, str | None]:
    """Адресное задание: система сама выбирает одно задание для кандидата — то, что проверяет навык
    с наименьшей уверенностью в профиле (свежий сигнал там, где данных меньше всего)."""
    from app.services.testing.skill_profile import confidence

    prof = c.skill_profile or {}

    def conf(s: str) -> float:
        return confidence(prof[s]["se"]) if s in prof else 0.0

    best, why, best_score = None, None, 2.0
    for t in tasks:
        if t.id in answered:
            continue
        skills = t.skills or []
        score = min([conf(s) for s in skills] or [0.5]) + (0.0 if t.grade == c.grade else 0.15)
        if score < best_score:
            best_score, best = score, t.id
            weakest = min(skills, key=conf) if skills else None
            why = (f"Проверит навык «{SKILL_TITLES.get(weakest, weakest)}» — по нему в профиле пока мало данных"
                   if weakest else "Свежий сигнал для работодателей вашей категории")
    return best, why


@router.get("/micro-tasks", response_model=list[MicroTaskOut])
def my_micro_tasks(c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    tasks = _task_pool(db, c)
    mine = {s.task_id: s for s in db.scalars(select(MicroTaskSubmission).where(MicroTaskSubmission.candidate_id == c.id))}
    rec_id, rec_why = _recommend(c, tasks, set(mine))
    out = [MicroTaskOut(id=t.id, company_name=t.company.name, specialization=t.specialization, grade=t.grade,
                        title=t.title, body=t.body, skills=t.skills, created_at=t.created_at,
                        answer_type=t.answer_type or "open",
                        my_answer=mine[t.id].answer if t.id in mine else None,
                        my_rating=mine[t.id].employer_rating if t.id in mine else None,
                        auto_checked=bool(mine[t.id].auto_checked) if t.id in mine else False,
                        recommended=t.id == rec_id, recommended_reason=rec_why if t.id == rec_id else None)
           for t in tasks]
    return sorted(out, key=lambda t: (not t.recommended, t.my_answer is not None))


@router.get("/badges")
def badges(c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    """Счётчики для меню кабинета: новые приглашения и непрочитанные сообщения, новые задания."""
    from sqlalchemy import func

    from app.models.entities import Message

    invs = list(db.scalars(select(Invitation).where(Invitation.candidate_id == c.id)))
    new_inv = sum(1 for i in invs if i.status == InvitationStatus.sent and i.expires_at > utcnow())
    unread = db.scalar(select(func.count()).select_from(Message).where(
        Message.invitation_id.in_([i.id for i in invs] or [-1]), Message.sender == "employer",
        Message.read_at.is_(None))) or 0
    answered = set(db.scalars(select(MicroTaskSubmission.task_id).where(MicroTaskSubmission.candidate_id == c.id)))
    tasks = sum(1 for t in _task_pool(db, c) if t.id not in answered)
    return {"invitations": new_inv + unread, "tasks": tasks}


@router.post("/micro-tasks/{tid}/answer", status_code=201, responses={409: {"model": ErrorOut}})
def answer_micro_task(tid: int, body: MicroTaskAnswerIn, c: CandidateProfile = Depends(me), db: Session = Depends(get_db)):
    t = db.get(MicroTask, tid)
    if not t or t.id not in {x.id for x in _task_pool(db, c)}:
        raise HTTPException(404, "Задание не найдено")
    if db.scalar(select(MicroTaskSubmission).where(MicroTaskSubmission.task_id == tid, MicroTaskSubmission.candidate_id == c.id)):
        raise HTTPException(409, "Ответ уже отправлен")
    if t.answer_type != "exact" and len(body.answer.strip()) < 20:
        raise HTTPException(422, "Опишите подход подробнее: минимум 20 символов")
    sub = MicroTaskSubmission(task_id=tid, candidate_id=c.id, answer=body.answer)
    result = None
    if t.answer_type == "exact" and t.reference_answer:
        # Есть эталон — проверяет система сразу; открытые ответы оценивает работодатель
        ok = check_exact(body.answer, t.reference_answer)
        sub.employer_rating, sub.auto_checked = (5 if ok else 1), True
        result = "correct" if ok else "wrong"
    db.add(sub)
    c.last_activity_at = utcnow()  # регулярные задания поддерживают актуальность профиля
    db.flush()
    if sub.auto_checked:
        update_microtask_evidence(db, c.id)
    db.commit()
    return {"ok": True, "result": result}
