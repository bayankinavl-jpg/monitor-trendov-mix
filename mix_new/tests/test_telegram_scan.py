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
