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
