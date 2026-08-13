"""Styles and design token definitions for Antigravity Obsidian theme."""

from nicegui import ui

OBSIDIAN_THEME_CSS = """
:root {
    --bg-obsidian: #0e1117;
    --bg-surface: #13151b;
    --bg-card: #1b1e27;
    --bg-card-hover: #222632;
    --border-subtle: #252936;
    --border-active: #3b82f6;
    --text-primary: #e6edf3;
    --text-secondary: #8b949e;
    --text-muted: #64748b;
    --accent-blue: #3b82f6;
    --accent-violet: #7c3aed;
    --addition-green: #22c55e;
    --deletion-red: #ef4444;
}

body {
    background-color: var(--bg-obsidian) !important;
    color: var(--text-primary) !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont,
        'Segoe UI', Roboto, sans-serif !important;
    margin: 0;
    padding: 0;
    overflow: hidden;
}

.q-layout, .q-page-container {
    background-color: var(--bg-obsidian) !important;
}

.bg-obsidian {
    background-color: var(--bg-obsidian) !important;
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
    background: #252936;
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
    background: #3b4252;
}

/* Antigravity buttons & controls */
.ag-btn {
    border: 1px solid var(--border-subtle);
    background-color: var(--bg-card);
    color: var(--text-primary);
    border-radius: 6px;
    transition: all 0.15s ease-in-out;
}

.ag-btn:hover {
    background-color: var(--bg-card-hover);
    border-color: #3b4252;
}

.ag-input-dock {
    background-color: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 12px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
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
