from __future__ import annotations

import urllib.parse
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


class _DuckDuckGoHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._current_result: dict[str, str] | None = None
        self._current_field: str | None = None
        self._text_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        classes = attr_dict.get("class", "").split()

        if tag == "a" and "result__a" in classes:
            if self._current_result is not None and self._current_result.get("title"):
                self.results.append(self._current_result)
            raw_href = attr_dict.get("href", "")
            clean_url = _clean_ddg_url(raw_href)
            self._current_result = {"title": "", "url": clean_url, "snippet": ""}
            self._current_field = "title"
            self._text_chunks = []
        elif "result__snippet" in classes:
            self._current_field = "snippet"
            self._text_chunks = []

    def handle_endtag(self, tag: str) -> None:
        if self._current_field is not None and self._current_result is not None:
            text = " ".join("".join(self._text_chunks).split())
            if self._current_field == "title":
                self._current_result["title"] = text
            elif self._current_field == "snippet":
                self._current_result["snippet"] = text
            self._current_field = None
            self._text_chunks = []

        if (
            tag in ("div", "tr")
            and self._current_result is not None
            and self._current_result.get("title")
            and self._current_result not in self.results
        ):
            self.results.append(self._current_result)
            self._current_result = None

    def handle_data(self, data: str) -> None:
        if self._current_field is not None:
            self._text_chunks.append(data)

    def close(self) -> None:
        super().close()
        if (
            self._current_result is not None
            and self._current_result.get("title")
            and self._current_result not in self.results
        ):
            self.results.append(self._current_result)
            self._current_result = None


def _clean_ddg_url(raw_href: str) -> str:
    if not raw_href:
        return ""
    if "uddg=" in raw_href:
        parsed = urllib.parse.urlparse(raw_href)
        query = urllib.parse.parse_qs(parsed.query)
        if "uddg" in query and query["uddg"]:
            return urllib.parse.unquote(query["uddg"][0])
    if raw_href.startswith("//"):
        return "https:" + raw_href
    return raw_href


async def search_web(
    query: str,
    domain: str | None = None,
    signal: AbortSignal | None = None,
    client: httpx.AsyncClient | None = None,
) -> SpellResult:
    """Search the web using DuckDuckGo zero-config search without API keys.

    Args:
        query: Search query terms.
        domain: Optional domain filter (e.g. 'python.org').
        signal: Optional cancellation signal.
        client: Optional HTTP client for testing.

    Returns:
        SpellResult with formatted search results markdown.
    """
    if signal is not None and getattr(signal, "aborted", False):
        raise AbortError("Operation aborted")

    search_query = f"site:{domain} {query}" if domain else query
    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {"q": search_query}

    try:
        if client is not None:
            response = await client.post(url, data=data, headers=headers, timeout=15.0)
        else:
            async with httpx.AsyncClient(
                timeout=15.0, follow_redirects=True
            ) as local_client:
                response = await local_client.post(url, data=data, headers=headers)

        if response.status_code != 200:
            return SpellResult(
                spell_name="search_web",
                status=SpellStatus.ERROR,
                error_message=(
                    f"DuckDuckGo search failed with HTTP status {response.status_code}"
                ),
            )

        if signal is not None and getattr(signal, "aborted", False):
            raise AbortError("Operation aborted")

        parser = _DuckDuckGoHTMLParser()
        parser.feed(response.text)
        parser.close()

        results = [r for r in parser.results if r.get("title") and r.get("url")]
        if not results:
            return SpellResult(
                spell_name="search_web",
                status=SpellStatus.SUCCESS,
                content=f"No search results found for query: '{search_query}'.",
            )

        formatted: list[str] = [f"Search results for: **{search_query}**\n"]
        for idx, res in enumerate(results[:10], start=1):
            title = res["title"]
            target_url = res["url"]
            snippet = res.get("snippet", "")
            formatted.append(f"### {idx}. [{title}]({target_url})")
            if snippet:
                formatted.append(f"{snippet}\n")

        return SpellResult(
            spell_name="search_web",
            status=SpellStatus.SUCCESS,
            content="\n".join(formatted).strip(),
        )
    except AbortError:
        raise
    except Exception as exc:
        return SpellResult(
            spell_name="search_web",
            status=SpellStatus.ERROR,
            error_message=f"Search failed: {exc}",
        )
