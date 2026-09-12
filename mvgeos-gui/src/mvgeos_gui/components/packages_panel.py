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
            .mark("package_dialog_source_input")
        )

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button("Cancel", on_click=install_dialog.close).props(
                "flat dense text-color=grey-4"
            ).mark("package_dialog_cancel_btn")

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
            ).classes("mvge-glow-btn text-white").mark("package_dialog_install_btn")

    with ui.column().classes("w-full h-full overflow-y-auto p-6 gap-4"):
        with ui.row().classes("w-full items-center justify-between"):
            with ui.column().classes("gap-1"):
                ui.label("Marketplace").classes("text-2xl font-semibold text-[#eceaf4]")
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
                render_extensions.refresh()

            ui.input(
                placeholder="Search packages & runes...",
                on_change=lambda e: _on_search(str(e.value or "")),
            ).props("dense dark outlined rounded").classes("flex-1 text-xs").mark(
                "package_search_input"
            )

            ui.button(
                "+ Install from URL/Git",
                on_click=install_dialog.open,
            ).props("unelevated dense").classes(
                "mvge-glow-btn text-white text-xs"
            ).mark("package_open_install_dialog_btn")

        @ui.refreshable
        def render_extensions() -> None:
            query = search_state["query"]
            # Build map of installed runes by name
            installed_by_name: dict[str, dict[str, Any]] = {
                str(r.get("name", "")): r for r in installed_data if "name" in r
            }

            # Merge all rune names from marketplace and installed
            all_names = set(marketplace_data.keys()) | set(installed_by_name.keys())

            filtered_names: list[str] = []
            for name in all_names:
                mp_meta = marketplace_data.get(name, {})
                inst_meta = installed_by_name.get(name, {})
                desc = (
                    mp_meta.get("description", "") if isinstance(mp_meta, dict) else ""
                ) or str(inst_meta.get("description", ""))

                if query in name.lower() or query in desc.lower():
                    filtered_names.append(name)

            if not filtered_names:
                ui.label("No extensions found").classes("text-xs text-[#6e6584] mt-2")
                return

            with ui.column().classes("w-full gap-3 mt-2"):
                for name in sorted(filtered_names):
                    mp_meta = marketplace_data.get(name, {})
                    inst_meta = installed_by_name.get(name, {})

                    # Determine installation status
                    is_installed = state.is_rune_installed(name) or bool(inst_meta)

                    # Gather metadata
                    version = "1.0.0"
                    runtime = "python"
                    desc = ""
                    git_url = ""
                    if isinstance(mp_meta, dict) and mp_meta:
                        version = mp_meta.get("version", version)
                        runtime = mp_meta.get("runtime", runtime)
                        desc = mp_meta.get("description", "")
                        git_url = mp_meta.get("git", "")

                    if inst_meta:
                        version = str(inst_meta.get("version", version))
                        runtime = str(inst_meta.get("runtime", runtime))
                        if not desc:
                            desc = str(inst_meta.get("description", ""))

                    path = str(inst_meta.get("path", ""))
                    hooks = inst_meta.get("hooks", [])
                    python_deps = inst_meta.get("python_deps", [])

                    with ui.card().classes(
                        "w-full p-4 bg-[#0e0e12] border border-[#292335] "
                        "rounded-xl gap-2"
                    ):
                        with ui.row().classes("w-full items-center justify-between"):
                            with ui.row().classes("items-center gap-2"):
                                if is_installed:
                                    ui.icon("check_circle", size="18px").classes(
                                        "text-green-400"
                                    )
                                else:
                                    ui.icon("extension", size="18px").classes(
                                        "text-[#7b6cf6]"
                                    )

                                ui.label(name).classes(
                                    "text-sm font-semibold text-[#eceaf4]"
                                )
                                ui.badge(f"v{version}", color="grey-9").props(
                                    "rounded dense"
                                ).classes("text-[10px] text-[#9c94b3] font-mono")
                                ui.badge(runtime, color="purple-9").props(
                                    "rounded dense"
                                ).classes("text-[10px]")

                            with ui.row().classes("items-center gap-2"):
                                if is_installed:

                                    async def _uninstall_item(
                                        r_name: str = name,
                                    ) -> None:
                                        ui.notify(
                                            f"Uninstalling {r_name}...",
                                            type="info",
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
                                        "Installed",
                                        on_click=_uninstall_item,
                                    ).props("unelevated dense size=sm").classes(
                                        "mvge-installed-btn text-xs font-medium"
                                    ).mark(f"package_install_item_{name}").mark(
                                        f"package_uninstall_item_{name}"
                                    )
                                else:

                                    async def _install_item(
                                        r: str = name,
                                    ) -> None:
                                        ui.notify(
                                            f"Installing {r}...",
                                            type="info",
                                        )
                                        success = await state.install_rune_async(r)
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
                                        "mvge-glow-btn text-white text-xs font-medium"
                                    ).mark(f"package_install_item_{name}")

                        if desc:
                            ui.label(desc).classes("text-xs text-[#9c94b3]")

                        if git_url:
                            with ui.row().classes("items-center gap-1"):
                                ui.icon("code", size="12px").classes("text-[#6e6584]")
                                ui.link(
                                    git_url,
                                    git_url,
                                    new_tab=True,
                                ).classes("text-[11px] text-[#7b6cf6] underline")

                        # Installed extension details
                        if is_installed:
                            with ui.column().classes(
                                "w-full gap-1 pt-1 mt-1 border-t border-[#292335]/50"
                            ):
                                if path:
                                    with ui.row().classes(
                                        "items-center gap-1.5 no-wrap"
                                    ):
                                        ui.icon("folder_open", size="12px").classes(
                                            "text-[#6e6584]"
                                        )
                                        ui.label(path).classes(
                                            "text-[11px] text-[#6e6584] "
                                            "font-mono truncate"
                                        )

                                if hooks:
                                    with ui.row().classes(
                                        "items-center gap-1 flex-wrap"
                                    ):
                                        ui.label("Hooks:").classes(
                                            "text-[10px] uppercase "
                                            "font-semibold text-[#6e6584]"
                                        )
                                        for h in hooks:
                                            h_name = (
                                                h
                                                if isinstance(h, str)
                                                else getattr(h, "value", str(h))
                                            )
                                            ui.badge(h_name, color="dark").props(
                                                "rounded dense"
                                            ).classes(
                                                "text-[9px] text-[#9c94b3] "
                                                "font-mono border border-[#292335]"
                                            )

                                if python_deps:
                                    with ui.row().classes(
                                        "items-center gap-1 flex-wrap"
                                    ):
                                        ui.label("Deps:").classes(
                                            "text-[10px] uppercase "
                                            "font-semibold text-[#6e6584]"
                                        )
                                        for dep in python_deps:
                                            ui.badge(str(dep), color="dark").props(
                                                "rounded dense"
                                            ).classes(
                                                "text-[9px] text-[#9c94b3] "
                                                "font-mono border border-[#292335]"
                                            )

        render_extensions()

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

        render_extensions.refresh()

    ui.timer(0.01, _refresh_data, once=True)
