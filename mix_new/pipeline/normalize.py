"""Нормализация ссылок, текста и дат перед фильтрацией/дедупликацией."""
from __future__ import annotations

from datetime import datetime
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from zoneinfo import ZoneInfo

from config import MOSCOW_TZ_NAME

MOSCOW_TZ = ZoneInfo(MOSCOW_TZ_NAME)

_TRACKING_PARAM_PREFIXES = ("utm_", "yclid", "fbclid", "gclid")


def normalize_url(url: str) -> str:
    """Убирает utm-метки и якоря, приводит к единому виду для дедупликации."""
    parts = urlsplit(url.strip())
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith(_TRACKING_PARAM_PREFIXES)
    ]
    cleaned_query = urlencode(query_pairs)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, cleaned_query, ""))


def normalize_text(text: str) -> str:
    """Нижний регистр, ё → е. Используется перед поиском ключевых слов."""
    return (text or "").lower().replace("ё", "е")


def to_moscow_tz(dt: datetime) -> datetime:
    """Приводит дату/время к часовому поясу Москвы. Наивную дату считает UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(MOSCOW_TZ)
