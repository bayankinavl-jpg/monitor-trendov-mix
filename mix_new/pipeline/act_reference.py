"""Распознавание упомянутых в новости известных актов РФ по справочнику
reference/law_aliases.json (взят из LawRegexParser).

Три способа:
- по номеру: «381-ФЗ», «№ 381-ФЗ», «№ 357-рп». Номер в справочнике может
  принадлежать нескольким актам разных лет, тогда нужна ещё дата из
  текста. Номер без суффикса (указы, «№ 77») связывается только вместе с
  датой;
- по названию в кавычках: «О лицензировании отдельных видов деятельности»;
- по названию кодекса: «Налогового кодекса», «НК РФ».

Справочник содержит акты до 2025 года включительно, поэтому показывает,
какой существующий акт упомянут (часто — тот, в который вносят
поправки), а не новый акт."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

from config import LAW_ALIASES_PATH
from pipeline.keywords_engine import phrase_in
from pipeline.morph import lemmas
from pipeline.normalize import normalize_text

_NUMBER_IN_ALIAS_RE = re.compile(r"№\s*(\d+(?:-[а-яa-z]+)?)", re.IGNORECASE)
_DATE_IN_ALIAS_RE = re.compile(r"от (\d{2})\.(\d{2})\.(\d{4})")
_QUOTED_RE = re.compile(r"[«\"„]([^«»\"„“]{4,}?)[»\"“]")
_NUMBER_IN_TEXT_RE = re.compile(
    r"№\s*(\d+(?:-(?:ФКЗ|ФЗ|рп))?)|(?<![\w-])(\d{1,4}-(?:ФКЗ|ФЗ|рп))(?!\w)", re.IGNORECASE
)


@dataclass(frozen=True)
class KnownAct:
    law_id: str
    name: str


@dataclass
class ActIndex:
    names: dict[str, str] = field(default_factory=dict)
    by_number: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    dates: dict[str, date] = field(default_factory=dict)
    by_quoted_title: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    code_phrases: list[tuple[str, str]] = field(default_factory=list)  # (law_id, фраза)
    code_abbreviations: list[tuple[str, str]] = field(default_factory=list)  # (law_id, «НК РФ»)


def build_index(aliases: dict[str, list[str]]) -> ActIndex:
    index = ActIndex()
    for law_id, variants in aliases.items():
        index.names[law_id] = variants[0]
        has_number = False
        for variant in variants:
            number = _NUMBER_IN_ALIAS_RE.search(variant)
            if number:
                has_number = True
                index.by_number[number.group(1).upper()].add(law_id)
            found_date = _DATE_IN_ALIAS_RE.search(variant)
            if found_date and law_id not in index.dates:
                d, m, y = found_date.groups()
                index.dates[law_id] = date(int(y), int(m), int(d))
            quoted = _QUOTED_RE.search(variant)
            if quoted:
                title = normalize_text(quoted.group(1)).strip()
                # Название из одного слова («Аренда») совпадёт с названием компании в кавычках.
                if len(title.split()) >= 2:
                    index.by_quoted_title[title].add(law_id)

        if has_number:
            continue
        for variant in variants:
            if "кодекс" in variant.lower():
                index.code_phrases.append((law_id, variant))
            elif " " in variant and not _QUOTED_RE.search(variant):
                index.code_abbreviations.append((law_id, variant))
    return index


@lru_cache(maxsize=1)
def get_index(path: Path = LAW_ALIASES_PATH) -> ActIndex:
    return build_index(json.loads(path.read_text(encoding="utf-8")))


def _by_number(text: str, act_date: date | None, index: ActIndex) -> set[str]:
    found = set()
    for m in _NUMBER_IN_TEXT_RE.finditer(text):
        number = (m.group(1) or m.group(2)).upper()
        candidates = index.by_number.get(number, set())
        has_suffix = "-" in number
        if len(candidates) == 1 and has_suffix:
            found |= candidates
        elif candidates and act_date is not None:
            found |= {c for c in candidates if index.dates.get(c) == act_date}
    return found


def _by_quoted_title(text: str, index: ActIndex) -> set[str]:
    found = set()
    for m in _QUOTED_RE.finditer(text):
        found |= index.by_quoted_title.get(normalize_text(m.group(1)).strip(), set())
    return found


def _by_code(text: str, index: ActIndex) -> set[str]:
    text_lemmas = lemmas(text)
    found = {law_id for law_id, phrase in index.code_phrases if phrase_in(text_lemmas, phrase)}
    for law_id, abbr in index.code_abbreviations:
        if re.search(r"(?<!\w)" + re.escape(abbr) + r"(?!\w)", text, flags=re.IGNORECASE):
            found.add(law_id)
    return found


def find_referenced_acts(text: str, act_date: date | None = None, index: ActIndex | None = None) -> list[KnownAct]:
    index = index or get_index()
    ids = _by_number(text, act_date, index) | _by_quoted_title(text, index) | _by_code(text, index)
    return [KnownAct(law_id=i, name=index.names[i]) for i in sorted(ids, key=int)]
