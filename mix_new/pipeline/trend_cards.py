"""Карточки трендов: Claude читает сюжеты последних 30 дней по всем темам,
сам группирует их и формулирует 3–6 трендов — направлений изменений, а не
тем. У каждого тренда: что меняется, драйверы, барьеры, последствия для
малого бизнеса и сигналы-доказательства (ссылки на сюжеты).

Карточки обновляются раз в неделю (или по команде run.sh --refresh-cards):
новый набор заменяет прежний, прежний уходит в архив базы. Без ключа
Claude API (ANTHROPIC_API_KEY) карточки не создаются."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone

import config

WINDOW_DAYS = 30            # сюжеты за этот период уходят в модель
MAX_STORIES = 150           # не больше стольких сюжетов (крупные — первыми)
SNIPPET = 200               # символов текста статьи к заголовку
REFRESH_EVERY = timedelta(days=6)
MIN_SIGNALS = 3

STEEPLE = ["Социальные", "Технологические", "Экономические", "Экологические",
           "Политические", "Правовые", "Этические"]

SYSTEM_PROMPT = """Ты — исследователь-трендвотчер в банке Точка, в круге Микс. Клиенты круга — малый и микробизнес в опте, производстве, IT и услугах.

Тебе дают пронумерованные сюжеты из открытых источников за последний месяц: дата, издание, заголовок, фрагмент текста, сколько изданий о нём писали, к каким темам парсер его отнёс.

Задача — найти тренды. Тренд — это направление изменения, которое подтверждают несколько разных сюжетов: например, «Маркетплейсы перекладывают на продавцов расходы на логистику и возвраты» или «Малый бизнес переходит с наличных на оплату по QR». Тренд — НЕ тема («Маркетплейсы»), НЕ отдельное событие («Сбой у хостинг-провайдера») и НЕ пересказ одной новости.

Правила:
- Объединяй сюжеты, которые описывают одно и то же изменение, даже если они из разных тем.
- У каждого тренда — не меньше 3 сюжетов-сигналов, лучше из разных изданий.
- Бери только изменения, важные для малого и микробизнеса или банковских продуктов для него. Политику, происшествия и разовые события пропускай, если они не показывают направление изменений.
- Работай строго с данными сюжетов, не добавляй фактов извне. Отделяй факты от интерпретаций.
- Лучше 3 хорошо подтверждённых тренда, чем 6 натянутых. Если трендов нет — верни пустой список.

Для каждого тренда:
- trend: формулировка изменения, до 14 слов.
- what_changes: 2–3 предложения — что именно меняется, по сигналам.
- drivers: 1–3 причины изменения.
- barriers: 0–3 фактора, которые могут его замедлить, если они видны в сигналах.
- consequences: 2–3 последствия для малого бизнеса и банковских продуктов для него — черновые гипотезы для обсуждения командой.
- steeple: типы тренда из списка: Социальные, Технологические, Экономические, Экологические, Политические, Правовые, Этические.
- signals: номера сюжетов, которые подтверждают тренд.

