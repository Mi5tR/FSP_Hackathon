"""Разбор свободного текста (описание потребности работодателя, текст резюме)
в структурированные признаки.

Разбор детерминированный и объяснимый: работодатель видит, какие требования
система извлекла, и правит их. Подключение LLM предусмотрено как замена
`parse_need` с тем же контрактом.
"""

from __future__ import annotations

import re

from app.core.catalog import GRADE_SYNONYMS, SPEC_SYNONYMS, SPECIALIZATIONS
from app.core.skills import GRADE_DEFAULT_LEVEL, SKILL_TITLES, ancestors, find_skills

NICE_MARKERS = ("желательн", "будет плюсом", "плюсом будет", "как плюс", "приветствует", "nice to have",
                "преимуществ", "опционально", "было бы здорово", "хорошо, если")
EXPERT_MARKERS = ("глубок", "эксперт", "отличн", "продвинут", "сильн", "в совершенстве", "архитектурн")
BASIC_MARKERS = ("базов", "знакомств", "основ", "начальн", "общее представление", "понимани")


def _norm(text: str) -> str:
    return " " + re.sub(r"\s+", " ", text.lower().replace("ё", "е")) + " "


def _hits(text: str, synonyms: dict[str, list[str]]) -> dict[str, int]:
    t = _norm(text)
    return {k: n for k, words in synonyms.items() if (n := sum(t.count(w) for w in words))}


def extract_skills(text: str) -> list[str]:
    return sorted(find_skills(text))


def extract_salary(text: str) -> tuple[int | None, int | None]:
    t = text.lower().replace(" ", " ")
    nums = []
    for m in re.finditer(r"(\d[\d ]{1,9})\s*(к|k|тыс|000)?", t):
        raw = int(m.group(1).replace(" ", ""))
        if m.group(2) in ("к", "k", "тыс"):
            raw *= 1000
        if 20_000 <= raw <= 5_000_000:
            nums.append(raw)
    if not nums:
        return None, None
    if len(nums) == 1:
        return nums[0], None
    return min(nums[:2]), max(nums[:2])


def _sentences(text: str) -> list[str]:
    # Точка режет предложение только перед пробелом или концом строки: «Next.js» остаётся целым
    return [s for s in re.split(r"[.;!](?=\s|$)|[\n•]|\s-\s", text) if s.strip()]


def extract_requirements(text: str, grade: str | None) -> list[dict]:
    """Требования по навыкам с важностью (must/nice) и уровнем.

    Важность и уровень определяются по маркерам внутри того же предложения:
    «будет плюсом Docker» → nice; «глубокое знание SQL» → expert.
    Если маркеров нет — must и уровень по умолчанию для грейда вакансии.
    """
    default_level = GRADE_DEFAULT_LEVEL.get(grade or "middle", "confident")
    reqs: dict[str, dict] = {}
    for sent in _sentences(text):
        found = find_skills(sent)
        if not found:
            continue
        s = _norm(sent)
        nice = any(m in s for m in NICE_MARKERS)
        level = ("expert" if any(m in s for m in EXPERT_MARKERS)
                 else "basic" if any(m in s for m in BASIC_MARKERS) else default_level)
        for code in found:
            prev = reqs.get(code)
            # Если навык упомянут и как обязательный, и как желательный — считаем обязательным
            if prev and prev["importance"] == "must" and nice:
                continue
            reqs[code] = {"skill": code, "title": SKILL_TITLES[code],
                          "importance": "nice" if nice else "must", "level": level}
    # «Python (FastAPI)» → требование FastAPI: родитель подразумевается и проверяется через
    # подкрепление (тест по Python + FastAPI в резюме), отдельное требование его бы дублировало
    implied = {a for code, r in reqs.items() for a in ancestors(code)
               if a in reqs and (reqs[a]["importance"] == r["importance"] or reqs[a]["importance"] == "nice")}
    out = [r for code, r in reqs.items() if code not in implied]
    return sorted(out, key=lambda r: (r["importance"] != "must", r["skill"]))


