"""Оценка достоверности записи (шаг 6 ТЗ)."""
from __future__ import annotations

from datetime import date

from models import Credibility


def assess_credibility(
    trust_tiers: list[str], act_number: str | None, act_date: date | None, independent_source_count: int
) -> Credibility:
    has_requisites = bool(act_number and act_date)

    if "official_publication" in trust_tiers:
        return Credibility.HIGH
    if "legal" in trust_tiers and has_requisites:
        return Credibility.HIGH

    if has_requisites and independent_source_count >= 2:
        return Credibility.MEDIUM

    return Credibility.LOW
