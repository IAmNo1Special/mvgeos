"""Styles and design token definitions for MvgeOS Obsidian theme."""

from nicegui import ui

OBSIDIAN_THEME_CSS = """
:root {
    --bg-canvas: #181a20;
    --bg-surface: #13151b;
    --bg-card: #1e212b;
    --bg-card-hover: #262a36;
    --border-subtle: #2b2f3d;
    --border-active: #3b82f6;
    --text-primary: #e6edf3;
    --text-secondary: #8b949e;
    --text-muted: #64748b;
    --accent-blue: #3b82f6;
    --accent-violet: #7c3aed;
    --addition-green: #22c55e;
    --deletion-red: #ef4444;
}

*, *::before, *::after {
    box-sizing: border-box;
}

html, body {
    background-color: var(--bg-canvas) !important;
    color: var(--text-primary) !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont,
        'Segoe UI', Roboto, sans-serif !important;
    margin: 0;
    padding: 0;
    width: 100vw;
    height: 100vh;
    max-height: 100vh;
    overflow: hidden;
}

.q-layout, .q-page-container, .q-page {
    background-color: var(--bg-canvas) !important;
    height: 100vh !important;
    max-height: 100vh !important;
    overflow: hidden !important;
    padding: 0 !important;
    margin: 0 !important;
}

.bg-canvas {
    background-color: var(--bg-canvas) !important;
}

.bg-surface {
    background-color: var(--bg-surface) !important;
}

.bg-card {
    background-color: var(--bg-card) !important;
}

.border-subtle {
    border-color: var(--border-subtle) !important;
}

.text-primary {
    color: var(--text-primary) !important;
}

.text-secondary {
    color: var(--text-secondary) !important;
}

.text-muted {
    color: var(--text-muted) !important;
}

.font-mono {
    font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
}

/* Custom scrollbars */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}
::-webkit-scrollbar-track {
    background: transparent;
}
::-webkit-scrollbar-thumb {
    background: #2b2f3d;
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
    background: #3b4252;
}

/* MvgeOS buttons & controls */
.ag-btn {
    border: 1px solid var(--border-subtle);
    background-color: var(--bg-card);
    color: var(--text-primary);
    border-radius: 8px;
    transition: all 0.15s ease-in-out;
}

.ag-btn:hover {
    background-color: var(--bg-card-hover);
    border-color: #3b4252;
}

.ag-input-dock {
    background-color: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 14px;
    box-shadow: 0 12px 36px rgba(0, 0, 0, 0.45);
}

.ag-input-dock:focus-within {
    border-color: var(--border-active);
}

.ag-accordion {
    border-bottom: 1px solid var(--border-subtle);
}

.ag-accordion .q-expansion-item__container {
    background-color: transparent;
}

/* ── Markdown rendering (assistant responses, artifacts, contemplation) ──
   Polished prose system matching OpenCode's readability: generous
   vertical rhythm, hierarchical headings, pill inline code, elevated
   code blocks, and muted markers. Targets both .markdown-content (our
   explicit class) and .nicegui-markdown (NiceGUI default) for robustness. */
.markdown-content,
.nicegui-markdown {
    font-size: 13.8px;
    line-height: 1.7;
    color: var(--text-primary);
    word-wrap: break-word;
    overflow-wrap: anywhere;
}
.markdown-content > *:first-child,
.nicegui-markdown > *:first-child {
    margin-top: 0 !important;
}
.markdown-content > *:last-child,
.nicegui-markdown > *:last-child {
    margin-bottom: 0 !important;
}

/* Headings */
.markdown-content h1,
.nicegui-markdown h1 {
    font-size: 1.55em;
    font-weight: 700;
    line-height: 1.25;
    letter-spacing: -0.02em;
    color: #f8fafc;
    margin: 1.35em 0 0.55em;
    padding-bottom: 0.32em;
    border-bottom: 1px solid #232836;
}
.markdown-content h2,
.nicegui-markdown h2 {
    font-size: 1.32em;
    font-weight: 600;
    line-height: 1.3;
    letter-spacing: -0.015em;
    color: #f1f5f9;
    margin: 1.25em 0 0.5em;
}
.markdown-content h3,
.nicegui-markdown h3 {
    font-size: 1.12em;
    font-weight: 600;
    line-height: 1.35;
    color: #e2e8f0;
    margin: 1.1em 0 0.4em;
}
.markdown-content h4,
.nicegui-markdown h4 {
    font-size: 1em;
    font-weight: 600;
    color: #cbd5e1;
    margin: 1em 0 0.35em;
}
.markdown-content h5,
.nicegui-markdown h5,
.markdown-content h6,
.nicegui-markdown h6 {
    font-size: 0.92em;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin: 1em 0 0.3em;
}

/* Paragraphs & text */
.markdown-content p,
.nicegui-markdown p {
    margin: 0.8em 0;
    color: #d6dce6;
}
.markdown-content strong,
.nicegui-markdown strong {
    font-weight: 620;
    color: #f1f5f9;
}
.markdown-content em,
.nicegui-markdown em {
    font-style: italic;
    color: #cbd5e1;
}
.markdown-content a,
.nicegui-markdown a {
    color: #60a5fa;
    text-decoration: none;
    border-bottom: 1px solid transparent;
    transition: color 0.15s, border-color 0.15s;
}
.markdown-content a:hover,
.nicegui-markdown a:hover {
    color: #93c5fd;
    border-bottom-color: rgba(147, 197, 253, 0.5);
}

/* Lists */
.markdown-content ul,
.nicegui-markdown ul,
.markdown-content ol,
.nicegui-markdown ol {
    margin: 0.65em 0;
    padding-left: 1.55em;
}
.markdown-content ul,
.nicegui-markdown ul {
    list-style-type: disc;
}
.markdown-content ol,
.nicegui-markdown ol {
    list-style-type: decimal;
}
.markdown-content li,
.nicegui-markdown li {
    margin: 0.32em 0;
    padding-left: 0.15em;
    color: #d6dce6;
}
.markdown-content li::marker,
.nicegui-markdown li::marker {
    color: #5b6477;
}
.markdown-content li > p,
.nicegui-markdown li > p {
    margin: 0.35em 0;
}
.markdown-content ul ul,
.nicegui-markdown ul ul,
.markdown-content ol ol,
.nicegui-markdown ol ol,
.markdown-content ul ol,
.nicegui-markdown ul ol,
.markdown-content ol ul,
.nicegui-markdown ol ul {
    margin: 0.3em 0;
}

/* Inline code — pill */
.markdown-content code,
.nicegui-markdown code {
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 0.84em;
    font-weight: 500;
    background: #1e232e;
    border: 1px solid #2a303f;
    color: #e2e8f0;
    padding: 0.16em 0.38em;
    border-radius: 5px;
    white-space: break-spaces;
    word-break: break-word;
}

/* Code blocks — elevated surface */
.markdown-content pre,
.nicegui-markdown pre,
.markdown-content .codehilite,
.nicegui-markdown .codehilite {
    background: #0e1117 !important;
    border: 1px solid #252836 !important;
    border-radius: 8px !important;
    padding: 12px 14px !important;
    margin: 0.9em 0 !important;
    overflow-x: auto;
    line-height: 1.6;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.02);
}
.markdown-content pre code,
.nicegui-markdown pre code,
.markdown-content .codehilite code,
.nicegui-markdown .codehilite code,
.markdown-content .codehilite pre,
.nicegui-markdown .codehilite pre {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    border-radius: 0 !important;
    font-size: 12.5px !important;
    font-weight: 400 !important;
    color: #e6edf3 !important;
    white-space: pre !important;
    word-break: normal !important;
    display: block;
    box-shadow: none !important;
}
.markdown-content pre::-webkit-scrollbar,
.nicegui-markdown pre::-webkit-scrollbar {
    height: 6px;
}

/* Blockquote */
.markdown-content blockquote,
.nicegui-markdown blockquote {
    margin: 0.9em 0;
    padding: 0.55em 1em;
    border-left: 3px solid var(--accent-blue);
    background: rgba(59, 130, 246, 0.07);
    border-radius: 0 7px 7px 0;
    color: #94a3b8;
}
.markdown-content blockquote p,
.nicegui-markdown blockquote p {
    margin: 0.4em 0;
    color: #94a3b8;
}

/* Tables */
.markdown-content table,
.nicegui-markdown table {
    width: 100%;
    border-collapse: collapse;
    margin: 0.9em 0;
    font-size: 0.92em;
    border: 1px solid #2b2f3d;
    border-radius: 7px;
    overflow: hidden;
    display: table;
}
.markdown-content th,
.nicegui-markdown th {
    background: #1e212b;
    color: #e6edf3;
    font-weight: 600;
    text-align: left;
    padding: 8px 12px;
    border-bottom: 1px solid #2b2f3d;
    border-right: 1px solid #2b2f3d;
}
.markdown-content th:last-child,
.nicegui-markdown th:last-child {
    border-right: none;
}
.markdown-content td,
.nicegui-markdown td {
    padding: 7px 12px;
    border-bottom: 1px solid #1e212b;
    border-right: 1px solid #1e212b;
    color: #cbd5e1;
}
.markdown-content td:last-child,
.nicegui-markdown td:last-child {
    border-right: none;
}
.markdown-content tr:last-child td,
.nicegui-markdown tr:last-child td {
    border-bottom: none;
}
.markdown-content tr:hover td,
.nicegui-markdown tr:hover td {
    background: rgba(30, 33, 43, 0.45);
}

/* Horizontal rule */
.markdown-content hr,
.nicegui-markdown hr {
    border: none;
    height: 1px;
    background: #232836;
    margin: 1.25em 0;
}

/* Images */
.markdown-content img,
.nicegui-markdown img {
    max-width: 100%;
    border-radius: 7px;
    border: 1px solid #2b2f3d;
    margin: 0.85em 0;
}

/* Task lists & kbd */
.markdown-content li input[type="checkbox"],
.nicegui-markdown li input[type="checkbox"] {
    margin-right: 0.45em;
}
.markdown-content kbd,
.nicegui-markdown kbd {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78em;
    background: #1a1d26;
    border: 1px solid #2b2f3d;
    border-bottom-width: 2px;
    padding: 0.15em 0.4em;
    border-radius: 4px;
    color: #cbd5e1;
}

/* Contemplation variant — muted italic thought content */
.markdown-contemplation,
.markdown-contemplation p,
.markdown-contemplation li,
.markdown-contemplation strong,
.markdown-contemplation em {
    color: #94a3b8 !important;
}
.markdown-contemplation {
    font-style: italic;
    font-size: 13px;
    line-height: 1.65;
}
.markdown-contemplation code {
    font-style: normal;
    color: #a6b0c0 !important;
    background: rgba(30, 35, 46, 0.9) !important;
    border-color: rgba(42, 48, 63, 0.7) !important;
}

/* Terminal output variant — dense mono on deep backdrop */
.markdown-terminal pre,
.markdown-terminal .codehilite {
    background: #08090c !important;
    border-color: #1b1e27 !important;
    padding: 8px 10px !important;
    margin: 0 !important;
    box-shadow: none !important;
}
.markdown-terminal pre code,
.markdown-terminal .codehilite code,
.markdown-terminal .codehilite pre {
    color: #a6accd !important;
    font-size: 11.5px !important;
    line-height: 1.55 !important;
}
"""

GOOGLE_FONTS_HTML = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link href="https://fonts.googleapis.com/css2?'
    "family=Inter:wght@300;400;500;600;700&"
    'family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">'
)


def inject_theme() -> None:
    """Inject custom obsidian/slate theme stylesheet into NiceGUI page."""
    ui.add_head_html(GOOGLE_FONTS_HTML)
    ui.add_css(OBSIDIAN_THEME_CSS)
    ui.dark_mode().enable()
