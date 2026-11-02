"""Доступ к SQLite-реестру: схема, upsert карточек, журнал запусков."""
from __future__ import annotations

import difflib
import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from models import (
    Act,
    AmendmentType,
    Credibility,
    Level,
    ManualCheckStatus,
    NewsItem,
    RecordStatus,
    Stage,
    Status,
)

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.row_factory = sqlite3.Row
    return conn


# Колонки, добавленные после первой версии таблицы news_items. CREATE TABLE
# IF NOT EXISTS не меняет уже созданную таблицу, поэтому добавляем их явно.
_NEWS_ITEMS_ADDED_COLUMNS = {
    "referenced_acts_json": "TEXT",
    "credibility_reasons_json": "TEXT",
}


_ARTICLES_ADDED_COLUMNS = {
    "title_tokens": "TEXT",
    "tokens_version": "TEXT",
}
_TREND_CARDS_ADDED_COLUMNS = {
    "origin": "TEXT NOT NULL DEFAULT 'manual'",
    "auto_key": "TEXT",
    "status": "TEXT NOT NULL DEFAULT 'active'",
    "stats_json": "TEXT",
    "weak_evidence": "INTEGER NOT NULL DEFAULT 0",
    "signals_hash": "TEXT",
    "ai_model": "TEXT",
    "ai_generated_at": "TEXT",
}


def init_db(conn: sqlite3.Connection) -> None:
    # Новые колонки articles добавляем до схемы: индекс или запрос в схеме
    # может на них ссылаться, а CREATE TABLE IF NOT EXISTS их не добавит.
    for table, added in (("news_items", _NEWS_ITEMS_ADDED_COLUMNS), ("articles", _ARTICLES_ADDED_COLUMNS),
                         ("trend_cards", _TREND_CARDS_ADDED_COLUMNS)):
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if existing:
            for column, sql_type in added.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")
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


def find_act_by_number_and_date(conn: sqlite3.Connection, number: str, act_date: date) -> Act | None:
    """Для «Связи с реестром» (шаг 7 ТЗ): ищет акт по номеру и дате
    (принятия либо опубликования), без привязки к уровню/ведомству —
    у новости их может не быть."""
    row = conn.execute(
        "SELECT * FROM acts WHERE number = ? AND (adoption_date = ? OR publication_date = ?) LIMIT 1",
        (number, act_date.isoformat(), act_date.isoformat()),
    ).fetchone()
    if row is None:
        return None
    return _row_to_act(conn, row)


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


# --- Реестр новостей (news_items) ------------------------------------------------

_FUZZY_TITLE_THRESHOLD = 0.6


def _row_to_news_item(row: sqlite3.Row) -> NewsItem:
    return NewsItem(
        title=row["title"],
        links=json.loads(row["links_json"]),
        published_at=datetime.fromisoformat(row["published_at"]),
        sources=json.loads(row["sources_json"]),
        matched_keywords=[tuple(x) for x in json.loads(row["matched_keywords_json"])],
        amendment_type=AmendmentType(row["amendment_type"]) if row["amendment_type"] else None,
        level=Level(row["level"]) if row["level"] else None,
        stage=row["stage"],
        topic=row["topic"],
        industry=row["industry"],
        okved_codes=json.loads(row["okved_codes_json"] or "[]"),
        act_number=row["act_number"],
        act_date=_parse_date(row["act_date"]),
        referenced_acts=json.loads(row["referenced_acts_json"] or "[]"),
        credibility=Credibility(row["credibility"]),
        credibility_reasons=json.loads(row["credibility_reasons_json"] or "[]"),
        record_status=RecordStatus(row["record_status"]),
        manual_check_status=ManualCheckStatus(row["manual_check_status"]),
        act_text_url=row["act_text_url"],
        first_seen_date=_parse_date(row["first_seen_date"]) or date.today(),
        related_act_id=row["related_act_id"],
        db_id=row["id"],
        natural_key=row["natural_key"],
    )


def _find_existing_news_item(conn: sqlite3.Connection, item: NewsItem) -> sqlite3.Row | None:
    """Ищет уже накопленную запись по пересечению ссылок, иначе — по
    похожему заголовку (fuzzy), чтобы одна и та же новость с чуть другим
    набором ссылок между запусками не плодила дубль."""
    rows = conn.execute("SELECT * FROM news_items").fetchall()
    item_links = set(item.links)

    for row in rows:
        if item_links & set(json.loads(row["links_json"])):
            return row

    for row in rows:
        # Разные номера актов — разные акты, даже если заголовки похожи.
        if item.act_number and row["act_number"] and item.act_number != row["act_number"]:
            continue
        score = difflib.SequenceMatcher(None, row["title"].lower(), item.title.lower()).ratio()
        if score >= _FUZZY_TITLE_THRESHOLD:
            return row

    return None


