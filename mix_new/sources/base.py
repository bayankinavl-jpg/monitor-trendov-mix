"""Общий интерфейс источников: прямые (pravo.gov.ru, regulation.gov.ru) и
источники-заглушки под будущее расширение."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


@dataclass
class CandidateAct:
    """Необработанные данные, снятые с одного источника. Строки, не enum'ы."""

    raw_title: str
    raw_number: str | None
    raw_act_kind: str | None
    raw_issuing_body: str | None
    raw_adoption_date: str | None
    raw_publication_date: str | None
    source_url: str  # обязательна прямая ссылка на текст акта
    page_count: int | None = None
    raw_text_excerpt: str | None = None
    extra: dict | None = None


class SourceUnreachableError(Exception):
    """Источник недоступен (сеть/DNS/таймаут/запрет robots.txt)."""


class SourceClient(ABC):
    name: str

    @abstractmethod
    def fetch_candidates(self, since: date, until: date) -> list[CandidateAct]:
        """Вернуть кандидатов, опубликованных/принятых в [since, until].

        Должен поднимать SourceUnreachableError при сетевой ошибке — runner
        фиксирует это в журнале как unreachable и НЕ подменяет источник
        новостями."""
        raise NotImplementedError
