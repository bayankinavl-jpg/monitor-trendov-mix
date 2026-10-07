"""Отбор по периметру задачи: ведомства, период, отбрасывание не-нормативных актов.

Эвристики ключевых слов — не точный классификатор; ожидаются ложные
отрицания/срабатывания, уточняется по мере обработки реальных актов."""
from __future__ import annotations

from datetime import date

from config import DISCARD_KEYWORDS, ISSUER_WHITELIST
from sources.base import CandidateAct


def is_in_scope_issuer(candidate: CandidateAct) -> bool:
    issuer = (candidate.raw_issuing_body or "").lower()
    if not issuer:
        return False
    return any(whitelisted.lower() in issuer for whitelisted in ISSUER_WHITELIST)


def in_discovery_window(candidate: CandidateAct, since: date, until: date) -> bool:
    """Фильтр по дате обнаружения прогона (для смок-теста и обычных запусков) —
    отличается от окна вступления в силу 2026-2028, которое проверяется позже,
    при построении этапов вступления в силу (см. runner.py/classify.py)."""
    from dateutil import parser as dateutil_parser

    raw_date = candidate.raw_publication_date or candidate.raw_adoption_date
    if not raw_date:
        return True  # не отбрасываем из-за отсутствия даты — это проверится на этапе verify
    try:
        parsed = dateutil_parser.parse(raw_date, dayfirst=True).date()
    except (ValueError, OverflowError):
        return True
    return since <= parsed <= until


def is_discardable(candidate: CandidateAct) -> tuple[bool, str | None]:
    text = f"{candidate.raw_title} {candidate.raw_text_excerpt or ''}".lower()
    for keyword in DISCARD_KEYWORDS:
        stems = keyword if isinstance(keyword, tuple) else (keyword,)
        if all(stem in text for stem in stems):
            label = " + ".join(stems)
            return True, f"не нормативное изменение по признаку: «{label}»"
    return False, None
