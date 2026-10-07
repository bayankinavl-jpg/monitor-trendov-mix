"""Классификация кандидата: вид акта, тип поправки, сквозной охват, ОКВЭД."""
from __future__ import annotations

import re
from datetime import date

from config import CROSS_CUTTING_KEYWORDS
from dateutil import parser as dateutil_parser
from mappings.okved_seed import lookup_by_code, lookup_by_keyword
from models import Act, AmendmentType, Level, Stage, Status
from sources.base import CandidateAct

_CODE_PATTERN = re.compile(r"\b\d{4,10}\b")

_ACT_KIND_BY_ISSUER_HINT = {
    "евразийская экономическая комиссия": ("решение", Level.EAEU),
    "еэк": ("решение", Level.EAEU),
    "государственная дума": ("федеральный закон", Level.FEDERAL_LAW),
    "правительство": ("постановление", Level.GOV_ACT),
}


def classify_level_and_kind(candidate: CandidateAct) -> tuple[Level, str]:
    issuer = (candidate.raw_issuing_body or "").lower()
    for hint, (kind, level) in _ACT_KIND_BY_ISSUER_HINT.items():
        if hint in issuer:
            return level, candidate.raw_act_kind or kind
    return Level.DEPT_ORDER, candidate.raw_act_kind or "приказ"


def classify_amendment_type(candidate: CandidateAct, existing: Act | None) -> AmendmentType:
    """Эвристика по ключевым словам применяется независимо от того, есть ли
    уже существующая карточка — заголовок/аннотация сами говорят о сути
    поправки. Отсутствие existing влияет лишь на выбор по умолчанию."""
    text = f"{candidate.raw_title} {candidate.raw_text_excerpt or ''}".lower()
    if "утратил силу" in text or "признать утратившим силу" in text:
        return AmendmentType.REPEAL
    if "ставк" in text:
        return AmendmentType.RATE_CHANGE
    if "перечень" in text:
        return AmendmentType.LIST_CHANGE
    if "обязан" in text:
        return AmendmentType.NEW_OBLIGATION
    return AmendmentType.NEW_ACT


def is_cross_cutting(candidate: CandidateAct) -> bool:
    text = f"{candidate.raw_title} {candidate.raw_text_excerpt or ''}".lower()
    return any(keyword in text for keyword in CROSS_CUTTING_KEYWORDS)


def link_okved(candidate: CandidateAct) -> tuple[list[str], list[str], str | None]:
    text = f"{candidate.raw_title} {candidate.raw_text_excerpt or ''}"
    codes_found: list[str] = []
    for code in _CODE_PATTERN.findall(text):
        mapped = lookup_by_code(code)
        codes_found.extend(mapped)

    if codes_found:
        return sorted(set(codes_found)), [], None

    groups, codes = lookup_by_keyword(text)
    if groups:
        return codes, groups, None

    return [], [], "привязка не определена"


def _try_parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return dateutil_parser.parse(raw, dayfirst=True).date()
    except (ValueError, OverflowError):
        return None


def build_stage_from_candidate(candidate: CandidateAct, amendment_type: AmendmentType) -> Stage:
    adoption = _try_parse_date(candidate.raw_adoption_date)
    if adoption:
        date_text = adoption.strftime("%d.%m.%Y")
    else:
        date_text = "год, дата уточняется"
    return Stage(date_text=date_text, what_changes=amendment_type.value)


def build_act(
    candidate: CandidateAct,
    status: Status,
    source_name: str,
    existing: Act | None,
    unconfirmed_reason: str | None = None,
) -> Act:
    level, act_kind = classify_level_and_kind(candidate)
    amendment_type = classify_amendment_type(candidate, existing)
    cross_cutting = is_cross_cutting(candidate)
    okved_codes, commodity_groups, linkage_note = link_okved(candidate)
    stage = build_stage_from_candidate(candidate, amendment_type)

    summary_bullets = []
    if candidate.raw_text_excerpt:
        summary_bullets = [line.strip("- •\t") for line in candidate.raw_text_excerpt.splitlines() if line.strip()]
    if not summary_bullets and candidate.raw_title:
        summary_bullets = [candidate.raw_title]

    return Act(
        level=level,
        act_kind=act_kind,
        number=candidate.raw_number,
        issuing_body=candidate.raw_issuing_body or "не определено",
        adoption_date=_try_parse_date(candidate.raw_adoption_date),
        publication_date=_try_parse_date(candidate.raw_publication_date),
        title=candidate.raw_title,
        source_url=candidate.source_url if status != Status.UNCONFIRMED else candidate.source_url or None,
        status=status,
        amendment_type=amendment_type,
        summary_bullets=summary_bullets,
        okved_codes=okved_codes,
        cross_cutting=cross_cutting,
        commodity_groups=commodity_groups,
        page_count=candidate.page_count,
        stages=[stage],
        linkage_note=linkage_note,
        unconfirmed_reason=unconfirmed_reason,
        source_name=source_name,
    )
