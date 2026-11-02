"""Карточки трендов: модель группирует сюжеты месяца в тренды."""
import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from pipeline import trend_cards
from registry.db import list_cards

TODAY = date(2026, 11, 2)


def _data(n=12):
    articles, stories = [], []
    for i in range(n):
        articles.append([f"2026-10-{10 + i:02d}", i % 3, f"Сюжет {i}", f"https://a.ru/{i}", [0]])
        stories.append([articles[-1][0], [len(articles) - 1]])
    articles.append(["2026-10-25", 1, "Перепечатка сюжета 0", "https://b.ru/0", [0]])
    stories[0][1].append(len(articles) - 1)
    old = ["2026-08-01", 0, "Старый сюжет", "https://a.ru/old", [1]]
    articles.append(old)
    return {
        "articles": articles,
        "stories": {"0": stories, "1": [[old[0], [len(articles) - 1]]]},
        "outlets": [{"title": f"Издание {i}", "category": "Деловые СМИ"} for i in range(3)],
        "tags": [{"label": "Платежи"}, {"label": "Маркетплейсы"}],
    }


class FakeWriter:
    available = True
    reason = ""

    def __init__(self, trends):
        self.trends, self.calls, self.seen = trends, 0, None

    def write(self, stories):
        self.calls += 1
        self.seen = stories
        return self.trends


TREND = {"trend": "Малый бизнес переходит на оплату по QR", "what_changes": "Всё больше сюжетов о QR.",
         "drivers": ["ниже комиссия"], "barriers": [], "consequences": ["спрос на QR-эквайринг", "новые тарифы"],
         "steeple": ["Экономические", "Неизвестный"], "signals": [1, 2, 3, 99]}


def test_stories_deduplicated_recent_and_biggest_first():
    stories = trend_cards.collect_stories(_data(), TODAY)
    assert len(stories) == 12  # старый сюжет за пределами 30 дней не попал
    assert stories[0]["title"] == "Сюжет 0" and stories[0]["outlets"] == 2 and stories[0]["pubs"] == 2


def test_cards_are_trends_with_signals(conn):
    writer = FakeWriter([TREND, {**TREND, "trend": "Слабый тренд", "signals": [1, 2]}])
    summary = trend_cards.update_trend_cards(conn, _data(), writer, today=TODAY)
    assert summary["updated"] and summary["cards"] == 1  # тренд с 2 сигналами отброшен
    card = list_cards(conn)[0]
    assert card["title"] == "Малый бизнес переходит на оплату по QR"
    assert card["steeple"] == ["Экономические"]
    assert len(card["signals"]) == 3  # номер 99 вне списка — отброшен
    assert card["consequences"] == "— спрос на QR-эквайринг\n— новые тарифы"
    assert "text" in writer.seen[0]


def test_refresh_weekly_and_old_cards_archived(conn):
    writer = FakeWriter([TREND])
    trend_cards.update_trend_cards(conn, _data(), writer, today=TODAY)
    trend_cards.update_trend_cards(conn, _data(), writer, today=TODAY)
    assert writer.calls == 1  # неделя не прошла
    trend_cards.update_trend_cards(conn, _data(), writer, force=True, today=TODAY)
    assert writer.calls == 2
    statuses = sorted(c["status"] for c in list_cards(conn))
    assert statuses == ["active", "archive"]


def test_no_key_no_cards(conn, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    summary = trend_cards.update_trend_cards(conn, _data(), today=TODAY)
    assert summary["llm"] is False and "ANTHROPIC_API_KEY" in summary["reason"]
    assert list_cards(conn) == []


def test_model_error_keeps_previous_cards(conn):
    trend_cards.update_trend_cards(conn, _data(), FakeWriter([TREND]), today=TODAY)

    class Broken(FakeWriter):
        def write(self, stories):
            raise RuntimeError("сеть недоступна")
    summary = trend_cards.update_trend_cards(conn, _data(), Broken([]), force=True, today=TODAY)
    assert summary["error"] and [c["status"] for c in list_cards(conn)] == ["active"]


def test_writer_request_shape():
    sent = {}

    def create(**kwargs):
        sent.update(kwargs)
        return SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text=json.dumps({"trends": [TREND]}))])

    w = trend_cards.TrendWriter.__new__(trend_cards.TrendWriter)
    w.client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    stories = [{"date": "2026-11-01", "source": "РБК", "title": "Заголовок", "text": "Текст", "outlets": 2, "themes": ["Платежи"]}]
    assert w.write(stories) == [TREND]
    assert sent["model"] == "claude-opus-5-5"
    assert sent["output_config"]["format"]["schema"] == trend_cards.TRENDS_SCHEMA
    assert sent["fallbacks"] == "default" and sent["betas"] == ["server-side-fallback-2026-07-01"]
    assert "1. [2026-11-01, РБК, изданий: 2; темы: Платежи] Заголовок" in sent["messages"][0]["content"]
