from datetime import datetime, timezone

from pipeline.dedupe_news import cluster_leads, independent_source_count
from sources.news_scan import NewsLead


def _lead(**overrides) -> NewsLead:
    base = dict(
        title="Минпромторг изменил перечень товаров",
        link="https://example.ru/news/1",
        annotation="",
        published=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source_name="tass",
        trust_tier="general",
        matched_keywords=[("перечень", "changes")],
    )
    base.update(overrides)
    return NewsLead(**base)


def test_exact_link_duplicate_merges_into_one_cluster():
    leads = [_lead(link="https://example.ru/news/1?utm_source=tg"), _lead(link="https://example.ru/news/1")]
    clusters = cluster_leads(leads)
    assert len(clusters) == 1
    assert len(clusters[0].links) == 1


def test_similar_titles_from_different_sources_merge():
    leads = [
        _lead(title="Минпромторг изменил перечень товаров", link="https://a.ru/1", source_name="tass"),
        _lead(title="Минпромторг изменил перечень товаров легпрома", link="https://b.ru/2", source_name="interfax"),
    ]
    clusters = cluster_leads(leads)
    assert len(clusters) == 1
    assert independent_source_count(clusters[0]) == 2


def test_unrelated_titles_stay_separate():
    leads = [
        _lead(title="Минпромторг изменил перечень товаров", link="https://a.ru/1"),
        _lead(title="ФНС обновила форму декларации по НДС", link="https://b.ru/2"),
    ]
    clusters = cluster_leads(leads)
    assert len(clusters) == 2


def test_agency_reprint_counts_as_one_source():
    leads = [
        _lead(title="Минпромторг изменил перечень товаров", link="https://tass.ru/1", source_name="tass"),
        _lead(
            title="Минпромторг изменил перечень товаров",
            link="https://kommersant.ru/2",
            source_name="kommersant",
            annotation="Как сообщает ТАСС, перечень изменён",
        ),
    ]
    clusters = cluster_leads(leads)
    assert len(clusters) == 1
    assert independent_source_count(clusters[0]) == 1
