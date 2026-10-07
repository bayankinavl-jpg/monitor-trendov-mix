"""Оркестратор: fetch → filter → verify → classify/dedupe → upsert, с
журналированием по каждому источнику."""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from models import Status
from pipeline.classify import build_act
from pipeline.dedupe import find_existing, is_deadline_extension
from pipeline.filters import in_discovery_window, is_discardable, is_in_scope_issuer
from pipeline.verify import verify_primary_source
from registry.db import update_stages_and_status, upsert_act, write_journal_entry
from sources.base import CandidateAct, SourceClient, SourceUnreachableError
from sources.news_check import verify_lead
from sources.news_scan import scan_all_feeds


@dataclass
class SourceRunStats:
    source_name: str
    found: int = 0
    discarded: int = 0
    unconfirmed: int = 0
    errors: int = 0
    unreachable: bool = False
    detail: dict = field(default_factory=dict)


@dataclass
class RunSummary:
    run_id: str
    stats: list[SourceRunStats] = field(default_factory=list)


def run_direct_sources(
    conn: sqlite3.Connection, sources: list[SourceClient], since: date, until: date, run_id: str
) -> list[SourceRunStats]:
    results = []
    for source in sources:
        stats = SourceRunStats(source_name=source.name)
        started_at = datetime.now(timezone.utc).isoformat()
        try:
            candidates = source.fetch_candidates(since, until)
        except SourceUnreachableError as exc:
            stats.unreachable = True
            stats.detail["error"] = str(exc)
            _flush_stats(conn, run_id, stats, started_at)
            results.append(stats)
            continue
        except Exception as exc:  # неожиданная ошибка одного источника не должна рушить весь прогон
            stats.errors += 1
            stats.detail["unexpected_error"] = str(exc)
            _flush_stats(conn, run_id, stats, started_at)
            results.append(stats)
            continue

        _process_candidates(conn, candidates, source.name, since, until, stats)
        _flush_stats(conn, run_id, stats, started_at)
        results.append(stats)
    return results


def run_news_signal_pipeline(
    conn: sqlite3.Connection, primary_sources: list[SourceClient], since: date, until: date, run_id: str
) -> SourceRunStats:
    stats = SourceRunStats(source_name="news_scan")
    started_at = datetime.now(timezone.utc).isoformat()

    leads, feed_errors = scan_all_feeds(since, until)
    if feed_errors:
        stats.detail["feed_errors"] = feed_errors

    # Кандидаты первоисточников собираются ОДИН раз за весь прогон (а не на
    # каждую наводку) — иначе таймауты недоступных источников умножаются на
    # число наводок и прогон может занимать неприемлемо долго.
    candidate_pool: list[CandidateAct] = []
    unreachable_notes: list[str] = []
    for source in primary_sources:
        try:
            candidate_pool.extend(source.fetch_candidates(since, until))
        except SourceUnreachableError as exc:
            unreachable_notes.append(f"{source.name}: {exc}")
    if unreachable_notes:
        stats.detail["primary_sources_unreachable"] = unreachable_notes

    for lead in leads:
        result = verify_lead(lead, candidate_pool, unreachable_notes)
        if result.confirmed and result.candidate is not None:
            candidate = result.candidate
            candidate_stats_name = "news_verified"
            existing = find_existing(conn, *_level_kind_issuer_for(candidate), candidate.raw_number, candidate.raw_title)
            if is_deadline_extension(existing, candidate):
                _apply_deadline_extension(conn, existing, candidate)
                stats.found += 1
                continue
            act = build_act(candidate, Status.ADOPTED, candidate_stats_name, existing)
            upsert_act(conn, act)
            stats.found += 1
        else:
            act = build_act(
                CandidateAct(
                    raw_title=lead.title,
                    raw_number=None,
                    raw_act_kind=None,
                    raw_issuing_body=None,
                    raw_adoption_date=lead.published.isoformat() if lead.published else None,
                    raw_publication_date=None,
                    source_url=lead.link,
                ),
                Status.UNCONFIRMED,
                "news_unconfirmed",
                None,
                unconfirmed_reason=result.reason,
            )
            upsert_act(conn, act)
            stats.unconfirmed += 1

    _flush_stats(conn, run_id, stats, started_at)
    return stats


def _level_kind_issuer_for(candidate: CandidateAct):
    from pipeline.classify import classify_level_and_kind

    level, kind = classify_level_and_kind(candidate)
    return level, kind, candidate.raw_issuing_body or "не определено"


def _process_candidates(
    conn: sqlite3.Connection,
    candidates: list[CandidateAct],
    source_name: str,
    since: date,
    until: date,
    stats: SourceRunStats,
) -> None:
    for candidate in candidates:
        if not is_in_scope_issuer(candidate):
            stats.discarded += 1
            continue
        if not in_discovery_window(candidate, since, until):
            stats.discarded += 1
            continue
        discard, reason = is_discardable(candidate)
        if discard:
            stats.discarded += 1
            continue

        level, kind, issuer = _level_kind_issuer_for(candidate)
        existing = find_existing(conn, level, kind, issuer, candidate.raw_number, candidate.raw_title)

        if is_deadline_extension(existing, candidate):
            _apply_deadline_extension(conn, existing, candidate)
            stats.found += 1
            continue

        ok, verify_reason = verify_primary_source(candidate)
        status = Status.ADOPTED if ok else Status.UNCONFIRMED
        act = build_act(candidate, status, source_name, existing, unconfirmed_reason=None if ok else verify_reason)
        upsert_act(conn, act)
        if ok:
            stats.found += 1
        else:
            stats.unconfirmed += 1


def _apply_deadline_extension(conn: sqlite3.Connection, existing, candidate: CandidateAct) -> None:
    from pipeline.classify import build_stage_from_candidate
    from models import AmendmentType

    stage = build_stage_from_candidate(candidate, AmendmentType.NEW_OBLIGATION)
    stage.what_changes = "продление срока: " + candidate.raw_title
    update_stages_and_status(conn, existing.db_id, stage, None, "продление срока, обновлена карточка вместо создания новой")


def _flush_stats(conn: sqlite3.Connection, run_id: str, stats: SourceRunStats, started_at: str) -> None:
    write_journal_entry(
        conn,
        run_id=run_id,
        source_name=stats.source_name,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc).isoformat(),
        found_count=stats.found,
        discarded_count=stats.discarded,
        unconfirmed_count=stats.unconfirmed,
        error_count=stats.errors,
        unreachable=stats.unreachable,
        detail=stats.detail,
    )


def run(
    conn: sqlite3.Connection,
    direct_sources: list[SourceClient],
    since: date,
    until: date,
    include_news_scan: bool = True,
) -> RunSummary:
    run_id = uuid.uuid4().hex
    all_stats = run_direct_sources(conn, direct_sources, since, until, run_id)
    if include_news_scan:
        news_stats = run_news_signal_pipeline(conn, direct_sources, since, until, run_id)
        all_stats.append(news_stats)
    return RunSummary(run_id=run_id, stats=all_stats)
