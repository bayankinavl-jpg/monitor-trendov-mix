from datetime import datetime, timezone

from pipeline.normalize import normalize_text, normalize_url, to_moscow_tz


def test_normalize_url_strips_utm_and_fragment():
    url = "https://Example.ru/news/article?utm_source=tg&id=5#section"
    assert normalize_url(url) == "https://example.ru/news/article?id=5"


def test_normalize_url_strips_trailing_slash():
    assert normalize_url("https://example.ru/news/") == "https://example.ru/news"


def test_normalize_text_lowercases_and_replaces_yo():
    assert normalize_text("Вступает в СИЛУ") == "вступает в силу"
    assert normalize_text("ёлка") == "елка"


def test_to_moscow_tz_converts_naive_as_utc():
    dt = datetime(2026, 1, 1, 0, 0, 0)
    converted = to_moscow_tz(dt)
    assert converted.hour == 3  # UTC+3


def test_to_moscow_tz_converts_aware():
    dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    converted = to_moscow_tz(dt)
    assert converted.hour == 3
