"""Разбор ленты publication.pravo.gov.ru на образце из реальных лент
(tests/fixtures/pravo_sample.rss), без обращения к сети."""
from datetime import date, datetime, timezone
from pathlib import Path

from models import Credibility, Level
from pipeline.classify_news import classify_level, extract_act_requisites
from pipeline.credibility import assess_credibility
from pipeline.dedupe_news import cluster_leads, same_act_possible
from pipeline.keywords_engine import match
from sources.news_scan import NewsLead, _parse_rss
from sources.sources_config import load_sources

SAMPLE = Path(__file__).parent / "fixtures" / "pravo_sample.rss"


def _items():
    return {title.split(" от ")[0][:40]: (title, link, desc) for title, link, desc, _ in _parse_rss(SAMPLE.read_bytes())}


def _title(prefix):
    return next(t for t, _, _, _ in _parse_rss(SAMPLE.read_bytes()) if t.startswith(prefix))


def test_feed_items_have_title_link_description():
    items = _parse_rss(SAMPLE.read_bytes())
    assert len(items) == 5
    title, link, description, pub = items[0]
    assert link.startswith("http://publication.pravo.gov.ru/document/")
    assert "Номер опубликования" in description
    assert pub


def test_requisites_from_official_title():
    number, act_date = extract_act_requisites(_title("Федеральный закон"))
    assert number == "321-ФЗ"
    assert act_date == date(2026, 8, 4)


def test_level_from_title_start():
    assert classify_level([], _title("Федеральный закон")) == Level.FEDERAL_LAW
    assert classify_level([], _title("Распоряжение Правительства")) == Level.GOV_ACT
    assert classify_level([], _title("Указ Президента")) == Level.UKAZ
    # Начало заголовка важнее слов «федеральный закон» в середине.
    duma = "Постановление Государственной Думы от 01.10.2026 № 1-8 ГД «О проекте федерального закона»"
    assert classify_level([("федеральный закон", "acts_and_bodies")], duma) == Level.PARLIAMENT


def test_personnel_acts_excluded():
    assert match(_title("Указ Президента")).passed is False  # «Об исполняющей обязанности»
    assert match(_title("Постановление Государственной Думы")).passed is False  # «О назначении … на должность»
    assert match(_title("Постановление Совета Федерации")).passed is False


def test_law_on_grain_passes():
    assert match(_title("Федеральный закон")).passed is True


def test_tax_exemption_not_excluded_by_personnel_rule():
    result = match("Об освобождении от уплаты НДС: Минфин снизит ставку для производителей")
    assert [w for w, g in result.matched if g == "exclusions"] == []
    assert result.passed is True


def test_primary_source_is_high_credibility():
    level, reasons = assess_credibility(["primary_source"], None, None, 1)
    assert level == Credibility.HIGH
    assert "портал официального опубликования" in reasons[0]


def test_acts_with_close_numbers_not_merged():
    a = "Распоряжение Правительства Российской Федерации от 08.10.2026 № 2826-р"
    b = "Распоряжение Правительства Российской Федерации от 08.10.2026 № 2827-р"
    assert same_act_possible(a, b) is False
    leads = [
        NewsLead(t, f"http://publication.pravo.gov.ru/document/{i}", "", datetime(2026, 10, 10, tzinfo=timezone.utc),
                 "pravo_gov", "primary_source", [])
        for i, t in enumerate((a, b))
    ]
    assert len(cluster_leads(leads)) == 2


def test_pravo_gov_no_longer_forbidden():
    assert any(s.domain == "publication.pravo.gov.ru" for s in load_sources())
