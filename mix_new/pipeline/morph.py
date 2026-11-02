"""Нормальные формы слов (леммы) через pymorphy3. Подход взят из
LawRegexParser (parser.py: normalize_words), без фильтра по частям речи."""
from __future__ import annotations

import re
from functools import lru_cache

import pymorphy3

_WORD_RE = re.compile(r"[а-яёa-z0-9]+(?:-[а-яёa-z0-9]+)*", re.IGNORECASE)


@lru_cache(maxsize=1)
def _analyzer() -> pymorphy3.MorphAnalyzer:
    return pymorphy3.MorphAnalyzer()


@lru_cache(maxsize=100_000)
def lemma(word: str) -> str:
    word = word.lower().replace("ё", "е")
    parsed = _analyzer().parse(word)
    return parsed[0].normal_form.replace("ё", "е") if parsed else word


def lemmas(text: str) -> list[str]:
    return [lemma(w) for w in _WORD_RE.findall(text or "")]


@lru_cache(maxsize=100_000)
def lemma_pos(word: str) -> tuple[str, str]:
    """Нормальная форма и грубая часть речи: N — существительное или
    аббревиатура, A — прилагательное или причастие, L — латиница,
    пустая строка — остальное (предлоги, глаголы, числа...)."""
    word = word.lower().replace("ё", "е")
    parsed = _analyzer().parse(word)
    if not parsed:
        return word, ""
    p = parsed[0]
    tag = p.tag
    # Имена, фамилии и географические названия для бизнес-трендов не
    # значимы: «Путин», «Иран» всплывали бы в сигналах из-за повестки дня.
    if {"Name", "Surn", "Patr", "Geox"} & set(str(tag).replace(" ", ",").split(",")):
        return p.normal_form.replace("ё", "е"), ""
    if "LATN" in tag:
        pos = "L"
    elif tag.POS == "NOUN" or "Abbr" in tag:
        pos = "N"
    elif tag.POS in ("ADJF", "PRTF"):
        pos = "A"
    else:
        pos = ""
    return p.normal_form.replace("ё", "е"), pos


def words(text: str) -> list[str]:
    return _WORD_RE.findall(text or "")
