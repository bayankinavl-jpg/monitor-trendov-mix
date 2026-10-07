"""JSON-экспорт реестра: все карточки, все поля, включая «не подтверждено»
(явно отделены в confirmed_acts/unconfirmed_acts для аудита)."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

from models import Act, Status
from registry.db import list_acts


def _encode(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if hasattr(obj, "value"):  # Enum
        return obj.value
    raise TypeError(f"Не удалось сериализовать {type(obj)}")


def _act_to_dict(act: Act) -> dict:
    d = asdict(act)
    d["level"] = act.level.value
    d["status"] = act.status.value
    d["amendment_type"] = act.amendment_type.value if act.amendment_type else None
    d["adoption_date"] = act.adoption_date.isoformat() if act.adoption_date else None
    d["publication_date"] = act.publication_date.isoformat() if act.publication_date else None
    d["discovered_date"] = act.discovered_date.isoformat() if act.discovered_date else None
    d["stages"] = [{"date_text": s.date_text, "what_changes": s.what_changes} for s in act.stages]
    return d


def export_json(conn: sqlite3.Connection, out_path: Path) -> tuple[int, int]:
    all_acts = list_acts(conn, include_unconfirmed=True)
    confirmed = [a for a in all_acts if a.status != Status.UNCONFIRMED]
    unconfirmed = [a for a in all_acts if a.status == Status.UNCONFIRMED]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "confirmed_acts": [_act_to_dict(a) for a in confirmed],
        "unconfirmed_acts": [_act_to_dict(a) for a in unconfirmed],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(confirmed), len(unconfirmed)