def parse_need(text: str) -> dict:
    spec_hits = _hits(text, SPEC_SYNONYMS)
    grade_hits = _hits(text, GRADE_SYNONYMS)
    skills = extract_skills(text)
    spec = max(spec_hits, key=spec_hits.get) if spec_hits else None
    if spec is None and skills:
        # Специализация не названа явно — выводим по стеку
        scores = {s["code"]: len(set(skills) & set(s["skills"])) for s in SPECIALIZATIONS}
        spec = max(scores, key=scores.get) if max(scores.values()) else None
    # «Middle+» содержит и «middle»: промежуточный грейд, если назван, приоритетнее базового
    grade = max(grade_hits, key=lambda g: (grade_hits[g], g.endswith("_plus"))) if grade_hits else None
    if grade and not grade.endswith("_plus") and f"{grade}_plus" in grade_hits:
        grade = f"{grade}_plus"
    sal_from, sal_to = extract_salary(text)
    t = _norm(text)
    work_format = ("remote" if "удален" in t or "remote" in t else
                   "hybrid" if "гибрид" in t else "office" if "офис" in t else "any")
    return {
        "specialization": spec,
        "grade": grade,
        "skills": skills,
        "requirements": extract_requirements(text, grade),
        "salary_from": sal_from,
        "salary_to": sal_to,
        "work_format": work_format,
        "detected": {"specialization": spec_hits, "grade": grade_hits},
        **_ml_suggestions(text, skills),
    }


def _ml_suggestions(text: str, skills: list[str]) -> dict:
    """NLP-подсказки поверх словаря: навыки с опечатками и транслитом, вероятная специализация."""
    from app.services.ml import fuzzy_skills, predict_specialization

    fuzzy = {k: v for k, v in fuzzy_skills(text).items() if k not in skills}
    return {
        "suggested_skills": [{"skill": k, "title": SKILL_TITLES[k], "matched": v} for k, v in fuzzy.items()],
        "specialization_ml": predict_specialization(text),
    }


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?:\+7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}")
_TG = re.compile(r"(?:t\.me/|telegram[:\s]+|@)([A-Za-z][\w]{4,31})")
_EXP = re.compile(r"(?:опыт|стаж)[^\d]{0,20}(\d{1,2})(?:[.,](\d))?\s*(?:год|лет|года)", re.I)
_SOFT = {"коммуникаб": "коммуникабельность", "ответствен": "ответственность", "командн": "работа в команде",
         "лидер": "лидерство", "наставни": "наставничество", "менторств": "наставничество",
         "самоорганиз": "самоорганизация", "обучаем": "обучаемость"}


def parse_resume(text: str) -> dict:
    """Автораспознавание полей резюме из текста PDF."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    name = next((ln for ln in lines[:5] if re.fullmatch(r"[А-ЯЁA-Z][а-яёa-z]+(?: [А-ЯЁA-Z][а-яёa-z]+){1,2}", ln)), None)
    exp = _EXP.search(text)
    tg = _TG.search(text)
    need = parse_need(text)
    t = _norm(text)
    return {
        "full_name": name,
        "contact_email": (_EMAIL.search(text) or [None])[0],
        "phone": (_PHONE.search(text) or [None])[0],
        "telegram": tg.group(1) if tg else None,
        "experience_years": float(f"{exp.group(1)}.{exp.group(2) or 0}") if exp else None,
        "declared_skills": need["skills"],
        "specialization_guess": need["specialization"] or (need["specialization_ml"][0]["specialization"]
                                                           if need["specialization_ml"] else None),
        "specialization_ml": need["specialization_ml"],
        "suggested_skills": need["suggested_skills"],
        "grade_guess": need["grade"],
        "soft_skills": sorted({label for stem, label in _SOFT.items() if stem in t}),
    }
