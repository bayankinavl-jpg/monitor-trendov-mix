"""Главная точка входа парсера новостей: python scripts/run_news.py --days N.

По умолчанию --days 90 при первом запуске (пустой реестр новостей),
иначе --days 1 (ежедневный режим) — см. tz_news_parser.md, шаг «Сбор»."""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from export.news_json_export import export_news_json
from export.news_xlsx_export import export_news_xlsx
from journal.journal import render_news_report
from pipeline.runner_news import run as run_pipeline
from registry.db import get_connection, init_db


def _default_days(conn) -> int:
    count = conn.execute("SELECT COUNT(*) AS c FROM news_items").fetchone()["c"]
    return 90 if count == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Парсер регуляторных новостей по ключевым словам")
    parser.add_argument("--days", type=int, default=None)
    args = parser.parse_args()

    conn = get_connection(config.MAIN_DB_PATH)
    init_db(conn)

    days = args.days if args.days is not None else _default_days(conn)
    until = date.today()
    since = until - timedelta(days=days)

    summary = run_pipeline(conn, since, until)

    timestamp = until.strftime("%Y%m%d")
    xlsx_path = config.EXPORTS_DIR / f"news_registry_{timestamp}.xlsx"
    json_path = config.EXPORTS_DIR / f"news_registry_{timestamp}.json"
    report_path = config.EXPORTS_DIR / f"news_report_{timestamp}.md"

    export_news_xlsx(conn, xlsx_path, run_id=summary.run_id)
    export_news_json(conn, json_path)

    report = render_news_report(conn, summary.run_id, summary)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    print(report)
    print(f"\nXLSX: {xlsx_path}")
    print(f"JSON: {json_path}")
    print(f"Отчёт: {report_path}")


if __name__ == "__main__":
    main()
