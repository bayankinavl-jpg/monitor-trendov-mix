from models import Act, Level, Status


def test_default_factories_not_shared_between_instances():
    a = Act(
        level=Level.FEDERAL_LAW, act_kind="закон", number=None, issuing_body="Госдума",
        adoption_date=None, publication_date=None, title="А", source_url=None,
        status=Status.DRAFT, amendment_type=None,
    )
    b = Act(
        level=Level.FEDERAL_LAW, act_kind="закон", number=None, issuing_body="Госдума",
        adoption_date=None, publication_date=None, title="Б", source_url=None,
        status=Status.DRAFT, amendment_type=None,
    )
    a.summary_bullets.append("пункт 1")
    assert b.summary_bullets == []
