"""Поиск уже существующей карточки (точное совпадение natural_key либо
fuzzy-сопоставление проекта без номера с уже принятым актом) и эвристика
«это только продление срока — не нужна новая карточка»."""
from __future__ import annotations

import difflib
import sqlite3

from config import DEADLINE_EXTENSION_KEYWORDS
from models import Act, Level
from registry.db import compute_natural_key, find_candidates_for_fuzzy_match, get_act_by_natural_key
from sources.base import CandidateAct

FUZZY_TITLE_THRESHOLD = 0.75


def find_existing(conn: sqlite3.Connection, level: Level, act_kind: str, issuing_body: str, number: str | None, title: str) -> Act | None:
    natural_key = compute_natural_key(level, act_kind, issuing_body, number, title)
    exact = get_act_by_natural_key(conn, natural_key)
    if exact is not None:
        return exact

    if not number:
        return None

    # Номер появился впервые (проект → принят) — ищем среди безномерных черновиков.
    for draft in find_candidates_for_fuzzy_match(conn, level, act_kind, issuing_body):
        score = difflib.SequenceMatcher(None, title.lower(), draft.title.lower()).ratio()
        if score >= FUZZY_TITLE_THRESHOLD:
            return draft
    return None


def is_deadline_extension(existing: Act | None, candidate: CandidateAct) -> bool:
    if existing is None:
        return False
    text = f"{candidate.raw_title} {candidate.raw_text_excerpt or ''}".lower()
    has_extension_keyword = any(keyword.split(" ... ")[0] in text for keyword in DEADLINE_EXTENSION_KEYWORDS)
    if not has_extension_keyword:
        return False
    # Эвристика: ссылается на тот же номер/название, что и существующий акт.
    if existing.number and existing.number in (candidate.raw_title + " " + (candidate.raw_text_excerpt or "")):
        return True
    title_similarity = difflib.SequenceMatcher(None, existing.title.lower(), candidate.raw_title.lower()).ratio()
    return title_similarity >= 0.5
