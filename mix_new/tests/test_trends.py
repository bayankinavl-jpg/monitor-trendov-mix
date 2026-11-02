"""Разметка статей темами и конкурентами (trends.yml) и хранение статей."""
from datetime import datetime, timezone
from pathlib import Path

from pipeline.trends import load_trends, tag_article
from registry.db import retag_articles, save_articles
from sources.news_scan import NewsLead

YML = """
themes:
  - label: Маркетплейсы
    sphere: Опт и производство
    words: [маркетплейс]
  - label: ИИ
    sphere: IT
    words: [искусственный интеллект]
competitors:
  - label: Точка
    group: Банки
    self: true
    names: [точка банк, «точка»]
  - label: Модульбанк
    group: Банки
    names: [модульбанк]
  - label: ВТБ
    group: Банки
    names: [втб]
"""


def _trends(tmp_path: Path, text: str = YML):
    p = tmp_path / "trends.yml"
    p.write_text(text, encoding="utf-8")
    return load_trends(p)


def _labels(trends, tags):
    names = {x.id: x.label for x in trends.themes + trends.competitors}
    return sorted(names[t] for t in tags)


def test_theme_found_in_any_word_form(tmp_path):
    t = _trends(tmp_path)
    assert _labels(t, tag_article("Продавцы уходят с маркетплейсов", "", t)) == ["Маркетплейсы"]


def test_competitor_with_russian_ending(tmp_path):
    t = _trends(tmp_path)
    assert _labels(t, tag_article("Клиенты Модульбанка получили кэшбэк", "", t)) == ["Модульбанк"]


def test_ambiguous_word_not_a_competitor(tmp_path):
    t = _trends(tmp_path)
    assert tag_article("Точка зрения: рынок растёт", "", t) == []
    assert _labels(t, tag_article("Банк «Точка» запустил сервис", "", t)) == ["Точка"]


def test_abbreviation_matches_whole_word_only(tmp_path):
    t = _trends(tmp_path)
    assert _labels(t, tag_article("ВТБ снизил ставки", "", t)) == ["ВТБ"]
    assert tag_article("ВТБшный офис", "", t) == []


def test_html_in_description_is_ignored(tmp_path):
    t = _trends(tmp_path)
    tags = tag_article("Новости", '<a href="x">Искусственный</a> <b>интеллект</b> в банках', t)
    assert _labels(t, tags) == ["ИИ"]


def _lead(link, title, text=""):
    return NewsLead(title=title, link=link, annotation=text, published=datetime(2026, 11, 1, tzinfo=timezone.utc),
                    source_name="rbc", trust_tier="general", matched_keywords=[])


def test_articles_saved_once_and_retagged_on_dictionary_change(conn, tmp_path):
    leads = [_lead("https://a.ru/1?utm_source=x", "Маркетплейсы растут"), _lead("https://a.ru/1", "Маркетплейсы растут")]
    assert save_articles(conn, leads) == 1
    t1 = _trends(tmp_path)
    assert retag_articles(conn, t1) == 1
    assert retag_articles(conn, t1) == 0  # словарь не менялся — повторной разметки нет
    t2 = _trends(tmp_path, YML.replace("[маркетплейс]", "[маркетплейс, продавец]"))
    assert retag_articles(conn, t2) == 1
    row = conn.execute("SELECT published_date, tags_json FROM articles").fetchone()
    assert row["published_date"] == "2026-11-01"
    assert row["tags_json"] == '["t0"]'


def test_real_dictionary_loads():
    t = load_trends()
    assert t.themes and t.competitors
    assert sum(c.is_self for c in t.competitors) == 1


def test_competitor_theme_needs_competitor_in_article(tmp_path):
    t = _trends(tmp_path, YML.replace("competitors:", """  - label: Сбои
    sphere: Конкуренты
    with_competitor: true
    words: [сбой]
competitors:"""))
    assert tag_article("Сбой у хостинг-провайдера", "", t) == []
    assert _labels(t, tag_article("Сбой в приложении ВТБ", "", t)) == ["ВТБ", "Сбои"]
