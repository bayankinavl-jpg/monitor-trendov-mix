"""Разметка статей для вкладки «Тренды»: темы (trends.yml → themes) и
конкуренты (trends.yml → competitors).

Тема ищется по нормальной форме слов (как keywords.yml), конкурент — по
названию как написано, с русскими окончаниями. Сами тренды (рост, новая,
устойчивая) считаются на странице в браузере по датам упоминаний, потому
что зависят от выбранного периода."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from config import TRENDS_PATH
from pipeline.keywords_engine import phrase_in
from pipeline.morph import lemma_pos, lemmas, words
from pipeline.normalize import normalize_text

# Окончания, с которыми название компании ещё считается тем же словом:
# «Модульбанк» → «Модульбанка», «Модульбанком»; «ВТБ» → только «ВТБ».
_ENDINGS = r"(?:а|я|у|ю|ом|ем|е|ы|и|ой|ей|ов|ев|ам|ям|ами|ями|ах|ях)?"
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class Theme:
    id: str
    label: str
    sphere: str
    words: list[str]
    steeple: list[str] = field(default_factory=list)  # тип тренда по STEEPLE
    with_competitor: bool = False  # тема засчитывается, только если в статье назван конкурент


@dataclass
class Competitor:
    id: str
    label: str
    group: str
    names: list[str]
    is_self: bool = False
    patterns: list[re.Pattern] = field(default_factory=list, repr=False)


@dataclass
class TrendDictionary:
    themes: list[Theme]
    competitors: list[Competitor]
    version: str  # хеш файла: если словарь изменился, статьи размечаются заново


def _name_pattern(name: str) -> re.Pattern:
    body = re.escape(normalize_text(name))
    # Название в кавычках («Точка») ищем как есть, без окончаний.
    if name.startswith("«"):
        return re.compile(body)
    return re.compile(r"(?<![\w-])" + body + _ENDINGS + r"(?![\w-])")


def load_trends(path: Path = TRENDS_PATH) -> TrendDictionary:
    raw_text = path.read_text(encoding="utf-8")
    raw = yaml.safe_load(raw_text) or {}
    themes = [
        Theme(id=f"t{i}", label=t["label"], sphere=t.get("sphere", "Другое"), words=list(t["words"]),
              steeple=list(t.get("steeple") or []), with_competitor=bool(t.get("with_competitor")))
        for i, t in enumerate(raw.get("themes", []))
    ]
    competitors = []
    for i, c in enumerate(raw.get("competitors", [])):
        names = [str(n) for n in c["names"]]
        competitors.append(Competitor(
            id=f"c{i}", label=c["label"], group=c.get("group", "Конкуренты"), names=names,
            is_self=bool(c.get("self")), patterns=[_name_pattern(n) for n in names],
        ))
    version = hashlib.sha1(raw_text.encode("utf-8")).hexdigest()[:12]
    return TrendDictionary(themes=themes, competitors=competitors, version=version)


@lru_cache(maxsize=1)
def get_trends() -> TrendDictionary:
    return load_trends()


def clean_text(text: str | None) -> str:
    """Убирает HTML-теги из описания RSS и лишние пробелы."""
    return " ".join(_TAG_RE.sub(" ", text or "").split())


def tag_article(title: str, text: str | None, trends: TrendDictionary | None = None) -> list[str]:
    """Возвращает id тем и конкурентов, которые упомянуты в статье."""
    trends = trends or get_trends()
    raw = f"{title} {clean_text(text)}"
    text_lemmas = lemmas(raw)
    lowered = normalize_text(raw)
    found = [c.id for c in trends.competitors if any(p.search(lowered) for p in c.patterns)]
    tags = [
        t.id for t in trends.themes
        if (found or not t.with_competitor) and any(phrase_in(text_lemmas, w) for w in t.words)
    ]
    return tags + found


# ---- Заголовок как последовательность значимых слов ----
# Нужна для склейки статей в сюжеты.
TOKENS_VERSION = "2"  # поменять, если изменились правила ниже: заголовки разберутся заново

# Слова, которые встречаются в новостях постоянно и сами ничего не значат.
STOP_LEMMAS = set("""
год месяц неделя день час минута время раз число процент доля половина треть
январь февраль март апрель май июнь июль август сентябрь октябрь ноябрь декабрь
понедельник вторник среда четверг пятница суббота воскресенье сегодня
россия рф российский страна мир москва регион город сша европа китай
рубль доллар евро тысяча млн млрд трлн миллион миллиард
человек люди компания организация власть правительство президент глава министр
эксперт аналитик специалист представитель гендиректор директор
новость данные итог вопрос слово дело случай часть место сторона тема
новый главный крупный большой первый второй третий последний весь такой это
""".split())


def title_tokens(title: str) -> str:
    """Значимые слова заголовка в нормальной форме с пометкой части речи
    («маркетплейс/N»); «|» — разрыв между ними (предлог, глагол, число,
    служебное слово)."""
    out: list[str] = []
    for w in words(title):
        lem, pos = lemma_pos(w)
        if not pos or lem in STOP_LEMMAS or (len(lem) < 3 and pos != "N"):
            if out and out[-1] != "|":
                out.append("|")
            continue
        out.append(f"{lem}/{pos}")
    while out and out[-1] == "|":
        out.pop()
    return " ".join(out)


def token_set(tokens: str) -> set[str]:
    return {t.split("/")[0] for t in tokens.split() if t != "|"}


def group_stories(items: list[tuple[int, str, set[str]]], days: int = 3,
                  threshold: float = 0.3) -> list[list[int]]:
    """Склеивает статьи об одном событии в сюжеты.

    items — (номер статьи, дата ISO, слова заголовка), отсортированные по
    дате. Статья присоединяется к сюжету, если сюжет начался не раньше чем
    за days дней и заголовок статьи похож на заголовок хотя бы одной статьи
    сюжета: общих слов не меньше двух и их доля ≥ threshold."""
    from datetime import date as _date

    stories: list[tuple[_date, list[set[str]], list[int]]] = []
    for idx, iso, toks in items:
        d = _date.fromisoformat(iso)
        best, best_score = None, 0.0
        for story in reversed(stories):
            if (d - story[0]).days > days:
                break
            for other in story[1]:
                common = toks & other
                if len(common) < 2:
                    continue
                score = len(common) / len(toks | other)
                if score >= threshold and score > best_score:
                    best, best_score = story, score
        if best is None:
            stories.append((d, [toks], [idx]))
        else:
            best[1].append(toks)
            best[2].append(idx)
    return [s[2] for s in stories]
