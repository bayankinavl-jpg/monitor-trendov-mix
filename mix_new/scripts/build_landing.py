"""Собирает страницу монитора data/exports/report_artifact.html из реестра.

python scripts/build_landing.py

Читает data/registry.sqlite3, keywords.yml, trends.yml и sources.yml и
записывает одну HTML-страницу: записи по сферам и нишам, фильтры, вкладка
источников, вкладка трендов (темы и конкуренты по всем прочитанным статьям).
Вызывается из run_news.py после каждого запуска парсера, поэтому страница
всегда показывает свежий реестр. Фильтры работают в браузере, сервер не нужен."""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from pipeline.keywords_engine import load_keywords
from pipeline.trends import get_trends, group_stories, token_set
from registry.db import init_db, retag_articles
from sources.sources_config import load_sources

OUT_PATH = config.EXPORTS_DIR / "report_artifact.html"
NO_NICHE = "Без ниши"
TREND_DAYS_LIMIT = 365  # статьи старше года на страницу не попадают
# Ленты актов (портал pravo.gov.ru, Гарант, КонсультантПлюс) публикуют
# документы, а не рыночные новости: в тренды их не берём, иначе темы
# вроде «Господдержка» росли бы от каждого постановления о субсидиях.
TREND_SKIP_TIERS = {"primary_source", "legal"}
STEEPLE = ["Социальные", "Технологические", "Экономические", "Экологические",
           "Политические", "Правовые", "Этические"]
TIER_TITLES = {
    "primary_source": "официальный портал",
    "official_publication": "официальное издание",
    "legal": "правовая система",
    "general": "СМИ и сайты ведомств",
}


def _json_list(value: str | None) -> list:
    try:
        return json.loads(value) if value else []
    except ValueError:
        return []


def collect(conn: sqlite3.Connection) -> dict:
    keywords = load_keywords()
    sources = load_sources()
    titles = {s.name: (s.title or s.name) for s in sources}

    niches = [
        {"label": g.label, "sphere": g.sphere, "okved": g.okved, "words": g.words}
        for g in keywords.industries
    ]
    spheres: list[str] = []
    for n in niches:
        if n["sphere"] not in spheres:
            spheres.append(n["sphere"])
    sphere_of = {n["label"]: n["sphere"] for n in niches}

    items = []
    for row in conn.execute("SELECT * FROM news_items ORDER BY published_at DESC, id DESC"):
        label = row["industry"] or NO_NICHE
        items.append({
            "title": row["title"],
            "links": _json_list(row["links_json"]),
            "date": (row["published_at"] or "")[:10],
            "sources": [titles.get(s, s) for s in _json_list(row["sources_json"])],
            "niche": label,
            "sphere": sphere_of.get(label, NO_NICHE),
            "okved": _json_list(row["okved_codes_json"]),
            "topic": row["topic"] or "",
            "level": row["level"] or "",
            "stage": row["stage"] or "",
            "change": row["amendment_type"] or "",
            "act_number": row["act_number"] or "",
            "act_date": row["act_date"] or "",
            "credibility": row["credibility"],
            "reasons": _json_list(row["credibility_reasons_json"]),
            "status": row["record_status"],
        })

    run = conn.execute("SELECT run_id, MIN(started_at) AS started FROM run_journal "
                       "GROUP BY run_id ORDER BY started DESC LIMIT 1").fetchone()
    journal = {}
    last_run = None
    if run:
        last_run = datetime.fromisoformat(run["started"]).astimezone().strftime("%d.%m.%Y %H:%M")
        for r in conn.execute("SELECT * FROM run_journal WHERE run_id = ?", (run["run_id"],)):
            error = ""
            if r["detail_json"]:
                error = (_json_list_or_dict(r["detail_json"]).get("error") or "")
            journal[r["source_name"]] = {
                "ok": not r["unreachable"], "found": r["found_count"], "error": error,
            }

    source_rows = [{
        "name": s.name, "title": s.title or s.name, "focus": s.focus,
        "tier": TIER_TITLES.get(s.trust_tier, s.trust_tier), "run": journal.get(s.name),
    } for s in sources]

    return {
        "trends": collect_trends(conn, sources),
        "built_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "last_run": last_run,
        "spheres": spheres + [NO_NICHE],
        "niches": niches,
        "items": items,
        "sources": source_rows,
    }


def _outlet(source) -> str:
    """Издание, к которому относится лента: cnews и cnews_top — одно издание.
    Для Telegram — сам канал. Нужен, чтобы считать независимые источники."""
    from urllib.parse import urlsplit

    parts = urlsplit(source.feed_url)
    host = parts.netloc.lower().removeprefix("www.").removeprefix("rss.").removeprefix("rssexport.")
    if getattr(source, "kind", "rss") == "telegram":
        return host + parts.path
    return host


