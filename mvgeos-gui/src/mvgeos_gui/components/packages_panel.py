"""Packages panel: installed packages and catalog."""

from __future__ import annotations

import logging
from typing import Any

from nicegui import ui

from mvgeos_gui.state import AppState

logger = logging.getLogger(__name__)

SORT_OPTIONS = [
    ("name_az", "Alphabetical (A-Z)"),
    ("name_za", "Alphabetical (Z-A)"),
    ("version_desc", "Version (Highest First)"),
    ("version_asc", "Version (Lowest First)"),
]

FILTER_HOOKS_OPTIONS = [
    ("before_invocation", "Before Invocation"),
    ("after_invocation", "After Invocation"),
    ("before_spell_cast", "Before Spell Cast"),
    ("after_spell_result", "After Spell Result"),
    ("before_provider_request", "Before Provider Request"),
    ("after_provider_response", "After Provider Response"),
    ("turn_start", "Turn Start"),
    ("turn_end", "Turn End"),
    ("session_start", "Session Start"),
    ("session_shutdown", "Session Shutdown"),
    ("context_transform", "Context Transform"),
    ("agent_start", "Agent Start"),
    ("agent_end", "Agent End"),
    ("input", "Input"),
    ("should_stop_after_turn", "Should Stop After Turn"),
    ("prepare_next_turn", "Prepare Next Turn"),
    ("resources_discover", "Resources Discover"),
]

RUNTIME_OPTIONS = [
    ("python", "Python"),
    ("node", "Node.js"),
    ("deno", "Deno"),
    ("bun", "Bun"),
]

EXECUTION_MODE_OPTIONS = [
    ("parallel", "Parallel"),
    ("serial", "Serial"),
]

SCOPE_OPTIONS = [
    ("project", "Project"),
    ("user", "User"),
    ("agent", "Agent"),
]


