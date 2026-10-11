"""Загрузка keywords.yml и отбор новостей по правилам из tz_news_parser.md
(раздел «Ключевые слова», правила 1-7).

Сравнение идёт по нормальной форме слова (pymorphy3): «ставки», «ставку»
совпадают с «ставка», а «Рыбаря» не совпадает с «рыба». Фраза из
нескольких слов совпадает, если нормальные формы её слов идут в тексте
подряд. Аббревиатуры (abbreviations) ищутся целым словом."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from config import KEYWORDS_PATH
from pipeline.morph import lemmas
from pipeline.normalize import normalize_text

WORD_GROUPS = ("acts_and_bodies", "stages", "changes", "topics", "exclusions")


@dataclass
class IndustryGroup:
    label: str
    words: list[str]
    okved: list[str]


@dataclass
class KeywordSet:
    acts_and_bodies: list[str] = field(default_factory=list)
    stages: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)
    abbreviations: list[str] = field(default_factory=list)
    industries: list[IndustryGroup] = field(default_factory=list)


@dataclass
class MatchResult:
    passed: bool
    matched: list[tuple[str, str]]  # (слово из keywords.yml, группа)
    industries: list[IndustryGroup]


def load_keywords(path: Path = KEYWORDS_PATH) -> KeywordSet:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    industries = [
        IndustryGroup(label=entry.get("label", entry["words"][0]), words=entry["words"], okved=entry["okved"])
        for entry in raw.get("industries", [])
    ]
    return KeywordSet(
        **{group: [normalize_text(w) for w in raw.get(group, [])] for group in WORD_GROUPS},
        abbreviations=list(raw.get("abbreviations", [])),
        industries=industries,
    )


@lru_cache(maxsize=1)
def get_keyword_set() -> KeywordSet:
    return load_keywords()


@lru_cache(maxsize=10_000)
def _phrase_lemmas(phrase: str) -> tuple[str, ...]:
    return tuple(lemmas(phrase))


def phrase_in(text_lemmas: list[str], phrase: str) -> bool:
    target = _phrase_lemmas(phrase)
    if not target:
        return False
    n = len(target)
    return any(tuple(text_lemmas[i:i + n]) == target for i in range(len(text_lemmas) - n + 1))


def _abbreviation_matches(text: str, abbreviations: list[str]) -> list[tuple[str, str]]:
    return [
        (abbr, "abbreviations")
        for abbr in abbreviations
        if re.search(r"(?<!\w)" + re.escape(abbr.lower()) + r"(?!\w)", text, flags=re.IGNORECASE)
    ]


def match(title: str, annotation: str | None = None, keyword_set: KeywordSet | None = None) -> MatchResult:
    keyword_set = keyword_set or get_keyword_set()
    raw_text = f"{title} {annotation or ''}"
    text_lemmas = lemmas(raw_text)

    matched: list[tuple[str, str]] = []
    for group_name in WORD_GROUPS:
        matched.extend((w, group_name) for w in getattr(keyword_set, group_name) if phrase_in(text_lemmas, w))
    matched.extend(_abbreviation_matches(normalize_text(raw_text), keyword_set.abbreviations))

    industry_groups = []
    for group in keyword_set.industries:
        hits = [w for w in group.words if phrase_in(text_lemmas, w)]
        if hits:
            matched.extend((w, "industries") for w in hits)
            industry_groups.append(group)

    groups_found = {group for _, group in matched}
    passed = (
        bool({"changes", "stages"} & groups_found)
        and bool({"acts_and_bodies", "topics", "industries"} & groups_found)
        and "exclusions" not in groups_found
    )
    return MatchResult(passed=passed, matched=matched, industries=industry_groups)
