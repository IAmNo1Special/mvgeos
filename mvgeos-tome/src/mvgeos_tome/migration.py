from __future__ import annotations

import hashlib
from typing import Any

from mvgeos_tome.types import TomeVersionError

CURRENT_SESSION_VERSION = 3


def extract_session_version(header: dict[str, Any]) -> int:
    """Extract and validate the session version from header.

    Raises TomeVersionError if version is invalid or incompatible.
    """
    version_raw = header.get("version", 1)
    try:
        version = int(version_raw)
    except (ValueError, TypeError) as e:
        raise TomeVersionError(
            version_raw, f"Invalid session version: {version_raw}"
        ) from e

    if version < 1:
        raise TomeVersionError(version, f"Invalid session version: {version}")

    if version > CURRENT_SESSION_VERSION:
        raise TomeVersionError(
            version,
            f"Unsupported session version {version}: "
            f"maximum supported is {CURRENT_SESSION_VERSION}",
        )

    return version


def _migrate_v1_to_v2(
    header: dict[str, Any], entries: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Migrate a v1 session (linear sequence) to v2.

    Upgrades to a tree structure with id/parentId linking.
    """
    migrated_header = dict(header)
    migrated_header["version"] = 2
    migrated_entries: list[dict[str, Any]] = []
    tome_id = str(migrated_header.get("id", ""))

    prev_id: str | None = None
    for entry_idx, entry in enumerate(entries):
        migrated_entry = dict(entry)
        entry_id = migrated_entry.get("id")
        if not entry_id:
            ts = entry.get("timestamp", entry_idx)
            entry_id = hashlib.sha256(
                f"{tome_id}:{entry_idx}:{ts}".encode()
            ).hexdigest()[:8]
        migrated_entry["id"] = entry_id

        if "parentId" not in migrated_entry or migrated_entry["parentId"] is None:
            migrated_entry["parentId"] = prev_id

        prev_id = entry_id

        payload = migrated_entry.setdefault("payload", {})
        if not isinstance(payload, dict):
            payload = {}
            migrated_entry["payload"] = payload

        for k in list(migrated_entry.keys()):
            if k not in ("id", "parentId", "type", "timestamp", "payload"):
                if k not in payload:
                    payload[k] = migrated_entry[k]
                del migrated_entry[k]

        migrated_entries.append(migrated_entry)

    # Pass 2: resolve compaction firstKeptEntryIndex to firstKeptEntryId
    for migrated_entry in migrated_entries:
        payload = migrated_entry.get("payload")
        if isinstance(payload, dict) and "firstKeptEntryIndex" in payload:
            target_idx = payload.pop("firstKeptEntryIndex")
            if isinstance(target_idx, int) and 0 <= target_idx < len(migrated_entries):
                payload["firstKeptEntryId"] = migrated_entries[target_idx]["id"]

    if not migrated_header.get("activeLeafId") and migrated_entries:
        migrated_header["activeLeafId"] = migrated_entries[-1]["id"]

    return migrated_header, migrated_entries


def _migrate_v2_to_v3(
    header: dict[str, Any], entries: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Migrate a v2 session to v3 (roles/types unification and canonical schema)."""
    migrated_header = dict(header)
    migrated_header["version"] = 3
    migrated_header.setdefault("schema_version", "1.0")
    migrated_entries: list[dict[str, Any]] = []

    for entry in entries:
        migrated_entry = dict(entry)
        entry_type = migrated_entry.get("type")
        payload = migrated_entry.setdefault("payload", {})
        if not isinstance(payload, dict):
            payload = {}
            migrated_entry["payload"] = payload

        if entry_type in ("hookMessage", "customMessage"):
            migrated_entry["type"] = "custom"
        elif entry_type in ("spellResult", "invocation"):
            migrated_entry["type"] = "message"
        elif entry_type in (
            "modelChange",
            "contemplationLevelChange",
            "spellCallsChange",
            "branchSummary",
        ):
            migrated_entry["type"] = "custom"

        if payload.get("role") == "hookMessage":
            payload["role"] = "custom"
            if migrated_entry.get("type") == "message":
                migrated_entry["type"] = "custom"

        if "firstKeptEntryIndex" in payload:
            target_idx = payload.pop("firstKeptEntryIndex")
            if isinstance(target_idx, int) and 0 <= target_idx < len(entries):
                target_id = entries[target_idx].get("id")
                if target_id is not None:
                    payload["firstKeptEntryId"] = target_id

        if "firstKeptEntryIndex" in migrated_entry:
            target_idx = migrated_entry.pop("firstKeptEntryIndex")
            if isinstance(target_idx, int) and 0 <= target_idx < len(entries):
                target_id = entries[target_idx].get("id")
                if target_id is not None:
                    payload["firstKeptEntryId"] = target_id

        migrated_entries.append(migrated_entry)

    return migrated_header, migrated_entries


def migrate_session_data(
    header: dict[str, Any], entries: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Upgrade session header and entries through the migration pipeline to v3."""
    version = extract_session_version(header)

    current_hdr = dict(header)
    current_entries = [dict(e) for e in entries]

    if version == 1:
        current_hdr, current_entries = _migrate_v1_to_v2(current_hdr, current_entries)
        current_hdr, current_entries = _migrate_v2_to_v3(current_hdr, current_entries)
    elif version == 2:
        current_hdr, current_entries = _migrate_v2_to_v3(current_hdr, current_entries)

    return current_hdr, current_entries
