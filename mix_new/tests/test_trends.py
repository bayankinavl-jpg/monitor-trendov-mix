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


# ---- Сюжеты, сигналы, карточки ----

from pipeline.trends import group_stories, title_tokens, token_set
from registry.db import add_card_signal, delete_card, list_cards, remove_card_signal, save_card


def test_title_tokens_skip_names_and_service_words():
    toks = title_tokens("Путин обсудил с Ираном поэкземплярный учёт масла")
    assert "путин" not in toks and "иран" not in toks
    assert "поэкземплярный/A учет/N" in toks


def test_same_event_from_different_outlets_is_one_story():
    t = lambda s: token_set(title_tokens(s))
    items = [
        (0, "2026-11-01", t("Хостинг-провайдер Beget связал массовый сбой с кибератакой")),
        (1, "2026-11-02", t("Масштабный сбой Beget произошёл из-за кибератаки")),
        (2, "2026-11-02", t("Wildberries снизил комиссию для продавцов одежды")),
        (3, "2026-11-09", t("Beget снова сообщил о сбое после кибератаки")),  # через неделю — новый сюжет
    ]
    assert group_stories(items) == [[0, 1], [2], [3]]


def test_trend_card_lifecycle(conn):
    card_id = save_card(conn, {"title": "ИИ-агенты", "drivers": "дешевле", "steeple": ["Технологические"]})
    add_card_signal(conn, card_id, {"link": "https://a.ru/1", "title": "Банки и ИИ", "date": "2026-11-01", "source": "РБК"})
    add_card_signal(conn, card_id, {"link": "https://a.ru/1", "title": "Банки и ИИ"})  # повтор не добавляется
    cards = list_cards(conn)
    assert cards[0]["title"] == "ИИ-агенты" and cards[0]["steeple"] == ["Технологические"]
    assert len(cards[0]["signals"]) == 1
    remove_card_signal(conn, cards[0]["signals"][0]["id"])
    assert list_cards(conn)[0]["signals"] == []
    delete_card(conn, card_id)
    assert list_cards(conn) == []


def test_card_rejects_bad_input(conn):
    import pytest
    with pytest.raises(ValueError):
        save_card(conn, {"title": "  "})
    card_id = save_card(conn, {"title": "Тренд"})
    with pytest.raises(ValueError):
        add_card_signal(conn, card_id, {"link": "javascript:alert(1)", "title": "x"})
