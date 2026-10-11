"""Авто-оценка достоверности записи (шаг 6 ТЗ). Ручной проверки нет,
поэтому оценка считается по признакам, и у каждой оценки сохраняется
список оснований. Это оценка доверия к новости, а не сверка с текстом
акта: текст акта программа не читает."""
from __future__ import annotations

from datetime import date

from models import Credibility

OFFICIAL = "official_publication"
LEGAL = "legal"
PUBLICATION_STAGES = {"опубликован", "подписан"}


def assess_credibility(
    trust_tiers: list[str],
    act_number: str | None,
    act_date: date | None,
    independent_source_count: int,
    stage: str | None = None,
    referenced_acts: list[str] | None = None,
) -> tuple[Credibility, list[str]]:
    referenced_acts = referenced_acts or []
    has_requisites = bool(act_number and act_date)
    is_official = OFFICIAL in trust_tiers
    is_legal = LEGAL in trust_tiers
    several_sources = independent_source_count >= 2

    reasons = []
    if is_official:
        reasons.append("источник — официальное издание (Российская газета или Парламентская газета)")
    if is_legal:
        reasons.append("источник — правовая система (Гарант или КонсультантПлюс)")
    if has_requisites:
        reasons.append(f"в тексте есть номер и дата акта: № {act_number} от {act_date:%d.%m.%Y}")
    elif act_number:
        reasons.append(f"в тексте есть номер акта без даты: № {act_number}")
    if stage:
        reasons.append(f"стадия документа: {stage}")
    reasons.append(f"независимых СМИ: {independent_source_count}")
    for name in referenced_acts:
        reasons.append(f"упомянут известный акт: {name}")

    if is_official and (has_requisites or stage in PUBLICATION_STAGES):
        level = Credibility.HIGH
    elif is_legal and has_requisites:
        level = Credibility.HIGH
    elif several_sources and (has_requisites or referenced_acts):
        level = Credibility.MEDIUM
    elif is_official or is_legal:
        level = Credibility.MEDIUM
    else:
        level = Credibility.LOW

    return level, reasons