def collect_trends(conn: sqlite3.Connection, sources) -> dict:
    """Данные вкладки «Тренды»: словарь тем и конкурентов, размеченные статьи,
    сюжеты (статьи об одном событии склеены) и карточки трендов. Статусы
    (растёт, новая...) считаются в браузере под выбранный период."""
    trends = get_trends()
    retag_articles(conn, trends)
    by_name = {s.name: s for s in sources}

    tags = [{"id": t.id, "label": t.label, "kind": "theme", "group": t.sphere, "self": False,
             "words": t.words, "steeple": t.steeple} for t in trends.themes]
    tags += [{"id": c.id, "label": c.label, "kind": "competitor", "group": c.group, "self": c.is_self,
              "words": c.names, "steeple": []} for c in trends.competitors]
    tag_index = {t["id"]: i for i, t in enumerate(tags)}

    outlets: list[dict] = []
    outlet_index: dict[str, int] = {}

    def outlet_of(source_name: str) -> int:
        src = by_name.get(source_name)
        key = _outlet(src) if src else source_name
        if key not in outlet_index:
            outlet_index[key] = len(outlets)
            outlets.append({
                "title": (src.title or src.name) if src else source_name,
                "category": src.category_title if src else "СМИ",
            })
        return outlet_index[key]

    skip = [s.name for s in sources if s.trust_tier in TREND_SKIP_TIERS]
    marks = ",".join("?" * len(skip)) or "''"
    first = conn.execute(
        f"SELECT MIN(first_seen) AS f, COUNT(*) AS n FROM articles WHERE source_name NOT IN ({marks})", skip
    ).fetchone()

    articles = []                       # статьи с темами: [дата, издание, заголовок, ссылка, [темы]]
    by_tag: dict[int, list] = {}        # тема → [(номер статьи, дата, слова заголовка)]
    for row in conn.execute(
        f"SELECT published_date, source_name, title, link, tags_json, title_tokens FROM articles "
        f"WHERE source_name NOT IN ({marks}) AND published_date >= date('now', ?) "
        "ORDER BY published_date, id",
        [*skip, f"-{TREND_DAYS_LIMIT} days"],
    ):
        tokens = row["title_tokens"] or ""
        o = outlet_of(row["source_name"])
        tag_ids = [tag_index[t] for t in _json_list(row["tags_json"]) if t in tag_index]
        if not tag_ids:
            continue
        idx = len(articles)
        articles.append([row["published_date"], o, row["title"], row["link"], tag_ids])
        words = token_set(tokens)
        for t in tag_ids:
            by_tag.setdefault(t, []).append((idx, row["published_date"], words))

    # Сюжеты: одна новость в десяти изданиях — один сюжет, а не десять упоминаний.
    stories = {
        str(t): [[articles[group[0]][0], group] for group in group_stories(items)]
        for t, items in by_tag.items()
    }

    # Сколько всего статей (с темами и без) вышло за каждый день: тренд
    # считается по доле, потому что объём сбора по дням неравномерный
    # (ленты отдают только последние материалы).
    daily = {
        r["d"]: r["n"] for r in conn.execute(
            f"SELECT published_date AS d, COUNT(*) AS n FROM articles WHERE source_name NOT IN ({marks}) "
            "AND published_date >= date('now', ?) GROUP BY published_date",
            [*skip, f"-{TREND_DAYS_LIMIT} days"],
        )
    }
    collecting_since = None
    if first["f"]:
        collecting_since = datetime.fromisoformat(first["f"]).astimezone().date().isoformat()
    return {
        "collecting_since": collecting_since,
        "history_start": min(daily) if daily else None,
        "daily": daily,
        "articles_total": first["n"],
        "tags": tags,
        "outlets": outlets,
        "articles": articles,
        "stories": stories,
        "steeple": STEEPLE,
    }


def _json_list_or_dict(value: str) -> dict:
    try:
        data = json.loads(value)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def build(conn: sqlite3.Connection, out_path: Path = OUT_PATH) -> Path:
    data = json.dumps(collect(conn), ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.replace("__DATA__", data)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path


def main() -> None:
    conn = sqlite3.connect(config.MAIN_DB_PATH)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    print(f"Страница: {build(conn)}")


TEMPLATE = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Монитор трендов Микс</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Golos+Text:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Макет: одна рабочая колонка — шапка, вкладки, фильтры, затем список записей по нишам. */
:root {
  --bg: #f2f4f6; --surface: #ffffff; --surface-2: #eaeef1; --ink: #15202b; --muted: #5b6875; --line: #d9dee4;
  --accent: #0e5f7a; --accent-soft: #dcebf1;
  --high: #1d6b4c; --high-soft: #dcefe5;
  --mid: #8a5a00; --mid-soft: #f6ead2;
  --low: #5b6875; --low-soft: #e6eaee;
  --danger: #a2332b;
  --font-body: "Golos Text", "Segoe UI", system-ui, sans-serif;
  --font-data: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #10161c; --surface: #18212a; --surface-2: #202b35; --ink: #e6ecf1; --muted: #9aa7b3; --line: #2b3742;
    --accent: #6cc1dc; --accent-soft: #173543; --high: #6fcf9f; --high-soft: #15352a;
    --mid: #e5b65c; --mid-soft: #3a2d12; --low: #9aa7b3; --low-soft: #26313b; --danger: #f08a80; color-scheme: dark;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink); font: 15px/1.5 var(--font-body);
  padding: max(24px, env(safe-area-inset-top, 0px)) max(16px, env(safe-area-inset-right, 0px)) 48px max(16px, env(safe-area-inset-left, 0px));
}
.wrap { max-width: 920px; margin: 0 auto; display: grid; grid-template-columns: minmax(0, 1fr); gap: 22px; }
.wrap > * { min-width: 0; }
a { color: var(--accent); }
header { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 6px 16px; }
h1 { font-size: 1.75rem; font-weight: 700; margin: 0; letter-spacing: -0.01em; text-wrap: balance; }
.status { font: 0.78rem var(--font-data); color: var(--muted); }
.tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--line); overflow-x: auto; }
.tab { font: 500 0.95rem var(--font-body); color: var(--muted); background: none; border: 0; padding: 8px 12px;
  border-bottom: 2px solid transparent; margin-bottom: -1px; cursor: pointer; white-space: nowrap; }
.tab[aria-selected="true"] { color: var(--ink); border-bottom-color: var(--accent); }
.tab:focus-visible, .chip:focus-visible, .btn:focus-visible, input:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.controls { display: grid; gap: 14px; }
.label { font-size: 0.72rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin-bottom: 6px; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { font: 500 0.92rem var(--font-body); color: var(--ink); background: var(--surface); border: 1px solid var(--line);
  border-radius: 999px; padding: 6px 14px; cursor: pointer; }
.chip:hover { border-color: var(--accent); }
.chip[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: var(--surface); }
.chip .n { font: 0.74rem var(--font-data); opacity: .7; margin-left: 6px; }
.chips.small .chip { font-size: 0.85rem; padding: 4px 11px; }
.search { width: 100%; font: 0.95rem var(--font-body); color: var(--ink); background: var(--surface);
  border: 1px solid var(--line); border-radius: 8px; padding: 9px 12px; }
.summary-bar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; }
.summary-bar p { margin: 0; color: var(--muted); }
.btn { font: 600 0.9rem var(--font-body); border-radius: 8px; padding: 8px 14px; cursor: pointer;
  border: 1px solid var(--accent); background: var(--accent); color: var(--surface); }
