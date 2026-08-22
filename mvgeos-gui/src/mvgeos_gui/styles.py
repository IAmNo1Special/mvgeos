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
