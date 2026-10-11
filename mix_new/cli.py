"""CLI: init-db / export (повторная выгрузка без повторного сбора).

Основной способ запуска — scripts/run_news.py --days N."""
from __future__ import annotations

import argparse
from pathlib import Path

import config
from export.news_json_export import export_news_json
from export.news_xlsx_export import export_news_xlsx
from registry.db import get_connection, init_db


def cmd_init_db(args: argparse.Namespace) -> None:
    conn = get_connection(config.MAIN_DB_PATH)
    init_db(conn)
    print(f"База инициализирована: {config.MAIN_DB_PATH}")


def cmd_export(args: argparse.Namespace) -> None:
    conn = get_connection(config.MAIN_DB_PATH)
    init_db(conn)
    out_dir = Path(args.out)
    if args.format in ("xlsx", "both"):
        n = export_news_xlsx(conn, out_dir / "news_registry.xlsx")
        print(f"XLSX: {n} записей -> {out_dir / 'news_registry.xlsx'}")
    if args.format in ("json", "both"):
        n = export_news_json(conn, out_dir / "news_registry.json")
        print(f"JSON: {n} записей -> {out_dir / 'news_registry.json'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Реестр регуляторных новостей (опт/производство)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db").set_defaults(func=cmd_init_db)

    p_export = sub.add_parser("export")
    p_export.add_argument("--format", choices=["xlsx", "json", "both"], default="both")
    p_export.add_argument("--out", default=str(config.EXPORTS_DIR))
    p_export.set_defaults(func=cmd_export)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
