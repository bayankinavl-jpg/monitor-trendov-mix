"""Загрузка sources.yml — список RSS-источников без правки кода."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from config import FORBIDDEN_DOMAINS, SOURCES_PATH


@dataclass
class NewsSource:
    name: str
    focus: str
    feed_url: str
    trust_tier: str  # official_publication | legal | general

    @property
    def domain(self) -> str:
        return urlsplit(self.feed_url).netloc.lower()


def load_sources(path: Path = SOURCES_PATH) -> list[NewsSource]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    sources = [NewsSource(**entry) for entry in raw.get("sources", [])]
    forbidden = [s for s in sources if s.domain in FORBIDDEN_DOMAINS]
    if forbidden:
        names = ", ".join(s.name for s in forbidden)
        raise ValueError(
            f"sources.yml содержит запрещённые домены ({names}) — см. config.FORBIDDEN_DOMAINS"
        )
    return sources
