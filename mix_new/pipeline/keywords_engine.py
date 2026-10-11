"""Загрузка keywords.yml и отбор новостей по правилам из tz_news_parser.md
(раздел «Ключевые слова», правила 1-7).

Слова ищутся по основе (подстрокой) без учёта регистра и с заменой ё на е
— кроме аббревиатур (abbreviations), которые ищутся только целым словом,
иначе они совпадают с частью других слов."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from config import KEYWORDS_PATH
from pipeline.normalize import normalize_text

STEM_GROUPS = ("acts_and_bodies", "stages", "changes", "topics", "exclusions")


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
    matched: list[tuple[str, str]]  # (слово, группа)
    industries: list[IndustryGroup]  # отрасли, чьи слова нашлись в тексте


def load_keywords(path: Path = KEYWORDS_PATH) -> KeywordSet:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    industries = [
        IndustryGroup(label=entry["words"][0], words=entry["words"], okved=entry["okved"])
        for entry in raw.get("industries", [])
    ]
    return KeywordSet(
        acts_and_bodies=[normalize_text(w) for w in raw.get("acts_and_bodies", [])],
        stages=[normalize_text(w) for w in raw.get("stages", [])],
        changes=[normalize_text(w) for w in raw.get("changes", [])],
        topics=[normalize_text(w) for w in raw.get("topics", [])],
        exclusions=[normalize_text(w) for w in raw.get("exclusions", [])],
        abbreviations=list(raw.get("abbreviations", [])),
        industries=industries,
    )


@lru_cache(maxsize=1)
def get_keyword_set() -> KeywordSet:
    return load_keywords()


def _stem_matches(text: str, words: list[str], group: str) -> list[tuple[str, str]]:
    return [(w, group) for w in words if w in text]


def _abbreviation_matches(text: str, abbreviations: list[str]) -> list[tuple[str, str]]:
    found = []
    for abbr in abbreviations:
        pattern = r"\b" + re.escape(abbr.lower()) + r"\b"
        if re.search(pattern, text, flags=re.IGNORECASE):
            found.append((abbr, "abbreviations"))
    return found


def _industry_matches(text: str, industries: list[IndustryGroup]) -> tuple[list[tuple[str, str]], list[IndustryGroup]]:
    matched_words = []
    matched_groups = []
    for group in industries:
        hits = [w for w in group.words if normalize_text(w) in text]
        if hits:
            matched_words.extend((w, "industries") for w in hits)
            matched_groups.append(group)
    return matched_words, matched_groups


def match(title: str, annotation: str | None = None, keyword_set: KeywordSet | None = None) -> MatchResult:
    keyword_set = keyword_set or get_keyword_set()
    text = normalize_text(f"{title} {annotation or ''}")

    matched: list[tuple[str, str]] = []
    for group_name in STEM_GROUPS:
        matched.extend(_stem_matches(text, getattr(keyword_set, group_name), group_name))
    matched.extend(_abbreviation_matches(text, keyword_set.abbreviations))

    industry_words, industry_groups = _industry_matches(text, keyword_set.industries)
    matched.extend(industry_words)

    groups_found = {group for _, group in matched}
    has_exclusion = "exclusions" in groups_found
    has_change_or_stage = bool({"changes", "stages"} & groups_found)
    has_context = bool({"acts_and_bodies", "topics", "industries"} & groups_found)

    passed = has_change_or_stage and has_context and not has_exclusion
    return MatchResult(passed=passed, matched=matched, industries=industry_groups)
