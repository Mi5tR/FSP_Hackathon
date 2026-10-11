"""Стандартизированный PDF-профиль кандидата (п. 2.1 ТЗ: «автогенерация стандартизированного PDF-профиля»).

Один шаблон для всех: категория и статус грейда, навыки, подтверждённые тестом (с уровнем), заявленные навыки,
достижения ФСП, история тестирования. Для работодателя без раскрытых контактов — обезличенная версия.
Шрифт — JetBrains Mono (фирменный шрифт ФСП, SIL OFL 1.1), лежит в app/assets/fonts.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fpdf import FPDF

from app.core.catalog import GRADE_TITLES, SPEC_TITLES
from app.core.skills import SKILL_TITLES
from app.models.entities import Assessment, CandidateProfile

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
BRAND = (64, 47, 255)
ACCENT = (236, 29, 53)
INK = (27, 28, 33)
MUTED = (92, 93, 102)
LINE = (227, 227, 232)
OK = (18, 122, 63)
WARN = (143, 82, 0)
WORK_FORMAT = {"office": "офис", "remote": "удалённо", "hybrid": "гибрид", "any": "любой"}
OUTCOME = {"confirmed": "подтверждён", "upgrade_eligible": "подтверждён уверенно", "not_confirmed": "не подтверждён",
           "skill_checked": "навык проверен"}


class _Pdf(FPDF):
    note = ""

    def footer(self):
        self.set_y(-15)
        self.set_font("JB", "", 6.5)
        self.set_text_color(*MUTED)
        self.multi_cell(0, 3.6, f"{self.note}\nФСП Карьера · стандартизированный профиль · стр. {self.page_no()}", align="C")


def _section(pdf: FPDF, title: str) -> None:
    pdf.ln(4)
    pdf.set_font("JB", "B", 11)
    pdf.set_text_color(*BRAND)
    pdf.cell(6, 7, "//")
    pdf.set_text_color(*INK)
    pdf.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*LINE)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(2)


def _kv(pdf: FPDF, key: str, value: str) -> None:
    pdf.set_font("JB", "", 9)
    pdf.set_text_color(*MUTED)
    pdf.cell(48, 6, key)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 6, value or "—", new_x="LMARGIN", new_y="NEXT")


def build_profile_pdf(c: CandidateProfile, history: list[Assessment], *, anonymous: bool) -> bytes:
    pdf = _Pdf(format="A4")
    pdf.note = (f"Сформировано {datetime.now():%d.%m.%Y %H:%M}. Грейд присваивается только по результатам адаптивного теста; "
                "достижения ФСП импортированы из реестра через ФСП ID." + (" Контакты скрыты до согласия кандидата." if anonymous else ""))
    pdf.add_font("JB", "", str(FONTS / "JetBrainsMono-Regular.ttf"))
    pdf.add_font("JB", "B", str(FONTS / "JetBrainsMono-Bold.ttf"))
    pdf.set_auto_page_break(True, margin=20)
    pdf.set_margins(16, 16, 16)
    pdf.add_page()

    # Шапка: тёмная полоса бренда с красным акцентом
    pdf.set_fill_color(*INK)
    pdf.rect(0, 0, pdf.w, 34, "F")
    pdf.set_fill_color(*BRAND)
    pdf.rect(0, 34, pdf.w * 0.78, 1.6, "F")
    pdf.set_fill_color(*ACCENT)
    pdf.rect(pdf.w * 0.78, 34, pdf.w * 0.22, 1.6, "F")
    pdf.set_xy(16, 9)
    pdf.set_font("JB", "B", 18)
    pdf.set_text_color(255, 255, 255)
    name = f"Кандидат #{c.id}" if anonymous or not c.full_name else c.full_name
    pdf.cell(0, 9, name, new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(16)
    pdf.set_font("JB", "", 9)
    pdf.set_text_color(185, 186, 194)
    pdf.cell(0, 6, "ФСП Карьера · профиль, подтверждённый тестированием", new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(42)

    # Категория
    if c.grade and c.specialization:
        cat = f"{SPEC_TITLES.get(c.specialization, c.specialization)} · {GRADE_TITLES.get(c.grade, c.grade)}"
        status, color = ("подтверждён тестом", OK) if c.grade_confirmed is not False else ("заявлен, тестом не подтверждён", WARN)
    else:
        cat, status, color = "категория не присвоена", "тест не пройден", WARN
    pdf.set_font("JB", "B", 14)
    pdf.set_text_color(*BRAND)
    pdf.cell(0, 8, cat, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("JB", "", 9)
    pdf.set_text_color(*color)
    extra = f" · θ = {c.theta:.2f} ± {c.theta_se:.2f}" if c.theta is not None and c.theta_se is not None else ""
    pdf.cell(0, 6, f"Грейд: {status}{extra}", new_x="LMARGIN", new_y="NEXT")

    _section(pdf, "Основное")
    p = c.privacy or {}

    def shown(key: str) -> bool:
        # Свой профиль кандидат видит полностью; обезличенная версия соблюдает его настройки приватности
        return not anonymous or p.get(key, True)

    if not anonymous:
        _kv(pdf, "Email", c.contact_email or "")
        _kv(pdf, "Телефон", c.phone or "")
        _kv(pdf, "Telegram", c.telegram or "")
    if shown("show_city"):
        _kv(pdf, "Город", c.city or "")
    if shown("show_experience"):
        _kv(pdf, "Стаж", f"{c.experience_years:g} г." if c.experience_years else "")
    _kv(pdf, "Формат работы", WORK_FORMAT.get(c.work_format, c.work_format))
    if c.roles:
        _kv(pdf, "Роли", ", ".join(c.roles))
    if c.soft_skills:
        _kv(pdf, "Софт-скиллы", ", ".join(c.soft_skills))
    if c.age is not None and c.age < 18:
        _kv(pdf, "Возраст", "до 18 лет: только лёгкий труд (ст. 63 ТК РФ), согласие представителя получено")

    _section(pdf, "Навыки, подтверждённые тестом")
    verified = sorted((c.verified_skills or {}).items(), key=lambda x: -x[1])
    if not verified:
        _kv(pdf, "—", "тест ещё не пройден")
    bar_x, bar_w = 16 + 62, 80
    for skill, level in verified:
        pdf.set_font("JB", "", 9)
        pdf.set_text_color(*INK)
        pdf.cell(62, 6, SKILL_TITLES.get(skill, skill))
        y = pdf.get_y() + 2
        pdf.set_fill_color(*LINE)
        pdf.rect(bar_x, y, bar_w, 2.2, "F")
        pdf.set_fill_color(*(OK if level >= 0.6 else BRAND if level >= 0.4 else WARN))
        pdf.rect(bar_x, y, bar_w * max(0.02, min(1, level)), 2.2, "F")
        pdf.set_x(bar_x + bar_w + 4)
        pdf.set_text_color(*MUTED)
        pdf.cell(0, 6, f"{level:.0%}", new_x="LMARGIN", new_y="NEXT")
    declared = [s for s in (c.declared_skills or []) if s not in (c.verified_skills or {})]
    if declared:
        pdf.ln(1)
        _kv(pdf, "Заявлено в резюме", ", ".join(SKILL_TITLES.get(s, s) for s in declared) + "  (не проверено тестом)")

    show_fsp = shown("show_fsp")
    _section(pdf, "Достижения ФСП")
    if c.fsp_id and show_fsp and c.achievements:
        if not anonymous:
            _kv(pdf, "ФСП ID", c.fsp_id)
        for a in c.achievements:
            place = f"{a.place} место" + (f" из {a.participants}" if a.participants else "") if a.place else "участие"
            role = f", роль: {a.role_in_team}" if a.role_in_team else ""
            _kv(pdf, (a.event_date or "")[:7], f"{a.event_name} — {place}{role}")
    else:
        _kv(pdf, "—", "истории соревнований нет: профиль оценивается по тесту и заданиям")

    _section(pdf, "История тестирования")
    rows = [a for a in history if a.finished_at]
    if not rows:
        _kv(pdf, "—", "попыток нет")
    for a in rows:
        what = f"навык {SKILL_TITLES.get(a.skill, a.skill)}" if a.kind == "skill" else \
            f"{SPEC_TITLES.get(a.specialization, a.specialization)}, заявлено {GRADE_TITLES.get(a.claimed_grade, a.claimed_grade)}"
        _kv(pdf, a.finished_at.strftime("%d.%m.%Y"), f"{what}: {OUTCOME.get(a.outcome or '', a.outcome or '')}")

    if c.about and shown("show_about"):
        _section(pdf, "О себе")
        pdf.set_font("JB", "", 9)
        pdf.set_text_color(*INK)
        pdf.multi_cell(0, 5.5, c.about)

    return bytes(pdf.output())
