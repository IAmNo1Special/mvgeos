"""Packages panel: installed packages and catalog."""

from __future__ import annotations

import logging
from typing import Any

from nicegui import ui

from mvgeos_gui.state import AppState

logger = logging.getLogger(__name__)


def render_packages_panel(state: AppState) -> None:
    """Render the packages and rune marketplace view."""
    marketplace_data: dict[str, Any] = {}
    installed_data: list[dict[str, Any]] = []
    search_state: dict[str, str] = {"query": ""}

    with (
        ui.dialog() as install_dialog,
        ui.card().classes(
            "w-[480px] p-6 bg-[#0e0e12] border border-[#292335] rounded-xl gap-4"
        ),
    ):
        ui.label("Install Extension Rune").classes(
            "text-lg font-semibold text-[#eceaf4]"
        )
        ui.label(
            "Enter a marketplace rune name, Git repository URL, or local path."
        ).classes("text-xs text-[#9c94b3]")
        source_input = (
            ui.input(placeholder="git URL, local path, or marketplace rune name")
            .props("dense dark outlined rounded")
            .classes("w-full text-xs")
        )

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button("Cancel", on_click=install_dialog.close).props(
                "flat dense text-color=grey-4"
            )

            async def _do_install() -> None:
                source = (source_input.value or "").strip()
                if not source:
                    ui.notify("Please enter a rune source", type="warning")
                    return
                ui.notify(f"Installing {source}...", type="info")
                success = await state.install_rune_async(source)
                if success:
                    ui.notify(f"Successfully installed {source}!", type="positive")
                    source_input.value = ""
                    install_dialog.close()
                    await _refresh_data()
                else:
                    ui.notify(f"Failed to install {source}", type="negative")

            ui.button("Install", on_click=_do_install).props(
                "unelevated dense"
            ).classes("mvge-glow-btn text-white")

    with ui.column().classes("w-full h-full overflow-y-auto p-6 gap-4"):
        with ui.row().classes("w-full items-center justify-between"):
            with ui.column().classes("gap-1"):
                ui.label("Packages").classes("text-2xl font-semibold text-[#eceaf4]")
                ui.label(
                    "Explore and manage MvgeOS extensions from the official "
                    "marketplace."
                ).classes("text-xs text-[#9c94b3]")

            ui.button(
                "Back to Chat",
                on_click=lambda: state.set_current_view("chat"),
            ).props("unelevated").classes("mvge-glow-btn text-white")

        with ui.row().classes("w-full items-center justify-between gap-4 mt-2"):

            def _on_search(val: str) -> None:
                search_state["query"] = val.strip().lower()
                render_marketplace.refresh()
                render_installed.refresh()

            ui.input(
                placeholder="Search packages & runes...",
                on_change=lambda e: _on_search(str(e.value or "")),
            ).props("dense dark outlined rounded").classes("flex-1 text-xs").mark(
                "package_search_input"
            )

            ui.button(
                "+ Install from URL/Git",
                on_click=install_dialog.open,
            ).props("unelevated dense").classes("mvge-glow-btn text-white text-xs")

        with ui.tabs().classes("w-full border-b border-[#241f38]") as tabs:
            tab_marketplace = ui.tab("Marketplace").classes("text-xs")
            tab_installed = ui.tab("Installed").classes("text-xs")

        with ui.tab_panels(tabs, value=tab_marketplace).classes(
            "w-full bg-transparent p-0"
        ):
            with ui.tab_panel(tab_marketplace).classes("p-0 pt-4 gap-3"):

                @ui.refreshable
                def render_marketplace() -> None:
                    query = search_state["query"]
                    filtered = {}
                    for name, meta in marketplace_data.items():
                        desc = (
                            meta.get("description", "")
                            if isinstance(meta, dict)
                            else ""
                        )
                        if query in name.lower() or query in desc.lower():
                            filtered[name] = meta

                    if not filtered:
                        ui.label("No marketplace runes found").classes(
                            "text-xs text-[#6e6584]"
                        )
                        return

                    with ui.column().classes("w-full gap-3"):
                        for name, meta in sorted(filtered.items()):
                            if not isinstance(meta, dict):
                                continue
                            version = meta.get("version", "1.0.0")
                            runtime = meta.get("runtime", "python")
                            desc = meta.get("description", "")
                            git_url = meta.get("git", "")

                            with ui.card().classes(
                                "w-full p-4 bg-[#0e0e12] border border-[#292335] "
                                "rounded-xl gap-2"
                            ):
                                with ui.row().classes(
                                    "w-full items-center justify-between"
                                ):
                                    with ui.row().classes("items-center gap-2"):
                                        ui.icon("extension", size="18px").classes(
                                            "text-[#7b6cf6]"
                                        )
                                        ui.label(name).classes(
                                            "text-sm font-semibold text-[#eceaf4]"
                                        )
                                        ui.badge(f"v{version}", color="grey-9").props(
                                            "rounded dense"
                                        ).classes(
                                            "text-[10px] text-[#9c94b3] font-mono"
                                        )
                                        ui.badge(runtime, color="purple-9").props(
                                            "rounded dense"
                                        ).classes("text-[10px]")

                                    with ui.row().classes("items-center gap-2"):
                                        if state.is_rune_installed(name):
                                            ui.badge(
                                                "Installed", color="positive"
                                            ).props("rounded dense").classes("text-xs")
                                        else:

                                            async def _install_item(
                                                r: str = name,
                                            ) -> None:
                                                ui.notify(
                                                    f"Installing {r}...",
                                                    type="info",
                                                )
                                                success = (
                                                    await state.install_rune_async(r)
                                                )
                                                if success:
                                                    ui.notify(
                                                        f"Successfully installed {r}!",
                                                        type="positive",
                                                    )
                                                    await _refresh_data()
                                                else:
                                                    ui.notify(
                                                        f"Failed to install {r}",
                                                        type="negative",
                                                    )

                                            ui.button(
                                                "Install",
                                                on_click=_install_item,
                                            ).props("unelevated dense size=sm").classes(
                                                "mvge-glow-btn text-white"
                                            )

                                if desc:
                                    ui.label(desc).classes("text-xs text-[#9c94b3]")

                                if git_url:
                                    with ui.row().classes("items-center gap-1"):
                                        ui.icon("code", size="12px").classes(
                                            "text-[#6e6584]"
                                        )
                                        ui.link(
                                            git_url,
                                            git_url,
                                            new_tab=True,
                                        ).classes(
                                            "text-[11px] text-[#7b6cf6] underline"
                                        )

                render_marketplace()

            with ui.tab_panel(tab_installed).classes("p-0 pt-4 gap-3"):

                @ui.refreshable
                def render_installed() -> None:
                    ui.label("Installed").classes(
                        "text-sm font-semibold text-[#eceaf4] mb-3"
                    )
                    query = search_state["query"]
                    filtered_installed = [
                        r
                        for r in installed_data
                        if query in str(r.get("name", "")).lower()
                        or query in str(r.get("description", "")).lower()
                    ]

                    if not filtered_installed:
                        ui.label("No packages installed").classes(
                            "text-xs text-[#6e6584]"
                        )
                        return

                    with ui.column().classes("w-full gap-3"):
                        for r in filtered_installed:
                            name = str(r.get("name", ""))
                            version = str(r.get("version", "unknown"))
                            path = str(r.get("path", ""))
                            desc = str(r.get("description", ""))

                            with ui.card().classes(
                                "w-full p-4 bg-[#0e0e12] border border-[#292335] "
                                "rounded-xl gap-2"
                            ):
                                with ui.row().classes(
                                    "w-full items-center justify-between"
                                ):
                                    with ui.row().classes("items-center gap-2"):
                                        ui.icon("check_circle", size="18px").classes(
                                            "text-green-400"
                                        )
                                        ui.label(name).classes(
                                            "text-sm font-semibold text-[#eceaf4]"
                                        )
                                        ui.badge(f"v{version}", color="grey-9").props(
                                            "rounded dense"
                                        ).classes(
                                            "text-[10px] text-[#9c94b3] font-mono"
                                        )

                                    async def _uninstall_item(
                                        r_name: str = name,
                                    ) -> None:
                                        ui.notify(
                                            f"Uninstalling {r_name}...", type="info"
                                        )
                                        success = await state.uninstall_rune_async(
                                            r_name
                                        )
                                        if success:
                                            ui.notify(
                                                f"Successfully uninstalled {r_name}!",
                                                type="positive",
                                            )
                                            await _refresh_data()
                                        else:
                                            ui.notify(
                                                f"Failed to uninstall {r_name}",
                                                type="negative",
                                            )

                                    ui.button(
                                        "Uninstall",
                                        on_click=_uninstall_item,
                                    ).props("flat dense size=sm text-color=red-4")

                                if path:
                                    ui.label(path).classes(
                                        "text-[11px] text-[#6e6584] font-mono"
                                    )
                                if desc:
                                    ui.label(desc).classes("text-xs text-[#9c94b3]")

                render_installed()

    async def _refresh_data() -> None:
        try:
            mp = await state.fetch_marketplace_runes_async()
            marketplace_data.clear()
            marketplace_data.update(mp)
        except Exception as exc:
            logger.warning("Failed to fetch marketplace runes: %s", exc)

        try:
            inst = await state.list_installed_runes_async()
            installed_data.clear()
            installed_data.extend(inst)
        except Exception as exc:
            logger.warning("Failed to list installed runes: %s", exc)

        render_marketplace.refresh()
        render_installed.refresh()

    ui.timer(0.01, _refresh_data, once=True)
