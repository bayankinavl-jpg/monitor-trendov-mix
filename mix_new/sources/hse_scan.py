"""Разбор ленты новостей сайтов НИУ ВШЭ (например, https://issek.hse.ru/news/).

У этих сайтов нет RSS, поэтому читается HTML-страница со списком новостей
(robots.txt разрешает). Возвращает те же кортежи, что и разбор RSS:
(заголовок, ссылка, аннотация, дата в формате ISO)."""
from __future__ import annotations

from bs4 import BeautifulSoup

_MONTHS = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "мая": 5, "май": 5, "июн": 6,
    "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
}


class NotHseNewsPageError(ValueError):
    """На странице нет списка новостей в формате сайтов ВШЭ."""


def parse_hse_news(content: bytes) -> list[tuple[str, str, str, str | None]]:
    soup = BeautifulSoup(content, "html.parser")
    posts = soup.select("div.post")
    if not posts:
        raise NotHseNewsPageError("на странице нет списка новостей (div.post): сайт изменил вёрстку")
    items = []
    for post in posts:
        a = post.select_one(".post__content h2 a[href]")
        if a is None:
            continue
        title = a.get_text(" ", strip=True)
        link = a["href"]
        if link.startswith("//"):
            link = "https:" + link
        elif link.startswith("/"):
            link = "https://www.hse.ru" + link
        text_el = post.select_one(".post__text")
        text = text_el.get_text(" ", strip=True) if text_el else ""
        published = None
        day = post.select_one(".post-meta__day")
        month = post.select_one(".post-meta__month")
        year = post.select_one(".post-meta__year")
        if day and month and year:
            m = _MONTHS.get(month.get_text(strip=True).lower()[:3])
            try:
                if m:
                    published = f"{int(year.get_text(strip=True)):04d}-{m:02d}-{int(day.get_text(strip=True)):02d}"
            except ValueError:
                published = None
        items.append((title, link, text, published))
    return items
