"""Сканер RSS-лент новостных СМИ — источник СИГНАЛОВ, не истины (см.
tz_news_parser.md). Каждая новость проходит через keywords_engine.match;
подтверждение остаётся за человеком (ручная сверка)."""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from urllib import robotparser

import requests
from dateutil import parser as dateutil_parser

from config import HTTP_RETRY_COUNT, HTTP_TIMEOUT, HTTP_USER_AGENT, REQUEST_DELAY_SECONDS
from pipeline import keywords_engine
from pipeline.normalize import to_moscow_tz
from sources.sources_config import NewsSource, load_sources
from sources.hse_scan import NotHseNewsPageError, parse_hse_news
from sources.telegram_scan import NotTelegramPageError, parse_channel_html
from journal.request_log import RequestLogger


@dataclass
class NewsLead:
    title: str
    link: str
    annotation: str
    published: datetime | None
    source_name: str
    trust_tier: str
    matched_keywords: list[tuple[str, str]]


class FeedUnavailableError(Exception):
    pass


class NotRssError(ValueError):
    """Ответ сайта разобран, но это не RSS-лента (например, HTML-страница)."""


_robots_cache: dict[str, robotparser.RobotFileParser] = {}


def _robots_allowed(feed_url: str, user_agent: str) -> bool:
    from urllib.parse import urlsplit

    parts = urlsplit(feed_url)
    base = f"{parts.scheme}://{parts.netloc}"
    rp = _robots_cache.get(base)
    if rp is None:
        rp = robotparser.RobotFileParser()
        rp.set_url(base + "/robots.txt")
        try:
            rp.read()
        except OSError:
            # robots.txt недоступен — не блокируем сбор из-за этого.
            rp = None
        _robots_cache[base] = rp
    if rp is None:
        return True
    return rp.can_fetch(user_agent, feed_url)


def scan_all_feeds(
    since: date,
    until: date,
    sources: list[NewsSource] | None = None,
    request_logger: RequestLogger | None = None,
    all_items: list[NewsLead] | None = None,
) -> tuple[list[NewsLead], dict[str, str], int]:
    """Возвращает (найденные наводки, {имя_источника: причина ошибки},
    сколько новостей всего прочитано до фильтрации по ключевым словам).

    Недоступность одного источника не останавливает сканирование
    остальных — ошибки собираются и возвращаются журналу вызывающей
    стороной, не подменяются новостями из других лент.

    Если передан список all_items, в него дописываются все прочитанные за
    период новости, а не только отобранные: по ним считаются тренды."""
    sources = sources or load_sources()
    request_logger = request_logger or RequestLogger()
    leads: list[NewsLead] = []
    errors: dict[str, str] = {}
    read_count = 0
    session = requests.Session()
    session.headers.update({"User-Agent": HTTP_USER_AGENT})

    for source in sources:
        if not _robots_allowed(source.feed_url, HTTP_USER_AGENT):
            errors[source.name] = "запрещено robots.txt"
            continue
        try:
            items = _fetch_feed(session, source, request_logger)
        except FeedUnavailableError as exc:
            errors[source.name] = str(exc)
            continue

        for title, link, annotation, pub_raw in items:
            published = _try_parse_date(pub_raw)
            if published is not None:
                published_date = to_moscow_tz(published).date()
                if not (since <= published_date <= until):
                    continue
            read_count += 1
            if all_items is not None:
                all_items.append(NewsLead(
                    title=title.strip(), link=link.strip(), annotation=annotation.strip(),
                    published=to_moscow_tz(published) if published else None,
                    source_name=source.name, trust_tier=source.trust_tier, matched_keywords=[],
                ))
            result = keywords_engine.match(title, annotation)
            if not result.passed:
                continue
            leads.append(
                NewsLead(
                    title=title.strip(),
                    link=link.strip(),
                    annotation=annotation.strip(),
                    published=to_moscow_tz(published) if published else None,
                    source_name=source.name,
                    trust_tier=source.trust_tier,
                    matched_keywords=result.matched,
                )
            )
        time.sleep(REQUEST_DELAY_SECONDS)

    return leads, errors, read_count


def _fetch_feed(
    session: requests.Session, source: NewsSource, request_logger: RequestLogger
) -> list[tuple[str, str, str, str | None]]:
    last_exc: Exception | None = None
    for attempt in range(HTTP_RETRY_COUNT + 1):
        try:
            resp = session.get(source.feed_url, timeout=HTTP_TIMEOUT, allow_redirects=True)
            request_logger.log(source.feed_url, resp.status_code)
            resp.raise_for_status()
            if source.kind == "telegram":
                return parse_channel_html(resp.content)
            if source.kind == "hse":
                return parse_hse_news(resp.content)
            return _parse_rss(resp.content)
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            request_logger.log(source.feed_url, "ERROR", str(exc))
            continue
        except (NotRssError, NotTelegramPageError, NotHseNewsPageError) as exc:
            request_logger.log(source.feed_url, "NOT_RSS", str(exc))
            raise FeedUnavailableError(f"{source.name}: ответ не RSS — {exc}") from exc
        except ET.ParseError as exc:
            request_logger.log(source.feed_url, "PARSE_ERROR", str(exc))
            raise FeedUnavailableError(f"{source.name}: не удалось разобрать RSS/XML — {exc}") from exc

    raise FeedUnavailableError(f"{source.name}: сетевая ошибка — {last_exc}")


def _parse_rss(content: bytes) -> list[tuple[str, str, str, str | None]]:
    # HTML-страница может оказаться корректным XML и разобраться без ошибки,
    # тогда источник молча дал бы 0 записей. Поэтому проверяем явно.
    head = content.lstrip(b"\xef\xbb\xbf \t\r\n")[:100].lower()
    if head.startswith((b"<!doctype html", b"<html")):
        raise NotRssError("сайт вернул HTML-страницу вместо RSS-ленты")
    root = ET.fromstring(content)
    # Некоторые сайты (Retail.ru, New Retail) пишут RSS с пространством имён:
    # <{http://backend.userland.com/rss2}rss>. Убираем его у всех тегов.
    if root.tag.startswith("{"):
        for el in root.iter():
            if isinstance(el.tag, str) and el.tag.startswith("{"):
                el.tag = el.tag.split("}", 1)[1]
    if root.tag != "rss":
        raise NotRssError(f"корневой элемент <{root.tag}>, а не <rss>")
    items = []
    for item in root.iter("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        pub_el = item.find("pubDate")
        desc_el = item.find("description")
        if title_el is None or link_el is None:
            continue
        annotation = (desc_el.text or "") if desc_el is not None else ""
        items.append((title_el.text or "", link_el.text or "", annotation, pub_el.text if pub_el is not None else None))
    return items


def _try_parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return dateutil_parser.parse(raw)
    except (ValueError, OverflowError):
        return None
