"""Packages panel: installed packages and catalog."""

from __future__ import annotations

import logging
import os
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from nicegui import ui

from mvgeos_gui.state import AppState

logger = logging.getLogger(__name__)


def open_folder_in_explorer(target_path: str | Path) -> bool:
    """Open a directory or file's parent in the OS default file explorer."""
    try:
        p = Path(target_path).expanduser().resolve()
        if not p.exists():
            return False
        folder = p if p.is_dir() else p.parent
        target = str(folder)
        system = platform.system()
        if system == "Windows" and hasattr(os, "startfile"):
            os.startfile(target)
        elif system == "Darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
        return True
    except Exception as exc:
        logger.warning("Failed to open file explorer for '%s': %s", target_path, exc)
        return False


def _parse_timestamp(val: Any) -> float:
    """Parse ISO date string, numeric timestamp, or return 0.0."""
    if not val:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    try:
        dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return 0.0


def _extract_rune_info(
    name: str,
    mp_meta: dict[str, Any],
    inst_meta: dict[str, Any],
    is_installed: bool,
) -> dict[str, Any]:
    """Extract unified metadata and timestamps for a rune."""
    version = "1.0.0"
    runtime = "python"
    desc = ""
    git_url = ""

    if isinstance(mp_meta, dict) and mp_meta:
        version = str(mp_meta.get("version", version))
        runtime = str(mp_meta.get("runtime", runtime))
        desc = str(mp_meta.get("description", ""))
        git_url = str(mp_meta.get("git", ""))

    if isinstance(inst_meta, dict) and inst_meta:
        version = str(inst_meta.get("version", version))
        runtime = str(inst_meta.get("runtime", runtime))
        if not desc:
            desc = str(inst_meta.get("description", ""))

    path = str(inst_meta.get("path", "")) if isinstance(inst_meta, dict) else ""
    hooks = [
        h if isinstance(h, str) else getattr(h, "value", str(h))
        for h in (inst_meta.get("hooks") or mp_meta.get("hooks", []))
    ]
    python_deps = [
        str(d) for d in (inst_meta.get("python_deps") or mp_meta.get("python_deps", []))
    ]

    types: list[str] = []
    raw_types = inst_meta.get("types") or (
        mp_meta.get("types") if isinstance(mp_meta, dict) else None
    )
    if isinstance(raw_types, list):
        types = [str(t) for t in raw_types if t]
    elif isinstance(raw_types, str) and raw_types:
        types = [raw_types]

    raw_type = inst_meta.get("type") or (
        mp_meta.get("type") if isinstance(mp_meta, dict) else None
    )
    if raw_type and isinstance(raw_type, str) and raw_type not in types:
        types.insert(0, raw_type)

    if not types:
        if "realm" in name.lower() or "provider" in name.lower():
            types = ["RealmProvider"]
        elif "seeker" in name.lower():
            types = ["Spell", "Spell Modifier"]
        elif "goap" in name.lower() or "planner" in name.lower():
            types = ["Planner", "Spell Modifier"]
        else:
            types = ["Rune"]

    created_at = inst_meta.get("created_at") or mp_meta.get("created_at")
    created_ts = _parse_timestamp(created_at)
    if created_ts == 0.0 and path:
        try:
            p = Path(path)
            if p.exists():
                created_ts = p.stat().st_ctime
        except Exception:
            pass

    updated_at = (
        inst_meta.get("updated_at")
        or mp_meta.get("updated_at")
        or inst_meta.get("last_updated")
        or mp_meta.get("last_updated")
        or created_at
    )
    updated_ts = _parse_timestamp(updated_at)
    if updated_ts == 0.0 and path:
        try:
            p = Path(path)
            if p.exists():
                updated_ts = p.stat().st_mtime
        except Exception:
            pass
    if updated_ts == 0.0:
        updated_ts = created_ts

    return {
        "name": name,
        "version": version,
        "runtime": runtime,
        "description": desc,
        "git_url": git_url,
        "path": path,
        "is_installed": is_installed,
        "hooks": hooks,
        "python_deps": python_deps,
        "types": types,
        "created_at": created_ts,
        "updated_at": updated_ts,
    }


