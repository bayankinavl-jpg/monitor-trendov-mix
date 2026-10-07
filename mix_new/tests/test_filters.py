from datetime import date

from pipeline.filters import in_discovery_window, is_discardable, is_in_scope_issuer
from sources.base import CandidateAct


def _candidate(**overrides) -> CandidateAct:
    base = dict(
        raw_title="Приказ об утверждении перечня",
        raw_number="123",
        raw_act_kind="приказ",
        raw_issuing_body="Минпромторг России",
        raw_adoption_date="01.03.2026",
        raw_publication_date="05.03.2026",
        source_url="https://publication.pravo.gov.ru/document/123",
    )
    base.update(overrides)
    return CandidateAct(**base)


def test_in_scope_issuer_matches_whitelist():
    assert is_in_scope_issuer(_candidate()) is True


def test_in_scope_issuer_rejects_unknown_body():
    assert is_in_scope_issuer(_candidate(raw_issuing_body="Правительство Московской области")) is False


def test_in_scope_issuer_rejects_empty():
    assert is_in_scope_issuer(_candidate(raw_issuing_body=None)) is False


def test_discardable_personnel_decision():
    discard, reason = is_discardable(_candidate(raw_title="О назначении на должность заместителя министра"))
    assert discard is True
    assert "назначении" in reason


def test_discardable_technical_correction():
    discard, _ = is_discardable(_candidate(raw_title="О внесении технической правки в приказ №5"))
    assert discard is True


def test_not_discardable_normal_act():
    discard, reason = is_discardable(_candidate())
    assert discard is False
    assert reason is None


def test_discovery_window_inside():
    c = _candidate(raw_publication_date="15.06.2026")
    assert in_discovery_window(c, date(2026, 1, 1), date(2026, 12, 31)) is True


def test_discovery_window_outside():
    c = _candidate(raw_publication_date="15.06.2020")
    assert in_discovery_window(c, date(2026, 1, 1), date(2026, 12, 31)) is False


def test_discovery_window_missing_date_not_discarded():
    c = _candidate(raw_publication_date=None, raw_adoption_date=None)
    assert in_discovery_window(c, date(2026, 1, 1), date(2026, 12, 31)) is True
