"""Доменная модель: карточка акта и связанные типы."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class Level(str, Enum):
    EAEU = "ЕАЭС"
    FEDERAL_LAW = "федеральный закон"
    UKAZ = "указ"
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


class Credibility(str, Enum):
    HIGH = "высокий"
    MEDIUM = "средний"
    LOW = "низкий"


class RecordStatus(str, Enum):
    NEW = "новая"
    UPDATED = "обновлена"
    REPEAT = "повтор"


class ManualCheckStatus(str, Enum):
    NOT_CHECKED = "не проверено"
    CONFIRMED = "подтверждено"
    REJECTED = "не подтверждено"


@dataclass
class NewsItem:
    """Запись реестра новостей — сигнал, не подтверждённое изменение.
    Подтверждение (manual_check_status/act_text_url) остаётся за человеком."""

    title: str
    links: list[str]
    published_at: datetime
    sources: list[str]
    matched_keywords: list[tuple[str, str]] = field(default_factory=list)

    amendment_type: AmendmentType | None = None
    level: Level | None = None
    stage: str | None = None
    topic: str | None = None
    industry: str | None = None
    okved_codes: list[str] = field(default_factory=list)

    act_number: str | None = None
    act_date: date | None = None

    credibility: Credibility = Credibility.LOW
    record_status: RecordStatus = RecordStatus.NEW
    manual_check_status: ManualCheckStatus = ManualCheckStatus.NOT_CHECKED
    act_text_url: str | None = None

    first_seen_date: date = field(default_factory=date.today)
    related_act_id: int | None = None

    db_id: int | None = None
    natural_key: str | None = None
