from datetime import date

from openpyxl import load_workbook

from export.xlsx_export import COLUMNS, export_xlsx
from models import Act, Level, Stage, Status
from registry.db import upsert_act


def _confirmed_act() -> Act:
    return Act(
        level=Level.DEPT_ORDER, act_kind="приказ", number="1", issuing_body="Минпромторг России",
        adoption_date=date(2026, 1, 1), publication_date=date(2026, 1, 5),
        title="Акт подтверждённый", source_url="https://example.gov.ru/1",
        status=Status.ADOPTED, amendment_type=None,
        stages=[Stage(date_text="01.01.2026", what_changes="новый акт")],
        cross_cutting=True,
        source_name="test",
    )


def _unconfirmed_act() -> Act:
    return Act(
        level=Level.DEPT_ORDER, act_kind="приказ", number=None, issuing_body="не определено",
        adoption_date=None, publication_date=None,
        title="Акт неподтверждённый", source_url="https://news.example.ru/x",
        status=Status.UNCONFIRMED, amendment_type=None,
        unconfirmed_reason="не найден на первоисточнике",
        source_name="test",
    )


def test_xlsx_excludes_unconfirmed(conn, tmp_path):
    upsert_act(conn, _confirmed_act())
    upsert_act(conn, _unconfirmed_act())

    out_path = tmp_path / "out.xlsx"
    count = export_xlsx(conn, out_path)
    assert count == 1

    wb = load_workbook(out_path)
    ws = wb.active
    header = [c.value for c in ws[1]]
    assert header == COLUMNS

    titles_in_sheet = [row[1].value for row in ws.iter_rows(min_row=2)]
    assert "Акт подтверждённый" in titles_in_sheet
    assert "Акт неподтверждённый" not in titles_in_sheet


def test_xlsx_marks_cross_cutting(conn, tmp_path):
    upsert_act(conn, _confirmed_act())
    out_path = tmp_path / "out.xlsx"
    export_xlsx(conn, out_path)

    wb = load_workbook(out_path)
    ws = wb.active
    row = next(ws.iter_rows(min_row=2))
    assert row[4].value == "сквозное"
