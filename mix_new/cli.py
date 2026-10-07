"""CLI: init-db / run / export / verify-lead."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path

import config
from export.json_export import export_json
from export.xlsx_export import export_xlsx
from journal.journal import render_run_report
from pipeline.runner import run as run_pipeline
from registry.db import get_connection, init_db
from sources.news_check import verify_lead_manual
from sources.pravo_gov import PravoGovSource
from sources.regulation_gov import RegulationGovSource


def _direct_sources():
    return [PravoGovSource(), RegulationGovSource()]


def cmd_init_db(args: argparse.Namespace) -> None:
    conn = get_connection(config.MAIN_DB_PATH)
    init_db(conn)
    print(f"База инициализирована: {config.MAIN_DB_PATH}")


def cmd_run(args: argparse.Namespace) -> None:
    since = date.fromisoformat(args.since) if args.since else date.today() - timedelta(days=90)
    until = date.fromisoformat(args.until) if args.until else date.today()
    conn = get_connection(config.MAIN_DB_PATH)
    init_db(conn)
    summary = run_pipeline(conn, _direct_sources(), since, until)
    print(render_run_report(conn, summary.run_id))


def cmd_export(args: argparse.Namespace) -> None:
    conn = get_connection(config.MAIN_DB_PATH)
    init_db(conn)
    out_dir = Path(args.out)
    if args.format in ("xlsx", "both"):
        n = export_xlsx(conn, out_dir / "registry.xlsx")
        print(f"XLSX: {n} карточек -> {out_dir / 'registry.xlsx'}")
    if args.format in ("json", "both"):
        confirmed, unconfirmed = export_json(conn, out_dir / "registry.json")
        print(f"JSON: {confirmed} подтверждено, {unconfirmed} не подтверждено -> {out_dir / 'registry.json'}")


def cmd_verify_lead(args: argparse.Namespace) -> None:
    result = verify_lead_manual(args.title, args.number, args.date, _direct_sources())
    if result.confirmed:
        print(f"ПОДТВЕРЖДЕНО: {result.candidate.source_url}")
    else:
        print(f"НЕ ПОДТВЕРЖДЕНО: {result.reason}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Реестр регуляторных изменений (опт/производство)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db").set_defaults(func=cmd_init_db)

    p_run = sub.add_parser("run")
    p_run.add_argument("--since")
    p_run.add_argument("--until")
    p_run.set_defaults(func=cmd_run)

    p_export = sub.add_parser("export")
    p_export.add_argument("--format", choices=["xlsx", "json", "both"], default="both")
    p_export.add_argument("--out", default=str(config.EXPORTS_DIR))
    p_export.set_defaults(func=cmd_export)

    p_verify = sub.add_parser("verify-lead")
    p_verify.add_argument("--title", required=True)
    p_verify.add_argument("--number")
    p_verify.add_argument("--date")
    p_verify.set_defaults(func=cmd_verify_lead)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
