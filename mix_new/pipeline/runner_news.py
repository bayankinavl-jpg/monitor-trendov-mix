"""Оркестратор 8 шагов ТЗ: сбор → нормализация → фильтрация → дедупликация
→ классификация → оценка достоверности → связь с реестром → накопление."""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from models import NewsItem, RecordStatus
from pipeline.classify_news import classify
from pipeline.credibility import PRIMARY, assess_credibility
from pipeline.dedupe_news import cluster_leads, independent_source_count
from pipeline.keywords_engine import get_keyword_set
from pipeline.link_registry import find_related_act_id
from journal.request_log import RequestLogger
from registry.db import save_articles, upsert_news_item, write_journal_entry
from sources.news_scan import scan_all_feeds
from sources.sources_config import NewsSource, load_sources


@dataclass
class RunSummary:
    run_id: str
    sources_polled: int = 0
    sources_failed: dict[str, str] = field(default_factory=dict)
    read_count: int = 0
    selected_count: int = 0
    new_count: int = 0
    updated_count: int = 0
    repeat_count: int = 0
    articles_new: int = 0  # новых статей для трендов


def run(conn: sqlite3.Connection, since: date, until: date, sources: list[NewsSource] | None = None) -> RunSummary:
    run_id = uuid.uuid4().hex
    started_at = datetime.now(timezone.utc).isoformat()

    sources = sources or load_sources()
    request_logger = RequestLogger()
    all_items: list = []
    leads, feed_errors, read_count = scan_all_feeds(
        since, until, sources=sources, request_logger=request_logger, all_items=all_items
    )
    articles_new = save_articles(conn, all_items)

    summary = RunSummary(
        run_id=run_id,
        sources_polled=len(sources),
        sources_failed=feed_errors,
        read_count=read_count,
        selected_count=len(leads),
        articles_new=articles_new,
    )

    keyword_set = get_keyword_set()
    clusters = cluster_leads(leads)

    for cluster in clusters:
        annotation = " ".join(l.annotation for l in cluster.leads if l.annotation)
        matched: list[tuple[str, str]] = []
        seen = set()
        for lead in cluster.leads:
            for pair in lead.matched_keywords:
                if pair not in seen:
                    seen.add(pair)
                    matched.append(pair)

        fields = classify(cluster.title, annotation, matched, keyword_set)
        trust_tiers = [lead.trust_tier for lead in cluster.leads]
        # Запись портала официального опубликования — это уже опубликованный акт.
        if PRIMARY in trust_tiers and fields["stage"] is None:
            fields["stage"] = "опубликован"
        src_count = independent_source_count(cluster)
        credibility, credibility_reasons = assess_credibility(
            trust_tiers,
            fields["act_number"],
            fields["act_date"],
            src_count,
            stage=fields["stage"],
            referenced_acts=fields["referenced_acts"],
        )
        related_act_id = find_related_act_id(conn, fields["act_number"], fields["act_date"])

        published_candidates = [lead.published for lead in cluster.leads if lead.published]
        published_at = min(published_candidates) if published_candidates else datetime.now(timezone.utc)

        item = NewsItem(
            title=cluster.title,
            links=cluster.links,
            published_at=published_at,
            sources=cluster.canonical_sources,
            matched_keywords=matched,
            credibility=credibility,
            credibility_reasons=credibility_reasons,
            related_act_id=related_act_id,
            first_seen_date=date.today(),
            **fields,
        )
        _, record_status = upsert_news_item(conn, item)
        if record_status == RecordStatus.NEW:
            summary.new_count += 1
        elif record_status == RecordStatus.UPDATED:
            summary.updated_count += 1
        else:
            summary.repeat_count += 1

    for source in sources:
        error = feed_errors.get(source.name)
        write_journal_entry(
            conn,
            run_id=run_id,
            source_name=source.name,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
            found_count=sum(1 for lead in leads if lead.source_name == source.name),
            discarded_count=0,
            unconfirmed_count=0,
            error_count=1 if error else 0,
            unreachable=bool(error),
            detail={"error": error} if error else {},
        )

    return summary