.btn.ghost { background: transparent; color: var(--accent); }
.btn:disabled { opacity: .55; cursor: default; }
.niche { display: grid; gap: 8px; }
.niche-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 12px; padding-top: 6px; }
.niche-head h2 { margin: 0; font-size: 1.12rem; font-weight: 650; }
.niche-head .sph { font-size: 0.72rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--accent); }
.okved { font: 0.76rem var(--font-data); color: var(--muted); }
.ledger { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
.item { display: grid; gap: 8px; padding: 16px 20px; border-top: 1px solid var(--line); min-width: 0; }
.item:first-child { border-top: 0; }
.meta { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; font: 0.76rem var(--font-data); color: var(--muted); }
.pill { font: 600 0.72rem var(--font-body); letter-spacing: .04em; text-transform: uppercase; padding: 2px 8px; border-radius: 4px; }
.pill.high { background: var(--high-soft); color: var(--high); }
.pill.mid { background: var(--mid-soft); color: var(--mid); }
.pill.low { background: var(--low-soft); color: var(--low); }
.pill.new { background: var(--accent-soft); color: var(--accent); }
.item h3 { margin: 0; font-size: 1.02rem; font-weight: 600; line-height: 1.4; text-wrap: balance; }
.item h3 a { color: var(--ink); text-decoration-color: var(--line); text-underline-offset: 3px; }
.item h3 a:hover { color: var(--accent); text-decoration-color: var(--accent); }
.row { display: grid; grid-template-columns: 96px 1fr; gap: 12px; font-size: 0.9rem; }
.row > span:first-child { font-size: 0.78rem; font-weight: 600; color: var(--muted); padding-top: 1px; }
.row > span:last-child { min-width: 0; overflow-wrap: anywhere; }
.reasons { margin: 0; padding-left: 16px; color: var(--muted); }
.empty { padding: 28px 20px; color: var(--muted); display: grid; gap: 6px; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; }
.empty strong { color: var(--ink); font-size: 1.02rem; }
.note { font-size: 0.85rem; color: var(--muted); }
.copy { margin-left: auto; font: 500 0.78rem var(--font-body); color: var(--accent); background: transparent;
  border: 1px solid var(--line); border-radius: 6px; padding: 3px 10px; cursor: pointer; }
.copy:hover { border-color: var(--accent); }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
.stat { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; display: grid; gap: 2px; }
.stat b { font: 500 1.5rem var(--font-data); }
.stat span { font-size: 0.8rem; color: var(--muted); }
.table-wrap { overflow-x: auto; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; }
table { width: 100%; border-collapse: collapse; font-size: 0.86rem; min-width: 560px; }
th, td { text-align: left; padding: 9px 14px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { color: var(--muted); font-size: 0.72rem; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; background: var(--surface-2); }
tr:last-child td { border-bottom: 0; }
td.ok { color: var(--high); font-family: var(--font-data); } td.fail { color: var(--danger); font-family: var(--font-data); }
td.off { color: var(--muted); font-family: var(--font-data); }
.words { font-size: 0.85rem; color: var(--muted); }
.spark { display: block; width: 100%; max-width: 280px; height: 30px; }
.spark rect { fill: var(--accent); }
.spark rect.prev { fill: var(--line); }
.nums { font: 0.8rem var(--font-data); color: var(--muted); }
.nums b { color: var(--ink); font-weight: 500; }
details.heads summary { cursor: pointer; font-size: 0.85rem; color: var(--accent); }
details.heads ul { margin: 8px 0 0; padding-left: 18px; display: grid; gap: 4px; font-size: 0.88rem; }
details.heads li span { font: 0.74rem var(--font-data); color: var(--muted); margin-right: 6px; }
.item.self { box-shadow: inset 3px 0 0 var(--accent); }
.quiet { font-size: 0.85rem; color: var(--muted); margin: 0; }
details.heads li em { font-style: normal; font-size: 0.8rem; color: var(--muted); margin-left: 6px; }
.mini { font: 500 0.74rem var(--font-body); color: var(--accent); background: transparent; border: 1px solid var(--line);
  border-radius: 6px; padding: 1px 8px; margin-left: 8px; cursor: pointer; white-space: nowrap; }
.mini:hover { border-color: var(--accent); }
.mini.danger { color: var(--danger); }
.picker { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 8px; }
.field-input { font: 0.92rem var(--font-body); color: var(--ink); background: var(--surface); border: 1px solid var(--line);
  border-radius: 8px; padding: 7px 10px; min-width: 0; }
textarea.field-input { width: 100%; resize: vertical; line-height: 1.45; }
input.field-input[type="text"] { flex: 1 1 220px; }
.card-form { display: grid; gap: 12px; }
.field { display: grid; gap: 4px; }
.field > span { font-size: 0.78rem; font-weight: 600; color: var(--muted); }
.card-form .field input { width: 100%; }
.pre { white-space: pre-wrap; }
.lead { margin: 0; line-height: 1.5; }
.draft { display: block; font-size: 0.68rem; font-weight: 600; color: var(--mid); text-transform: uppercase; letter-spacing: .04em; }
.mini:focus-visible, .field-input:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.head-side { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; }
.btn.small { font-size: 0.82rem; padding: 5px 12px; }
.settings-head { display: grid; gap: 10px; justify-items: start; padding-bottom: 14px; border-bottom: 1px solid var(--line); }
.settings-head h2 { margin: 4px 0 0; font-size: 1.3rem; font-weight: 650; }
.settings-head .note { margin: 0; }
footer { color: var(--muted); font-size: 0.8rem; border-top: 1px solid var(--line); padding-top: 14px; display: grid; gap: 4px; }
[hidden] { display: none !important; }
@media (max-width: 560px) { .row { grid-template-columns: 1fr; gap: 2px; } .item { padding: 14px 16px; } h1 { font-size: 1.45rem; } }
@media (prefers-reduced-motion: no-preference) { .chip, .btn { transition: background-color .15s, border-color .15s; } }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Монитор трендов Микс</h1>
    <div class="head-side">
      <div class="status" id="status"></div>
      <button class="btn ghost small" id="openSettings" type="button">Источники и словари</button>
    </div>
  </header>

  <nav class="tabs" role="tablist" id="mainTabs">
    <button class="tab" id="tab-feed" role="tab" aria-selected="true">Регуляторика</button>
    <button class="tab" id="tab-trend" role="tab" aria-selected="false">Тренды</button>
  </nav>

  <div id="settingsHead" class="settings-head" hidden>
    <button class="btn ghost small" id="closeSettings" type="button">← К монитору</button>
    <h2>Источники и словари</h2>
    <p class="note">Справка о том, откуда и по каким словам собираются данные. Правится в файлах
      <span class="okved">sources.yml</span>, <span class="okved">keywords.yml</span>, <span class="okved">trends.yml</span>.</p>
    <div class="chips" id="settingsTabs" role="tablist">
      <button class="chip" id="tab-src" type="button" aria-pressed="true">Источники</button>
      <button class="chip" id="tab-niche" type="button" aria-pressed="false">Ниши регуляторики</button>
      <button class="chip" id="tab-dict" type="button" aria-pressed="false">Темы и конкуренты</button>
    </div>
  </div>

  <section id="feed" class="controls">
    <div><div class="label">Сфера</div><div class="chips" id="spheres"></div></div>
    <div id="nicheBox" hidden><div class="label">Ниша</div><div class="chips small" id="niches"></div></div>
    <div><div class="label">Период</div><div class="chips" id="periods"></div></div>
    <div><div class="label">Достоверность</div><div class="chips" id="creds"></div></div>
    <input class="search" id="q" type="search" placeholder="Поиск по заголовку, источнику, номеру акта" aria-label="Поиск">
    <div class="summary-bar">
      <p id="count"></p>
      <button class="btn ghost" id="copyAll" hidden>Скопировать список</button>
    </div>
    <div id="list" style="display:grid;gap:22px"></div>
  </section>

  <section id="src" hidden style="display:grid;gap:16px">
    <div class="stats" id="srcStats"></div>
    <div class="table-wrap"><table>
      <thead><tr><th>Источник</th><th>Тип</th><th>Последний запуск</th><th>Отобрано</th><th>Примечание</th></tr></thead>
      <tbody id="srcRows"></tbody>
    </table></div>
    <p class="note">Источники и их типы задаются в <span class="okved">sources.yml</span>, правка действует со следующего запуска.
      Сайты, которые запрещают сбор в robots.txt, парсер не читает.</p>
  </section>

  <section id="nicheTab" hidden style="display:grid;gap:18px"></section>

  <section id="dictTab" hidden style="display:grid;gap:18px"></section>

  <section id="trendTab" class="controls" hidden>
    <div><div class="label">Показать</div><div class="chips" id="tViews"></div></div>
    <div id="tGroupBox"><div class="label" id="tGroupLabel">Сфера</div><div class="chips small" id="tGroups"></div></div>
    <div id="tSteepleBox"><div class="label">Тип тренда (STEEPLE)</div><div class="chips small" id="tSteeple"></div></div>
    <div id="tPeriodBox"><div class="label">Период</div><div class="chips" id="tPeriods"></div></div>
    <p class="note" id="tHistory"></p>
    <div class="stats" id="tStats"></div>
    <div id="tList" style="display:grid;gap:22px"></div>
    <p class="note" id="tHelp"></p>
  </section>

  <footer id="regFooter">
    <p>Достоверность ставит программа по признакам: тип источника, номер и дата акта, стадия, число независимых СМИ. Основания перечислены под каждой записью.</p>
    <p>Программа не читает текст акта и не проверяет, что запись относится к нише по смыслу: ниша определяется по ключевым словам. Перед решением откройте источник.</p>
  </footer>
</div>

<script>
const DATA = __DATA__;
const PERIODS = [[7, "Неделя"], [30, "Месяц"], [90, "3 месяца"], [0, "Всё время"]];
const CREDS = [["", "Любая"], ["высокий", "Высокая"], ["средний", "Средняя"], ["низкий", "Низкая"]];
const CRED_CLASS = { "высокий": "high", "средний": "mid", "низкий": "low" };
const CRED_TITLE = { "высокий": "высокая", "средний": "средняя", "низкий": "низкая" };
const ALL = "__all__";

const store = (() => { try { return window.localStorage; } catch { return null; } })();
const recall = (k, d) => { try { return store?.getItem(k) ?? d; } catch { return d; } };
const remember = (k, v) => { try { store?.setItem(k, v); } catch {} };

const state = { sphere: recall("sphere", ALL), niche: ALL, days: Number(recall("days", 30)), cred: recall("cred", ""), q: "" };
if (!DATA.spheres.includes(state.sphere)) state.sphere = ALL;
if (!PERIODS.some(([d]) => d === state.days)) state.days = 30;

const $ = (id) => document.getElementById(id);
function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) k === "class" ? (n.className = v) : n.setAttribute(k, v);
  for (const c of kids) if (c != null) n.append(c);
  return n;
}
const ruDate = (s) => { if (!s) return ""; const [y, m, d] = s.split("-"); return `${d}.${m}.${y}`; };
const safeUrl = (u) => /^https?:\/\//i.test(String(u)) ? String(u) : null;
const host = (u) => { try { return new URL(u).host.replace(/^www\./, ""); } catch { return u; } };
const sinceDate = (days) => { const d = new Date(); d.setDate(d.getDate() - days); return d.toISOString().slice(0, 10); };

