from __future__ import annotations

from mvgeos_runes.sigils import SigilRegistry
from mvgeos_runes.types import SigilHook


def test_sigil_registry_register_and_get_handlers() -> None:
    registry = SigilRegistry()

    def sync_handler() -> None:
        pass

    async def async_handler() -> None:
        pass

    registry.register(SigilHook.BEFORE_INVOCATION, sync_handler)
    registry.register(SigilHook.BEFORE_INVOCATION, async_handler)

    handlers = registry.get_handlers(SigilHook.BEFORE_INVOCATION)
    assert len(handlers) == 2
    assert sync_handler in handlers
    assert async_handler in handlers


def test_sigil_registry_get_handlers_empty() -> None:
    registry = SigilRegistry()

    handlers = registry.get_handlers(SigilHook.BEFORE_INVOCATION)
    assert handlers == []


def test_sigil_registry_handlers_property() -> None:
    registry = SigilRegistry()

    def sync_handler() -> None:
        pass

    registry.register(SigilHook.BEFORE_INVOCATION, lambda: None)
    registry.register(SigilHook.AFTER_INVOCATION, lambda: None)

    handlers = registry.handlers
    assert isinstance(handlers, dict)
    assert SigilHook.BEFORE_INVOCATION in handlers
    assert SigilHook.AFTER_INVOCATION in handlers
    assert len(handlers[SigilHook.BEFORE_INVOCATION]) == 1
    assert len(handlers[SigilHook.AFTER_INVOCATION]) == 1
