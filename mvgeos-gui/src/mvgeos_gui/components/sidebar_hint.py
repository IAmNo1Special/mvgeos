"""Sidebar hint: tooltip that names a collapsed nav item."""

from nicegui import ui


def sidebar_hint(text: str) -> ui.tooltip:
    """Attach a right-side tooltip to the current nav link.

    Call inside a nav link's element scope. Returns the tooltip so the
    shell can toggle its visibility with the sidebar's collapsed state.
    """
    tip = (
        ui.tooltip(text)
        .classes("tooltip sidebar-hint")
        .props(
            'anchor="center right" self="center left" '
            ':offset="[16, 0]" '
            'transition-show="jump-right" transition-hide="jump-left"'
        )
    )
    return tip
