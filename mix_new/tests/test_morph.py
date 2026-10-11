from pipeline.morph import lemma, lemmas


def test_word_forms_reduce_to_one_lemma():
    assert lemma("ставки") == lemma("ставку") == "ставка"


def test_name_is_not_reduced_to_common_noun():
    assert lemma("Рыбаря") != "рыба"


def test_yo_replaced():
    assert "е" in lemma("Ёлки") and "ё" not in lemma("Ёлки")


def test_lemmas_split_text_and_keep_hyphenated_words():
    assert lemmas("Шоу-бизнес и ставки") == ["шоу-бизнес", "и", "ставка"]