def render_packages_panel(state: AppState) -> None:
    """Render the packages and rune marketplace view."""
    marketplace_data: dict[str, Any] = {}
    installed_data: list[dict[str, Any]] = []
    search_state: dict[str, str] = {"query": ""}
    filter_state: dict[str, Any] = {
        "hooks": [],
        "runtime": "",
        "execution_mode": "",
        "scope": "",
        "installed_only": False,
        "marketplace_only": False,
    }
    sort_state: dict[str, str] = {"sort_by": "name_az"}

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

        # Filter and sort controls
        with ui.row().classes("w-full items-center gap-3 mt-2 flex-wrap"):
            # Hooks filter (multi-select)
            with ui.column().classes("gap-1"):
                ui.label("Hooks").classes(
                    "text-[10px] uppercase font-semibold text-[#6e6584]"
                )
                hooks_select = (
                    ui.select(
                        options=dict(FILTER_HOOKS_OPTIONS),
                        with_input=True,
                        multiple=True,
                        value=[],
                    )
                    .props("dense dark outlined rounded")
                    .classes("w-[200px] text-xs")
                    .mark("package_filter_hooks")
                )

            # Runtime filter
            with ui.column().classes("gap-1"):
                ui.label("Runtime").classes(
                    "text-[10px] uppercase font-semibold text-[#6e6584]"
                )
                runtime_select = (
                    ui.select(
                        options=dict(RUNTIME_OPTIONS),
                        with_input=True,
                        value=None,
                    )
                    .props("dense dark outlined rounded")
                    .classes("w-[140px] text-xs")
                    .mark("package_filter_runtime")
                )

            # Execution mode filter
            with ui.column().classes("gap-1"):
                ui.label("Exec Mode").classes(
                    "text-[10px] uppercase font-semibold text-[#6e6584]"
                )
                exec_mode_select = (
                    ui.select(
                        options=dict(EXECUTION_MODE_OPTIONS),
                        with_input=True,
                        value=None,
                    )
                    .props("dense dark outlined rounded")
                    .classes("w-[140px] text-xs")
                    .mark("package_filter_exec_mode")
                )

            # Scope filter
            with ui.column().classes("gap-1"):
                ui.label("Scope").classes(
                    "text-[10px] uppercase font-semibold text-[#6e6584]"
                )
                scope_select = (
                    ui.select(
                        options=dict(SCOPE_OPTIONS),
                        with_input=True,
                        value=None,
                    )
                    .props("dense dark outlined rounded")
                    .classes("w-[140px] text-xs")
                    .mark("package_filter_scope")
                )

            # Installed only checkbox
            installed_only_chk = (
                ui.checkbox("Installed only")
                .props("dense dark color=primary")
                .classes("text-xs self-end")
                .mark("package_filter_installed_only")
            )

            # Marketplace only checkbox
            marketplace_only_chk = (
                ui.checkbox("Marketplace only")
                .props("dense dark color=primary")
                .classes("text-xs self-end")
                .mark("package_filter_marketplace_only")
            )

            # Sort dropdown
            with ui.column().classes("gap-1"):
                ui.label("Sort").classes(
                    "text-[10px] uppercase font-semibold text-[#6e6584]"
                )
                sort_select = (
                    ui.select(
                        options=dict(SORT_OPTIONS),
                        with_input=True,
                        value="name_az",
                    )
                    .props("dense dark outlined rounded")
                    .classes("w-[200px] text-xs")
                    .mark("package_sort_select")
                )

        def _on_filter_change() -> None:
            filter_state["hooks"] = hooks_select.value or []
            filter_state["runtime"] = runtime_select.value or ""
            filter_state["execution_mode"] = exec_mode_select.value or ""
            filter_state["scope"] = scope_select.value or ""
            filter_state["installed_only"] = bool(installed_only_chk.value)
            filter_state["marketplace_only"] = bool(marketplace_only_chk.value)
            render_extensions.refresh()

        def _on_sort_change() -> None:
            sort_state["sort_by"] = sort_select.value or "name_az"
            render_extensions.refresh()

        hooks_select.on("update:model-value", _on_filter_change)
        runtime_select.on("update:model-value", _on_filter_change)
        exec_mode_select.on("update:model-value", _on_filter_change)
        scope_select.on("update:model-value", _on_filter_change)
        installed_only_chk.on("update:model-value", _on_filter_change)
        marketplace_only_chk.on("update:model-value", _on_filter_change)
        sort_select.on("update:model-value", _on_sort_change)

        @ui.refreshable
        def render_extensions() -> None:
            query = search_state["query"]
            hooks_filter = filter_state.get("hooks", [])
            runtime_filter = filter_state.get("runtime", "")
            exec_mode_filter = filter_state.get("execution_mode", "")
            scope_filter = filter_state.get("scope", "")
            installed_only = filter_state.get("installed_only", False)
            marketplace_only = filter_state.get("marketplace_only", False)
            sort_by = sort_state.get("sort_by", "name_az")

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

                # Search filter
                if query and query not in name.lower() and query not in desc.lower():
                    continue

                # Installed/Marketplace filter
                is_installed = state.is_rune_installed(name) or bool(inst_meta)
                if installed_only and not is_installed:
                    continue
                if marketplace_only and is_installed:
                    continue

                # Runtime filter
                r_runtime = ""
                if isinstance(mp_meta, dict) and mp_meta:
                    r_runtime = mp_meta.get("runtime", "python")
                if inst_meta:
                    r_runtime = str(inst_meta.get("runtime", r_runtime))
                if runtime_filter and r_runtime != runtime_filter:
                    continue

                # Execution mode filter
                r_exec_mode = ""
                if isinstance(mp_meta, dict) and mp_meta:
                    r_exec_mode = mp_meta.get("execution_mode", "parallel")
                if inst_meta:
                    r_exec_mode = str(inst_meta.get("execution_mode", r_exec_mode))
                if exec_mode_filter and r_exec_mode != exec_mode_filter:
                    continue

                # Scope filter
                r_scope = ""
                if isinstance(mp_meta, dict) and mp_meta:
                    r_scope = mp_meta.get("scope", "project")
                if inst_meta:
                    r_scope = str(inst_meta.get("scope", r_scope))
                if scope_filter and r_scope != scope_filter:
                    continue

                # Hooks filter (must have ALL selected hooks)
                r_hooks: list[str] = []
                if isinstance(mp_meta, dict) and mp_meta:
                    r_hooks = mp_meta.get("hooks", []) or []
                if inst_meta:
                    r_hooks = inst_meta.get("hooks", r_hooks) or []
                if hooks_filter and not all(h in r_hooks for h in hooks_filter):
                    continue

                filtered_names.append(name)

            # Apply sorting
            def _sort_key(n: str) -> tuple[str, tuple[int, ...]]:
                mp = marketplace_data.get(n, {})
                inst = installed_by_name.get(n, {})
                version_str = str(mp.get("version", inst.get("version", "0.0.0")))
                # Simple version tuple for sorting
                version_parts = [int(x) for x in version_str.split(".") if x.isdigit()]
                version_tuple = tuple(version_parts)
                if len(version_tuple) < 3:
                    version_tuple = version_tuple + (0,) * (3 - len(version_tuple))
                return (n.lower(), version_tuple)

            if sort_by == "name_az":
                filtered_names.sort(key=lambda n: n.lower())
            elif sort_by == "name_za":
                filtered_names.sort(key=lambda n: n.lower(), reverse=True)
            elif sort_by == "version_desc":
                filtered_names.sort(key=_sort_key, reverse=True)
            elif sort_by == "version_asc":
                filtered_names.sort(key=_sort_key)

            if not filtered_names:
                ui.label("No extensions found").classes("text-xs text-[#6e6584] mt-2")
                return

            with ui.column().classes("w-full gap-3 mt-2"):
                for name in filtered_names:
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
