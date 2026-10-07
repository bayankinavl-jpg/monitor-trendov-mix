"""Смок-тест: прогон за последние 3 месяца по pravo.gov.ru + regulation.gov.ru
(+ новостной сканер как источник сигналов), отчёт сохраняется в файл."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from export.json_export import export_json
from export.xlsx_export import export_xlsx
from journal.journal import render_run_report
from pipeline.runner import run as run_pipeline
from registry.db import get_connection, init_db
from sources.pravo_gov import PravoGovSource
from sources.regulation_gov import RegulationGovSource


def main() -> None:
    since = date.today() - timedelta(days=90)
    until = date.today()

    config.SMOKE_DB_PATH.unlink(missing_ok=True)
    conn = get_connection(config.SMOKE_DB_PATH)
    init_db(conn)

    sources = [PravoGovSource(), RegulationGovSource()]
    summary = run_pipeline(conn, sources, since, until, include_news_scan=True)

    report = render_run_report(conn, summary.run_id)

    timestamp = date.today().strftime("%Y%m%d")
    report_path = config.EXPORTS_DIR / f"smoke_test_report_{timestamp}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    xlsx_path = config.EXPORTS_DIR / f"smoke_test_registry_{timestamp}.xlsx"
    json_path = config.EXPORTS_DIR / f"smoke_test_registry_{timestamp}.json"
    n_xlsx = export_xlsx(conn, xlsx_path)
    n_confirmed, n_unconfirmed = export_json(conn, json_path)

    print(report)
    print(f"\nXLSX ({n_xlsx} карточек): {xlsx_path}")
    print(f"JSON (подтверждено {n_confirmed}, не подтверждено {n_unconfirmed}): {json_path}")
    print(f"Отчёт сохранён: {report_path}")


if __name__ == "__main__":
    main()
