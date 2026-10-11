"""JSON-выгрузка реестра новостей: полный дамп всех полей."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

from models import NewsItem
from registry.db import list_news_items


def _item_to_dict(item: NewsItem) -> dict:
    d = asdict(item)
    d["published_at"] = item.published_at.isoformat()
    d["act_date"] = item.act_date.isoformat() if item.act_date else None
    d["first_seen_date"] = item.first_seen_date.isoformat()
    d["amendment_type"] = item.amendment_type.value if item.amendment_type else None
    d["level"] = item.level.value if item.level else None
    d["credibility"] = item.credibility.value
    d["record_status"] = item.record_status.value
    d["manual_check_status"] = item.manual_check_status.value
    return d


def export_news_json(conn: sqlite3.Connection, out_path: Path) -> int:
    items = list_news_items(conn)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "news_items": [_item_to_dict(item) for item in items],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(items)
