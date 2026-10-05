"""Unit tests for the GUI's default model contract.

`mvgeos-gui` used to re-derive the default model slug as a string literal in
four places (``main``, ``services.config_service``, and ``state`` twice). No
test tied those copies to the engine's ``DEFAULT_MODEL``, so moving the
constant in ``mvgeos_core.constants`` shipped a GUI on a different default
model with a fully green suite.

The invariant spans three source modules, so this is the "small cluster" unit
tier from the Testing Standards Charter rather than a single-module test. Each
assertion below is observable behaviour -- what the GUI hands a Mvge or its own
CLI when nobody chose a model -- not the import that produced it.
"""

from __future__ import annotations

from mvgeos_core.constants import DEFAULT_MODEL
from mvgeos_provider import list_models

from mvgeos_gui.main import parse_args
from mvgeos_gui.services.config_service import AppSettings
from mvgeos_gui.state import AppState, ServerState


def test_app_settings_default_model_is_the_engine_default() -> None:
    """Persisted GUI settings default to the engine's model, not a copy."""
    assert AppSettings().default_model == DEFAULT_MODEL


def test_server_state_default_model_is_the_engine_default() -> None:
    """A freshly built session starts on the engine's model."""
    assert ServerState().selected_model == DEFAULT_MODEL


def test_app_state_default_model_is_the_engine_default() -> None:
    """A newly attached client inherits the engine's model from its server."""
    assert AppState().selected_model == DEFAULT_MODEL


def test_cli_model_flag_defaults_to_the_engine_default() -> None:
    """`mvgeos-gui --model` pre-filled the engine's model before any flag."""
    assert parse_args([]).model == DEFAULT_MODEL


def test_default_model_is_a_free_catalog_entry() -> None:
    """The free-tier promise: the default must resolve, and resolve as free."""
    model = next((m for m in list_models() if m.id == DEFAULT_MODEL), None)
    assert model is not None, f"{DEFAULT_MODEL} is absent from the shipped catalog"
    assert model.is_free is True
