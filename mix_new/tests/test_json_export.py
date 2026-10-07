import json
from datetime import date

from export.json_export import export_json
from models import Act, Level, Status
from registry.db import upsert_act


def _act(status: Status, **overrides) -> Act:
    base = dict(
        level=Level.FEDERAL_LAW, act_kind="закон", number="1", issuing_body="Государственная Дума",
        adoption_date=date(2026, 1, 1), publication_date=date(2026, 1, 5),
        title="Акт", source_url="https://example.gov.ru/1", status=status, amendment_type=None,
        source_name="test",
    )
    base.update(overrides)
    return Act(**base)


def test_json_splits_confirmed_and_unconfirmed(conn, tmp_path):
    upsert_act(conn, _act(Status.ADOPTED, number="1", title="Подтверждённый"))
    upsert_act(conn, _act(Status.UNCONFIRMED, number=None, title="Неподтверждённый", unconfirmed_reason="нет ссылки"))

    out_path = tmp_path / "out.json"
    confirmed, unconfirmed = export_json(conn, out_path)
    assert confirmed == 1
    assert unconfirmed == 1

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(payload["confirmed_acts"]) == 1
    assert len(payload["unconfirmed_acts"]) == 1
    assert payload["confirmed_acts"][0]["title"] == "Подтверждённый"
    assert payload["unconfirmed_acts"][0]["unconfirmed_reason"] == "нет ссылки"


def test_json_dates_serialized_as_iso_strings(conn, tmp_path):
    upsert_act(conn, _act(Status.ADOPTED))
    out_path = tmp_path / "out.json"
    export_json(conn, out_path)

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["confirmed_acts"][0]["adoption_date"] == "2026-01-01"
