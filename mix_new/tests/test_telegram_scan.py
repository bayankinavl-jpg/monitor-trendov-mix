"""Разбор страницы публичного Telegram-канала на сохранённом образце, без сети."""
from datetime import datetime
from pathlib import Path

import pytest

from sources.telegram_scan import NotTelegramPageError, parse_channel_html
from sources.sources_config import load_sources

SAMPLE = Path(__file__).parent / "fixtures" / "telegram_sample.html"


def test_posts_have_title_link_text_and_date():
    items = parse_channel_html(SAMPLE.read_bytes())
    assert items
    for title, link, text, published in items:
        assert title and len(title) <= 201
        assert link.startswith("https://t.me/government_rus/")
        assert text.startswith(title.rstrip("…")[:20])
        datetime.fromisoformat(published)


def test_page_without_posts_is_rejected():
    with pytest.raises(NotTelegramPageError):
        parse_channel_html(b"<html><body>no posts</body></html>")


def test_sources_yml_has_telegram_kind():
    tg = [s for s in load_sources() if s.kind == "telegram"]
    assert tg and all(s.feed_url.startswith("https://t.me/s/") for s in tg)


def test_rss_with_namespace_is_read():
    from sources.news_scan import _parse_rss
    xml = (b'<?xml version="1.0"?><rss xmlns="http://backend.userland.com/rss2" version="2.0"><channel>'
           b'<item><title>Retail news</title><link>https://r.ru/1</link><pubDate>Mon, 02 Nov 2026 10:00:00 +0300</pubDate></item>'
           b'</channel></rss>')
    assert _parse_rss(xml) == [("Retail news", "https://r.ru/1", "", "Mon, 02 Nov 2026 10:00:00 +0300")]


def test_source_category_defaults():
    from sources.sources_config import NewsSource
    assert NewsSource("x", "", "https://t.me/s/x", "general", kind="telegram").category_title == "Telegram"
    assert NewsSource("x", "", "https://a.ru", "legal").category_title == "Официальные и правовые"
    assert NewsSource("x", "", "https://a.ru", "general", category="Исследования").category_title == "Исследования"


def test_hse_news_page_parsed():
    from sources.hse_scan import parse_hse_news
    items = parse_hse_news((Path(__file__).parent / "fixtures" / "hse_news_sample.html").read_bytes())
    assert len(items) >= 5
    title, link, text, published = items[1]
    assert title == "Как прогнозировать будущее науки и технологий"
    assert link.startswith("https://www.hse.ru/news/")
    assert "Лаборатория" in text
    assert published == "2026-10-29"
