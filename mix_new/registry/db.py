"""Доступ к SQLite-реестру: схема, upsert карточек, журнал запусков."""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from models import Act, AmendmentType, Level, Stage, Status

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _parse_date(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def compute_natural_key(level: Level, act_kind: str, issuing_body: str, number: str | None, title: str) -> str:
    if number:
        return f"{level.value}|{act_kind}|{issuing_body}|{number}"
    normalized_title = " ".join(title.lower().split())[:120]
    return f"{level.value}|{act_kind}|{issuing_body}|~{normalized_title}"


def get_act_by_natural_key(conn: sqlite3.Connection, natural_key: str) -> Act | None:
    row = conn.execute("SELECT * FROM acts WHERE natural_key = ?", (natural_key,)).fetchone()
    if row is None:
        return None
    return _row_to_act(conn, row)


def _row_to_act(conn: sqlite3.Connection, row: sqlite3.Row) -> Act:
    stage_rows = conn.execute(
        "SELECT date_text, what_changes FROM stages WHERE act_id = ? ORDER BY sort_order", (row["id"],)
    ).fetchall()
    return Act(
        level=Level(row["level"]),
        act_kind=row["act_kind"],
        number=row["number"],
        issuing_body=row["issuing_body"],
        adoption_date=_parse_date(row["adoption_date"]),
        publication_date=_parse_date(row["publication_date"]),
        title=row["title"],
        source_url=row["source_url"],
        status=Status(row["status"]),
        amendment_type=AmendmentType(row["amendment_type"]) if row["amendment_type"] else None,
        summary_bullets=json.loads(row["summary_bullets_json"] or "[]"),
        okved_codes=json.loads(row["okved_codes_json"] or "[]"),
        cross_cutting=bool(row["cross_cutting"]),
        commodity_groups=json.loads(row["commodity_groups_json"] or "[]"),
        page_count=row["page_count"],
        discovered_date=_parse_date(row["discovered_date"]) or date.today(),
        stages=[Stage(date_text=r["date_text"], what_changes=r["what_changes"]) for r in stage_rows],
        linkage_note=row["linkage_note"],
        unconfirmed_reason=row["unconfirmed_reason"],
        db_id=row["id"],
        source_name=row["source_name"],
        natural_key=row["natural_key"],
    )


def upsert_act(conn: sqlite3.Connection, act: Act) -> tuple[int, bool]:
    """Создаёт или обновляет карточку по natural_key. Возвращает (id, is_new)."""
    natural_key = act.natural_key or compute_natural_key(
        act.level, act.act_kind, act.issuing_body, act.number, act.title
    )
    now = datetime.now(timezone.utc).isoformat()
    existing = get_act_by_natural_key(conn, natural_key)

    params = (
        act.level.value,
        act.act_kind,
        act.number,
        act.issuing_body,
        _iso(act.adoption_date),
        _iso(act.publication_date),
        act.title,
        act.source_url,
        act.status.value,
        act.amendment_type.value if act.amendment_type else None,
        json.dumps(act.summary_bullets, ensure_ascii=False),
        json.dumps(act.okved_codes, ensure_ascii=False),
        int(act.cross_cutting),
        json.dumps(act.commodity_groups, ensure_ascii=False),
        act.page_count,
        _iso(act.discovered_date),
        act.linkage_note,
        act.unconfirmed_reason,
        act.source_name,
        natural_key,
    )

    if existing is None:
        cur = conn.execute(
            """INSERT INTO acts (
                level, act_kind, number, issuing_body, adoption_date, publication_date,
                title, source_url, status, amendment_type, summary_bullets_json,
                okved_codes_json, cross_cutting, commodity_groups_json, page_count,
                discovered_date, linkage_note, unconfirmed_reason, source_name, natural_key,
                created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            params + (now, now),
        )
        act_id = cur.lastrowid
        conn.execute(
            "INSERT INTO status_history (act_id, old_status, new_status, changed_at, note) VALUES (?,?,?,?,?)",
            (act_id, None, act.status.value, now, "первое обнаружение"),
        )
        _replace_stages(conn, act_id, act.stages)
        conn.commit()
        return act_id, True

    act_id = existing.db_id
    conn.execute(
        """UPDATE acts SET
            level=?, act_kind=?, number=?, issuing_body=?, adoption_date=?, publication_date=?,
            title=?, source_url=?, status=?, amendment_type=?, summary_bullets_json=?,
            okved_codes_json=?, cross_cutting=?, commodity_groups_json=?, page_count=?,
            discovered_date=?, linkage_note=?, unconfirmed_reason=?, source_name=?, natural_key=?,
            updated_at=?
        WHERE id=?""",
        params + (now, act_id),
    )
    if existing.status != act.status:
        conn.execute(
            "INSERT INTO status_history (act_id, old_status, new_status, changed_at, note) VALUES (?,?,?,?,?)",
            (act_id, existing.status.value, act.status.value, now, "обновление при повторном запуске"),
        )
    _replace_stages(conn, act_id, act.stages)
    conn.commit()
    return act_id, False


def update_stages_and_status(
    conn: sqlite3.Connection, act_id: int, new_stage: Stage, new_status: Status | None, note: str
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    row = conn.execute("SELECT status FROM acts WHERE id = ?", (act_id,)).fetchone()
    old_status = row["status"] if row else None
    max_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), -1) AS m FROM stages WHERE act_id = ?", (act_id,)
    ).fetchone()["m"]
    conn.execute(
        "INSERT INTO stages (act_id, date_text, what_changes, sort_order) VALUES (?,?,?,?)",
        (act_id, new_stage.date_text, new_stage.what_changes, max_order + 1),
    )
    if new_status is not None:
        conn.execute("UPDATE acts SET status=?, updated_at=? WHERE id=?", (new_status.value, now, act_id))
        conn.execute(
            "INSERT INTO status_history (act_id, old_status, new_status, changed_at, note) VALUES (?,?,?,?,?)",
            (act_id, old_status, new_status.value, now, note),
        )
    conn.commit()


def _replace_stages(conn: sqlite3.Connection, act_id: int, stages: list[Stage]) -> None:
    conn.execute("DELETE FROM stages WHERE act_id = ?", (act_id,))
    for i, stage in enumerate(stages):
        conn.execute(
            "INSERT INTO stages (act_id, date_text, what_changes, sort_order) VALUES (?,?,?,?)",
            (act_id, stage.date_text, stage.what_changes, i),
        )


def list_acts(conn: sqlite3.Connection, include_unconfirmed: bool = False) -> list[Act]:
    if include_unconfirmed:
        rows = conn.execute("SELECT * FROM acts ORDER BY discovered_date DESC").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM acts WHERE status != ? ORDER BY discovered_date DESC", (Status.UNCONFIRMED.value,)
        ).fetchall()
    return [_row_to_act(conn, r) for r in rows]


def find_candidates_for_fuzzy_match(conn: sqlite3.Connection, level: Level, act_kind: str, issuing_body: str) -> list[Act]:
    """Акты без номера (проекты) того же уровня/вида/ведомства — для fuzzy-дедупликации."""
    rows = conn.execute(
        "SELECT * FROM acts WHERE level=? AND act_kind=? AND issuing_body=? AND number IS NULL",
        (level.value, act_kind, issuing_body),
    ).fetchall()
    return [_row_to_act(conn, r) for r in rows]


def write_journal_entry(
    conn: sqlite3.Connection,
    run_id: str,
    source_name: str,
    started_at: str,
    finished_at: str | None,
    found_count: int,
    discarded_count: int,
    unconfirmed_count: int,
    error_count: int,
    unreachable: bool,
    detail: dict,
) -> None:
    conn.execute(
        """INSERT INTO run_journal (
            run_id, source_name, started_at, finished_at, found_count, discarded_count,
            unconfirmed_count, error_count, unreachable, detail_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            run_id, source_name, started_at, finished_at, found_count, discarded_count,
            unconfirmed_count, error_count, int(unreachable), json.dumps(detail, ensure_ascii=False),
        ),
    )
    conn.commit()


def get_journal_for_run(conn: sqlite3.Connection, run_id: str) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM run_journal WHERE run_id = ?", (run_id,)).fetchall()
