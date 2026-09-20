from __future__ import annotations

import mimetypes
from base64 import b64encode
from dataclasses import dataclass
from typing import Any

from mvgeos_core.channel import MvgeResponse
from mvgeos_core.spells import SpellResultMessage


@dataclass
class SummonerRequest:
    role: str = "user"
    content: str | list[dict[str, Any]] | None = None
    timestamp: float = 0.0


MvgeInvocation = SummonerRequest | MvgeResponse | SpellResultMessage


@dataclass
class Attachment:
    """A file attached to a summoner message, carried as native content parts."""

    filename: str
    data: bytes
    mime_type: str | None = None


_FALLBACK_MIME_TYPE = "application/octet-stream"


def _attachment_mime_type(attachment: Attachment) -> str:
    if attachment.mime_type:
        return attachment.mime_type
    guessed, _ = mimetypes.guess_type(attachment.filename)
    return guessed or _FALLBACK_MIME_TYPE


def _attachment_part(attachment: Attachment) -> dict[str, Any]:
    mime_type = _attachment_mime_type(attachment)
    data_url = f"data:{mime_type};base64,{b64encode(attachment.data).decode('ascii')}"
    if mime_type.startswith("image/"):
        return {"type": "image_url", "image_url": {"url": data_url}}
    return {
        "type": "file",
        "file": {"filename": attachment.filename, "file_data": data_url},
    }


def build_content_parts(
    text: str, attachments: list[Attachment]
) -> str | list[dict[str, Any]]:
    """Build summoner message content from text plus file attachments.

    Returns the plain text string when there are no attachments; otherwise
    returns content parts in the documented OpenRouter multimodal shape so
    images, PDFs, markdown, and text files travel natively.
    """
    if not attachments:
        return text
    parts: list[dict[str, Any]] = []
    if text:
        parts.append({"type": "text", "text": text})
    parts.extend(_attachment_part(attachment) for attachment in attachments)
    return parts


__all__ = [
    "Attachment",
    "MvgeInvocation",
    "SummonerRequest",
    "build_content_parts",
]
