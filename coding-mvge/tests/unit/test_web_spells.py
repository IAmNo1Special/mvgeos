import httpx
import pytest
from mvgeos_agent.types import AbortController, AbortError, SpellStatus

from coding_mvge.spells.read_url import read_url
from coding_mvge.spells.search_web import search_web


@pytest.mark.asyncio
async def test_search_web_success() -> None:
    ddg_html = """
    <html><body>
    <div class="result results_links results_links_deep web-result">
      <a class="result__a"
         href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.python.org%2F3%2F&rut=1">
         Python Documentation</a>
      <a class="result__snippet">Official documentation for Python 3.</a>
    </div>
    <div class="result results_links results_links_deep web-result">
      <a class="result__a" href="https://pypi.org/">PyPI · The Python Package Index</a>
      <a class="result__snippet">Find, install and publish Python packages.</a>
    </div>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert "html.duckduckgo.com" in str(request.url)
        return httpx.Response(200, text=ddg_html)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await search_web("python docs", client=client)
    assert result.status == SpellStatus.SUCCESS
    assert result.content is not None
    assert "[Python Documentation](https://docs.python.org/3/)" in result.content
    assert "Official documentation for Python 3." in result.content
    assert "[PyPI · The Python Package Index](https://pypi.org/)" in result.content


@pytest.mark.asyncio
async def test_search_web_with_domain() -> None:
    captured_body = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_body
        captured_body = request.content.decode()
        return httpx.Response(200, text="<html><body></body></html>")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await search_web("asyncio", domain="python.org", client=client)
    assert result.status == SpellStatus.SUCCESS
    assert (
        "q=site%3Apython.org+asyncio" in captured_body
        or "site:python.org asyncio" in captured_body
    )


@pytest.mark.asyncio
async def test_search_web_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await search_web("test", client=client)
    assert result.status == SpellStatus.ERROR
    assert "503" in (result.error_message or "")


@pytest.mark.asyncio
async def test_search_web_aborted() -> None:
    controller = AbortController()
    controller.abort()
    with pytest.raises(AbortError):
        await search_web("test", signal=controller.signal)


@pytest.mark.asyncio
async def test_read_url_html_conversion() -> None:
    html_content = """
    <!DOCTYPE html>
    <html>
      <head><title>MvgeOS Guide</title></head>
      <body>
        <nav><a href="/home">Home</a></nav>
        <script>console.log("bad");</script>
        <style>.bad { color: red; }</style>
        <h1>Welcome to MvgeOS</h1>
        <p>This is a paragraph with a
           <a href="https://mvgeos.dev/docs">link to docs</a>.</p>
        <ul>
          <li>First item</li>
          <li>Second item</li>
        </ul>
      </body>
    </html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=html_content,
            headers={"Content-Type": "text/html; charset=utf-8"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await read_url("https://mvgeos.dev/guide", client=client)
    assert result.status == SpellStatus.SUCCESS
    content = result.content or ""
    assert "# MvgeOS Guide" in content
    assert "# Welcome to MvgeOS" in content
    assert "[link to docs](https://mvgeos.dev/docs)" in content
    assert "- First item" in content
    assert "console.log" not in content
    assert ".bad {" not in content


@pytest.mark.asyncio
async def test_read_url_rejects_binary() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"%PDF-1.4...",
            headers={"Content-Type": "application/pdf"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await read_url("https://example.com/doc.pdf", client=client)
    assert result.status == SpellStatus.ERROR
    assert "Binary content type" in (result.error_message or "")


@pytest.mark.asyncio
async def test_read_url_truncation() -> None:
    long_text = "A" * 500

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=long_text,
            headers={"Content-Type": "text/plain"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await read_url(
        "https://example.com/long.txt", max_length=100, client=client
    )
    assert result.status == SpellStatus.SUCCESS
    content = result.content or ""
    assert len(content) < 200
    assert "truncated at 100 characters" in content


@pytest.mark.asyncio
async def test_read_url_invalid_scheme() -> None:
    result = await read_url("file:///etc/passwd")
    assert result.status == SpellStatus.ERROR
    assert "Invalid URL" in (result.error_message or "")
