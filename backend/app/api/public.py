from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import Grade, Spec, VacancyOut
from app.core.catalog import GRADES, INDUSTRIES, SPECIALIZATIONS, SURVEY, SURVEY_SCALE
from app.core.skills import LEVEL_TITLES, tree
from app.services.testing.cat import testable_root
from app.core.db import get_db
from app.models.entities import HiringNeed
from app.services.testing.item_bank import BANK

router = APIRouter(tags=["public"])


@router.get("/catalog")
def catalog():
    """Справочник отраслей, специализаций, грейдов и навыков."""
    skills = [{**s, "testable_as": testable_root(s["code"])} for s in tree()]
    return {"industries": INDUSTRIES, "specializations": SPECIALIZATIONS,
            "grades": [{k: v for k, v in g.items() if k != "theta_min"} for g in GRADES],
            "skills": skills, "levels": LEVEL_TITLES, "survey": SURVEY, "survey_scale": SURVEY_SCALE}


@router.get("/catalog/item-bank")
def item_bank_overview():
    """Открытое описание банка семейств заданий (без вариантов и ответов) — для прозрачности механики."""
    return [{"id": f.id, "title": f.title, "skill": f.skill, "specializations": f.specs,
             "difficulty_b": f.b, "discrimination_a": f.a} for f in BANK]


@router.get("/vacancies", response_model=list[VacancyOut])
def vacancies(specialization: Spec | None = None, grade: Grade | None = None, db: Session = Depends(get_db)):
    from app.models.entities import Company
    # Вакансии компаний, приостановленных по жалобам, скрываются до проверки
    q = (select(HiringNeed).join(Company, Company.id == HiringNeed.company_id)
         .where(HiringNeed.is_published.is_(True), Company.moderation_status != "review"))
    if specialization:
        q = q.where(HiringNeed.specialization == specialization)
    if grade:
        q = q.where(HiringNeed.grade == grade)
    rows = db.scalars(q.order_by(HiringNeed.id.desc()).limit(200))
    return [VacancyOut(**{c: getattr(n, c) for c in VacancyOut.model_fields if c != "company_name"},
                       company_name=n.company.name) for n in rows]


@router.get("/stats")
def platform_stats(db: Session = Depends(get_db)):
    """Обезличенная статистика платформы для главной страницы: только агрегаты, без персональных данных."""
    from sqlalchemy import func

    from app.models.entities import CandidateProfile, Company, FspAchievement, Invitation, InvitationStatus

    visible = [c for c in db.scalars(select(CandidateProfile).where(CandidateProfile.grade.is_not(None)))
               if c.is_visible]
    by_cat: dict[tuple[str, str], int] = {}
    for c in visible:
        by_cat[(c.specialization, c.grade)] = by_cat.get((c.specialization, c.grade), 0) + 1
    inv_total = db.scalar(select(func.count()).select_from(Invitation)) or 0
    inv_acc = db.scalar(select(func.count()).select_from(Invitation).where(
        Invitation.status == InvitationStatus.accepted)) or 0
    return {
        "candidates": len(visible),
        "confirmed": sum(1 for c in visible if c.grade_confirmed is not False),
        "with_fsp": sum(1 for c in visible if c.fsp_id),
        "achievements": db.scalar(select(func.count()).select_from(FspAchievement)) or 0,
        "companies": db.scalar(select(func.count()).select_from(Company).where(Company.name != "")) or 0,
        "vacancies": db.scalar(select(func.count()).select_from(HiringNeed).where(HiringNeed.is_published.is_(True))) or 0,
        "item_families": len(BANK),
        "invitations": inv_total,
        "acceptance_rate": round(inv_acc / inv_total, 2) if inv_total else None,
        "categories": [{"specialization": s, "grade": g, "count": n} for (s, g), n in sorted(by_cat.items())],
    }
