"""Связь с реестром регуляторных изменений (шаг 7 ТЗ): если номер и дата
акта совпали с уже существующей карточкой в таблице acts, новость
помечается как относящаяся к этому акту, новая карточка не создаётся."""
from __future__ import annotations

import sqlite3
from datetime import date

from registry.db import find_act_by_number_and_date


def find_related_act_id(conn: sqlite3.Connection, act_number: str | None, act_date: date | None) -> int | None:
    if not act_number or not act_date:
        return None
    act = find_act_by_number_and_date(conn, act_number, act_date)
    return act.db_id if act else None
