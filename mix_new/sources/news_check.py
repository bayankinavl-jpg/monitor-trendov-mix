"""Проверка новостных наводок на первоисточниках.

Новость сама по себе никогда не основание для карточки (правило проверки
из ТЗ). Эта проверка — единственный мост между новостным сигналом и
карточкой: если наводка находит соответствие у источника-первоисточника,
кандидат идёт в пайплайн как обычно (с source_name="news_verified" и
source_url с первоисточника, а не из новости). Если соответствие не
найдено — наводка сохраняется со статусом "не подтверждено"."""
from __future__ import annotations

import difflib
from dataclasses import dataclass
from datetime import date, timedelta

from sources.base import CandidateAct
from sources.news_scan import NewsLead

FUZZY_MATCH_THRESHOLD = 0.6
DATE_WINDOW_PAD_DAYS = 30


@dataclass
class VerificationResult:
    confirmed: bool
    candidate: CandidateAct | None
    reason: str | None


def verify_lead(
    lead: NewsLead, candidate_pool: list[CandidateAct], unreachable_notes: list[str] | None = None
) -> VerificationResult:
    """Ищет наводку в уже загруженном пуле кандидатов первоисточников (fuzzy
    по заголовку). Пул должен быть собран ОДИН раз за весь прогон (см.
    runner.py) — повторный сетевой запрос на каждую наводку был бы слишком
    медленным (десятки секунд таймаута умножаются на число наводок)."""
    match = _best_match(lead.title, candidate_pool)
    if match is not None:
        return VerificationResult(confirmed=True, candidate=match, reason=None)

    if unreachable_notes:
        reason = "первоисточники недоступны для проверки: " + "; ".join(unreachable_notes)
    else:
        reason = "наводка не найдена ни на одном первоисточнике (pravo.gov.ru, regulation.gov.ru)"
    return VerificationResult(confirmed=False, candidate=None, reason=reason)


def _best_match(title: str, candidates: list[CandidateAct]) -> CandidateAct | None:
    best_score = 0.0
    best_candidate: CandidateAct | None = None
    for candidate in candidates:
        score = difflib.SequenceMatcher(None, title.lower(), candidate.raw_title.lower()).ratio()
        if score > best_score:
            best_score = score
            best_candidate = candidate
    if best_score >= FUZZY_MATCH_THRESHOLD:
        return best_candidate
    return None


def verify_lead_manual(
    title_hint: str, number_hint: str | None, date_hint: str | None, primary_sources: list
) -> VerificationResult:
    """Ручная проверка одной наводки через CLI (verify-lead). Здесь разовый
    сетевой запрос оправдан — вызывается один раз человеком, не в цикле."""
    from sources.base import SourceUnreachableError

    fake_lead = NewsLead(title=title_hint, link="", published=None, feed_name="manual")
    if date_hint:
        from dateutil import parser as dateutil_parser

        try:
            fake_lead.published = dateutil_parser.parse(date_hint).date()
        except ValueError:
            pass

    anchor = fake_lead.published or date.today()
    since = anchor - timedelta(days=DATE_WINDOW_PAD_DAYS)
    until = anchor + timedelta(days=DATE_WINDOW_PAD_DAYS)

    pool: list[CandidateAct] = []
    unreachable_notes: list[str] = []
    for source in primary_sources:
        try:
            pool.extend(source.fetch_candidates(since, until))
        except SourceUnreachableError as exc:
            unreachable_notes.append(f"{source.name}: {exc}")

    return verify_lead(fake_lead, pool, unreachable_notes)
