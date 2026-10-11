from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.core.catalog import GRADE_CODES, SPEC_CODES

Spec = Literal[tuple(SPEC_CODES)]  # type: ignore[valid-type]
Grade = Literal[tuple(GRADE_CODES)]  # type: ignore[valid-type]
WorkFormat = Literal["office", "remote", "hybrid", "any"]


class ErrorOut(BaseModel):
    detail: str


# ------------------------------------------------------------------ auth
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Literal["candidate", "employer"]
    consent_processing: bool = Field(description="Согласие на обработку ПДн (152-ФЗ), обязательно")


class RegisterOut(BaseModel):
    id: int
    email: str
    message: str
    dev_verify_token: str | None = Field(None, description="Только в DEV_MODE, для демо без почтового сервера")


class VerifyIn(BaseModel):
    token: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class DemoLoginIn(BaseModel):
    role: Literal["candidate", "employer"] = Field(description="Новый чистый аккаунт для самостоятельной проверки")


class FspIdAuthorizeIn(BaseModel):
    """Имитация экрана входа ФСП ID (Keycloak). В проде этот шаг выполняет сам Keycloak."""
    login: str = Field(min_length=3, description="Email или ФСП ID участника, например FSP-102345")
    password: str = Field(min_length=1)
    state: str = Field(min_length=8)
    redirect_uri: str


class FspIdCallbackIn(BaseModel):
    code: str
    state: str


class MeOut(BaseModel):
    id: int
    email: str
    role: str
    email_verified: bool


