from __future__ import annotations

import re
from html.parser import HTMLParser

import httpx
from mvgeos_core.abort import (
    AbortError,
    AbortSignal,
)
from mvgeos_core.spells import (
    SpellResult,
    SpellStatus,
)

_BINARY_TYPES = {
    "image/",
    "audio/",
    "video/",
    "application/pdf",
    "application/zip",
    "application/octet-stream",
    "application/x-tar",
    "application/gzip",
}

_IGNORED_TAGS = {"script", "style", "noscript", "svg", "header", "footer", "nav"}


class _HTMLToMarkdownParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str = ""
        self.body_lines: list[str] = []
        self._ignore_stack: list[str] = []
        self._in_title: bool = False
        self._current_tag: str = ""
        self._current_link_href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        if tag_lower in _IGNORED_TAGS:
            self._ignore_stack.append(tag_lower)
            return
        if self._ignore_stack:
            return

        self._current_tag = tag_lower
        if tag_lower == "title":
            self._in_title = True
        elif tag_lower == "a":
            attr_dict = {k.lower(): (v or "") for k, v in attrs}
            self._current_link_href = attr_dict.get("href")
        elif tag_lower in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag_lower[1])
            self.body_lines.append(f"\n{'#' * level} ")
        elif tag_lower in ("p", "div", "section", "article"):
            self.body_lines.append("\n")
        elif tag_lower == "li":
            self.body_lines.append("\n- ")
        elif tag_lower == "br":
            self.body_lines.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if self._ignore_stack:
            if self._ignore_stack[-1] == tag_lower:
                self._ignore_stack.pop()
            return

        if tag_lower == "title":
            self._in_title = False
        elif tag_lower == "a":
            self._current_link_href = None
        elif tag_lower in (
            "p",
            "div",
            "section",
            "article",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
        ):
            self.body_lines.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignore_stack:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title += text + " "
        elif self._current_link_href:
            self.body_lines.append(f"[{text}]({self._current_link_href})")
        else:
            self.body_lines.append(text + " ")

    def get_markdown(self) -> str:
        raw = "".join(self.body_lines)
        # Condense multiple newlines
        cleaned = re.sub(r"\n{3,}", "\n\n", raw).strip()
        title_str = self.title.strip()
        if title_str:
            return f"# {title_str}\n\n{cleaned}"
        return cleaned


async def read_url(
    url: str,
    max_length: int = 20000,
    signal: AbortSignal | None = None,
    client: httpx.AsyncClient | None = None,
) -> SpellResult:
    """Fetch and extract readable text content from a web URL.

    Args:
        url: The web URL to fetch (HTTP or HTTPS).
        max_length: Maximum character length of returned content (default 20,000).
        signal: Optional cancellation signal.
        client: Optional HTTP client for testing.

    Returns:
        SpellResult containing readable text/markdown representation.
    """
    if signal is not None and getattr(signal, "aborted", False):
        raise AbortError("Operation aborted")

    if not url.startswith(("http://", "https://")):
        return SpellResult(
            spell_name="read_url",
            status=SpellStatus.ERROR,
            error_message=f"Invalid URL '{url}'. Must start with http:// or https://",
        )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
    }

    try:
        if client is not None:
            response = await client.get(url, headers=headers, timeout=15.0)
        else:
            async with httpx.AsyncClient(
                timeout=15.0, follow_redirects=True
            ) as local_client:
                response = await local_client.get(url, headers=headers)

        if response.status_code != 200:
            return SpellResult(
                spell_name="read_url",
                status=SpellStatus.ERROR,
                error_message=f"Failed to fetch '{url}': HTTP {response.status_code}",
            )

        if signal is not None and getattr(signal, "aborted", False):
            raise AbortError("Operation aborted")

        content_type = response.headers.get("content-type", "").lower()
        for bin_type in _BINARY_TYPES:
            if bin_type in content_type:
                return SpellResult(
                    spell_name="read_url",
                    status=SpellStatus.ERROR,
                    error_message=(
                        f"Binary content type '{content_type}' is not supported."
                    ),
                )

        if "text/html" in content_type:
            parser = _HTMLToMarkdownParser()
            parser.feed(response.text)
            parser.close()
            content = parser.get_markdown()
        else:
            # Plain text, JSON, Markdown, XML, etc.
            content = response.text.strip()

        if not content:
            content = f"Page at {url} returned empty content."

        if len(content) > max_length:
            content = (
                content[:max_length] + f"\n\n... [truncated at {max_length} characters]"
            )

        return SpellResult(
            spell_name="read_url",
            status=SpellStatus.SUCCESS,
            content=content,
        )
    except AbortError:
        raise
    except Exception as exc:
        return SpellResult(
            spell_name="read_url",
            status=SpellStatus.ERROR,
            error_message=f"Failed to read URL: {exc}",
        )