function inScope(it, withNiche = true) {
  if (state.sphere !== ALL && it.sphere !== state.sphere) return false;
  if (withNiche && state.niche !== ALL && it.niche !== state.niche) return false;
  if (state.days && it.date < sinceDate(state.days)) return false;
  if (state.cred && it.credibility !== state.cred) return false;
  if (state.q) {
    const hay = [it.title, it.sources.join(" "), it.act_number, it.topic, it.niche].join(" ").toLowerCase();
    if (!state.q.split(/\s+/).every((w) => hay.includes(w))) return false;
  }
  return true;
}

function chip(text, pressed, onclick, count) {
  const b = el("button", { class: "chip", type: "button", "aria-pressed": String(pressed) }, text);
  if (count != null) b.append(el("span", { class: "n" }, String(count)));
  b.onclick = onclick;
  return b;
}

function renderControls() {
  const sp = $("spheres"); sp.replaceChildren();
  const countFor = (s) => DATA.items.filter((it) => (s === ALL || it.sphere === s)
    && (!state.days || it.date >= sinceDate(state.days)) && (!state.cred || it.credibility === state.cred)).length;
  for (const s of [ALL, ...DATA.spheres]) {
    sp.append(chip(s === ALL ? "Все сферы" : s, state.sphere === s, () => {
      state.sphere = s; state.niche = ALL; remember("sphere", s); render();
    }, countFor(s)));
  }
  const nb = $("nicheBox"), nc = $("niches"); nc.replaceChildren();
  const niches = state.sphere === ALL ? [] : DATA.niches.filter((n) => n.sphere === state.sphere);
  nb.hidden = niches.length === 0;
  if (niches.length) {
    const nCount = (label) => DATA.items.filter((it) => it.sphere === state.sphere && it.niche === label
      && (!state.days || it.date >= sinceDate(state.days)) && (!state.cred || it.credibility === state.cred)).length;
    nc.append(chip("Все ниши", state.niche === ALL, () => { state.niche = ALL; render(); }));
    for (const n of niches) nc.append(chip(n.label, state.niche === n.label, () => { state.niche = n.label; render(); }, nCount(n.label)));
  }
  const pr = $("periods"); pr.replaceChildren();
  for (const [d, t] of PERIODS) pr.append(chip(t, state.days === d, () => { state.days = d; remember("days", String(d)); render(); }));
  const cr = $("creds"); cr.replaceChildren();
  for (const [v, t] of CREDS) cr.append(chip(t, state.cred === v, () => { state.cred = v; remember("cred", v); render(); }));
}

