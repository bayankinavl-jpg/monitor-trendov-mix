from datetime import date

from pipeline.act_reference import build_index, find_referenced_acts

_ALIASES = {
    "1": ["Налоговый кодекс Российской Федерации", "Налоговый кодекс", "НК РФ", "НК"],
    "2": [
        "Федеральный закон №381-ФЗ от 28.12.2009 «Об основах государственного регулирования торговой деятельности в Российской Федерации»",
        "Федеральный закон №381-ФЗ",
    ],
    "3": ["Федеральный закон №99-ФЗ от 04.05.2011 «О лицензировании отдельных видов деятельности»"],
    "4": ["Федеральный закон №127-ФЗ от 26.10.2002 «О несостоятельности (банкротстве)»"],
    "5": ["Федеральный закон №127-ФЗ от 23.05.2016 «О внесении изменений в отдельные законодательные акты»"],
    "6": ["Указ Президента Российской Федерации №77 от 30.01.2020 «О денежном вознаграждении»"],
}
_INDEX = build_index(_ALIASES)


def _ids(text, act_date=None):
    return [a.law_id for a in find_referenced_acts(text, act_date, index=_INDEX)]


def test_unique_number_without_number_sign():
    assert _ids("Госдума приняла поправки в 381-ФЗ о торговле") == ["2"]


def test_number_with_number_sign():
    assert _ids("Изменения в закон № 99-ФЗ одобрены") == ["3"]


def test_quoted_title():
    assert _ids("Поправки в закон «О лицензировании отдельных видов деятельности» внесены") == ["3"]


def test_code_in_other_word_form():
    assert _ids("Минфин предложил изменить статью Налогового кодекса") == ["1"]


def test_code_abbreviation():
    assert _ids("Согласно ст. 374 НК РФ ставка меняется") == ["1"]


def test_bare_code_abbreviation_not_used():
    assert _ids("Жильцы ЖК и НК обсудили новости") == []


def test_ambiguous_number_needs_date():
    assert _ids("Изменения в 127-ФЗ") == []
    assert _ids("Изменения в 127-ФЗ", date(2016, 5, 23)) == ["5"]


def test_bare_decree_number_needs_date():
    assert _ids("Указ № 77 подписан") == []
    assert _ids("Указ № 77 подписан", date(2020, 1, 30)) == ["6"]


def test_single_word_quoted_title_not_used():
    index = build_index({"9": ['ФСБУ "АРЕНДА"']})
    assert find_referenced_acts("Компания «Аренда» сменила владельца", index=index) == []


def test_no_reference():
    assert _ids("Роспотребнадзор запретил ввоз вин") == []


def test_full_reference_file_loads():
    acts = find_referenced_acts("Поправки в Налоговый кодекс и 381-ФЗ")
    assert any("Налоговый кодекс" in a.name for a in acts)
    assert any("381-ФЗ" in a.name for a in acts)
