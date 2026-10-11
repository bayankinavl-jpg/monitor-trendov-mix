"""Общие типы для источников новостей."""
from __future__ import annotations


class SourceUnreachableError(Exception):
    """Источник недоступен (сеть/DNS/таймаут/запрет robots.txt)."""