function itemText(it) {
  const act = [it.level, it.act_number && `№ ${it.act_number}`, it.act_date && `от ${ruDate(it.act_date)}`].filter(Boolean).join(" ");
  return [`${it.title}`, `${ruDate(it.date)} · ${it.niche} · достоверность: ${CRED_TITLE[it.credibility] || it.credibility}`,
    act && `Акт: ${act}`, `Источники: ${it.sources.join(", ")}`, `Ссылка: ${it.links.filter(safeUrl)[0] || ""}`].filter(Boolean).join("\n");
}

async function copyText(text, btn) {
  const label = btn.textContent;
  try { await navigator.clipboard.writeText(text); btn.textContent = "Скопировано"; }
  catch { btn.textContent = "Не вышло: буфер недоступен"; }
  setTimeout(() => { btn.textContent = label; }, 1800);
}

function itemNode(it) {
  const copy = el("button", { class: "copy", type: "button", title: "Скопировать запись" }, "Копировать");
  copy.onclick = () => copyText(itemText(it), copy);
  const first = it.links.map(safeUrl).filter(Boolean)[0];
  const title = first ? el("a", { href: first, target: "_blank", rel: "noopener" }, it.title) : document.createTextNode(it.title);
  const act = [it.level, it.act_number && `№ ${it.act_number}`, it.act_date && `от ${ruDate(it.act_date)}`].filter(Boolean).join(" ");
  const node = el("article", { class: "item" },
    el("div", { class: "meta" },
      el("span", { class: "pill " + (CRED_CLASS[it.credibility] || "low"), title: "Достоверность записи" }, "достоверность: " + (CRED_TITLE[it.credibility] || it.credibility)),
      it.status === "новая" ? el("span", { class: "pill new" }, "новая") : null,
      el("span", {}, ruDate(it.date)), copy),
    el("h3", {}, title));
  if (act) node.append(el("div", { class: "row" }, el("span", {}, "Акт"), el("span", {}, act + (it.stage ? " · " + it.stage : ""))));
  else if (it.stage || it.change) node.append(el("div", { class: "row" }, el("span", {}, "Изменение"), el("span", {}, [it.change, it.stage].filter(Boolean).join(" · "))));
  if (it.topic) node.append(el("div", { class: "row" }, el("span", {}, "Тема"), el("span", {}, it.topic)));
  const links = el("span");
  it.links.map(safeUrl).filter(Boolean).slice(0, 3).forEach((u, i) => { if (i) links.append(", "); links.append(el("a", { href: u, target: "_blank", rel: "noopener" }, host(u))); });
  node.append(el("div", { class: "row" }, el("span", {}, "Источники"), el("span", {}, it.sources.join(", ") + " · ", links)));
  if (it.reasons.length) {
    const ul = el("ul", { class: "reasons" }); it.reasons.forEach((r) => ul.append(el("li", {}, r)));
    node.append(el("div", { class: "row" }, el("span", {}, "Основания"), ul));
  }
  return node;
}

function render() {
  renderControls();
  const shown = DATA.items.filter((it) => inScope(it));
  const period = PERIODS.find(([d]) => d === state.days)[1].toLowerCase();
  $("count").textContent = `${shown.length} из ${DATA.items.length} записей · период: ${period}`;
  $("copyAll").hidden = !shown.length;
  const list = $("list"); list.replaceChildren();
  if (!shown.length) {
    list.append(el("div", { class: "empty" }, el("strong", {}, "По выбранным фильтрам записей нет"),
      el("span", {}, "Расширьте период, сбросьте нишу или достоверность. Новые записи появятся после запуска парсера.")));
    return;
  }
  const order = [...DATA.niches.map((n) => n.label), "Без ниши"];
  const groups = new Map(order.map((l) => [l, []]));
  shown.forEach((it) => groups.get(it.niche)?.push(it));
  for (const label of order) {
    const items = groups.get(label);
    if (!items.length) continue;
    const meta = DATA.niches.find((n) => n.label === label);
    const head = el("div", { class: "niche-head" },
      meta ? el("span", { class: "sph" }, meta.sphere) : null,
      el("h2", {}, label), el("span", { class: "okved" }, `${items.length} зап.` + (meta ? ` · ОКВЭД ${meta.okved.join(", ")}` : "")));
    const ledger = el("div", { class: "ledger" });
    items.forEach((it) => ledger.append(itemNode(it)));
    list.append(el("section", { class: "niche" }, head, ledger));
  }
}

