import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint, false, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Role(str, enum.Enum):
    candidate = "candidate"
    employer = "employer"


class InvitationStatus(str, enum.Enum):
    sent = "sent"
    viewed = "viewed"
    accepted = "accepted"
    offer = "offer"        # после принятия работодатель сделал оффер
    hired = "hired"        # кандидат вышел на работу (фиксирует работодатель или ATS)
    declined = "declined"
    expired = "expired"
    withdrawn = "withdrawn"


class ApplicationStatus(str, enum.Enum):
    sent = "sent"
    viewed = "viewed"
    invited = "invited"
    rejected = "rejected"


class AssessmentStatus(str, enum.Enum):
    in_progress = "in_progress"
    finished = "finished"
    abandoned = "abandoned"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role))
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verify_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    candidate: Mapped["CandidateProfile | None"] = relationship(back_populates="user", uselist=False)
    company: Mapped["Company | None"] = relationship(back_populates="user", uselist=False)


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    # Контакты раскрываются работодателю только после принятия приглашения или отклика
    full_name: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    telegram: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Самоописание: не влияет на категорию, только дополняет карточку
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    experience_years: Mapped[float] = mapped_column(Float, default=0)
    declared_skills: Mapped[list] = mapped_column(JSON, default=list)
    roles: Mapped[list] = mapped_column(JSON, default=list)
    soft_skills: Mapped[list] = mapped_column(JSON, default=list)
    about: Mapped[str] = mapped_column(Text, default="")
    work_format: Mapped[str] = mapped_column(String(20), default="any")  # office/remote/hybrid/any
    # Ожидание по зарплате работодателю не показывается, только признак «укладывается в бюджет»
    salary_expectation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    open_to_offers: Mapped[bool] = mapped_column(Boolean, default=True)
    privacy: Mapped[dict] = mapped_column(
        JSON, default=lambda: {"show_city": True, "show_about": True, "show_fsp": True, "show_experience": True}
    )
    consent_processing_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consent_publication_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Категория, присвоенная по итогам опроса и теста
    specialization: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    grade: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    # False — заявленный грейд тестом не подтверждён: кандидат остаётся в выдаче с пометкой и ниже подтверждённых
    grade_confirmed: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    theta: Mapped[float | None] = mapped_column(Float, nullable=True)
    theta_se: Mapped[float | None] = mapped_column(Float, nullable=True)
    verified_skills: Mapped[dict] = mapped_column(JSON, default=dict)  # skill -> уровень 0..1 для отображения
    # skill -> {theta, se, n, correct}: оценка по каждому навыку из всех попыток (см. skill_profile.py)
    skill_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    # skill -> {score 0..1, n}: оценки работодателей за регулярные задания
    microtask_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    grade_assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Когда кандидат попал в текущую категорию (в т.ч. с неподтверждённым грейдом): для уведомлений «новые кандидаты»
    category_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Связь с ФСП ID
    fsp_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    fsp_linked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fsp_rank: Mapped[str | None] = mapped_column(String(50), nullable=True)  # спортивный разряд из реестра ФСП
    # Несовершеннолетние (15–17 лет): публикация только с согласием законного представителя (152-ФЗ, ст. 63 ТК РФ)
    birth_date: Mapped[str | None] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD
    guardian_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    guardian_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    guardian_consent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship(back_populates="candidate")
    achievements: Mapped[list["FspAchievement"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    survey: Mapped["SurveyAnswer | None"] = relationship(back_populates="candidate", uselist=False)

    @property
    def age(self) -> int | None:
        if not self.birth_date:
            return None
        try:
            b = datetime.strptime(self.birth_date, "%Y-%m-%d").date()
        except ValueError:
            return None
        t = utcnow().date()
        return t.year - b.year - ((t.month, t.day) < (b.month, b.day))

    @property
    def minor_blocked(self) -> bool:
        """До 15 лет публикация запрещена; 15–17 — только с согласием законного представителя."""
        a = self.age
        return a is not None and (a < 15 or (a < 18 and not self.guardian_consent_at))

    @property
    def is_visible(self) -> bool:
        # Неподтверждённый грейд: по умолчанию кандидат виден с пометкой и ниже подтверждённых,
        # но может сам скрыть профиль до успешной пересдачи (privacy.show_unconfirmed)
        hidden_unconfirmed = self.grade_confirmed is False and not (self.privacy or {}).get("show_unconfirmed", True)
        return bool(self.consent_publication_at and self.grade and self.open_to_offers and not self.minor_blocked
                    and not hidden_unconfirmed)


class SurveyAnswer(Base):
    """Опрос по отрасли и специализации, первый шаг обязательного пути."""
    __tablename__ = "survey_answers"
    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"), unique=True)
    industry: Mapped[str] = mapped_column(String(50))
    specialization: Mapped[str] = mapped_column(String(30))
    claimed_grade: Mapped[str] = mapped_column(String(20))
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    candidate: Mapped[CandidateProfile] = relationship(back_populates="survey")


class FspAchievement(Base):
    __tablename__ = "fsp_achievements"
    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"), index=True)
    event_name: Mapped[str] = mapped_column(String(255))
    discipline: Mapped[str] = mapped_column(String(100))
    level: Mapped[str] = mapped_column(String(50))  # regional / federal / international
    event_date: Mapped[str] = mapped_column(String(20))
    place: Mapped[int | None] = mapped_column(Integer, nullable=True)
    participants: Mapped[int | None] = mapped_column(Integer, nullable=True)
    role_in_team: Mapped[str | None] = mapped_column(String(100), nullable=True)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    candidate: Mapped[CandidateProfile] = relationship(back_populates="achievements")


class Assessment(Base):
    __tablename__ = "assessments"
    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"), index=True)
    specialization: Mapped[str] = mapped_column(String(30))
    claimed_grade: Mapped[str] = mapped_column(String(20))
    # grade — тест на категорию; skill — короткая проверка навыка из резюме (грейд не меняет)
    kind: Mapped[str] = mapped_column(String(10), default="grade")
    skill: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[AssessmentStatus] = mapped_column(Enum(AssessmentStatus), default=AssessmentStatus.in_progress)
    seed: Mapped[int] = mapped_column(Integer)
    theta: Mapped[float] = mapped_column(Float, default=0.0)
    theta_se: Mapped[float] = mapped_column(Float, default=1.0)
    outcome: Mapped[str | None] = mapped_column(String(30), nullable=True)
    result_grade: Mapped[str | None] = mapped_column(String(20), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Сигналы честности прохождения: уходы с вкладки, вставки, слишком быстрые ответы
    integrity: Mapped[dict] = mapped_column(JSON, default=dict)

    items: Mapped[list["AssessmentItem"]] = relationship(
        back_populates="assessment", order_by="AssessmentItem.id", cascade="all, delete-orphan"
    )


class AssessmentItem(Base):
    __tablename__ = "assessment_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), index=True)
    family_id: Mapped[str] = mapped_column(String(64), index=True)
    variant_seed: Mapped[int] = mapped_column(Integer)
    # Правильный ответ хранится только на сервере, клиенту не отдаётся
    correct_option: Mapped[int] = mapped_column(Integer)
    presented_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    answered_option: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    response_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    assessment: Mapped[Assessment] = relationship(back_populates="items")


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    industry: Mapped[str] = mapped_column(String(100), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    inn: Mapped[str | None] = mapped_column(String(12), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow, nullable=True)
    # ok — работает; review — автоматически приостановлена по жалобам кандидатов до проверки
    moderation_status: Mapped[str] = mapped_column(String(20), default="ok", server_default="ok")

    user: Mapped[User] = relationship(back_populates="company")

    @property
    def inn_valid(self) -> bool:
        from app.core.inn import inn_valid
        return inn_valid(self.inn)


class HiringNeed(Base):
    """Потребность работодателя. С флагом is_published это одновременно открытая вакансия."""
    __tablename__ = "hiring_needs"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    specialization: Mapped[str] = mapped_column(String(30))
    grade: Mapped[str] = mapped_column(String(20))
    skills: Mapped[list] = mapped_column(JSON, default=list)
    # [{skill, importance: must|nice, level: basic|confident|expert}]
    requirements: Mapped[list] = mapped_column(JSON, default=list)
    # Настройки скоринга (веса блоков, строгость, фильтры) — см. ranking.ScoringConfig
    scoring: Mapped[dict] = mapped_column(JSON, default=dict)
    salary_from: Mapped[int] = mapped_column(Integer)
    salary_to: Mapped[int] = mapped_column(Integer)
    work_format: Mapped[str] = mapped_column(String(20), default="any")
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    # Когда работодатель последний раз смотрел подборку: всё, что появилось позже, помечается «новым»
    seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ats_external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    company: Mapped[Company] = relationship()


class ShortlistEntry(Base):
    """Сохранённая подборка: уточнение фильтров не теряет уже отобранных кандидатов."""
    __tablename__ = "shortlist_entries"
    __table_args__ = (UniqueConstraint("need_id", "candidate_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    need_id: Mapped[int] = mapped_column(ForeignKey("hiring_needs.id"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Invitation(Base):
    __tablename__ = "invitations"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"), index=True)
    need_id: Mapped[int | None] = mapped_column(ForeignKey("hiring_needs.id"), nullable=True)
    position_title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    salary_from: Mapped[int] = mapped_column(Integer)
    salary_to: Mapped[int] = mapped_column(Integer)
    contact_method: Mapped[str] = mapped_column(String(255))
    status: Mapped[InvitationStatus] = mapped_column(Enum(InvitationStatus), default=InvitationStatus.sent)
    match_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    decline_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    # Кандидат может отозвать доступ к контактам после принятия приглашения
    contacts_revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    offer_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    hired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Флаг защиты от «приманок»: вилка заметно выше рынка категории
    salary_flag: Mapped[str | None] = mapped_column(String(30), nullable=True)

    company: Mapped[Company] = relationship()
    candidate: Mapped[CandidateProfile] = relationship()


class Message(Base):
    """Переписка по приглашению: открывается после отправки приглашения, контакты при этом не раскрываются."""
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    invitation_id: Mapped[int] = mapped_column(ForeignKey("invitations.id"), index=True)
    sender: Mapped[str] = mapped_column(String(10))  # candidate | employer
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("need_id", "candidate_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    need_id: Mapped[int] = mapped_column(ForeignKey("hiring_needs.id"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"), index=True)
    cover_note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[ApplicationStatus] = mapped_column(Enum(ApplicationStatus), default=ApplicationStatus.sent)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    need: Mapped[HiringNeed] = relationship()
    candidate: Mapped[CandidateProfile] = relationship()


class MicroTask(Base):
    """Регулярное короткое задание от работодателя для категории кандидатов."""
    __tablename__ = "micro_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    specialization: Mapped[str] = mapped_column(String(30))
    grade: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    # exact — у задания есть эталон, ответ проверяет система; open — открытый ответ оценивает работодатель
    answer_type: Mapped[str] = mapped_column(String(10), default="open", server_default="open")
    reference_answer: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    company: Mapped[Company] = relationship()


class MicroTaskSubmission(Base):
    __tablename__ = "micro_task_submissions"
    __table_args__ = (UniqueConstraint("task_id", "candidate_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("micro_tasks.id"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"), index=True)
    answer: Mapped[str] = mapped_column(Text)
    employer_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1..5
    auto_checked: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Complaint(Base):
    """Жалоба кандидата на приглашение: основа автоматической приостановки недобросовестных работодателей."""
    __tablename__ = "complaints"
    __table_args__ = (UniqueConstraint("invitation_id", "candidate_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    invitation_id: Mapped[int] = mapped_column(ForeignKey("invitations.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"))
    reason: Mapped[str] = mapped_column(String(30))
    text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AtsConnection(Base):
    """Подключение работодателя к ATS (Huntflow). Токен хранится только на сервере."""
    __tablename__ = "ats_connections"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), unique=True)
    provider: Mapped[str] = mapped_column(String(30), default="huntflow")
    account_id: Mapped[str] = mapped_column(String(64))
    token: Mapped[str] = mapped_column(String(255), default="")
    webhook_secret: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(10), default="mock")  # mock | live
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AtsEvent(Base):
    """Журнал синхронизации с ATS: что и когда ушло или пришло."""
    __tablename__ = "ats_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    direction: Mapped[str] = mapped_column(String(3))  # out | in
    event: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="ok")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
