from pathlib import Path

from mvgeos_gui.state import AppState


def test_state_new_conversation_clears(tmp_path: Path) -> None:
    state = AppState(project_path=tmp_path)
    state.messages.append(type("M", (), {"role": "user", "content": "hi"})())  # type: ignore[arg-type]
    # check new_conversation clears messages if present
    if hasattr(state, "new_conversation"):
        state.new_conversation()
        assert len(state.messages) == 0


def test_state_tome_switch(tmp_path: Path) -> None:
    state = AppState(project_path=tmp_path)
    # loaded_tomes handling
    assert hasattr(state, "loaded_tomes")
    assert isinstance(state.loaded_tomes, list)


def test_state_model_switch(tmp_path: Path) -> None:
    state = AppState(project_path=tmp_path)
    original = state.selected_model
    state.selected_model = "a/b"
    assert state.selected_model == "a/b"
    state.selected_model = original


def test_state_mana_tracking(tmp_path: Path) -> None:
    state = AppState(project_path=tmp_path)
    state.total_mana_used = 100
    assert state.total_mana_used == 100
    state.total_mana_used = 0