function renderSources() {
  const rows = DATA.sources, answered = rows.filter((s) => s.run?.ok).length, ran = rows.filter((s) => s.run).length;
  const stats = $("srcStats"); stats.replaceChildren();
  [[rows.length, "источников подключено"], [ran ? `${answered} из ${ran}` : "—", "ответили в последнем запуске"],
   [rows.reduce((a, s) => a + (s.run?.found || 0), 0), "записей отобрано в последнем запуске"]]
    .forEach(([v, l]) => stats.append(el("div", { class: "stat" }, el("b", {}, String(v)), el("span", {}, l))));
  const body = $("srcRows"); body.replaceChildren();
  for (const s of rows) {
    const res = !s.run ? ["off", "не запускался"] : s.run.ok ? ["ok", "ответил"] : ["fail", "не ответил"];
    body.append(el("tr", {}, el("td", {}, el("strong", {}, s.title), el("div", { class: "note" }, s.focus)),
      el("td", {}, s.tier), el("td", { class: res[0] }, res[1]),
      el("td", { class: "okved" }, s.run ? String(s.run.found) : "—"), el("td", { class: "note" }, s.run?.error || "")));
  }
}

function renderNiches() {
  const box = $("nicheTab"); box.replaceChildren();
  box.append(el("p", { class: "note" }, "Ниша определяется по ключевым словам из keywords.yml (слова сравниваются по нормальной форме). Правка файла действует со следующего запуска."));
  for (const sph of DATA.spheres.filter((s) => s !== "Без ниши")) {
    const wrap = el("div", { class: "niche" }, el("div", { class: "niche-head" }, el("h2", {}, sph)));
    const ledger = el("div", { class: "ledger" });
    DATA.niches.filter((n) => n.sphere === sph).forEach((n) => ledger.append(el("div", { class: "item" },
      el("div", { class: "meta" }, el("strong", { style: "font:600 1rem var(--font-body);color:var(--ink)" }, n.label), el("span", {}, `ОКВЭД ${n.okved.join(", ")}`)),
      el("div", { class: "words" }, n.words.join(", ")))));
    wrap.append(ledger); box.append(wrap);
  }
}

/* ---------- Тренды ---------- */
const T = DATA.trends;
const TVIEWS = [["theme", "Темы"], ["competitor", "Конкуренты"]];
const STATUS = {
  new: ["новая", "new"], up: ["растёт", "high"], steady: ["устойчивая", "mid"],
  down: ["снижается", "low"], calm: ["спокойно", "low"], na: ["", ""],
};
const STATUS_ORDER = ["new", "up", "steady", "down", "calm", "na"];
const tstate = { view: recall("tview", "theme"), group: ALL, steeple: ALL, days: Number(recall("tdays", 30)) };
if (!TVIEWS.some(([v]) => v === tstate.view)) tstate.view = "theme";
if (!PERIODS.some(([d]) => d === tstate.days)) tstate.days = 30;