def render_packages_panel(state: AppState) -> None:
    """Render the packages and rune marketplace view."""
    marketplace_data: dict[str, Any] = {}
    installed_data: list[dict[str, Any]] = []
    search_state: dict[str, str] = {
        "query": "",
        "type": "All Types",
        "hook": "All Hooks",
        "dep": "All Deps",
        "sort": "Alphabetical (A-Z)",
    }

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
        with ui.column().classes("gap-1"):
            ui.label("Marketplace").classes("text-2xl font-semibold text-[#eceaf4]")
            ui.label(
                "Explore and manage MvgeOS extensions from the official marketplace."
            ).classes("text-xs text-[#9c94b3]")

        with ui.row().classes("w-full items-center justify-between gap-4 mt-2"):

            def _on_search(val: str) -> None:
                search_state["query"] = val.strip().lower()
                render_extensions.refresh()

            search_input = (
                ui.input(
                    placeholder="Search packages, types, hooks, or deps...",
                    on_change=lambda e: _on_search(str(e.value or "")),
                )
                .props("dense dark outlined rounded")
                .classes("flex-1 text-xs")
                .mark("package_search_input")
            )

            ui.button(
                "+ Install from URL/Git",
                on_click=install_dialog.open,
            ).props("unelevated dense").classes(
                "mvge-glow-btn text-white text-xs"
            ).mark("package_open_install_dialog_btn")

        def _set_filter(key: str, val: str) -> None:
            search_state[key] = val
            render_extensions.refresh()

        def _clear_filters() -> None:
            search_input.value = ""
            search_state["query"] = ""
            search_state["type"] = "All Types"
            search_state["hook"] = "All Hooks"
            search_state["dep"] = "All Deps"
            search_state["sort"] = "Alphabetical (A-Z)"
            type_select.value = "All Types"
            hook_select.value = "All Hooks"
            dep_select.value = "All Deps"
            sort_select.value = "Alphabetical (A-Z)"
            render_extensions.refresh()

        with ui.row().classes("w-full items-center gap-2 flex-wrap"):
            ui.icon("filter_list", size="16px").classes("text-[#6e6584]")
            type_select = (
                ui.select(
                    options=["All Types"],
                    value=search_state["type"],
                    on_change=lambda e: _set_filter(
                        "type", str(e.value or "All Types")
                    ),
                )
                .props("dense dark outlined rounded options-dense")
                .classes("min-w-[130px] text-xs")
                .mark("package_filter_type_select")
            )

            hook_select = (
                ui.select(
                    options=["All Hooks"],
                    value=search_state["hook"],
                    on_change=lambda e: _set_filter(
                        "hook", str(e.value or "All Hooks")
                    ),
                )
                .props("dense dark outlined rounded options-dense")
                .classes("min-w-[140px] text-xs")
                .mark("package_filter_hook_select")
            )

            dep_select = (
                ui.select(
                    options=["All Deps"],
                    value=search_state["dep"],
                    on_change=lambda e: _set_filter("dep", str(e.value or "All Deps")),
                )
                .props("dense dark outlined rounded options-dense")
                .classes("min-w-[130px] text-xs")
                .mark("package_filter_dep_select")
            )

            with ui.row().classes("items-center gap-1.5 ml-auto"):
                ui.icon("sort", size="16px").classes("text-[#6e6584]")
                sort_select = (
                    ui.select(
                        options=[
                            "Alphabetical (A-Z)",
                            "Alphabetical (Z-A)",
                            "Date Added",
                            "Last Updated",
                        ],
                        value=search_state["sort"],
                        on_change=lambda e: _set_filter(
                            "sort", str(e.value or "Alphabetical (A-Z)")
                        ),
                    )
                    .props("dense dark outlined rounded options-dense")
                    .classes("min-w-[160px] text-xs")
                    .mark("package_sort_select")
                )

                ui.button(
                    "Clear",
                    icon="clear",
                    on_click=_clear_filters,
                ).props("flat dense size=sm text-color=grey-5").classes("text-xs").mark(
                    "package_clear_filters_btn"
                )

        @ui.refreshable
        def render_extensions() -> None:
            query = search_state["query"]
            selected_type = search_state["type"]
            selected_hook = search_state["hook"]
            selected_dep = search_state["dep"]
            sort_by = search_state["sort"]

            # Build map of installed runes by name
            installed_by_name: dict[str, dict[str, Any]] = {
                str(r.get("name", "")): r for r in installed_data if "name" in r
            }

            # Merge all rune names from marketplace and installed
            all_names = set(marketplace_data.keys()) | set(installed_by_name.keys())

            all_infos: list[dict[str, Any]] = []
            for name in all_names:
                mp_meta = marketplace_data.get(name, {})
                inst_meta = installed_by_name.get(name, {})
                is_installed = state.is_rune_installed(name) or bool(inst_meta)
                all_infos.append(
                    _extract_rune_info(name, mp_meta, inst_meta, is_installed)
                )

            filtered_runes: list[dict[str, Any]] = []
            for r in all_infos:
                if query:
                    q = query.lower()
                    name_match = q in r["name"].lower()
                    desc_match = q in r["description"].lower()
                    type_match = any(q in t.lower() for t in r["types"])
                    hook_match = any(q in h.lower() for h in r["hooks"])
                    dep_match = any(q in d.lower() for d in r["python_deps"])
                    if not (
                        name_match
                        or desc_match
                        or type_match
                        or hook_match
                        or dep_match
                    ):
                        continue

                if selected_type != "All Types" and not any(
                    t.lower() == selected_type.lower() for t in r["types"]
                ):
                    continue

                if selected_hook != "All Hooks" and not any(
                    h.lower() == selected_hook.lower() for h in r["hooks"]
                ):
                    continue

                if selected_dep != "All Deps" and not any(
                    selected_dep.lower() in d.lower()
                    or d.lower() in selected_dep.lower()
                    for d in r["python_deps"]
                ):
                    continue

                filtered_runes.append(r)

            if not filtered_runes:
                with ui.column().classes(
                    "items-center justify-center p-8 gap-2 w-full"
                ):
                    ui.icon("search_off", size="32px").classes("text-[#6e6584]")
                    ui.label("No extensions found").classes("text-xs text-[#6e6584]")
                    has_active_filters = (
                        bool(query)
                        or selected_type != "All Types"
                        or selected_hook != "All Hooks"
                        or selected_dep != "All Deps"
                    )
                    if has_active_filters:
                        ui.button(
                            "Reset Filters",
                            on_click=_clear_filters,
                        ).props("flat dense text-color=purple-4").classes("text-xs")
                return

            if sort_by == "Alphabetical (Z-A)":
                filtered_runes.sort(key=lambda r: r["name"].lower(), reverse=True)
            elif sort_by == "Date Added":
                filtered_runes.sort(
                    key=lambda r: (r["created_at"], r["name"].lower()),
                    reverse=True,
                )
            elif sort_by == "Last Updated":
                filtered_runes.sort(
                    key=lambda r: (r["updated_at"], r["name"].lower()),
                    reverse=True,
                )
            else:
                filtered_runes.sort(key=lambda r: r["name"].lower())

            with ui.column().classes("w-full gap-3 mt-2"):
                for r in filtered_runes:
                    name = r["name"]
                    version = r["version"]
                    runtime = r["runtime"]
                    desc = r["description"]
                    git_url = r["git_url"]
                    is_installed = r["is_installed"]
                    path = r["path"]
                    hooks = r["hooks"]
                    python_deps = r["python_deps"]
                    types = r["types"]

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
                                    ).props(
                                        "unelevated dense size=sm color=green-7"
                                    ).classes(
                                        "mvge-installed-btn text-white text-xs "
                                        "font-medium"
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

                        # Extension details (path, types, hooks, deps)
                        has_details = bool(
                            (is_installed and path) or types or hooks or python_deps
                        )
                        if has_details:
                            with ui.column().classes(
                                "w-full gap-1 pt-1 mt-1 border-t border-[#292335]/50"
                            ):
                                if is_installed and path:

                                    def _open_folder(p: str = path) -> None:
                                        opened = open_folder_in_explorer(p)
                                        if not opened:
                                            ui.notify(
                                                f"Could not open directory: {p}",
                                                type="warning",
                                            )

                                    with (
                                        ui.row()
                                        .classes(
                                            "items-center gap-1.5 no-wrap "
                                            "cursor-pointer hover:opacity-80 "
                                            "transition-opacity"
                                        )
                                        .on("click", _open_folder)
                                        .tooltip("Open folder in file explorer")
                                    ):
                                        ui.icon("folder_open", size="12px").classes(
                                            "text-[#7b6cf6]"
                                        ).on("click", _open_folder)
                                        ui.label(path).classes(
                                            "text-[11px] text-[#7b6cf6] underline "
                                            "font-mono truncate cursor-pointer"
                                        ).on("click", _open_folder)

                                if types:
                                    with ui.row().classes(
                                        "items-center gap-1 flex-wrap"
                                    ):
                                        ui.label("Type:").classes(
                                            "text-[10px] uppercase "
                                            "font-semibold text-[#6e6584]"
                                        )
                                        for t in types:
                                            ui.badge(str(t), color="purple-9").props(
                                                "rounded dense"
                                            ).classes(
                                                "text-[9px] text-[#e0daf7] font-mono "
                                                "border border-[#7b6cf6]/30"
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
