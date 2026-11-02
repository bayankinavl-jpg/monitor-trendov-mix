"""Разбор веб-версии публичного Telegram-канала (https://t.me/s/<канал>).

Страница отдаёт около 20 последних постов. Пост в Telegram не имеет
заголовка, поэтому заголовком становится первая строка текста, а весь
текст идёт в аннотацию. Возвращает те же кортежи, что и разбор RSS:
(заголовок, ссылка, аннотация, дата в формате ISO)."""
from __future__ import annotations

from bs4 import BeautifulSoup

MAX_TITLE_LEN = 200


class NotTelegramPageError(ValueError):
    """Ответ не похож на страницу публичного канала."""


def parse_channel_html(content: bytes) -> list[tuple[str, str, str, str | None]]:
    soup = BeautifulSoup(content, "html.parser")
    messages = soup.select("div.tgme_widget_message[data-post]")
    if not messages:
        raise NotTelegramPageError(
            "на странице нет постов: канал не публичный, не существует "
            "или у него отключена веб-версия"
        )
    items = []
    for msg in messages:
        text_el = msg.select_one(".tgme_widget_message_text")
        if text_el is None:
            continue  # пост без текста (только картинка или видео)
        for br in text_el.find_all("br"):
            br.replace_with("\n")
        text = text_el.get_text().strip()
        if not text:
            continue
        first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), text)
        title = first_line if len(first_line) <= MAX_TITLE_LEN else first_line[:MAX_TITLE_LEN].rstrip() + "…"
        link = f"https://t.me/{msg['data-post']}"
        time_el = msg.select_one("a.tgme_widget_message_date time[datetime]")
        published = time_el["datetime"] if time_el is not None else None
        items.append((title, link, text, published))
    return items