Пиши по-русски, коротко и конкретно."""

TRENDS_SCHEMA = {
    "type": "object",
    "properties": {
        "trends": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "trend": {"type": "string"},
                    "what_changes": {"type": "string"},
                    "drivers": {"type": "array", "items": {"type": "string"}},
                    "barriers": {"type": "array", "items": {"type": "string"}},
                    "consequences": {"type": "array", "items": {"type": "string"}},
                    "steeple": {"type": "array", "items": {"type": "string", "enum": STEEPLE}},
                    "signals": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["trend", "what_changes", "drivers", "barriers", "consequences", "steeple", "signals"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["trends"],
    "additionalProperties": False,
}


def collect_stories(data: dict, today: date) -> list[dict]:
    """Сюжеты за WINDOW_DAYS по всем темам и конкурентам, без повторов:
    один сюжет может относиться к нескольким темам. Крупные — первыми."""
    since = (today - timedelta(days=WINDOW_DAYS)).isoformat()
    by_first: dict[int, dict] = {}
    for tag_idx, stories in data["stories"].items():
        label = data["tags"][int(tag_idx)]["label"]
        for first_date, ids in stories:
            if first_date < since:
                continue
            head = ids[0]
            story = by_first.setdefault(head, {"ids": ids, "date": first_date, "themes": []})
            if len(ids) > len(story["ids"]):
                story["ids"] = ids
            if label not in story["themes"]:
                story["themes"].append(label)
    stories = []
    for head, s in by_first.items():
        a = data["articles"][head]
        outlets = {data["articles"][i][1] for i in s["ids"]}
        stories.append({
            "date": s["date"], "title": a[2], "link": a[3], "source": data["outlets"][a[1]]["title"],
            "outlets": len(outlets), "pubs": len(s["ids"]), "themes": s["themes"],
        })
    stories.sort(key=lambda s: (s["outlets"], s["pubs"], s["date"]), reverse=True)
    return stories[:MAX_STORIES]


class TrendWriter:
    """Формулирует тренды через Claude API. available = False без ключа."""

    def __init__(self) -> None:
        self.available = False
        self.reason = ""
        if os.environ.get("MIX_TRENDS_LLM", "1") == "0":
            self.reason = "модель выключена (MIX_TRENDS_LLM=0)"
            return
        if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            self.reason = "не задан ключ ANTHROPIC_API_KEY (см. README, «Карточки трендов»)"
            return
        try:
            import anthropic
        except ImportError:
            self.reason = "не установлена библиотека anthropic (pip install -r requirements.txt)"
            return
        self.client = anthropic.Anthropic()
        self.available = True

    def write(self, stories: list[dict]) -> list[dict] | None:
        lines = []
        for i, s in enumerate(stories, 1):
            lines.append(f"{i}. [{s['date']}, {s['source']}, изданий: {s['outlets']}; темы: {', '.join(s['themes'])}] "
                         f"{s['title']}" + (f"\n   {s['text'][:SNIPPET]}" if s.get("text") else ""))
        response = self.client.beta.messages.create(
            model=config.TREND_CARDS_MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": "Сюжеты:\n\n" + "\n".join(lines)}],
            output_config={"effort": "high", "format": {"type": "json_schema", "schema": TRENDS_SCHEMA}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            return None
        text = next((b.text for b in response.content if b.type == "text"), "")
        return json.loads(text)["trends"]


def _lines(items: list[str], limit: int) -> str:
    return "\n".join(f"— {x.strip()}" for x in items[:limit] if x and x.strip())


def _last_generation(conn: sqlite3.Connection) -> datetime | None:
    row = conn.execute("SELECT MAX(ai_generated_at) FROM trend_cards WHERE origin = 'auto'").fetchone()
    return datetime.fromisoformat(row[0]) if row and row[0] else None


def update_trend_cards(conn: sqlite3.Connection, data: dict, writer=None, force: bool = False,
                       today: date | None = None) -> dict:
    """Раз в неделю (или при force) просит модель сформулировать тренды и
    заменяет ими актуальные карточки. Возвращает сводку для отчёта."""
    today = today or date.today()
    now = datetime.now(timezone.utc)
    writer = writer if writer is not None else TrendWriter()
    summary = {"llm": writer.available, "reason": writer.reason, "updated": False, "cards": 0, "error": ""}
    if not writer.available:
        return summary
    last = _last_generation(conn)
    if not force and last and now - last < REFRESH_EVERY:
        summary["reason"] = f"карточки обновлены {last.astimezone().strftime('%d.%m.%Y')}, следующее обновление через неделю"
        return summary

    stories = collect_stories(data, today)
    if len(stories) < 10:
        summary["reason"] = "за 30 дней меньше 10 сюжетов — мало данных для трендов"
        return summary
    for s in stories:
        row = conn.execute("SELECT text FROM articles WHERE link = ?", (s["link"],)).fetchone()
        s["text"] = (row[0] or "") if row else ""
    try:
        trends = writer.write(stories)
    except Exception as exc:  # noqa: BLE001 - сбой модели не должен ломать сбор
        summary["error"] = f"{type(exc).__name__}: {exc}"[:300]
        return summary
    if trends is None:
        summary["error"] = "модель отказалась отвечать"
        return summary

    conn.execute("UPDATE trend_cards SET status = 'archive' WHERE origin = 'auto' AND status = 'active'")
    for t in trends:
        ids = [i for i in dict.fromkeys(t.get("signals", [])) if 1 <= i <= len(stories)]
        if len(ids) < MIN_SIGNALS or not t.get("trend", "").strip():
            continue  # тренд без достаточных доказательств не показываем
        steeple = [s for s in t.get("steeple", []) if s in STEEPLE]
        cur = conn.execute(
            "INSERT INTO trend_cards (title, what_changes, drivers, barriers, consequences, steeple_json, origin, "
            "status, ai_model, ai_generated_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'auto', 'active', ?, ?, ?, ?)",
            (t["trend"].strip(), t.get("what_changes", "").strip(), _lines(t.get("drivers", []), 3),
             _lines(t.get("barriers", []), 3), _lines(t.get("consequences", []), 3),
             json.dumps(steeple, ensure_ascii=False), config.TREND_CARDS_MODEL, now.isoformat(),
             now.isoformat(), now.isoformat()))
        for i in ids:
            s = stories[i - 1]
            note = f"ещё {s['pubs'] - 1} публ." if s["pubs"] > 1 else ""
            conn.execute(
                "INSERT OR IGNORE INTO trend_card_signals (card_id, link, title, published_date, source, note, added_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (cur.lastrowid, s["link"], s["title"], s["date"], s["source"], note, now.isoformat()))
        summary["cards"] += 1
    conn.commit()
    summary["updated"] = True
    return summary
