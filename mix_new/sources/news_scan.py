"""Сканер RSS-лент новостных СМИ как источник СИГНАЛОВ (не истины).

Каждая найденная новость — это только наводка (NewsLead): заголовок, ссылка
на новость, дата. Сама новость никогда не становится карточкой акта —
только проверка на первоисточнике (см. news_check.verify_lead) может
превратить наводку либо в обычную карточку (со статусом из первоисточника),
либо в карточку со статусом "не подтверждено"."""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime

import requests
from dateutil import parser as dateutil_parser

from config import HTTP_TIMEOUT, HTTP_USER_AGENT, NEWS_RELEVANCE_KEYWORDS, REQUEST_DELAY_SECONDS, RSS_FEEDS


@dataclass
class NewsLead:
    title: str
    link: str
    published: date | None
    feed_name: str


class FeedUnavailableError(Exception):
    pass


def scan_all_feeds(since: date, until: date, feeds: dict[str, str] | None = None) -> tuple[list[NewsLead], dict[str, str]]:
    """Возвращает (найденные наводки, {имя_ленты: причина ошибки} для недоступных лент).

    Никогда не бросает исключение наружу за одну ленту — недоступность одной
    ленты не должна останавливать сканирование остальных; ошибки собираются
    и возвращаются журналу вызывающей стороной."""
    feeds = feeds or RSS_FEEDS
    leads: list[NewsLead] = []
    errors: dict[str, str] = {}
    session = requests.Session()
    session.headers.update({"User-Agent": HTTP_USER_AGENT})

    for feed_name, url in feeds.items():
        try:
            items = _fetch_feed(session, feed_name, url)
        except FeedUnavailableError as exc:
            errors[feed_name] = str(exc)
            continue
        for title, link, pub_raw in items:
            published = _try_parse_date(pub_raw)
            if published is not None and not (since <= published <= until):
                continue
            if not _is_relevant(title):
                continue
            leads.append(NewsLead(title=title.strip(), link=link.strip(), published=published, feed_name=feed_name))
        time.sleep(REQUEST_DELAY_SECONDS)

    return leads, errors


def _fetch_feed(session: requests.Session, feed_name: str, url: str) -> list[tuple[str, str, str | None]]:
    try:
        resp = session.get(url, timeout=HTTP_TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise FeedUnavailableError(f"{feed_name}: сетевая ошибка — {exc}") from exc

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as exc:
        raise FeedUnavailableError(f"{feed_name}: не удалось разобрать RSS/XML — {exc}") from exc

    items = []
    for item in root.iter("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        pub_el = item.find("pubDate")
        if title_el is None or link_el is None:
            continue
        items.append((title_el.text or "", link_el.text or "", pub_el.text if pub_el is not None else None))
    return items


def _try_parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return dateutil_parser.parse(raw).date()
    except (ValueError, OverflowError):
        return None


def _is_relevant(title: str) -> bool:
    lowered = title.lower()
    return any(keyword in lowered for keyword in NEWS_RELEVANCE_KEYWORDS)
