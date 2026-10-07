"""Доменная модель: карточка акта и связанные типы."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Level(str, Enum):
    EAEU = "ЕАЭС"
    FEDERAL_LAW = "федеральный закон"
    GOV_ACT = "акт Правительства"
    DEPT_ORDER = "ведомственный приказ"


class Status(str, Enum):
    DRAFT = "проект"
    SUBMITTED = "внесен"
    ADOPTED = "принят"
    IN_FORCE = "действует"
    AMENDED = "изменен"
    REPEALED = "утратил силу"
    UNCONFIRMED = "не подтверждено"


class AmendmentType(str, Enum):
    NEW_ACT = "новый акт"
    RATE_CHANGE = "изменение ставки"
    LIST_CHANGE = "изменение перечня"
    NEW_OBLIGATION = "новая обязанность"
    REPEAL = "отмена"


@dataclass
class Stage:
    """Один этап вступления в силу."""
    date_text: str  # "дд.мм.гггг" либо "год, дата уточняется"
    what_changes: str


@dataclass
class Act:
    level: Level
    act_kind: str
    number: str | None
    issuing_body: str

    adoption_date: date | None
    publication_date: date | None
    title: str
    source_url: str | None
    status: Status
    amendment_type: AmendmentType | None

    summary_bullets: list[str] = field(default_factory=list)
    okved_codes: list[str] = field(default_factory=list)
    cross_cutting: bool = False
    commodity_groups: list[str] = field(default_factory=list)
    page_count: int | None = None
    discovered_date: date = field(default_factory=date.today)
    stages: list[Stage] = field(default_factory=list)
    linkage_note: str | None = None
    unconfirmed_reason: str | None = None

    db_id: int | None = None
    source_name: str | None = None
    natural_key: str | None = None
