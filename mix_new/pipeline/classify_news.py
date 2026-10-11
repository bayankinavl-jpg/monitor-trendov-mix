"""Классификация новости: тип изменения, уровень НПА, стадия, тема,
отрасль/ОКВЭД, реквизиты акта — по совпавшим ключевым словам (шаг 5 ТЗ).
Если признак не найден, поле остаётся пустым (None)."""
from __future__ import annotations

import re
from datetime import date

from dateutil import parser as dateutil_parser

from models import AmendmentType, Level
from pipeline.keywords_engine import IndustryGroup, KeywordSet
from pipeline.normalize import normalize_text

_LEVEL_BY_WORD = {
    "решение совета еэк": Level.EAEU,
    "решение коллегии еэк": Level.EAEU,
    "технический регламент": Level.EAEU,
    "федеральный закон": Level.FEDERAL_LAW,
    "законопроект": Level.FEDERAL_LAW,
    "указ президента": Level.UKAZ,
    "постановление правительства": Level.GOV_ACT,
    "распоряжение правительства": Level.GOV_ACT,
    "приказ": Level.DEPT_ORDER,
}

_STAGE_BY_WORD = {
    "проект постановления": "проект",
    "общественное обсуждение": "проект",
    "внесен в госдум": "внесен",
    "первое чтение": "принят в чтении",
    "второе чтение": "принят в чтении",
    "третье чтение": "принят в чтении",
    "госдума приняла": "принят в чтении",
    "совет федерации одобрил": "принят в чтении",
    "подписал закон": "подписан",
    "опубликован": "опубликован",
    "вступает в сил": "вступает в силу",
    "вступил в сил": "вступил в силу",
    "утратил силу": "утратил силу",
}

_AMENDMENT_BY_WORD = {
    "ставк": AmendmentType.RATE_CHANGE,
    "перечень": AmendmentType.LIST_CHANGE,
    "обязан": AmendmentType.NEW_OBLIGATION,
}

_ACT_NUMBER_RE = re.compile(r"№\s*([0-9０-９]+[-\w]*)")
_ACT_DATE_RE = re.compile(r"\bот\s+(\d{1,2}[.\s]\d{1,2}[.\s]\d{2,4}|\d{1,2}\s+\w+\s+\d{4}\s*г\.?)", re.IGNORECASE)


def classify_level(matched: list[tuple[str, str]]) -> Level | None:
    for word, _group in matched:
        level = _LEVEL_BY_WORD.get(normalize_text(word))
        if level is not None:
            return level
    return None


def classify_stage(matched: list[tuple[str, str]]) -> str | None:
    for word, _group in matched:
        stage = _STAGE_BY_WORD.get(normalize_text(word))
        if stage is not None:
            return stage
    return None


def classify_topic(matched: list[tuple[str, str]]) -> str | None:
    topics = [word for word, group in matched if group == "topics"]
    return topics[0] if topics else None


def classify_amendment_type(matched: list[tuple[str, str]]) -> AmendmentType:
    if classify_stage(matched) == "утратил силу":
        return AmendmentType.REPEAL
    for word, group in matched:
        if group != "changes":
            continue
        amendment = _AMENDMENT_BY_WORD.get(normalize_text(word))
        if amendment is not None:
            return amendment
    return AmendmentType.NEW_ACT


def classify_industry(matched: list[tuple[str, str]], keyword_set: KeywordSet) -> tuple[str | None, list[str]]:
    industry_words = {normalize_text(w) for w, g in matched if g == "industries"}
    if not industry_words:
        return None, []
    matched_groups = [
        group for group in keyword_set.industries if industry_words & {normalize_text(w) for w in group.words}
    ]
    if not matched_groups:
        return None, []
    codes = sorted({code for group in matched_groups for code in group.okved})
    return matched_groups[0].label, codes


def extract_act_requisites(text: str) -> tuple[str | None, date | None]:
    number_match = _ACT_NUMBER_RE.search(text)
    number = number_match.group(1) if number_match else None

    date_match = _ACT_DATE_RE.search(text)
    act_date = None
    if date_match:
        try:
            act_date = dateutil_parser.parse(date_match.group(1), dayfirst=True).date()
        except (ValueError, OverflowError):
            act_date = None

    return number, act_date


def classify(title: str, annotation: str, matched: list[tuple[str, str]], keyword_set: KeywordSet) -> dict:
    """Собирает все классификационные поля сразу — удобно для сборки NewsItem."""
    number, act_date = extract_act_requisites(f"{title} {annotation}")
    industry, okved_codes = classify_industry(matched, keyword_set)
    return {
        "amendment_type": classify_amendment_type(matched),
        "level": classify_level(matched),
        "stage": classify_stage(matched),
        "topic": classify_topic(matched),
        "industry": industry,
        "okved_codes": okved_codes,
        "act_number": number,
        "act_date": act_date,
    }
