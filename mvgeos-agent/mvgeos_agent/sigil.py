from __future__ import annotations

from typing import Any, Protocol


class Sigil(Protocol):
    def before_spell_cast(
        self, spell_name: str, params: dict[str, Any]
    ) -> dict[str, Any] | None: ...

    def after_spell_result(
        self, spell_name: str, result: dict[str, Any]
    ) -> dict[str, Any] | None: ...

    def before_mvge_response(self, invocation: Any) -> dict[str, Any] | None: ...

    def after_mvge_response(self, invocation: Any) -> dict[str, Any] | None: ...
