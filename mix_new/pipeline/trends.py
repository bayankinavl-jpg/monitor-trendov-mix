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
from pipeline.morph import lemmas
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
              with_competitor=bool(t.get("with_competitor")))
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
