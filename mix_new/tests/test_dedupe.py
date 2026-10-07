from datetime import date

from models import Act, Level, Status
from pipeline.dedupe import find_existing, is_deadline_extension
from registry.db import upsert_act
from sources.base import CandidateAct


def _act(**overrides) -> Act:
    base = dict(
        level=Level.DEPT_ORDER, act_kind="приказ", number="123", issuing_body="Минпромторг России",
        adoption_date=date(2026, 3, 1), publication_date=date(2026, 3, 5),
        title="Об утверждении перечня товаров", source_url="https://example.gov.ru/doc/123",
        status=Status.ADOPTED, amendment_type=None, source_name="test",
    )
    base.update(overrides)
    return Act(**base)


def _candidate(**overrides) -> CandidateAct:
    base = dict(
        raw_title="Об утверждении перечня товаров", raw_number="123", raw_act_kind="приказ",
        raw_issuing_body="Минпромторг России", raw_adoption_date="01.03.2026",
        raw_publication_date="05.03.2026", source_url="https://example.gov.ru/doc/123",
        raw_text_excerpt=None,
    )
    base.update(overrides)
    return CandidateAct(**base)


def test_find_existing_exact_match(conn):
    upsert_act(conn, _act())
    found = find_existing(conn, Level.DEPT_ORDER, "приказ", "Минпромторг России", "123", "Об утверждении перечня товаров")
    assert found is not None
    assert found.number == "123"


def test_find_existing_no_match(conn):
    found = find_existing(conn, Level.DEPT_ORDER, "приказ", "Минпромторг России", "999", "Другой акт")
    assert found is None


def test_find_existing_fuzzy_draft_to_numbered(conn):
    draft = _act(number=None, title="Проект приказа об утверждении перечня товаров лёгкой промышленности")
    upsert_act(conn, draft)
    found = find_existing(
        conn, Level.DEPT_ORDER, "приказ", "Минпромторг России", "456",
        "Проект приказа об утверждении перечня товаров лёгкой промышленности",
    )
    assert found is not None
    assert found.number is None  # нашли именно черновик


def test_is_deadline_extension_true():
    existing = _act()
    candidate = _candidate(
        raw_title="О продлении срока действия приказа №123",
        raw_text_excerpt="продлить срок действия до 2027 года",
    )
    assert is_deadline_extension(existing, candidate) is True


def test_is_deadline_extension_false_no_keyword():
    existing = _act()
    candidate = _candidate(raw_title="Об утверждении нового перечня товаров")
    assert is_deadline_extension(existing, candidate) is False


def test_is_deadline_extension_false_no_existing():
    candidate = _candidate(raw_title="О продлении срока действия приказа")
    assert is_deadline_extension(None, candidate) is False