def upsert_news_item(conn: sqlite3.Connection, item: NewsItem) -> tuple[int, RecordStatus]:
    """Накопление записи (шаг 8 ТЗ). Поля manual_check_status и
    act_text_url при повторном запуске НЕ перезатираются — они
    заполняются только человеком. record_status выставляется по
    правилу: новой записи не было — «новая», появился новый независимый
    источник — «обновлена», иначе — «повтор»."""
    now = datetime.now(timezone.utc).isoformat()
    existing = _find_existing_news_item(conn, item)

    natural_key = item.natural_key or sorted(item.links)[0]
    merged_links = sorted(set(item.links) | (set(json.loads(existing["links_json"])) if existing else set()))
    merged_sources = sorted(set(item.sources) | (set(json.loads(existing["sources_json"])) if existing else set()))

    if existing is None:
        record_status = RecordStatus.NEW
        manual_check_status = ManualCheckStatus.NOT_CHECKED
        act_text_url = None
        first_seen_date = item.first_seen_date
    else:
        gained_source = bool(set(merged_sources) - set(json.loads(existing["sources_json"])))
        record_status = RecordStatus.UPDATED if gained_source else RecordStatus.REPEAT
        manual_check_status = ManualCheckStatus(existing["manual_check_status"])
        act_text_url = existing["act_text_url"]
        first_seen_date = _parse_date(existing["first_seen_date"]) or item.first_seen_date

    params = (
        item.title,
        json.dumps(merged_links, ensure_ascii=False),
        natural_key,
        item.published_at.isoformat(),
        json.dumps(merged_sources, ensure_ascii=False),
        json.dumps(item.matched_keywords, ensure_ascii=False),
        item.amendment_type.value if item.amendment_type else None,
        item.level.value if item.level else None,
        item.stage,
        item.topic,
        item.industry,
        json.dumps(item.okved_codes, ensure_ascii=False),
        item.act_number,
        _iso(item.act_date),
        item.credibility.value,
        record_status.value,
        manual_check_status.value,
        act_text_url,
        _iso(first_seen_date),
        item.related_act_id,
        json.dumps(item.referenced_acts, ensure_ascii=False),
        json.dumps(item.credibility_reasons, ensure_ascii=False),
    )

    if existing is None:
        cur = conn.execute(
            """INSERT INTO news_items (
                title, links_json, natural_key, published_at, sources_json,
                matched_keywords_json, amendment_type, level, stage, topic, industry,
                okved_codes_json, act_number, act_date, credibility, record_status,
                manual_check_status, act_text_url, first_seen_date, related_act_id,
                referenced_acts_json, credibility_reasons_json,
                created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            params + (now, now),
        )
        conn.commit()
        return cur.lastrowid, RecordStatus.NEW

    conn.execute(
        """UPDATE news_items SET
            title=?, links_json=?, natural_key=?, published_at=?, sources_json=?,
            matched_keywords_json=?, amendment_type=?, level=?, stage=?, topic=?, industry=?,
            okved_codes_json=?, act_number=?, act_date=?, credibility=?, record_status=?,
            manual_check_status=?, act_text_url=?, first_seen_date=?, related_act_id=?,
            referenced_acts_json=?, credibility_reasons_json=?,
            updated_at=?
        WHERE id=?""",
        params + (now, existing["id"]),
    )
    conn.commit()
    return existing["id"], record_status


def list_news_items(conn: sqlite3.Connection) -> list[NewsItem]:
    rows = conn.execute("SELECT * FROM news_items ORDER BY published_at DESC").fetchall()
    return [_row_to_news_item(r) for r in rows]


# ---- Статьи для трендов ----

ARTICLE_TEXT_LIMIT = 2000


def save_articles(conn: sqlite3.Connection, leads) -> int:
    """Сохраняет все прочитанные статьи (NewsLead). Повтор по ссылке
    пропускается. Возвращает число новых статей."""
    from pipeline.normalize import normalize_url
    from pipeline.trends import clean_text

    today = date.today().isoformat()
    now = datetime.now(timezone.utc).isoformat()
    added = 0
    for lead in leads:
        if not lead.link or not lead.title:
            continue
        published = lead.published.date().isoformat() if lead.published else today
        cur = conn.execute(
            "INSERT OR IGNORE INTO articles (link, title, text, published_date, source_name, first_seen) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (normalize_url(lead.link), lead.title, clean_text(lead.annotation)[:ARTICLE_TEXT_LIMIT],
             published, lead.source_name, now),
        )
        added += cur.rowcount
    conn.commit()
    return added


def retag_articles(conn: sqlite3.Connection, trends=None) -> int:
    """Размечает темами и конкурентами статьи, размеченные старой версией
    словаря trends.yml (или ещё не размеченные). Возвращает число статей."""
    from pipeline.trends import get_trends, tag_article

    from pipeline.trends import TOKENS_VERSION, title_tokens

    trends = trends or get_trends()
    rows = conn.execute(
        "SELECT id, title, text FROM articles WHERE tags_version IS NULL OR tags_version != ?",
        (trends.version,),
    ).fetchall()
    for row in rows:
        tags = tag_article(row["title"], row["text"], trends)
        conn.execute("UPDATE articles SET tags_json = ?, tags_version = ? WHERE id = ?",
                     (json.dumps(tags), trends.version, row["id"]))
    # Значимые слова заголовка — для сюжетов и новых сигналов.
    for row in conn.execute(
        "SELECT id, title FROM articles WHERE tokens_version IS NULL OR tokens_version != ?", (TOKENS_VERSION,)
    ).fetchall():
        conn.execute("UPDATE articles SET title_tokens = ?, tokens_version = ? WHERE id = ?",
                     (title_tokens(row["title"]), TOKENS_VERSION, row["id"]))
    conn.commit()
    return len(rows)


# ---- Карточки трендов ----

CARD_TEXT_FIELDS = ("what_changes", "drivers", "barriers", "consequences")


def list_cards(conn: sqlite3.Connection) -> list[dict]:
    cards = []
    for row in conn.execute("SELECT * FROM trend_cards ORDER BY updated_at DESC, id DESC"):
        signals = [dict(r) for r in conn.execute(
            "SELECT id, link, title, published_date, source, note FROM trend_card_signals "
            "WHERE card_id = ? ORDER BY published_date DESC, id DESC", (row["id"],))]
        cards.append({
            "id": row["id"], "title": row["title"],
            **{f: row[f] for f in CARD_TEXT_FIELDS},
            "steeple": json.loads(row["steeple_json"] or "[]"),
            "origin": row["origin"], "status": row["status"],
            "stats": json.loads(row["stats_json"]) if row["stats_json"] else None,
            "weak_evidence": bool(row["weak_evidence"]),
            "ai_model": row["ai_model"], "ai_generated_at": (row["ai_generated_at"] or "")[:10],
            "updated_at": row["updated_at"][:10], "signals": signals,
        })
    return cards


def save_card(conn: sqlite3.Connection, data: dict) -> int:
    """Создаёт карточку (без id) или обновляет её поля (с id)."""
    title = str(data.get("title") or "").strip()
    if not title:
        raise ValueError("у карточки должно быть название")
    values = {f: str(data.get(f) or "").strip() for f in CARD_TEXT_FIELDS}
    steeple = json.dumps([str(x) for x in data.get("steeple") or []], ensure_ascii=False)
    now = datetime.now(timezone.utc).isoformat()
    card_id = data.get("id")
    if card_id:
        cur = conn.execute(
            "UPDATE trend_cards SET title = ?, what_changes = ?, drivers = ?, barriers = ?, consequences = ?, "
            "steeple_json = ?, updated_at = ? WHERE id = ?",
            (title, *values.values(), steeple, now, int(card_id)))
        if cur.rowcount == 0:
            raise ValueError("карточка не найдена")
    else:
        cur = conn.execute(
            "INSERT INTO trend_cards (title, what_changes, drivers, barriers, consequences, steeple_json, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (title, *values.values(), steeple, now, now))
        card_id = cur.lastrowid
    conn.commit()
    return int(card_id)


def delete_card(conn: sqlite3.Connection, card_id: int) -> None:
    conn.execute("DELETE FROM trend_cards WHERE id = ?", (int(card_id),))
    conn.commit()


def add_card_signal(conn: sqlite3.Connection, card_id: int, signal: dict) -> None:
    link = str(signal.get("link") or "").strip()
    title = str(signal.get("title") or "").strip()
    if not link.startswith(("http://", "https://")) or not title:
        raise ValueError("у сигнала должны быть заголовок и ссылка")
    if conn.execute("SELECT 1 FROM trend_cards WHERE id = ?", (int(card_id),)).fetchone() is None:
        raise ValueError("карточка не найдена")
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO trend_card_signals (card_id, link, title, published_date, source, note, added_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (int(card_id), link, title, signal.get("date"), signal.get("source"), str(signal.get("note") or ""), now))
    conn.execute("UPDATE trend_cards SET updated_at = ? WHERE id = ?", (now, int(card_id)))
    conn.commit()


def remove_card_signal(conn: sqlite3.Connection, signal_id: int) -> None:
    conn.execute("DELETE FROM trend_card_signals WHERE id = ?", (int(signal_id),))
    conn.commit()
