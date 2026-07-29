from mvgeos_spells.types import SpellResult, SpellStatus


def test_spell_result_defaults() -> None:
    result = SpellResult(spell_name="test_spell")
    assert result.status == SpellStatus.SUCCESS
    assert result.content == ""
    assert result.details == {}


def test_spell_result_with_content() -> None:
    result = SpellResult(
        spell_name="test_spell", content="hello world", status=SpellStatus.SUCCESS
    )
    assert result.content == "hello world"
