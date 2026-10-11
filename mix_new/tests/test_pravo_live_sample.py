"""Лента publication.pravo.gov.ru (block=government), скачанная 11.10.2026 в
data/samples/pravo_live.xml, и обработка ответов, которые не являются RSS.
Без обращения к сети."""
from datetime import date
from pathlib import Path

import pytest

from pipeline.classify_news import classify_level, extract_act_requisites
from models import Level
from sources import news_scan
from sources.news_scan import FeedUnavailableError, NotRssError, _fetch_feed, _parse_rss, scan_all_feeds
from journal.request_log import RequestLogger
from sources.sources_config import NewsSource

LIVE = Path(__file__).resolve().parent.parent / "data" / "samples" / "pravo_live.xml"
HTML = b"<!DOCTYPE html>\n<html lang=\"ru\"><head><title>RSS</title></head><body></body></html>"


def test_live_sample_is_rss():
    assert LIVE.read_bytes().lstrip().startswith(b"<rss")


def test_live_sample_parsed():
    items = _parse_rss(LIVE.read_bytes())
    assert len(items) == 200
    assert all(link.startswith("http://publication.pravo.gov.ru/document/") for _, link, _, _ in items)
    assert all("Номер опубликования" in description for _, _, description, _ in items)


def test_live_sample_government_acts():
    titles = [title for title, _, _, _ in _parse_rss(LIVE.read_bytes())]
    assert all(classify_level([], t) == Level.GOV_ACT for t in titles)
    number, act_date = extract_act_requisites(titles[0])
    assert number == "1323"
    assert act_date == date(2026, 10, 9)


def test_html_page_rejected():
    with pytest.raises(NotRssError, match="HTML-страницу"):
        _parse_rss(HTML)


def test_other_xml_rejected():
    with pytest.raises(NotRssError, match="<feed>"):
        _parse_rss(b"<feed><entry/></feed>")


def test_consultant_brackets_stay_plain():
    rss = (
        "<rss><channel><item><title>Распоряжение Правительства РФ от 07.10.2026 N 2805-р "
        "&lt;О внесении изменений&gt;</title><link>https://www.consultant.ru/x</link></item></channel></rss>"
    ).encode("utf-8")
    title = _parse_rss(rss)[0][0]
    assert "<О внесении изменений>" in title
    assert "&lt;" not in title


class _Response:
    def __init__(self, content: bytes):
        self.content = content
        self.status_code = 200

    def raise_for_status(self):
        pass


class _Session:
    def __init__(self, responses: dict[str, bytes]):
        self.responses = responses
        self.headers = {}

    def get(self, url, **kwargs):
        return _Response(self.responses[url])


def _source(name, url):
    return NewsSource(name=name, focus="", feed_url=url, trust_tier="primary_source")


def test_fetch_html_reports_not_rss(tmp_path):
    session = _Session({"http://x/rss": HTML})
    with pytest.raises(FeedUnavailableError, match="ответ не RSS"):
        _fetch_feed(session, _source("pravo_old", "http://x/rss"), RequestLogger(logs_dir=tmp_path))
    assert "NOT_RSS" in next(tmp_path.iterdir()).read_text(encoding="utf-8")


def test_run_continues_when_one_source_is_html(tmp_path, monkeypatch):
    responses = {"http://x/rss": HTML, "http://x/api/rss": LIVE.read_bytes()}
    monkeypatch.setattr(news_scan.requests, "Session", lambda: _Session(responses))
    monkeypatch.setattr(news_scan, "_robots_allowed", lambda url, ua: True)
    monkeypatch.setattr(news_scan.time, "sleep", lambda s: None)

    leads, errors, read_count = scan_all_feeds(
        date(2026, 9, 1),
        date(2026, 10, 31),
        sources=[_source("pravo_old", "http://x/rss"), _source("pravo_government", "http://x/api/rss")],
        request_logger=RequestLogger(logs_dir=tmp_path),
    )
    assert "ответ не RSS" in errors["pravo_old"]
    assert "pravo_government" not in errors
    assert read_count == 200
