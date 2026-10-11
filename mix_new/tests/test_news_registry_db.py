from datetime import datetime, timezone

from models import Credibility, ManualCheckStatus, NewsItem, RecordStatus
from registry.db import list_news_items, upsert_news_item


def _item(**overrides) -> NewsItem:
    base = dict(
        title="Минпромторг изменил перечень товаров",
        links=["https://example.ru/news/1"],
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        sources=["tass"],
        matched_keywords=[("перечень", "changes")],
        credibility=Credibility.LOW,
    )
    base.update(overrides)
    return NewsItem(**base)


def test_first_upsert_creates_new_record(conn):
    _, status = upsert_news_item(conn, _item())
    assert status == RecordStatus.NEW
    items = list_news_items(conn)
    assert len(items) == 1
    assert items[0].record_status == RecordStatus.NEW


def test_repeat_run_same_sources_marks_repeat(conn):
    upsert_news_item(conn, _item())
    _, status = upsert_news_item(conn, _item())
    assert status == RecordStatus.REPEAT


def test_new_independent_source_marks_updated(conn):
    upsert_news_item(conn, _item())
    _, status = upsert_news_item(conn, _item(sources=["tass", "interfax"], links=["https://example.ru/news/1"]))
    assert status == RecordStatus.UPDATED


def test_manual_fields_not_overwritten_on_rerun(conn):
    db_id, _ = upsert_news_item(conn, _item())
    item = list_news_items(conn)[0]
    assert item.manual_check_status == ManualCheckStatus.NOT_CHECKED

    conn.execute(
        "UPDATE news_items SET manual_check_status=?, act_text_url=? WHERE id=?",
        (ManualCheckStatus.CONFIRMED.value, "https://pravo.example/act", db_id),
    )
    conn.commit()

    upsert_news_item(conn, _item())

    refreshed = list_news_items(conn)[0]
    assert refreshed.manual_check_status == ManualCheckStatus.CONFIRMED
    assert refreshed.act_text_url == "https://pravo.example/act"


def test_merged_links_accumulate_across_runs(conn):
    upsert_news_item(conn, _item(links=["https://example.ru/news/1"]))
    upsert_news_item(conn, _item(links=["https://example.ru/news/1-mirror"], sources=["interfax"]))

    item = list_news_items(conn)[0]
    assert set(item.links) == {"https://example.ru/news/1", "https://example.ru/news/1-mirror"}


def test_new_fields_round_trip(conn):
    upsert_news_item(
        conn,
        _item(referenced_acts=["Налоговый кодекс Российской Федерации"], credibility_reasons=["независимых СМИ: 1"]),
    )
    item = list_news_items(conn)[0]
    assert item.referenced_acts == ["Налоговый кодекс Российской Федерации"]
    assert item.credibility_reasons == ["независимых СМИ: 1"]


def test_init_db_adds_new_columns_to_old_table(tmp_path):
    import sqlite3

    from registry.db import get_connection, init_db

    db_path = tmp_path / "old.sqlite3"
    old = sqlite3.connect(db_path)
    old.execute(
        """CREATE TABLE news_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, links_json TEXT NOT NULL,
            natural_key TEXT NOT NULL UNIQUE, published_at TEXT NOT NULL, sources_json TEXT NOT NULL,
            matched_keywords_json TEXT NOT NULL, amendment_type TEXT, level TEXT, stage TEXT, topic TEXT,
            industry TEXT, okved_codes_json TEXT, act_number TEXT, act_date TEXT,
            credibility TEXT NOT NULL, record_status TEXT NOT NULL,
            manual_check_status TEXT NOT NULL DEFAULT 'не проверено', act_text_url TEXT,
            first_seen_date TEXT NOT NULL, related_act_id INTEGER,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"""
    )
    old.commit()
    old.close()

    conn = get_connection(db_path)
    init_db(conn)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(news_items)")}
    assert {"referenced_acts_json", "credibility_reasons_json"} <= columns
    upsert_news_item(conn, _item())
    assert len(list_news_items(conn)) == 1
    conn.close()
