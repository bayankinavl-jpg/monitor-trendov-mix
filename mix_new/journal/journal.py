"""Человекочитаемый отчёт по журналу одного прогона."""
from __future__ import annotations

import sqlite3

from registry.db import get_journal_for_run, list_news_items


def render_run_report(conn: sqlite3.Connection, run_id: str) -> str:
    rows = get_journal_for_run(conn, run_id)
    lines = [f"# Отчёт по прогону {run_id}", ""]
    total_found = total_discarded = total_unconfirmed = total_errors = 0
    for row in rows:
        total_found += row["found_count"]
        total_discarded += row["discarded_count"]
        total_unconfirmed += row["unconfirmed_count"]
        total_errors += row["error_count"]
        status = "НЕДОСТУПЕН" if row["unreachable"] else "ОК"
        lines.append(
            f"## {row['source_name']} — {status}\n"
            f"- найдено: {row['found_count']}\n"
            f"- отброшено: {row['discarded_count']}\n"
            f"- не подтверждено: {row['unconfirmed_count']}\n"
            f"- ошибок: {row['error_count']}\n"
            f"- детали: {row['detail_json']}\n"
        )
    lines.insert(
        2,
        f"**Итого:** найдено {total_found}, отброшено {total_discarded}, "
        f"не подтверждено {total_unconfirmed}, ошибок {total_errors}\n",
    )
    return "\n".join(lines)


def render_news_report(conn: sqlite3.Connection, run_id: str, summary) -> str:
    """Отчёт по запуску парсера новостей: источники, счётчики по шагам,
    топ-10 самых свежих записей (раздел «Результат и формат выгрузки»)."""
    lines = [f"# Отчёт по прогону новостей {run_id}", ""]
    lines.append(
        f"Источников опрошено: {summary.sources_polled}, "
        f"не ответило: {len(summary.sources_failed)}\n"
    )
    lines.append(
        f"Прочитано: {summary.read_count}, отобрано: {summary.selected_count}, "
        f"новых: {summary.new_count}, обновлено: {summary.updated_count}, "
        f"повторов: {summary.repeat_count}\n"
    )

    if summary.sources_failed:
        lines.append("## Источники, которые не ответили\n")
        for name, reason in summary.sources_failed.items():
            lines.append(f"- {name}: {reason}")
        lines.append("")

    lines.append("## 10 самых свежих записей\n")
    for item in list_news_items(conn)[:10]:
        lines.append(f"- {item.published_at:%Y-%m-%d} — {item.title} ({item.credibility.value})")

    return "\n".join(lines)
