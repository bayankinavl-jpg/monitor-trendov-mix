"""XLSX-экспорт реестра: только подтверждённые карточки."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.worksheet.worksheet import Worksheet

from models import Act
from registry.db import list_acts

COLUMNS = [
    "Уровень НПА",
    "Изменение",
    "Вид НПА и вид поправки",
    "Что меняется",
    "На кого распространяется",
    "Когда",
    "Ссылка",
    "Статус проверки",
]


def _format_what_changes(act: Act) -> str:
    return "\n".join(f"- {b}" for b in act.summary_bullets)


def _format_target(act: Act) -> str:
    if act.cross_cutting:
        return "сквозное"
    parts = list(act.okved_codes) + list(act.commodity_groups)
    if not parts:
        return act.linkage_note or "привязка не определена"
    return ", ".join(parts)


def _format_when(act: Act) -> str:
    return "\n".join(f"{s.date_text} — {s.what_changes}" for s in act.stages)


def export_xlsx(conn: sqlite3.Connection, out_path: Path) -> int:
    acts = list_acts(conn, include_unconfirmed=False)

    wb = Workbook()
    ws: Worksheet = wb.active
    ws.title = "Реестр изменений"
    ws.append(COLUMNS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.freeze_panes = "A2"

    for act in acts:
        ws.append(
            [
                act.level.value,
                act.title,
                f"{act.act_kind} / {act.amendment_type.value if act.amendment_type else ''}",
                _format_what_changes(act),
                _format_target(act),
                _format_when(act),
                act.source_url or "",
                act.status.value,
            ]
        )

    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True)

    widths = [18, 40, 28, 40, 25, 30, 40, 18]
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = width

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return len(acts)
