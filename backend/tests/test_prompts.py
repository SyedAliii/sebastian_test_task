from app.domain.prompts import prompt_refusal


def test_sixteen_year_old_hyphen() -> None:
    assert prompt_refusal("a 16-year-old at the beach") == ["minor"]


def test_sixteen_year_old_spaces() -> None:
    assert prompt_refusal("16 year old") == ["minor"]


def test_sixteen_yo() -> None:
    assert prompt_refusal("16yo") == ["minor"]


def test_teen_is_case_insensitive() -> None:
    assert prompt_refusal("Teen") == ["minor"]


def test_incest_is_refused() -> None:
    assert prompt_refusal("incest") == ["incest"]


def test_human_trafficking_is_refused() -> None:
    assert prompt_refusal("human trafficking") == ["trafficking"]


def test_adults_on_a_beach_are_allowed() -> None:
    assert prompt_refusal("two adults on a beach at sunset") == []


def test_thirty_year_old_is_allowed() -> None:
    assert prompt_refusal("a 30 year old couple") == []
