"""Классификация новости: тип изменения, уровень НПА, стадия, тема,
отрасль/ОКВЭД, реквизиты акта — по совпавшим ключевым словам (шаг 5 ТЗ).
Если признак не найден, поле остаётся пустым (None)."""
from __future__ import annotations

import re
from datetime import date

from models import AmendmentType, Level
from pipeline.act_reference import find_referenced_acts
from pipeline.keywords_engine import IndustryGroup, KeywordSet
from pipeline.normalize import normalize_text

_LEVEL_BY_WORD = {
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
    "внесен в госдуму": "внесен",
    "первое чтение": "принят в чтении",
    "второе чтение": "принят в чтении",
    "третье чтение": "принят в чтении",
    "госдума приняла": "принят в чтении",
    "совет федерации одобрил": "принят в чтении",
    "подписал закон": "подписан",
    "опубликован": "опубликован",
    "вступает в силу": "вступает в силу",
    "вступил в силу": "вступил в силу",
    "утратил силу": "утратил силу",
}

_AMENDMENT_BY_WORD = {
    "ставка": AmendmentType.RATE_CHANGE,
    "перечень": AmendmentType.LIST_CHANGE,
    "обязан": AmendmentType.NEW_OBLIGATION,
    "обязанность": AmendmentType.NEW_OBLIGATION,
}

_ACT_NUMBER_RE = re.compile(r"№\s*(\d+(?:-[\w]+)?)|(?<![\w-])(\d{1,4}-(?:ФКЗ|ФЗ|рп))(?!\w)", re.IGNORECASE)
_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
_ACT_DATE_NUMERIC_RE = re.compile(r"\bот\s+(\d{1,2})\.(\d{1,2})\.(\d{4})")
_ACT_DATE_WORDS_RE = re.compile(r"\bот\s+(\d{1,2})\s+(" + "|".join(_MONTHS) + r")\s+(\d{4})", re.IGNORECASE)


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


def _safe_date(year: str, month: int, day: str) -> date | None:
    try:
        return date(int(year), month, int(day))
    except ValueError:
        return None


def extract_act_requisites(text: str) -> tuple[str | None, date | None]:
    number_match = _ACT_NUMBER_RE.search(text)
    number = (number_match.group(1) or number_match.group(2)) if number_match else None

    act_date = None
    numeric = _ACT_DATE_NUMERIC_RE.search(text)
    if numeric:
        act_date = _safe_date(numeric.group(3), int(numeric.group(2)), numeric.group(1))
    else:
        words = _ACT_DATE_WORDS_RE.search(text)
        if words:
            act_date = _safe_date(words.group(3), _MONTHS[words.group(2).lower()], words.group(1))

    return number, act_date


def classify(title: str, annotation: str, matched: list[tuple[str, str]], keyword_set: KeywordSet) -> dict:
    """Собирает все классификационные поля сразу — удобно для сборки NewsItem."""
    text = f"{title} {annotation}"
    number, act_date = extract_act_requisites(text)
    industry, okved_codes = classify_industry(matched, keyword_set)
    referenced_acts = [act.name for act in find_referenced_acts(text, act_date)]
    return {
        "amendment_type": classify_amendment_type(matched),
        "level": classify_level(matched),
        "stage": classify_stage(matched),
        "topic": classify_topic(matched),
        "industry": industry,
        "okved_codes": okved_codes,
        "act_number": number,
        "act_date": act_date,
        "referenced_acts": referenced_acts,
    }