# ------------------------------------------------------------------ candidate
class ProfileIn(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    telegram: str | None = None
    contact_email: EmailStr | None = None
    city: str | None = None
    experience_years: float | None = Field(None, ge=0, le=60)
    declared_skills: list[str] | None = None
    roles: list[str] | None = None
    soft_skills: list[str] | None = None
    about: str | None = Field(None, max_length=3000)
    work_format: WorkFormat | None = None
    salary_expectation: int | None = Field(None, ge=0)
    open_to_offers: bool | None = None
    birth_date: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    guardian_name: str | None = None
    guardian_contact: str | None = None
    guardian_consent: bool | None = Field(None, description="Согласие законного представителя (для 15–17 лет)")


class GradeHintOut(BaseModel):
    grade: str
    probability: float | None = Field(None, description="Вероятность подсказанного грейда по ML-модели")
    distribution: dict[str, float] = Field(default_factory=dict)
    reasons: list[str]
    specializations: list[dict] = Field(default_factory=list, description="Вероятные специализации по тексту профиля")
    note: str


class PrivacyIn(BaseModel):
    show_city: bool = True
    show_about: bool = True
    show_fsp: bool = True
    show_experience: bool = True
    show_unconfirmed: bool = Field(True, description="Показывать профиль, пока грейд не подтверждён тестом (с пометкой)")
    hide_below_expectation: bool = Field(False, description="Не принимать приглашения с вилкой ниже моих ожиданий")
    consent_publication: bool = Field(description="Согласие на публикацию профиля для работодателей")


class AchievementOut(BaseModel):
    event_name: str
    discipline: str
    level: str
    event_date: str
    place: int | None
    participants: int | None
    role_in_team: str | None
    skills: list[str]
    source_url: str | None

    model_config = {"from_attributes": True}


class ProfileOut(BaseModel):
    id: int
    full_name: str
    phone: str | None
    telegram: str | None
    contact_email: str | None
    city: str | None
    experience_years: float
    declared_skills: list[str]
    roles: list[str]
    soft_skills: list[str]
    about: str
    work_format: str
    salary_expectation: int | None
    open_to_offers: bool
    privacy: dict
    consent_processing_at: datetime | None
    consent_publication_at: datetime | None
    specialization: str | None
    grade: str | None
    grade_confirmed: bool = True
    theta: float | None
    verified_skills: dict
    grade_assigned_at: datetime | None
    next_grade_change_at: datetime | None = None
    fsp_id: str | None
    fsp_rank: str | None = None
    achievements: list[AchievementOut]
    is_visible: bool
    upgrade_available: str | None = Field(None, description="Грейд, тест на который система предлагает после уверенного результата")
    birth_date: str | None = None
    age: int | None = None
    guardian_name: str | None = None
    guardian_contact: str | None = None
    guardian_consent_at: datetime | None = None
    minor_blocked: bool = False

    model_config = {"from_attributes": True}


class SurveyIn(BaseModel):
    industry: str
    specialization: Spec
    claimed_grade: Grade
    answers: dict = Field(default_factory=dict, description="Ответы опроса: роли, задачи, предпочтения")


class AssessmentStartIn(BaseModel):
    specialization: Spec | None = Field(None, description="По умолчанию из опроса")
    claimed_grade: Grade | None = Field(None, description="По умолчанию из опроса")


class ItemOut(BaseModel):
    item_id: int
    number: int
    title: str
    skill: str
    prompt: str
    code: str | None
    options: list[str]
    time_limit_s: int
    presented_at: datetime


class AnswerIn(BaseModel):
    item_id: int
    option: int = Field(ge=0, le=3)
    focus_lost: int = Field(0, ge=0, le=1000, description="Сколько раз кандидат уходил с вкладки во время задания")
    copy_attempts: int = Field(0, ge=0, le=1000, description="Попытки скопировать условие (подсказки LLM)")


class AssessmentOut(BaseModel):
    id: int
    kind: str = "grade"
    skill: str | None = None
    specialization: str
    claimed_grade: str
    status: str
    answered: int
    max_items: int
    theta: float
    theta_se: float
    outcome: str | None
    result_grade: str | None
    suggested_grade: str | None
    explanation: str | None
    skills: dict
    started_at: datetime
    finished_at: datetime | None
    integrity: dict = Field(default_factory=dict, description="Сигналы честности: уходы с вкладки, копирование, быстрые ответы")
    time_limit_min: int = 20


class StepOut(BaseModel):
    assessment: AssessmentOut
    item: ItemOut | None


class SkillCheckIn(BaseModel):
    skill: str = Field(examples=["postgresql"])


class SkillCheckOut(BaseModel):
    skill: str
    title: str
    status: str = Field(description="verified | testable | not_testable")
    tested_as: str | None = Field(None, description="Через какой навык банка проверяется")
    level: float | None = None
    demanded: int = Field(0, description="Сколько открытых потребностей требуют этот навык")


class FspLinkIn(BaseModel):
    fsp_id: str = Field(pattern=r"^FSP-[A-Za-z0-9-]{2,40}$", examples=["FSP-102345"])


# ------------------------------------------------------------------ employer
class CompanyIn(BaseModel):
    name: str = Field(min_length=2)
    industry: str = ""
    description: str = ""
    website: str | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    inn: str | None = Field(None, pattern=r"^\d{10}(\d{2})?$")


class CompanyOut(CompanyIn):
    id: int
    inn_valid: bool = Field(False, description="ИНН прошёл проверку контрольной суммы — добровольная метка доверия")
    model_config = {"from_attributes": True}


class NeedParseIn(BaseModel):
    text: str = Field(min_length=10)


class RequirementIn(BaseModel):
    skill: str
    importance: Literal["must", "nice"] = "must"
    level: Literal["basic", "confident", "expert"] = "confident"


class HardFiltersIn(BaseModel):
    must_skills: bool = False
    salary: bool = False
    work_format: bool = False
    exact_grade: bool = False
    fsp_only: bool = False


class ScoringIn(BaseModel):
    """Настройки скоринга потребности. Все поля необязательны: пропущенные берутся по умолчанию."""
    weights: dict[str, float] | None = Field(None, description="role, stack, level, verification, conditions, freshness")
    strictness: float | None = Field(None, ge=-3, le=1, description="1 — компенсаторно, 0 — геометрическое, <0 — строго")
    fsp_bonus: float | None = Field(None, ge=0, le=0.5)
    nice_weight: float | None = Field(None, ge=0, le=1)
    must_threshold: float | None = Field(None, ge=0, le=1)
    must_penalty: float | None = Field(None, ge=0, le=1, description="Множитель за каждый проваленный обязательный навык")
    min_confidence: float | None = Field(None, ge=0, le=1)
    unverified_penalty: float | None = Field(None, ge=0, le=1)
    confidence_weight: float | None = Field(None, ge=0, le=2)
    hard: HardFiltersIn | None = None


class NeedIn(BaseModel):
    title: str
    description: str = ""
    specialization: Spec
    grade: Grade
    skills: list[str] = Field(default_factory=list, description="Устарело: используйте requirements")
    requirements: list[RequirementIn] = Field(default_factory=list)
    scoring: ScoringIn = Field(default_factory=ScoringIn)
    salary_from: int = Field(gt=0, description="Рубли, обязательно")
    salary_to: int = Field(gt=0)
    work_format: WorkFormat = "any"
    is_published: bool = False

    @model_validator(mode="after")
    def _range(self):
        if self.salary_from > self.salary_to:
            raise ValueError("salary_from должен быть ≤ salary_to")
        return self


class NeedOut(BaseModel):
    id: int
    company_id: int
    title: str
    description: str
    specialization: str
    grade: str
    skills: list[str]
    requirements: list[dict]
    scoring: dict
    salary_from: int
    salary_to: int
    work_format: str
    is_published: bool
    created_at: datetime
    ats_external_id: str | None = None
    new_candidates: int = 0
    model_config = {"from_attributes": True}


class VacancyOut(NeedOut):
    company_name: str
    company_trust: dict | None = None


class BlockOut(BaseModel):
    key: str
    title: str
    score: float
    weight: float
    reason: str


class RequirementResultOut(BaseModel):
    skill: str
    title: str
    importance: str
    level: str
    coverage: float
    confidence: float
    source: str | None
    reason: str
    testable: bool
    status: str = Field(description="ok | failed | unverified")


class FlagOut(BaseModel):
    severity: str
    text: str


class CandidateCard(BaseModel):
    """Карточка кандидата для работодателя. Контакты — только после согласия кандидата."""
    id: int
    display_name: str
    specialization: str
    grade: str
    grade_confirmed: bool = True
    minor_age: int | None = Field(None, description="Возраст, если кандидату нет 18: только лёгкий труд (ст. 63 ТК РФ)")
    integrity: dict = Field(default_factory=dict, description="Сводка честности прохождения теста на грейд")
    theta: float | None
    verified_skills: dict
    declared_skills: list[str]
    experience_years: float | None
    city: str | None
    about: str | None
    work_format: str
    has_fsp: bool
    fsp_rank: str | None = None
    achievements: list[AchievementOut]
    last_activity_at: datetime | None
    is_new: bool = Field(False, description="Появился в категории после последнего просмотра подборки")
    contacts_revealed: bool
    contacts: dict | None = None


class MatchOut(BaseModel):
    candidate: CandidateCard
    score: float
    percent: int
    probability: float | None = Field(None, description="Откалиброванная вероятность релевантности")
    confidence: float
    blocks: list[BlockOut]
    requirements: list[RequirementResultOut]
    flags: list[FlagOut]
    shortlisted: bool = False
    invitation_status: str | None = None


class CategoryOut(BaseModel):
    specialization: str
    grade: str
    title: str
    fit: float
    count: int
    with_fsp: int
    avg_score: float
    best_percent: int
    unconfirmed: int = 0
    new: int = 0


class MatchesOut(BaseModel):
    need_id: int | None
    categories: list[CategoryOut]
    total: int
    excluded: dict[str, int] = Field(default_factory=dict, description="Сколько кандидатов отсеял каждый жёсткий фильтр")
    excluded_titles: dict[str, str] = Field(default_factory=dict)
    scoring: dict
    items: list[MatchOut]


class InvitationIn(BaseModel):
    candidate_id: int
    need_id: int | None = Field(None, description="Привязка к потребности необязательна")
    position_title: str = Field(min_length=2)
    message: str = Field(min_length=10, max_length=4000)
    salary_from: int = Field(gt=0)
    salary_to: int = Field(gt=0)
    contact_method: str = Field(min_length=3, description="Как связаться: telegram, email, телефон рекрутера")

    @model_validator(mode="after")
    def _range(self):
        if self.salary_from > self.salary_to:
            raise ValueError("salary_from должен быть ≤ salary_to")
        return self


class InvitationOut(BaseModel):
    id: int
    company_id: int
    company_name: str
    candidate_id: int
    need_id: int | None
    position_title: str
    message: str
    salary_from: int
    salary_to: int
    contact_method: str
    status: str
    decline_reason: str | None
    match: dict | None = Field(None, description="Снимок соответствия на момент приглашения: блоки, навыки, флаги")
    created_at: datetime
    viewed_at: datetime | None
    responded_at: datetime | None
    expires_at: datetime
    company_stats: dict | None = None
    company_trust: dict | None = Field(None, description="Сигналы доверия к работодателю: ИНН, домен, ответы, жалобы")
    company_inn_valid: bool = False
    salary_flag: str | None = Field(None, description="above_market — вилка заметно выше рынка категории (возможная приманка)")
    below_expectation: bool = False
    complained: bool = False
    offer_at: datetime | None = None
    hired_at: datetime | None = None
    candidate_contacts: dict | None = None
    contacts_revoked_at: datetime | None = None
    unread: int = 0
    messages_count: int = 0


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class MessageOut(BaseModel):
    id: int
    sender: str
    text: str
    created_at: datetime
    read_at: datetime | None
    model_config = {"from_attributes": True}


class ComplaintIn(BaseModel):
    reason: Literal["fake", "payment", "conditions", "spam", "rude", "other"]
    text: str = Field("", max_length=2000)


class AtsConnectIn(BaseModel):
    provider: Literal["huntflow"] = "huntflow"
    account_id: str = Field(min_length=1, max_length=64)
    token: str = Field("", max_length=255, description="Пусто — демонстрационный режим без сети")


class DeclineIn(BaseModel):
    reason: Literal["salary", "stack", "company", "not_looking", "other"] = "other"


class ApplicationIn(BaseModel):
    cover_note: str = Field("", max_length=2000)


class ApplicationOut(BaseModel):
    id: int
    need_id: int
    vacancy_title: str
    company_name: str
    candidate_id: int
    status: str
    cover_note: str
    created_at: datetime
    candidate: CandidateCard | None = None


class ApplicationStatusIn(BaseModel):
    status: Literal["viewed", "invited", "rejected"]


class ShortlistIn(BaseModel):
    candidate_id: int
    note: str = ""


class MicroTaskIn(BaseModel):
    specialization: Spec
    grade: Grade
    skills: list[str] = Field(default_factory=list, description="Навыки, которые проверяет задание")
    title: str
    body: str = Field(min_length=20)
    answer_type: Literal["open", "exact"] = Field("open", description="exact — ответ проверяет система по эталону")
    reference_answer: str | None = Field(None, max_length=500, description="Эталон для answer_type=exact; кандидату не показывается")

    @model_validator(mode="after")
    def _ref(self):
        if self.answer_type == "exact" and not (self.reference_answer or "").strip():
            raise ValueError("Для задания с автопроверкой нужен эталонный ответ")
        return self


class MicroTaskOut(BaseModel):
    id: int
    company_name: str
    specialization: str
    grade: str
    title: str
    body: str
    skills: list[str] = []
    created_at: datetime
    answer_type: str = "open"
    my_answer: str | None = None
    my_rating: int | None = None
    auto_checked: bool = False
    recommended: bool = Field(False, description="Задание, которое система адресно предлагает этому кандидату")
    recommended_reason: str | None = None


class MicroTaskAnswerIn(BaseModel):
    answer: str = Field(min_length=1, max_length=5000)


class SubmissionOut(BaseModel):
    id: int
    candidate_id: int
    answer: str
    employer_rating: int | None
    auto_checked: bool = False
    created_at: datetime


class RateIn(BaseModel):
    rating: int = Field(ge=1, le=5)
