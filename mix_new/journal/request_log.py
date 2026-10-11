"""Журнал отдельных HTTP-запросов (адрес, код ответа, время) — требование
раздела «Нефункциональные требования» ТЗ. Отдельно от run_journal в SQLite,
который считает агрегаты по источникам."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from config import LOGS_DIR


class RequestLogger:
    def __init__(self, run_date: date | None = None, logs_dir: Path = LOGS_DIR):
        run_date = run_date or date.today()
        logs_dir.mkdir(parents=True, exist_ok=True)
        self.path = logs_dir / f"requests_{run_date.strftime('%Y%m%d')}.log"

    def log(self, url: str, http_code: int | str, note: str = "") -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        line = f"{timestamp}\t{http_code}\t{url}"
        if note:
            line += f"\t{note}"
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
