"""Человекочитаемый отчёт по журналу одного прогона."""
from __future__ import annotations

import sqlite3

from registry.db import get_journal_for_run


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
