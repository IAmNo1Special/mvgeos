"""Packages panel: installed packages and catalog (Mvges and Runes)."""

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


def _extract_mvge_info(
    name: str,
    mp_meta: dict[str, Any],
    inst_meta: dict[str, Any],
    is_installed: bool,
) -> dict[str, Any]:
    """Extract unified metadata and timestamps for an mvge agent."""
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
    spells = [str(s) for s in (inst_meta.get("spells") or mp_meta.get("spells", []))]
    python_deps = [
        str(d) for d in (inst_meta.get("python_deps") or mp_meta.get("python_deps", []))
    ]

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
        "spells": spells,
        "python_deps": python_deps,
        "created_at": created_ts,
        "updated_at": updated_ts,
    }


def render_packages_panel(state: AppState) -> None:
    """Render the packages, agents (Mvges), and rune marketplace view."""
    marketplace_data: dict[str, Any] = {}
    installed_data: list[dict[str, Any]] = []
    search_state: dict[str, str] = {
        "query": "",
        "type": "All Types",
        "hook": "All Hooks",
        "dep": "All Deps",
        "sort": "Alphabetical (A-Z)",
    }

    marketplace_mvges_data: dict[str, Any] = {}
    installed_mvges_data: list[dict[str, Any]] = []
    mvge_search_state: dict[str, str] = {
        "query": "",
        "spell": "All Spells",
        "sort": "Alphabetical (A-Z)",
    }

    # Rune install dialog
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

    # Mvge install dialog
    with (
        ui.dialog() as mvge_install_dialog,
        ui.card().classes(
            "w-[480px] p-6 bg-[#0e0e12] border border-[#292335] rounded-xl gap-4"
        ),
    ):
        ui.label("Install Mvge Agent").classes("text-lg font-semibold text-[#eceaf4]")
        ui.label(
            "Enter a marketplace mvge name, Git repository URL, or local path."
        ).classes("text-xs text-[#9c94b3]")
        mvge_source_input = (
            ui.input(placeholder="git URL, local path, or marketplace mvge name")
            .props("dense dark outlined rounded")
            .classes("w-full text-xs")
            .mark("mvge_dialog_source_input")
        )

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button("Cancel", on_click=mvge_install_dialog.close).props(
                "flat dense text-color=grey-4"
            ).mark("mvge_dialog_cancel_btn")

            async def _do_mvge_install() -> None:
                source = (mvge_source_input.value or "").strip()
                if not source:
                    ui.notify("Please enter an agent source", type="warning")
                    return
                ui.notify(f"Installing {source}...", type="info")
                success = await state.install_mvge_async(source)
                if success:
                    ui.notify(f"Successfully installed {source}!", type="positive")
                    mvge_source_input.value = ""
                    mvge_install_dialog.close()
                    await _refresh_data()
                else:
                    ui.notify(f"Failed to install {source}", type="negative")

            ui.button("Install", on_click=_do_mvge_install).props(
                "unelevated dense"
            ).classes("mvge-glow-btn text-white").mark("mvge_dialog_install_btn")

    with ui.column().classes("w-full h-full overflow-y-auto p-6 gap-4"):
        with ui.column().classes("gap-1"):
            ui.label("Marketplace").classes("text-2xl font-semibold text-[#eceaf4]")
            ui.label(
                "Explore and manage MvgeOS agents and extensions from the "
                "official marketplace."
            ).classes("text-xs text-[#9c94b3]")

        with ui.tabs().classes(
            "w-full border-b border-[#292335] text-[#eceaf4]"
        ) as tabs:
            mvges_tab = (
                ui.tab("Mvges", icon="smart_toy")
                .classes("text-xs font-medium")
                .mark("marketplace_mvges_tab")
            )
            runes_tab = (
                ui.tab("Runes", icon="extension")
                .classes("text-xs font-medium")
                .mark("marketplace_runes_tab")
            )

        with ui.tab_panels(tabs, value=mvges_tab).classes("w-full bg-transparent p-0"):
            # MVGES TAB PANEL
            with ui.tab_panel(mvges_tab).classes("p-0 gap-4 flex flex-col"):
                with ui.row().classes("w-full items-center justify-between gap-4 mt-2"):

                    def _on_mvge_search(val: str) -> None:
                        mvge_search_state["query"] = val.strip().lower()
                        render_mvges.refresh()

                    mvge_search_input = (
                        ui.input(
                            placeholder="Search agents, descriptions, or spells...",
                            on_change=lambda e: _on_mvge_search(str(e.value or "")),
                        )
                        .props("dense dark outlined rounded")
                        .classes("flex-1 text-xs")
                        .mark("mvge_search_input")
                    )

                    ui.button(
                        "+ Install Agent from URL/Git",
                        on_click=mvge_install_dialog.open,
                    ).props("unelevated dense").classes(
                        "mvge-glow-btn text-white text-xs"
                    ).mark("mvge_open_install_dialog_btn")

                def _set_mvge_filter(key: str, val: str) -> None:
                    mvge_search_state[key] = val
                    render_mvges.refresh()

                def _clear_mvge_filters() -> None:
                    mvge_search_input.value = ""
                    mvge_search_state["query"] = ""
                    mvge_search_state["spell"] = "All Spells"
                    mvge_search_state["sort"] = "Alphabetical (A-Z)"
                    mvge_spell_select.value = "All Spells"
                    mvge_sort_select.value = "Alphabetical (A-Z)"
                    render_mvges.refresh()

                with ui.row().classes("w-full items-center gap-2 flex-wrap"):
                    ui.icon("filter_list", size="16px").classes("text-[#6e6584]")
                    mvge_spell_select = (
                        ui.select(
                            options=["All Spells"],
                            value=mvge_search_state["spell"],
                            on_change=lambda e: _set_mvge_filter(
                                "spell", str(e.value or "All Spells")
                            ),
                        )
                        .props("dense dark outlined rounded options-dense")
                        .classes("min-w-[140px] text-xs")
                        .mark("mvge_filter_spell_select")
                    )

                    with ui.row().classes("items-center gap-1.5 ml-auto"):
                        ui.icon("sort", size="16px").classes("text-[#6e6584]")
                        mvge_sort_select = (
                            ui.select(
                                options=[
                                    "Alphabetical (A-Z)",
                                    "Alphabetical (Z-A)",
                                    "Date Added",
                                    "Last Updated",
                                ],
                                value=mvge_search_state["sort"],
                                on_change=lambda e: _set_mvge_filter(
                                    "sort", str(e.value or "Alphabetical (A-Z)")
                                ),
                            )
                            .props("dense dark outlined rounded options-dense")
                            .classes("min-w-[160px] text-xs")
                            .mark("mvge_sort_select")
                        )

                        ui.button(
                            "Clear",
                            icon="clear",
                            on_click=_clear_mvge_filters,
                        ).props("flat dense size=sm text-color=grey-5").classes(
                            "text-xs"
                        ).mark("mvge_clear_filters_btn")

                @ui.refreshable
                def render_mvges() -> None:
                    m_query = mvge_search_state["query"]
                    m_selected_spell = mvge_search_state["spell"]
                    m_sort_by = mvge_search_state["sort"]

                    installed_mvges_by_name: dict[str, dict[str, Any]] = {
                        str(m.get("name", "")): m
                        for m in installed_mvges_data
                        if "name" in m
                    }

                    all_mvge_names = set(marketplace_mvges_data.keys()) | set(
                        installed_mvges_by_name.keys()
                    )

                    all_mvges: list[dict[str, Any]] = []
                    for m_name in all_mvge_names:
                        mp_m_meta = marketplace_mvges_data.get(m_name, {})
                        inst_m_meta = installed_mvges_by_name.get(m_name, {})
                        is_inst = state.is_mvge_installed(m_name) or bool(inst_m_meta)
                        all_mvges.append(
                            _extract_mvge_info(m_name, mp_m_meta, inst_m_meta, is_inst)
                        )

                    filtered_mvges: list[dict[str, Any]] = []
                    for m in all_mvges:
                        if m_query:
                            q = m_query.lower()
                            name_match = q in m["name"].lower()
                            desc_match = q in m["description"].lower()
                            spell_match = any(q in s.lower() for s in m["spells"])
                            if not (name_match or desc_match or spell_match):
                                continue

                        if m_selected_spell != "All Spells" and not any(
                            s.lower() == m_selected_spell.lower() for s in m["spells"]
                        ):
                            continue

                        filtered_mvges.append(m)

                    if not filtered_mvges:
                        with ui.column().classes(
                            "items-center justify-center p-8 gap-2 w-full"
                        ):
                            ui.icon("search_off", size="32px").classes("text-[#6e6584]")
                            ui.label("No agents found").classes(
                                "text-xs text-[#6e6584]"
                            )
                            has_active_filters = (
                                bool(m_query) or m_selected_spell != "All Spells"
                            )
                            if has_active_filters:
                                ui.button(
                                    "Reset Filters",
                                    on_click=_clear_mvge_filters,
                                ).props("flat dense text-color=purple-4").classes(
                                    "text-xs"
                                )
                        return

                    if m_sort_by == "Alphabetical (Z-A)":
                        filtered_mvges.sort(
                            key=lambda m: m["name"].lower(), reverse=True
                        )
                    elif m_sort_by == "Date Added":
                        filtered_mvges.sort(
                            key=lambda m: (m["created_at"], m["name"].lower()),
                            reverse=True,
                        )
                    elif m_sort_by == "Last Updated":
                        filtered_mvges.sort(
                            key=lambda m: (m["updated_at"], m["name"].lower()),
                            reverse=True,
                        )
                    else:
                        filtered_mvges.sort(key=lambda m: m["name"].lower())

                    with ui.column().classes("w-full gap-3 mt-2"):
                        for m in filtered_mvges:
                            m_name = m["name"]
                            m_version = m["version"]
                            m_runtime = m["runtime"]
                            m_desc = m["description"]
                            m_git_url = m["git_url"]
                            m_is_installed = m["is_installed"]
                            m_path = m["path"]
                            m_spells = m["spells"]
                            m_deps = m["python_deps"]

                            with ui.card().classes(
                                "w-full p-4 bg-[#0e0e12] border border-[#292335] "
                                "rounded-xl gap-2"
                            ):
                                with ui.row().classes(
                                    "w-full items-center justify-between"
                                ):
                                    with ui.row().classes("items-center gap-2"):
                                        if m_is_installed:
                                            ui.icon(
                                                "check_circle", size="18px"
                                            ).classes("text-green-400")
                                        else:
                                            ui.icon("smart_toy", size="18px").classes(
                                                "text-[#7b6cf6]"
                                            )

                                        ui.label(m_name).classes(
                                            "text-sm font-semibold text-[#eceaf4]"
                                        )
                                        ui.badge(f"v{m_version}", color="grey-9").props(
                                            "rounded dense"
                                        ).classes(
                                            "text-[10px] text-[#9c94b3] font-mono"
                                        )
                                        ui.badge(m_runtime, color="purple-9").props(
                                            "rounded dense"
                                        ).classes("text-[10px]")

                                    with ui.row().classes("items-center gap-2"):
                                        if m_is_installed:

                                            async def _uninstall_mvge(
                                                target_name: str = m_name,
                                            ) -> None:
                                                ui.notify(
                                                    f"Uninstalling {target_name}...",
                                                    type="info",
                                                )
                                                success = (
                                                    await state.uninstall_mvge_async(
                                                        target_name
                                                    )
                                                )
                                                if success:
                                                    ui.notify(
                                                        (
                                                            f"Successfully uninstalled "
                                                            f"{target_name}!"
                                                        ),
                                                        type="positive",
                                                    )
                                                    await _refresh_data()
                                                else:
                                                    ui.notify(
                                                        (
                                                            f"Failed to uninstall "
                                                            f"{target_name}"
                                                        ),
                                                        type="negative",
                                                    )

                                            ui.button(
                                                "Installed",
                                                on_click=_uninstall_mvge,
                                            ).props(
                                                "unelevated dense size=sm color=green-7"
                                            ).classes(
                                                "mvge-installed-btn "
                                                "text-white text-xs font-medium"
                                            ).mark(f"mvge_install_item_{m_name}").mark(
                                                f"mvge_uninstall_item_{m_name}"
                                            )
                                        else:

                                            async def _install_mvge(
                                                target_name: str = m_name,
                                            ) -> None:
                                                ui.notify(
                                                    f"Installing {target_name}...",
                                                    type="info",
                                                )
                                                success = (
                                                    await state.install_mvge_async(
                                                        target_name
                                                    )
                                                )
                                                if success:
                                                    ui.notify(
                                                        (
                                                            f"Successfully installed "
                                                            f"{target_name}!"
                                                        ),
                                                        type="positive",
                                                    )
                                                    await _refresh_data()
                                                else:
                                                    ui.notify(
                                                        (
                                                            f"Failed to install "
                                                            f"{target_name}"
                                                        ),
                                                        type="negative",
                                                    )

                                            ui.button(
                                                "Install",
                                                on_click=_install_mvge,
                                            ).props("unelevated dense size=sm").classes(
                                                "mvge-glow-btn text-white "
                                                "text-xs font-medium"
                                            ).mark(f"mvge_install_item_{m_name}")

                                if m_desc:
                                    ui.label(m_desc).classes("text-xs text-[#9c94b3]")

                                if m_git_url:
                                    with ui.row().classes("items-center gap-1"):
                                        ui.icon("code", size="12px").classes(
                                            "text-[#6e6584]"
                                        )
                                        ui.link(
                                            m_git_url,
                                            m_git_url,
                                            new_tab=True,
                                        ).classes(
                                            "text-[11px] text-[#7b6cf6] underline"
                                        )

                                has_mvge_details = bool(
                                    (m_is_installed and m_path) or m_spells or m_deps
                                )
                                if has_mvge_details:
                                    with ui.column().classes(
                                        "w-full gap-1 pt-1 mt-1 "
                                        "border-t border-[#292335]/50"
                                    ):
                                        if m_is_installed and m_path:

                                            def _open_agent_folder(
                                                p: str = m_path,
                                            ) -> None:
                                                opened = open_folder_in_explorer(p)
                                                if not opened:
                                                    ui.notify(
                                                        f"Could not open: {p}",
                                                        type="warning",
                                                    )

                                            with (
                                                ui.row()
                                                .classes(
                                                    "items-center gap-1.5 no-wrap "
                                                    "cursor-pointer "
                                                    "hover:opacity-80 "
                                                    "transition-opacity"
                                                )
                                                .on("click", _open_agent_folder)
                                                .tooltip("Open folder in file explorer")
                                            ):
                                                ui.icon(
                                                    "folder_open", size="12px"
                                                ).classes("text-[#7b6cf6]").on(
                                                    "click", _open_agent_folder
                                                )
                                                ui.label(m_path).classes(
                                                    "text-[11px] text-[#7b6cf6] "
                                                    "underline font-mono truncate "
                                                    "cursor-pointer"
                                                ).on("click", _open_agent_folder)

                                        if m_spells:
                                            with ui.row().classes(
                                                "items-center gap-1 flex-wrap"
                                            ):
                                                ui.label("Spells:").classes(
                                                    "text-[10px] uppercase "
                                                    "font-semibold "
                                                    "text-[#6e6584]"
                                                )
                                                for spell in m_spells:
                                                    ui.badge(
                                                        str(spell), color="purple-9"
                                                    ).props("rounded dense").classes(
                                                        "text-[9px] text-[#e0daf7] "
                                                        "font-mono "
                                                        "border border-[#7b6cf6]/30"
                                                    )

                                        if m_deps:
                                            with ui.row().classes(
                                                "items-center gap-1 flex-wrap"
                                            ):
                                                ui.label("Deps:").classes(
                                                    "text-[10px] uppercase "
                                                    "font-semibold "
                                                    "text-[#6e6584]"
                                                )
                                                for dep in m_deps:
                                                    ui.badge(
                                                        str(dep), color="dark"
                                                    ).props("rounded dense").classes(
                                                        "text-[9px] text-[#9c94b3] "
                                                        "font-mono "
                                                        "border border-[#292335]"
                                                    )

                render_mvges()

            # RUNES TAB PANEL
            with ui.tab_panel(runes_tab).classes("p-0 gap-4 flex flex-col"):
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
                            on_change=lambda e: _set_filter(
                                "dep", str(e.value or "All Deps")
                            ),
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
                        ).props("flat dense size=sm text-color=grey-5").classes(
                            "text-xs"
                        ).mark("package_clear_filters_btn")

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
                    all_names = set(marketplace_data.keys()) | set(
                        installed_by_name.keys()
                    )

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
                            ui.label("No extensions found").classes(
                                "text-xs text-[#6e6584]"
                            )
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
                                ).props("flat dense text-color=purple-4").classes(
                                    "text-xs"
                                )
                        return

                    if sort_by == "Alphabetical (Z-A)":
                        filtered_runes.sort(
                            key=lambda r: r["name"].lower(), reverse=True
                        )
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
                                with ui.row().classes(
                                    "w-full items-center justify-between"
                                ):
                                    with ui.row().classes("items-center gap-2"):
                                        if is_installed:
                                            ui.icon(
                                                "check_circle", size="18px"
                                            ).classes("text-green-400")
                                        else:
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
                                        if is_installed:

                                            async def _uninstall_item(
                                                r_name: str = name,
                                            ) -> None:
                                                ui.notify(
                                                    f"Uninstalling {r_name}...",
                                                    type="info",
                                                )
                                                success = (
                                                    await state.uninstall_rune_async(
                                                        r_name
                                                    )
                                                )
                                                if success:
                                                    ui.notify(
                                                        (
                                                            f"Successfully uninstalled "
                                                            f"{r_name}!"
                                                        ),
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
                                                "mvge-installed-btn "
                                                "text-white text-xs font-medium"
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
                                                "mvge-glow-btn text-white "
                                                "text-xs font-medium"
                                            ).mark(f"package_install_item_{name}")

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

                                # Extension details (path, types, hooks, deps)
                                has_details = bool(
                                    (is_installed and path)
                                    or types
                                    or hooks
                                    or python_deps
                                )
                                if has_details:
                                    with ui.column().classes(
                                        "w-full gap-1 pt-1 mt-1 "
                                        "border-t border-[#292335]/50"
                                    ):
                                        if is_installed and path:

                                            def _open_folder(p: str = path) -> None:
                                                opened = open_folder_in_explorer(p)
                                                if not opened:
                                                    ui.notify(
                                                        f"Could not open: {p}",
                                                        type="warning",
                                                    )

                                            with (
                                                ui.row()
                                                .classes(
                                                    "items-center gap-1.5 no-wrap "
                                                    "cursor-pointer "
                                                    "hover:opacity-80 "
                                                    "transition-opacity"
                                                )
                                                .on("click", _open_folder)
                                                .tooltip("Open folder in file explorer")
                                            ):
                                                ui.icon(
                                                    "folder_open", size="12px"
                                                ).classes("text-[#7b6cf6]").on(
                                                    "click", _open_folder
                                                )
                                                ui.label(path).classes(
                                                    "text-[11px] text-[#7b6cf6] "
                                                    "underline font-mono truncate "
                                                    "cursor-pointer"
                                                ).on("click", _open_folder)

                                        if types:
                                            with ui.row().classes(
                                                "items-center gap-1 flex-wrap"
                                            ):
                                                ui.label("Type:").classes(
                                                    "text-[10px] uppercase "
                                                    "font-semibold "
                                                    "text-[#6e6584]"
                                                )
                                                for t in types:
                                                    ui.badge(
                                                        str(t), color="purple-9"
                                                    ).props("rounded dense").classes(
                                                        "text-[9px] text-[#e0daf7] "
                                                        "font-mono "
                                                        "border border-[#7b6cf6]/30"
                                                    )

                                        if hooks:
                                            with ui.row().classes(
                                                "items-center gap-1 flex-wrap"
                                            ):
                                                ui.label("Hooks:").classes(
                                                    "text-[10px] uppercase "
                                                    "font-semibold "
                                                    "text-[#6e6584]"
                                                )
                                                for h in hooks:
                                                    h_name = (
                                                        h
                                                        if isinstance(h, str)
                                                        else getattr(h, "value", str(h))
                                                    )
                                                    ui.badge(
                                                        h_name, color="dark"
                                                    ).props("rounded dense").classes(
                                                        "text-[9px] text-[#9c94b3] "
                                                        "font-mono "
                                                        "border border-[#292335]"
                                                    )

                                        if python_deps:
                                            with ui.row().classes(
                                                "items-center gap-1 flex-wrap"
                                            ):
                                                ui.label("Deps:").classes(
                                                    "text-[10px] uppercase "
                                                    "font-semibold "
                                                    "text-[#6e6584]"
                                                )
                                                for dep in python_deps:
                                                    ui.badge(
                                                        str(dep), color="dark"
                                                    ).props("rounded dense").classes(
                                                        "text-[9px] text-[#9c94b3] "
                                                        "font-mono "
                                                        "border border-[#292335]"
                                                    )

                render_extensions()

    async def _refresh_data() -> None:
        try:
            mp = await state.fetch_marketplace_runes_async()
            if mp:
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

        try:
            mp_m = await state.fetch_marketplace_mvges_async()
            if mp_m:
                marketplace_mvges_data.clear()
                marketplace_mvges_data.update(mp_m)
        except Exception as exc:
            logger.warning("Failed to fetch marketplace mvges: %s", exc)

        try:
            inst_m = await state.list_installed_mvges_async()
            installed_mvges_data.clear()
            installed_mvges_data.extend(inst_m)
        except Exception as exc:
            logger.warning("Failed to list installed mvges: %s", exc)

        render_mvges.refresh()

    ui.timer(0.01, _refresh_data, once=True)
