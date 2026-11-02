"""XLSX-выгрузка реестра новостей: 4 листа — Новости, Источники,
Ключевые слова, Сводка по месяцам (см. tz_news_parser.md)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import yaml
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

from config import KEYWORDS_PATH
from models import NewsItem
from registry.db import get_journal_for_run, list_news_items

NEWS_COLUMNS = [
    "Дата публикации",
    "Заголовок",
    "Ссылка",
    "Источники",
    "Совпавшие слова",
    "Тип изменения",
    "Уровень НПА",
    "Стадия",
    "Тема",
    "Отрасль",
    "Коды ОКВЭД",
    "Реквизиты акта",
    "Упомянутые законы",
    "Достоверность",
    "Основание оценки",
    "Статус записи",
    "Статус ручной проверки",
    "Ссылка на текст акта",
    "Первое обнаружение",
]

SOURCES_COLUMNS = ["Источник", "Статус", "Найдено", "Ошибок", "Детали"]


def _requisites(item: NewsItem) -> str:
    if not item.act_number and not item.act_date:
        return ""
    parts = []
    if item.act_number:
        parts.append(f"№ {item.act_number}")
    if item.act_date:
        parts.append(f"от {item.act_date.strftime('%d.%m.%Y')}")
    return " ".join(parts)


def _matched_keywords_str(item: NewsItem) -> str:
    return ", ".join(f"{w} ({g})" for w, g in item.matched_keywords)


def _news_row(item: NewsItem) -> list:
    return [
        item.published_at.strftime("%d.%m.%Y %H:%M"),
        item.title,
        item.links[0] if item.links else "",
        f"{len(item.sources)}: " + ", ".join(item.sources),
        _matched_keywords_str(item),
        item.amendment_type.value if item.amendment_type else "",
        item.level.value if item.level else "",
        item.stage or "",
        item.topic or "",
        item.industry or "",
        ", ".join(item.okved_codes),
        _requisites(item),
        "\n".join(item.referenced_acts),
        item.credibility.value,
        "\n".join(item.credibility_reasons),
        item.record_status.value,
        item.manual_check_status.value,
        item.act_text_url or "",
        item.first_seen_date.strftime("%d.%m.%Y"),
    ]


def _write_news_sheet(wb: Workbook, items: list[NewsItem]) -> None:
    ws = wb.active
    ws.title = "Новости"
    ws.append(NEWS_COLUMNS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.freeze_panes = "A2"
    for item in items:
        ws.append(_news_row(item))
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True)


def _write_sources_sheet(wb: Workbook, conn: sqlite3.Connection, run_id: str | None) -> None:
    ws = wb.create_sheet("Источники")
    ws.append(SOURCES_COLUMNS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    if run_id is None:
        return
    for row in get_journal_for_run(conn, run_id):
        status = "недоступен" if row["unreachable"] else "ок"
        ws.append([row["source_name"], status, row["found_count"], row["error_count"], row["detail_json"]])


def _write_keywords_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("Ключевые слова")
    raw = yaml.safe_load(KEYWORDS_PATH.read_text(encoding="utf-8"))
    ws.append(["Группа", "Слова / отрасли"])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for group in ("acts_and_bodies", "stages", "markers", "changes", "topics", "exclusions", "abbreviations"):
        ws.append([group, ", ".join(raw.get(group, []))])
    for entry in raw.get("industries", []):
        ws.append(["industries", f"{', '.join(entry['words'])} -> {', '.join(entry['okved'])}"])


def _write_monthly_summary_sheet(wb: Workbook, items: list[NewsItem]) -> None:
    ws = wb.create_sheet("Сводка по месяцам")
    ws.append(["Месяц", "Тема", "Отрасль", "Записей с реквизитами"])
    for cell in ws[1]:
        cell.font = Font(bold=True)

    with_requisites = [item for item in items if item.act_number and item.act_date]
    counts: dict[tuple[str, str, str], int] = {}
    for item in with_requisites:
        month = item.published_at.strftime("%Y-%m")
        key = (month, item.topic or "", item.industry or "")
        counts[key] = counts.get(key, 0) + 1

    for (month, topic, industry), count in sorted(counts.items()):
        ws.append([month, topic, industry, count])

    total_row = ["Итого", "", "", len(with_requisites)]
    ws.append(total_row)


def export_news_xlsx(conn: sqlite3.Connection, out_path: Path, run_id: str | None = None) -> int:
    items = list_news_items(conn)

    wb = Workbook()
    _write_news_sheet(wb, items)
    _write_sources_sheet(wb, conn, run_id)
    _write_keywords_sheet(wb)
    _write_monthly_summary_sheet(wb, items)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return len(items)