const addDays = (iso, n) => { const d = new Date(iso + "T00:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
const today = () => new Date().toISOString().slice(0, 10);

// Сравнение долей: сколько сюжетов с темой приходится на все прочитанные
// статьи. Доля не зависит от того, сколько статей удалось собрать за день.
const MIN_BASE = 150;   // минимум статей в периоде, чтобы сравнивать доли
const MIN_BIN = 15;     // минимум статей в столбике графика
function totalBetween(from, to) {
  let n = 0;
  for (const [d, c] of Object.entries(T.daily)) if ((!from || d >= from) && (!to || d < to)) n += c;
  return n;
}
function comparable(days) {
  if (!days) return false;
  return totalBetween(sinceDate(2 * days), sinceDate(days)) >= MIN_BASE && totalBetween(sinceDate(days), "") >= MIN_BASE;
}
const pct = (x) => (x * 100).toLocaleString("ru-RU", { maximumFractionDigits: x < 0.01 ? 2 : 1 }) + "%";

function tagStats(idx, days) {
  const stories = T.stories[String(idx)] || [];
  const from = days ? sinceDate(days) : "", prevFrom = days ? sinceDate(2 * days) : "";
  const cur = [], prev = [];
  for (const s of stories) {
    if (!days || s[0] >= from) cur.push(s);
    else if (s[0] >= prevFrom) prev.push(s);
  }
  const arts = cur.flatMap((s) => s[1].map((i) => T.articles[i]));
  const outlets = new Set(arts.map((a) => a[1])).size;
  const cats = new Map();
  for (const a of arts) { const c = T.outlets[a[1]].category; cats.set(c, (cats.get(c) || 0) + 1); }
  const curTotal = totalBetween(from, ""), prevTotal = days ? totalBetween(prevFrom, from) : 0;
  const share = curTotal ? cur.length / curTotal : 0, prevShare = prevTotal ? prev.length / prevTotal : 0;
  let status = "na";
  if (comparable(days)) {
    const c = cur.length, p = prev.length;
    if (p === 0 && c >= 3 && outlets >= 3) status = "new";
    else if (p > 0 && share >= 2 * prevShare && c >= 3 && outlets >= 3) status = "up";
    else if (p >= 3 && share * 2 <= prevShare) status = "down";
    else if (c >= 5 && outlets >= 3) status = "steady";
    else status = "calm";
  }
  return { cur, prev, pubs: arts.length, outlets, cats, share, prevShare, status };
}

// Столбики: доля сюжетов по дням (неделя, месяц) или неделям (3 месяца,
// всё время). Серый — в этот день или неделю статей собрано слишком мало.
function sparkline(dates, days) {
  const end = today();
  const start = days ? sinceDate(days) : (T.history_start || end);
  const span = Math.max(1, Math.round((new Date(end) - new Date(start)) / 864e5) + 1);
  const step = span > 45 ? 7 : 1;
  const n = Math.min(60, Math.ceil(span / step));
  const hits = new Array(n).fill(0), totals = new Array(n).fill(0);
  const binOf = (d) => Math.floor((new Date(d) - new Date(start)) / 864e5 / step);
  for (const d of dates) { const i = binOf(d); if (i >= 0 && i < n) hits[i]++; }
  for (const [d, c] of Object.entries(T.daily)) { const i = binOf(d); if (i >= 0 && i < n) totals[i] += c; }
  const shares = hits.map((h, i) => totals[i] >= MIN_BIN ? h / totals[i] : null);
  const max = Math.max(0.0001, ...shares.filter((x) => x != null)), w = 6, h = 30;
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("class", "spark"); svg.setAttribute("viewBox", `0 0 ${n * w} ${h}`);
  svg.setAttribute("preserveAspectRatio", "none"); svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `Доля сюжетов ${step === 7 ? "по неделям" : "по дням"}`);
  shares.forEach((v, i) => {
    const r = document.createElementNS(ns, "rect");
    const bh = v == null ? 1 : v ? Math.max(2, (v / max) * (h - 2)) : 1;
    r.setAttribute("x", i * w + 0.5); r.setAttribute("width", w - 1.5);
    r.setAttribute("y", h - bh); r.setAttribute("height", bh);
    if (!v) r.setAttribute("class", "prev");
    const t = document.createElementNS(ns, "title");
    t.textContent = `${ruDate(addDays(start, i * step))}: ` + (v == null ? `мало статей (${totals[i]})` : `${hits[i]} сюж. на ${totals[i]} статей (${pct(v)})`);
    r.append(t); svg.append(r);
  });
  return svg;
}

function headline(a, extra) {
  const u = safeUrl(a[3]);
  const source = T.outlets[a[1]].title;
  return el("li", {}, el("span", {}, `${ruDate(a[0])} · ${source}`),
    u ? el("a", { href: u, target: "_blank", rel: "noopener" }, a[2]) : a[2],
    extra ? el("em", {}, extra) : null);
}

function catLine(cats) {
  if (!cats.size) return null;
  const parts = [...cats.entries()].sort((a, b) => b[1] - a[1]).map(([c, n]) => `${c} ${n}`);
  return el("div", { class: "nums" }, "Кто пишет: " + parts.join(" · "));
}

function trendNode(tag, st) {
  const [stText, stClass] = STATUS[st.status];
  const prevText = comparable(tstate.days) ? ` · было ${pct(st.prevShare)} (${st.prev.length} сюж.)` : "";
  const node = el("article", { class: "item" + (tag.self ? " self" : "") },
    el("div", { class: "meta" },
      stText ? el("span", { class: "pill " + stClass }, stText) : null,
      tag.self ? el("span", { class: "pill new" }, "мы") : null,
      el("span", {}, [tag.group, ...tag.steeple].join(" · "))),
    el("h3", {}, tag.label),
    el("div", { class: "nums" }, el("b", {}, pct(st.share)), " · ", el("b", {}, String(st.cur.length)), " сюж. (",
      String(st.pubs), " публ.) · ", el("b", {}, String(st.outlets)), " изд." + prevText),
    catLine(st.cats),
    sparkline(st.cur.map((s) => s[0]), tstate.days));
  if (st.cur.length) {
    const ul = el("ul");
    [...st.cur].sort((a, b) => (a[0] < b[0] ? 1 : -1)).slice(0, 8).forEach((s) => {
      const more = s[1].length > 1 ? ` · ещё ${s[1].length - 1} публ.` : "";
      ul.append(headline(T.articles[s[1][0]], more));
    });
    node.append(el("details", { class: "heads" },
      el("summary", {}, `Сюжеты (${Math.min(8, st.cur.length)} из ${st.cur.length})`), ul));
  }
  return node;
}

function renderTrendControls() {
  const v = $("tViews"); v.replaceChildren();
  for (const [id, t] of TVIEWS) v.append(chip(t, tstate.view === id, () => {
    tstate.view = id; tstate.group = ALL; remember("tview", id); renderTrends();
  }));
  const tagView = tstate.view === "theme" || tstate.view === "competitor";
  $("tGroupBox").hidden = !tagView;
  $("tSteepleBox").hidden = tstate.view !== "theme";
  if (tagView) {
    $("tGroupLabel").textContent = tstate.view === "theme" ? "Сфера" : "Группа";
    const groups = [...new Set(T.tags.filter((t) => t.kind === tstate.view).map((t) => t.group))];
    if (!groups.includes(tstate.group)) tstate.group = ALL;
    const g = $("tGroups"); g.replaceChildren();
    for (const gr of [ALL, ...groups]) g.append(chip(gr === ALL ? "Все" : gr, tstate.group === gr, () => { tstate.group = gr; renderTrends(); }));
  }
  const sp = $("tSteeple"); sp.replaceChildren();
  for (const s of [ALL, ...T.steeple]) sp.append(chip(s === ALL ? "Все" : s, tstate.steeple === s, () => { tstate.steeple = s; renderTrends(); }));
  const p = $("tPeriods"); p.replaceChildren();
  for (const [d, t] of PERIODS) p.append(chip(t, tstate.days === d, () => { tstate.days = d; remember("tdays", String(d)); renderTrends(); }));
}

function setStats(pairs) {
  const stats = $("tStats"); stats.replaceChildren();
  pairs.forEach(([v, l]) => stats.append(el("div", { class: "stat" }, el("b", {}, String(v)), el("span", {}, l))));
}

function emptyBox(title, text) {
  return el("div", { class: "empty" }, el("strong", {}, title), el("span", {}, text));
}

function renderTagView() {
  const hist = $("tHistory");
  if (!T.history_start) {
    hist.textContent = "Статьи для трендов ещё не собраны: они начнут копиться после следующего запуска парсера.";
  } else {
    const base = `Сравниваются доли: сколько сюжетов с темой приходится на все прочитанные статьи. Сюжет — одна новость во всех изданиях. Сбор статей идёт с ${ruDate(T.collecting_since)}; более ранние дни восстановлены из лент частично.`;
    hist.textContent = !tstate.days ? base + " За всё время статусы не считаются."
      : comparable(tstate.days) ? base
      : base + ` За предыдущий период статей меньше ${MIN_BASE} — статусов пока нет, они появятся по мере ежедневных запусков.`;
  }
  const tags = T.tags.map((t, i) => ({ t, i })).filter(({ t }) => t.kind === tstate.view
    && (tstate.group === ALL || t.group === tstate.group)
    && (tstate.view !== "theme" || tstate.steeple === ALL || t.steeple.includes(tstate.steeple)));
  const rows = tags.map(({ t, i }) => ({ tag: t, st: tagStats(i, tstate.days) }));
  const active = rows.filter((r) => r.st.cur.length || r.st.prev.length || r.tag.self);
  const silent = rows.filter((r) => !r.st.cur.length && !r.st.prev.length && !r.tag.self);
  active.sort((a, b) => (b.tag.self - a.tag.self) || (STATUS_ORDER.indexOf(a.st.status) - STATUS_ORDER.indexOf(b.st.status)) || (b.st.share - a.st.share));
  const cnt = (s) => rows.filter((r) => r.st.status === s).length;
  const ok = comparable(tstate.days);
  setStats([[totalBetween(tstate.days ? sinceDate(tstate.days) : "", ""), "статей прочитано за период"],
    [ok ? cnt("new") : "—", "новых"], [ok ? cnt("up") : "—", "растут"], [ok ? cnt("down") : "—", "снижаются"]]);
  const list = $("tList"); list.replaceChildren();
  if (!active.length) {
    list.append(emptyBox("За период упоминаний нет", "Расширьте период или выберите другую сферу. Статьи копятся с каждым запуском парсера."));
  } else {
    const ledger = el("div", { class: "ledger" });
    active.forEach((r) => ledger.append(trendNode(r.tag, r.st)));
    list.append(ledger);
  }
  if (silent.length) list.append(el("p", { class: "quiet" }, "Без упоминаний за период: " + silent.map((r) => r.tag.label).join(", ") + "."));
  $("tHelp").replaceChildren(
    "Статусы — сравнение с таким же предыдущим периодом. ", el("b", {}, "Новая"), ": раньше не было, сейчас ≥3 сюжетов в ≥3 изданиях. ",
    el("b", {}, "Растёт"), ": доля выросла вдвое, ≥3 издания. ", el("b", {}, "Устойчивая"), ": ≥5 сюжетов в ≥3 изданиях без резких изменений. ",
    el("b", {}, "Снижается"), ": доля упала вдвое (было ≥3 сюжетов). Ленты одного издания считаются одним изданием. ",
    "«Кто пишет» — типы источников из sources.yml. Темы, конкуренты и тип STEEPLE задаются в trends.yml.");
}

function renderTrends() {
  renderTrendControls();
  renderTagView();
}

function renderDict() {
  const box = $("dictTab"); box.replaceChildren();
  box.append(el("p", { class: "note" }, "Темы ищутся по нормальной форме слов, конкуренты — по названию с русскими окончаниями. Правка trends.yml действует при следующей сборке страницы: сохранённые статьи размечаются заново."));
  const groups = [];
  for (const t of T.tags) { const key = (t.kind === "theme" ? "Темы · " : "Конкуренты · ") + t.group; if (!groups.includes(key)) groups.push(key); }
  for (const g of groups) {
    const wrap = el("div", { class: "niche" }, el("div", { class: "niche-head" }, el("h2", {}, g)));
    const ledger = el("div", { class: "ledger" });
    T.tags.filter((t) => (t.kind === "theme" ? "Темы · " : "Конкуренты · ") + t.group === g).forEach((t) => ledger.append(el("div", { class: "item" },
      el("div", { class: "meta" }, el("strong", { style: "font:600 1rem var(--font-body);color:var(--ink)" }, t.label), t.self ? el("span", { class: "pill new" }, "мы") : null),
      el("div", { class: "words" }, t.words.join(", ")))));
    wrap.append(ledger); box.append(wrap);
  }
}

// Основной режим — вкладки «Регуляторика» и «Тренды». Источники и словари —
// отдельный справочный режим с собственными разделами.
const MAIN = [["feed", "feed"], ["trend", "trendTab"]];
const SETTINGS = [["src", "src"], ["niche", "nicheTab"], ["dict", "dictTab"]];
function showTab(which) {
  const inSettings = SETTINGS.some(([t]) => t === which);
  $("mainTabs").hidden = inSettings;
  $("settingsHead").hidden = !inSettings;
  $("openSettings").hidden = inSettings;
  for (const [t, id] of MAIN) { $("tab-" + t).setAttribute("aria-selected", String(t === which)); $(id).hidden = t !== which; }
  for (const [t, id] of SETTINGS) { $("tab-" + t).setAttribute("aria-pressed", String(t === which)); $(id).hidden = t !== which; }
  $("regFooter").hidden = which !== "feed";
  if (inSettings) remember("settingsTab", which); else remember("tab", which);
  window.scrollTo(0, 0);
}
$("tab-feed").onclick = () => showTab("feed");
$("tab-trend").onclick = () => showTab("trend");
$("tab-src").onclick = () => showTab("src");
$("tab-niche").onclick = () => showTab("niche");
$("tab-dict").onclick = () => showTab("dict");
$("openSettings").onclick = () => showTab(recall("settingsTab", "src"));
$("closeSettings").onclick = () => showTab(recall("tab", "feed"));
$("q").oninput = (e) => { state.q = e.target.value.trim().toLowerCase(); render(); };
$("copyAll").onclick = () => copyText(DATA.items.filter((it) => inScope(it)).map(itemText).join("\n\n"), $("copyAll"));
$("status").textContent = (DATA.last_run ? `Последний запуск ${DATA.last_run}` : "Парсер ещё не запускался") + ` · записей: ${DATA.items.length}`;
render(); renderSources(); renderNiches(); renderTrends(); renderDict();
{ const t = recall("tab", "feed"); showTab(["feed", "trend"].includes(t) ? t : "feed"); }
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
