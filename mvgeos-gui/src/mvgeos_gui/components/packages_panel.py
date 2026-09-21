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

from mvgeos_gui.approval.types import is_approval_rune_name
from mvgeos_gui.components.approval_dialog import render_approval_permissions
from mvgeos_gui.components.rune_settings_dialog import render_rune_settings_dialog
from mvgeos_gui.state import AppState

logger = logging.getLogger(__name__)


class _MarketplaceFetchProbe(logging.Handler):
    """Observes marketplace fetch failures via the libraries' warnings.

    The library fetch helpers (mvgeos_runes / mvgeos_agent installers)
    swallow network errors: on failure they log
    "Failed to fetch marketplace ..." and return {}. The only failure
    signal that survives is that warning, so this handler watches for it
    while a fetch is in flight. Fetches are awaited sequentially, so a
    warning seen during one fetch belongs to that fetch: reset ``failed``
    before each fetch and read it right after.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.failed = False

    def emit(self, record: logging.LogRecord) -> None:
        if record.getMessage().startswith("Failed to fetch marketplace"):
            self.failed = True


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
        "types": ["Mvge"],
        "spells": spells,
        "python_deps": python_deps,
        "created_at": created_ts,
        "updated_at": updated_ts,
    }


def render_packages_panel(state: AppState) -> None:
    """Render the unified rune marketplace view (Mvges are a kind of rune)."""
    marketplace_data: dict[str, Any] = {}
    installed_data: list[dict[str, Any]] = []
    marketplace_mvges_data: dict[str, Any] = {}
    installed_mvges_data: list[dict[str, Any]] = []
    # Tracks catalog fetch failures separately from empty data: a failed
    # fetch must show a distinct error state, not the "No packages found"
    # empty-catalog message.
    catalog_error: dict[str, bool] = {"runes": False, "mvges": False}
    search_state: dict[str, str] = {
        "query": "",
        "type": "All Types",
        "hook": "All Hooks",
        "dep": "All Deps",
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
        source_error = (
            ui.label("Enter a git URL, local path, or marketplace rune name.")
            .classes("text-[11px] text-[#ef4444] -mt-2")
            .mark("package_dialog_source_error")
        )
        source_error.visible = False

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button("Cancel", on_click=install_dialog.close).props(
                "flat dense text-color=grey-4"
            ).mark("package_dialog_cancel_btn")

            async def _do_install() -> None:
                source = (source_input.value or "").strip()
                if not source:
                    source_error.visible = True
                    ui.notify("Please enter a rune source", type="warning")
                    return
                source_error.visible = False
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
        mvge_source_error = (
            ui.label("Enter a git URL, local path, or marketplace mvge name.")
            .classes("text-[11px] text-[#ef4444] -mt-2")
            .mark("mvge_dialog_source_error")
        )
        mvge_source_error.visible = False

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button("Cancel", on_click=mvge_install_dialog.close).props(
                "flat dense text-color=grey-4"
            ).mark("mvge_dialog_cancel_btn")

            async def _do_mvge_install() -> None:
                source = (mvge_source_input.value or "").strip()
                if not source:
                    mvge_source_error.visible = True
                    ui.notify("Please enter an agent source", type="warning")
                    return
                mvge_source_error.visible = False
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

    def _render_mvge_card(m: dict[str, Any]) -> None:
        """Render a single mvge agent card in the merged list."""
        m_name = m["name"]
        m_version = m["version"]
        m_runtime = m["runtime"]
        m_desc = m["description"]
        m_git_url = m["git_url"]
        m_is_installed = m["is_installed"]
        m_path = m["path"]
        m_types = m.get("types", [])
        m_spells = m["spells"]
        m_deps = m["python_deps"]

        with ui.card().classes(
            "w-full p-4 bg-[#0e0e12] border border-[#292335] rounded-xl gap-2"
        ):
            with ui.row().classes("w-full items-center justify-between"):
                with ui.row().classes("items-center gap-2"):
                    if m_is_installed:
                        ui.icon("check_circle", size="18px").classes("text-green-400")
                    else:
                        ui.icon("smart_toy", size="18px").classes("text-[#7b6cf6]")

                    ui.label(m_name).classes("text-sm font-semibold text-[#eceaf4]")
                    ui.badge(f"v{m_version}", color="grey-9").props(
                        "rounded dense"
                    ).classes("text-[10px] text-[#9c94b3] font-mono")
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
                            success = await state.uninstall_mvge_async(target_name)
                            if success:
                                ui.notify(
                                    (f"Successfully uninstalled {target_name}!"),
                                    type="positive",
                                )
                                await _refresh_data()
                            else:
                                ui.notify(
                                    (f"Failed to uninstall {target_name}"),
                                    type="negative",
                                )

                        ui.button(
                            "Installed",
                            on_click=_uninstall_mvge,
                        ).props("unelevated dense size=sm color=green-7").classes(
                            "mvge-installed-btn text-white text-xs font-medium"
                        ).mark(
                            f"mvge_install_item_{m_name}",
                            f"mvge_uninstall_item_{m_name}",
                        )
                    else:

                        async def _install_mvge(
                            target_name: str = m_name,
                        ) -> None:
                            ui.notify(
                                f"Installing {target_name}...",
                                type="info",
                            )
                            success = await state.install_mvge_async(target_name)
                            if success:
                                ui.notify(
                                    (f"Successfully installed {target_name}!"),
                                    type="positive",
                                )
                                await _refresh_data()
                            else:
                                ui.notify(
                                    (f"Failed to install {target_name}"),
                                    type="negative",
                                )

                        ui.button(
                            "Install",
                            on_click=_install_mvge,
                        ).props("unelevated dense size=sm").classes(
                            "mvge-glow-btn text-white text-xs font-medium"
                        ).mark(f"mvge_install_item_{m_name}")

            if m_desc:
                ui.label(m_desc).classes("text-xs text-[#9c94b3]")

            if m_git_url:
                with ui.row().classes("items-center gap-1"):
                    ui.icon("code", size="12px").classes("text-[#6e6584]")
                    ui.link(
                        m_git_url,
                        m_git_url,
                        new_tab=True,
                    ).classes("text-[11px] text-[#7b6cf6] underline")

            has_mvge_details = bool(
                (m_is_installed and m_path) or m_types or m_spells or m_deps
            )
            if has_mvge_details:
                with ui.column().classes(
                    "w-full gap-1 pt-1 mt-1 border-t border-[#292335]/50"
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
                            ui.icon("folder_open", size="12px").classes(
                                "text-[#7b6cf6]"
                            ).on("click", _open_agent_folder)
                            ui.label(m_path).classes(
                                "text-[11px] text-[#7b6cf6] "
                                "underline font-mono truncate "
                                "cursor-pointer"
                            ).on("click", _open_agent_folder)

                    if m_types:
                        with ui.row().classes("items-center gap-1 flex-wrap"):
                            ui.label("Type:").classes(
                                "text-[10px] uppercase font-semibold text-[#6e6584]"
                            )
                            for t in m_types:
                                ui.badge(str(t), color="purple-9").props(
                                    "rounded dense"
                                ).classes(
                                    "text-[9px] text-[#e0daf7] "
                                    "font-mono "
                                    "border border-[#7b6cf6]/30"
                                )

                    if m_spells:
                        with ui.row().classes("items-center gap-1 flex-wrap"):
                            ui.label("Spells:").classes(
                                "text-[10px] uppercase font-semibold text-[#6e6584]"
                            )
                            for spell in m_spells:
                                ui.badge(str(spell), color="purple-9").props(
                                    "rounded dense"
                                ).classes(
                                    "text-[9px] text-[#e0daf7] "
                                    "font-mono "
                                    "border border-[#7b6cf6]/30"
                                )

                    if m_deps:
                        with ui.row().classes("items-center gap-1 flex-wrap"):
                            ui.label("Deps:").classes(
                                "text-[10px] uppercase font-semibold text-[#6e6584]"
                            )
                            for dep in m_deps:
                                ui.badge(str(dep), color="dark").props(
                                    "rounded dense"
                                ).classes(
                                    "text-[9px] text-[#9c94b3] "
                                    "font-mono "
                                    "border border-[#292335]"
                                )

    def _render_rune_card(r: dict[str, Any]) -> None:
        """Render a single rune card in the merged list."""
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
            "w-full p-4 bg-[#0e0e12] border border-[#292335] rounded-xl gap-2"
        ):
            with ui.row().classes("w-full items-center justify-between"):
                with ui.row().classes("items-center gap-2"):
                    if is_installed:
                        ui.icon("check_circle", size="18px").classes("text-green-400")
                    else:
                        ui.icon("extension", size="18px").classes("text-[#7b6cf6]")

                    ui.label(name).classes("text-sm font-semibold text-[#eceaf4]")
                    ui.badge(f"v{version}", color="grey-9").props(
                        "rounded dense"
                    ).classes("text-[10px] text-[#9c94b3] font-mono")
                    ui.badge(runtime, color="purple-9").props("rounded dense").classes(
                        "text-[10px]"
                    )

                with ui.row().classes("items-center gap-2"):
                    if is_installed:

                        def _open_rune_settings(r: dict[str, Any] = r) -> None:
                            """Open the settings dialog for an installed rune."""

                            def _approval_section() -> None:
                                render_approval_permissions(state)

                            extra_section = None
                            wide = False
                            if is_approval_rune_name(r["name"]):
                                extra_section = _approval_section
                                wide = True
                            render_rune_settings_dialog(
                                state,
                                r,
                                _refresh_data,
                                extra_section=extra_section,
                                wide=wide,
                            )

                        ui.button(
                            icon="settings",
                            on_click=_open_rune_settings,
                        ).props("flat dense round size=sm text-color=grey-5").mark(
                            f"package_settings_item_{name}",
                        )

                        async def _uninstall_item(
                            r_name: str = name,
                        ) -> None:
                            ui.notify(
                                f"Uninstalling {r_name}...",
                                type="info",
                            )
                            success = await state.uninstall_rune_async(r_name)
                            if success:
                                ui.notify(
                                    (f"Successfully uninstalled {r_name}!"),
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
                        ).props("unelevated dense size=sm color=green-7").classes(
                            "mvge-installed-btn text-white text-xs font-medium"
                        ).mark(
                            f"package_install_item_{name}",
                            f"package_uninstall_item_{name}",
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
            has_details = bool((is_installed and path) or types or hooks or python_deps)
            if has_details:
                with ui.column().classes(
                    "w-full gap-1 pt-1 mt-1 border-t border-[#292335]/50"
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
                            ui.icon("folder_open", size="12px").classes(
                                "text-[#7b6cf6]"
                            ).on("click", _open_folder)
                            ui.label(path).classes(
                                "text-[11px] text-[#7b6cf6] "
                                "underline font-mono truncate "
                                "cursor-pointer"
                            ).on("click", _open_folder)

                    if types:
                        with ui.row().classes("items-center gap-1 flex-wrap"):
                            ui.label("Type:").classes(
                                "text-[10px] uppercase font-semibold text-[#6e6584]"
                            )
                            for t in types:
                                ui.badge(str(t), color="purple-9").props(
                                    "rounded dense"
                                ).classes(
                                    "text-[9px] text-[#e0daf7] "
                                    "font-mono "
                                    "border border-[#7b6cf6]/30"
                                )

                    if hooks:
                        with ui.row().classes("items-center gap-1 flex-wrap"):
                            ui.label("Hooks:").classes(
                                "text-[10px] uppercase font-semibold text-[#6e6584]"
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
                                    "font-mono "
                                    "border border-[#292335]"
                                )

                    if python_deps:
                        with ui.row().classes("items-center gap-1 flex-wrap"):
                            ui.label("Deps:").classes(
                                "text-[10px] uppercase font-semibold text-[#6e6584]"
                            )
                            for dep in python_deps:
                                ui.badge(str(dep), color="dark").props(
                                    "rounded dense"
                                ).classes(
                                    "text-[9px] text-[#9c94b3] "
                                    "font-mono "
                                    "border border-[#292335]"
                                )

    with ui.column().classes("w-full h-full overflow-y-auto p-6 gap-4"):
        with ui.column().classes("gap-1"):
            ui.label("Marketplace").classes("text-2xl font-semibold text-[#eceaf4]")
            ui.label(
                "Explore and manage MvgeOS agents and extensions from the "
                "official marketplace."
            ).classes("text-xs text-[#9c94b3]")

        with ui.row().classes("w-full items-center justify-between gap-4 mt-2"):

            def _on_search(val: str) -> None:
                search_state["query"] = val.strip().lower()
                render_packages.refresh()

            search_input = (
                ui.input(
                    placeholder=(
                        "Search packages, descriptions, spells, types, "
                        "hooks, or deps..."
                    ),
                    on_change=lambda e: _on_search(str(e.value or "")),
                )
                .props("dense dark outlined rounded")
                .classes("flex-1 text-xs")
                .mark("package_search_input", "mvge_search_input")
            )

            ui.button(
                "+ Install Rune from URL/Git",
                on_click=install_dialog.open,
            ).props("unelevated dense").classes(
                "mvge-glow-btn text-white text-xs"
            ).mark("package_open_install_dialog_btn")

            ui.button(
                "+ Install Mvge from URL/Git",
                on_click=mvge_install_dialog.open,
            ).props("unelevated dense").classes(
                "mvge-glow-btn text-white text-xs"
            ).mark("mvge_open_install_dialog_btn")

        @ui.refreshable
        def render_filters() -> None:
            def _set_filter(key: str, val: str) -> None:
                search_state[key] = val
                render_packages.refresh()

            # Build dynamic type options from all available packages.
            # Mvges are a type of rune, so "Mvge" appears alongside
            # rune types like "Spell", "Sigil", "Command".
            available_types: set[str] = set()
            for meta in list(marketplace_data.values()):
                if isinstance(meta, dict):
                    available_types.update(str(t) for t in meta.get("types", []))
            for meta in installed_data:
                if isinstance(meta, dict):
                    available_types.update(str(t) for t in meta.get("types", []))
            if marketplace_mvges_data or installed_mvges_data:
                available_types.add("Mvge")
            type_options = ["All Types"] + sorted(available_types)

            with ui.row().classes("w-full items-center gap-2 flex-wrap"):
                ui.icon("filter_list", size="16px").classes("text-[#6e6584]")
                ui.select(
                    options=type_options,
                    value=search_state["type"],
                    on_change=lambda e: _set_filter(
                        "type", str(e.value or "All Types")
                    ),
                ).props("dense dark outlined rounded options-dense").classes(
                    "min-w-[130px] text-xs"
                ).mark("package_filter_type_select")

                ui.select(
                    options=["All Hooks"],
                    value=search_state["hook"],
                    on_change=lambda e: _set_filter(
                        "hook", str(e.value or "All Hooks")
                    ),
                ).props("dense dark outlined rounded options-dense").classes(
                    "min-w-[140px] text-xs"
                ).mark("package_filter_hook_select")

                ui.select(
                    options=["All Deps"],
                    value=search_state["dep"],
                    on_change=lambda e: _set_filter("dep", str(e.value or "All Deps")),
                ).props("dense dark outlined rounded options-dense").classes(
                    "min-w-[130px] text-xs"
                ).mark("package_filter_dep_select")

                ui.select(
                    options=["All Spells"],
                    value=search_state["spell"],
                    on_change=lambda e: _set_filter(
                        "spell", str(e.value or "All Spells")
                    ),
                ).props("dense dark outlined rounded options-dense").classes(
                    "min-w-[140px] text-xs"
                ).mark("mvge_filter_spell_select")

                with ui.row().classes("items-center gap-1.5 ml-auto"):
                    ui.icon("sort", size="16px").classes("text-[#6e6584]")
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
                    ).props("dense dark outlined rounded options-dense").classes(
                        "min-w-[160px] text-xs"
                    ).mark("package_sort_select", "mvge_sort_select")

                    ui.button(
                        "Clear",
                        icon="clear",
                        on_click=_clear_filters,
                    ).props("flat dense size=sm text-color=grey-5").classes(
                        "text-xs"
                    ).mark("package_clear_filters_btn", "mvge_clear_filters_btn")

        @ui.refreshable
        def render_packages() -> None:
            query = search_state["query"]
            selected_type = search_state["type"]
            selected_hook = search_state["hook"]
            selected_dep = search_state["dep"]
            selected_spell = search_state["spell"]
            sort_by = search_state["sort"]

            installed_by_name: dict[str, dict[str, Any]] = {
                str(r.get("name", "")): r for r in installed_data if "name" in r
            }
            installed_mvges_by_name: dict[str, dict[str, Any]] = {
                str(m.get("name", "")): m for m in installed_mvges_data if "name" in m
            }

            all_infos: list[dict[str, Any]] = []
            for r_name in set(marketplace_data.keys()) | set(installed_by_name.keys()):
                mp_meta = marketplace_data.get(r_name, {})
                inst_meta = installed_by_name.get(r_name, {})
                is_installed = state.is_rune_installed(r_name) or bool(inst_meta)
                info = _extract_rune_info(r_name, mp_meta, inst_meta, is_installed)
                all_infos.append(info)
            for m_name in set(marketplace_mvges_data.keys()) | set(
                installed_mvges_by_name.keys()
            ):
                mp_m_meta = marketplace_mvges_data.get(m_name, {})
                inst_m_meta = installed_mvges_by_name.get(m_name, {})
                is_inst = state.is_mvge_installed(m_name) or bool(inst_m_meta)
                info = _extract_mvge_info(m_name, mp_m_meta, inst_m_meta, is_inst)
                all_infos.append(info)

            filtered: list[dict[str, Any]] = []
            for info in all_infos:
                if query:
                    q = query.lower()
                    name_match = q in info["name"].lower()
                    desc_match = q in info["description"].lower()
                    type_match = any(q in t.lower() for t in info.get("types", []))
                    hook_match = any(q in h.lower() for h in info.get("hooks", []))
                    dep_match = any(q in d.lower() for d in info["python_deps"])
                    spell_match = any(q in s.lower() for s in info.get("spells", []))
                    if not (
                        name_match
                        or desc_match
                        or type_match
                        or hook_match
                        or dep_match
                        or spell_match
                    ):
                        continue

                if selected_type != "All Types" and not any(
                    t.lower() == selected_type.lower() for t in info.get("types", [])
                ):
                    continue
                if selected_hook != "All Hooks" and not any(
                    h.lower() == selected_hook.lower() for h in info.get("hooks", [])
                ):
                    continue
                if selected_dep != "All Deps" and not any(
                    selected_dep.lower() in d.lower()
                    or d.lower() in selected_dep.lower()
                    for d in info["python_deps"]
                ):
                    continue
                if selected_spell != "All Spells" and not any(
                    s.lower() == selected_spell.lower() for s in info.get("spells", [])
                ):
                    continue

                filtered.append(info)

            if not filtered:
                # Distinct state for a failed catalog fetch: the catalog
                # didn't load at all, so this is not "no packages match" --
                # show the error and a retry instead.
                catalog_failed = catalog_error["runes"] or catalog_error["mvges"]
                has_installed = bool(installed_data) or bool(installed_mvges_data)
                if catalog_failed and not has_installed:
                    with ui.column().classes(
                        "items-center justify-center p-8 gap-2 w-full"
                    ):
                        ui.icon("cloud_off", size="32px").classes("text-[#e5484d]")
                        ui.label("Couldn't load the marketplace catalog").classes(
                            "text-sm text-[#eceaf4]"
                        )
                        ui.label(
                            "The catalog couldn't be reached. Check your "
                            "connection and try again. Installed packages "
                            "still show once their listing loads."
                        ).classes(
                            "text-[11px] text-[#6e6584]/70 text-center max-w-[420px]"
                        )
                        ui.button(
                            "Retry",
                            on_click=lambda: ui.timer(0.01, _refresh_data, once=True),
                        ).props("unelevated").classes("mvge-glow-btn text-white")
                    return
                with ui.column().classes(
                    "items-center justify-center p-8 gap-2 w-full"
                ):
                    ui.icon("search_off", size="32px").classes("text-[#6e6584]")
                    ui.label("No packages found").classes("text-xs text-[#6e6584]")
                    ui.label(
                        "Get packages with the Install buttons above -- from "
                        "a marketplace name, git URL, or local path."
                    ).classes("text-[11px] text-[#6e6584]/70 text-center max-w-[420px]")
                    has_active_filters = (
                        bool(query)
                        or selected_type != "All Types"
                        or selected_hook != "All Hooks"
                        or selected_dep != "All Deps"
                        or selected_spell != "All Spells"
                    )
                    if has_active_filters:
                        ui.button(
                            "Reset Filters",
                            on_click=_clear_filters,
                        ).props("flat dense text-color=purple-4").classes("text-xs")
                return

            if sort_by == "Alphabetical (Z-A)":
                filtered.sort(key=lambda i: i["name"].lower(), reverse=True)
            elif sort_by == "Date Added":
                filtered.sort(
                    key=lambda i: (i["created_at"], i["name"].lower()),
                    reverse=True,
                )
            elif sort_by == "Last Updated":
                filtered.sort(
                    key=lambda i: (i["updated_at"], i["name"].lower()),
                    reverse=True,
                )
            else:
                filtered.sort(key=lambda i: i["name"].lower())

            with ui.column().classes("w-full gap-3 mt-2"):
                for info in filtered:
                    if "Mvge" in info.get("types", []):
                        _render_mvge_card(info)
                    else:
                        _render_rune_card(info)

        def _clear_filters() -> None:
            search_input.value = ""
            search_state["query"] = ""
            search_state["type"] = "All Types"
            search_state["hook"] = "All Hooks"
            search_state["dep"] = "All Deps"
            search_state["spell"] = "All Spells"
            search_state["sort"] = "Alphabetical (A-Z)"
            render_filters.refresh()
            render_packages.refresh()

        render_filters()
        render_packages()

    async def _refresh_data() -> None:
        # The library fetch helpers swallow network errors and return {}
        # on failure, so an empty result is ambiguous. Observe the
        # installers' loggers during each fetch: a "Failed to fetch
        # marketplace ..." warning marks a failed fetch, while a quiet
        # empty result means a genuinely empty catalog.
        fetch_probe = _MarketplaceFetchProbe()
        installer_loggers = [
            logging.getLogger("mvgeos_runes.installer"),
            logging.getLogger("mvgeos_agent.installer"),
        ]
        for installer_logger in installer_loggers:
            installer_logger.addHandler(fetch_probe)
        try:
            try:
                fetch_probe.failed = False
                mp = await state.fetch_marketplace_runes_async()
                if mp:
                    marketplace_data.clear()
                    marketplace_data.update(mp)
                    catalog_error["runes"] = False
                else:
                    catalog_error["runes"] = fetch_probe.failed
            except Exception as exc:
                catalog_error["runes"] = True
                logger.warning("Failed to fetch marketplace runes: %s", exc)

            try:
                inst = await state.list_installed_runes_async()
                installed_data.clear()
                installed_data.extend(inst)
            except Exception as exc:
                logger.warning("Failed to list installed runes: %s", exc)

            try:
                fetch_probe.failed = False
                mp_m = await state.fetch_marketplace_mvges_async()
                if mp_m:
                    marketplace_mvges_data.clear()
                    marketplace_mvges_data.update(mp_m)
                    catalog_error["mvges"] = False
                else:
                    catalog_error["mvges"] = fetch_probe.failed
            except Exception as exc:
                catalog_error["mvges"] = True
                logger.warning("Failed to fetch marketplace mvges: %s", exc)

            try:
                inst_m = await state.list_installed_mvges_async()
                installed_mvges_data.clear()
                installed_mvges_data.extend(inst_m)
            except Exception as exc:
                logger.warning("Failed to list installed mvges: %s", exc)

            render_filters.refresh()
            render_packages.refresh()
        finally:
            for installer_logger in installer_loggers:
                installer_logger.removeHandler(fetch_probe)

    ui.timer(0.01, _refresh_data, once=True)
