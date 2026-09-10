"""Styles and design token definitions for the MvgeOS Void theme.

Dark, minimal, and quietly luminous: near-black violet surfaces with a
violet primary and pink secondary, matching the curvy composer.
"""

from nicegui import ui

VOID_THEME_CSS = """
:root {
    --bg-canvas: #000000;
    --bg-surface: #08080a;
    --bg-card: #0e0e12;
    --bg-card-hover: #16161d;
    --border-subtle: #292335;
    --border-active: #7b6cf6;
    --text-primary: #eceaf4;
    --text-secondary: #9c94b3;
    --text-muted: #6e6584;
    --accent-primary: #7b6cf6;
    --accent-pink: #cf30aa;
    --addition-green: #22c55e;
    --deletion-red: #ef4444;
}

*, *::before, *::after {
    box-sizing: border-box;
}

::selection {
    background: rgba(123, 108, 246, 0.4);
    color: #f4f2fa;
}

:focus-visible {
    outline: 1px solid var(--border-active);
    outline-offset: 2px;
    box-shadow: 0 0 12px rgba(123, 108, 246, 0.35);
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
    background: #292335;
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
    background: #7b6cf6;
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
    border-color: rgba(123, 108, 246, 0.6);
    box-shadow: 0 0 12px rgba(123, 108, 246, 0.22);
}

.ag-input-dock {
    background-color: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 14px;
    box-shadow: 0 12px 36px rgba(0, 0, 0, 0.45);
}

.ag-input-dock:focus-within {
    border-color: var(--border-active);
    box-shadow:
        0 0 0 1px rgba(123, 108, 246, 0.35),
        0 12px 36px rgba(0, 0, 0, 0.45);
}

/* Primary CTA buttons: glassy dark pill with a violet under-glow ring.
   Adapted from Uiverse.io "young-newt-20" by dexter-st (MIT License):
   hue shifted 210deg -> 258deg, base matched to space-black surfaces,
   per-letter/svg animations omitted (NiceGUI buttons carry plain text). */
.mvge-glow-btn {
    --glow-btn-radius: 24px;
    --glow-btn-pad: 4px;
    --glow-btn-speed: 0.4s;
    --glow-btn-base: #0d0d13;
    --highlight-color-hue: 258deg;

    position: relative;
    isolation: isolate;
    user-select: none;
    cursor: pointer;
    background-color: var(--glow-btn-base) !important;
    border: solid 1px rgba(255, 255, 255, 0.13) !important;
    border-radius: var(--glow-btn-radius) !important;
    box-shadow:
        inset 0px 1px 1px rgba(255, 255, 255, 0.2),
        inset 0px 2px 2px rgba(255, 255, 255, 0.15),
        inset 0px 4px 4px rgba(255, 255, 255, 0.1),
        inset 0px 8px 8px rgba(255, 255, 255, 0.05),
        inset 0px 16px 16px rgba(255, 255, 255, 0.05),
        0px -1px 1px rgba(0, 0, 0, 0.02),
        0px -2px 2px rgba(0, 0, 0, 0.03),
        0px -4px 4px rgba(0, 0, 0, 0.05),
        0px -8px 8px rgba(0, 0, 0, 0.06),
        0px -16px 16px rgba(0, 0, 0, 0.08) !important;
    transition:
        box-shadow var(--glow-btn-speed),
        border var(--glow-btn-speed),
        background-color var(--glow-btn-speed) !important;
}
.mvge-glow-btn::before {
    content: "";
    position: absolute;
    top: calc(0px - var(--glow-btn-pad));
    left: calc(0px - var(--glow-btn-pad));
    width: calc(100% + var(--glow-btn-pad) * 2);
    height: calc(100% + var(--glow-btn-pad) * 2);
    border-radius: calc(var(--glow-btn-radius) + var(--glow-btn-pad));
    pointer-events: none;
    background-image: linear-gradient(0deg, #0004, #000a);
    z-index: -1;
    transition:
        box-shadow var(--glow-btn-speed),
        filter var(--glow-btn-speed);
    box-shadow:
        0 -8px 8px -6px #0000 inset,
        0 -16px 16px -8px #00000000 inset,
        1px 1px 1px #fff2,
        2px 2px 2px #fff1,
        -1px -1px 1px #0002,
        -2px -2px 2px #0001;
}
.mvge-glow-btn::after {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    border-radius: inherit;
    pointer-events: none;
    background-image: linear-gradient(0deg, #fff,
        hsl(var(--highlight-color-hue), 100%, 70%),
        hsla(var(--highlight-color-hue), 100%, 70%, 50%), 8%,
        transparent);
    background-position: 0 0;
    opacity: 0;
    transition:
        opacity var(--glow-btn-speed),
        filter var(--glow-btn-speed);
}
.mvge-glow-btn:hover {
    border: solid 1px hsla(var(--highlight-color-hue), 100%, 80%,
        40%) !important;
    text-shadow: 0 0 8px rgba(157, 143, 255, 0.8);
}
.mvge-glow-btn:hover::before {
    box-shadow:
        0 -8px 8px -6px #fffa inset,
        0 -16px 16px -8px hsla(var(--highlight-color-hue), 100%, 70%,
            30%) inset,
        1px 1px 1px #fff2,
        2px 2px 2px #fff1,
        -1px -1px 1px #0002,
        -2px -2px 2px #0001;
}
.mvge-glow-btn:hover::after,
.mvge-glow-btn:focus-visible::after {
    opacity: 1;
    -webkit-mask-image: linear-gradient(0deg, #fff, transparent);
    mask-image: linear-gradient(0deg, #fff, transparent);
}
.mvge-glow-btn:active {
    border: solid 1px rgba(207, 48, 170, 0.7) !important;
    background-color: rgba(207, 48, 170, 0.16) !important;
}
.mvge-glow-btn:active::before {
    box-shadow:
        0 -8px 12px -6px #fffa inset,
        0 -16px 16px -8px hsla(var(--highlight-color-hue), 100%, 70%,
            80%) inset,
        1px 1px 1px #fff4,
        2px 2px 2px #fff2,
        -1px -1px 1px #0002,
        -2px -2px 2px #0001;
}
.mvge-glow-btn:active::after {
    opacity: 1;
    -webkit-mask-image: linear-gradient(0deg, #fff, transparent);
    mask-image: linear-gradient(0deg, #fff, transparent);
    filter: brightness(200%);
}
.mvge-glow-btn:focus-visible {
    outline: 1px solid #9d8fff !important;
    outline-offset: 3px;
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
    color: #f4f2fa;
    margin: 1.35em 0 0.55em;
    padding-bottom: 0.32em;
    border-bottom: 1px solid #211c34;
}
.markdown-content h2,
.nicegui-markdown h2 {
    font-size: 1.32em;
    font-weight: 600;
    line-height: 1.3;
    letter-spacing: -0.015em;
    color: #eceaf4;
    margin: 1.25em 0 0.5em;
}
.markdown-content h3,
.nicegui-markdown h3 {
    font-size: 1.12em;
    font-weight: 600;
    line-height: 1.35;
    color: #ddd9ea;
    margin: 1.1em 0 0.4em;
}
.markdown-content h4,
.nicegui-markdown h4 {
    font-size: 1em;
    font-weight: 600;
    color: #bdb8d2;
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
    color: #c9c4da;
}
.markdown-content strong,
.nicegui-markdown strong {
    font-weight: 620;
    color: #eceaf4;
}
.markdown-content em,
.nicegui-markdown em {
    font-style: italic;
    color: #bdb8d2;
}
.markdown-content a,
.nicegui-markdown a {
    color: #9d8fff;
    text-decoration: none;
    border-bottom: 1px solid transparent;
    transition: color 0.15s, border-color 0.15s;
}
.markdown-content a:hover,
.nicegui-markdown a:hover {
    color: #c9bcff;
    border-bottom-color: rgba(157, 143, 255, 0.5);
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
    color: #c9c4da;
}
.markdown-content li::marker,
.nicegui-markdown li::marker {
    color: #5f5778;
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
    background: #101015;
    border: 1px solid #23232e;
    color: #ddd9ea;
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
    background: #050507 !important;
    border: 1px solid #241f38 !important;
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
    color: #eceaf4 !important;
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
    border-left: 3px solid var(--accent-primary);
    background: rgba(123, 108, 246, 0.07);
    border-radius: 0 7px 7px 0;
    color: #8f87a8;
}
.markdown-content blockquote p,
.nicegui-markdown blockquote p {
    margin: 0.4em 0;
    color: #8f87a8;
}

/* Tables */
.markdown-content table,
.nicegui-markdown table {
    width: 100%;
    border-collapse: collapse;
    margin: 0.9em 0;
    font-size: 0.92em;
    border: 1px solid #292335;
    border-radius: 7px;
    overflow: hidden;
    display: table;
}
.markdown-content th,
.nicegui-markdown th {
    background: #0e0e12;
    color: #eceaf4;
    font-weight: 600;
    text-align: left;
    padding: 8px 12px;
    border-bottom: 1px solid #292335;
    border-right: 1px solid #292335;
}
.markdown-content th:last-child,
.nicegui-markdown th:last-child {
    border-right: none;
}
.markdown-content td,
.nicegui-markdown td {
    padding: 7px 12px;
    border-bottom: 1px solid #0e0e12;
    border-right: 1px solid #0e0e12;
    color: #bdb8d2;
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
    background: rgba(36, 31, 56, 0.45);
}

/* Horizontal rule */
.markdown-content hr,
.nicegui-markdown hr {
    border: none;
    height: 1px;
    background: linear-gradient(90deg, transparent, #292335, transparent);
    margin: 1.25em 0;
}

/* Images */
.markdown-content img,
.nicegui-markdown img {
    max-width: 100%;
    border-radius: 7px;
    border: 1px solid #292335;
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
    background: #101014;
    border: 1px solid #292335;
    border-bottom-width: 2px;
    padding: 0.15em 0.4em;
    border-radius: 4px;
    color: #bdb8d2;
}

/* Contemplation variant — muted italic thought content */
.markdown-contemplation,
.markdown-contemplation p,
.markdown-contemplation li,
.markdown-contemplation strong,
.markdown-contemplation em {
    color: #8f87a8 !important;
}
.markdown-contemplation {
    font-style: italic;
    font-size: 13px;
    line-height: 1.65;
}
.markdown-contemplation code {
    font-style: normal;
    color: #a79fc4 !important;
    background: rgba(16, 16, 21, 0.9) !important;
    border-color: rgba(35, 35, 46, 0.7) !important;
}

/* Terminal output variant — dense mono on deep backdrop */
.markdown-terminal pre,
.markdown-terminal .codehilite {
    background: #000000 !important;
    border-color: #0e0e14 !important;
    padding: 8px 10px !important;
    margin: 0 !important;
    box-shadow: none !important;
}
.markdown-terminal pre code,
.markdown-terminal .codehilite code,
.markdown-terminal .codehilite pre {
    color: #a49cc8 !important;
    font-size: 11.5px !important;
    line-height: 1.55 !important;
}

/* Sidebar collapsible transition */
.sidebar-container {
    transition: width 0.3s ease-in-out !important;
}

.sidebar-label {
    transition: opacity 0.3s ease-in-out, transform 0.3s ease-in-out !important;
    transform-origin: left center;
    white-space: nowrap;
    overflow: hidden;
    display: inline-block;
    min-width: 0;
}

.sidebar-label.collapsed {
    opacity: 0 !important;
    transform: translateX(-10px) !important;
    width: 0 !important;
    min-width: 0 !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
    margin-left: 0 !important;
    margin-right: 0 !important;
}

.sidebar-label.expanded {
    opacity: 1 !important;
    transform: translateX(0) !important;
    width: auto !important;
    min-width: auto !important;
}

/* Active sidebar nav link */
.nav-link-active {
    background: var(--bg-card) !important;
    border-radius: 2rem !important;
    position: relative !important;
}
.nav-link-active::before {
    content: '' !important;
    position: absolute !important;
    left: 12px !important;
    top: 50% !important;
    transform: translateY(-50%) !important;
    width: 3px !important;
    height: 60% !important;
    border-radius: 3px !important;
    background: linear-gradient(180deg, #9d8fff 0%, #7b6cf6 55%,
        #cf30aa 130%) !important;
    box-shadow: 0 0 8px rgba(123, 108, 246, 0.7) !important;
}
.nav-icon-active {
    color: #9d8fff !important;
    filter: drop-shadow(0 0 6px rgba(123, 108, 246, 0.6));
}

/* Sidebar hint tooltip */
.sidebar-hint {
    font-size: 0.8rem !important;
    padding: 6px 12px !important;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.16) !important;
}

/* Quasar polish: hairline inputs, void tooltips. */
.q-field--outlined .q-field__control::before {
    border-color: var(--border-subtle) !important;
}
.q-field--outlined.q-field--focused .q-field__control::after {
    border-color: var(--border-active) !important;
}
.q-tooltip {
    background: #16161d !important;
    border: 1px solid var(--border-subtle) !important;
    color: var(--text-primary) !important;
    font-size: 11px !important;
}

/* Sidebar collapse button rotation */
.collapse-btn-icon {
    transition: transform 0.3s ease-in-out !important;
}
.collapse-btn-icon.collapsed {
    transform: rotate(180deg) !important;
}
"""

GOOGLE_FONTS_HTML = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link href="https://fonts.googleapis.com/css2?'
    "family=Inter:wght@300;400;500;600;700&"
    'family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">'
)

# ── Curvy composer (adapted from Uiverse.io "curvy-earwig-22" by
# Lakshay-art, MIT License). Changes vs upstream: fluid full-width layout
# (no fixed 301px), no search icon, filter slot reused as the send/stop
# button, glow blur/padding calibrated so the halo fringe decays before
# the chat column's overflow:hidden walls, Quasar/NiceGUI textarea
# overrides, `mvge-` namespacing.
CURVY_COMPOSER_CSS = """
.mvge-poda {
    display: flex;
    align-items: stretch;
    justify-content: center;
    width: 100%;
    position: relative;
}
.mvge-white,
.mvge-border,
.mvge-dark-border-bg,
.mvge-glow {
    height: 100%;
    width: 100%;
    position: absolute;
    inset: 0;
    overflow: hidden;
    z-index: 0;
    border-radius: 12px;
    filter: blur(3px);
    pointer-events: none;
}
.mvge-main {
    position: relative;
    z-index: 1;
    width: 100%;
    background-color: #010201;
    border-radius: 10px;
    padding: 10px 10px 6px 10px;
}
.mvge-main .q-field__control,
.mvge-main .q-field__native,
.mvge-main .q-textarea .q-field__control {
    background: transparent !important;
}
.mvge-main .q-field__control::before,
.mvge-main .q-field__control::after {
    display: none !important;
}
.mvge-main textarea.q-field__native,
.mvge-main textarea {
    background-color: #010201 !important;
    border: none !important;
    color: white !important;
    padding-left: 16px !important;
    padding-right: 62px !important;
    padding-top: 6px !important;
    padding-bottom: 6px !important;
    font-size: 15px !important;
    line-height: 1.55 !important;
    min-height: 48px !important;
    resize: none !important;
}
.mvge-main textarea.q-field__native::placeholder,
.mvge-main textarea::placeholder {
    color: #c0b9c0 !important;
    opacity: 1 !important;
}
.mvge-main textarea.q-field__native:focus,
.mvge-main textarea:focus {
    outline: none !important;
}
.mvge-input-zone {
    position: relative;
    width: 100%;
}
.mvge-main:focus-within > .mvge-input-zone > .mvge-input-mask {
    display: none;
}
.mvge-input-mask {
    pointer-events: none;
    width: 60px;
    height: 20px;
    position: absolute;
    background: linear-gradient(90deg, transparent, #010201);
    top: 16px;
    right: 62px;
    z-index: 1;
}
.mvge-pink-mask {
    pointer-events: none;
    width: 30px;
    height: 20px;
    position: absolute;
    background: #cf30aa;
    top: 8px;
    left: 5px;
    filter: blur(20px);
    opacity: 0.8;
    transition: all 2s;
    z-index: 1;
}
.mvge-main:hover > .mvge-input-zone > .mvge-pink-mask,
.mvge-poda:hover .mvge-pink-mask {
    opacity: 0;
}
.mvge-white {
    border-radius: 10px;
    filter: blur(2px);
}
.mvge-white::before {
    content: "";
    z-index: 0;
    text-align: center;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%) rotate(83deg);
    position: absolute;
    width: 600px;
    height: 600px;
    background-repeat: no-repeat;
    background-position: 0 0;
    filter: brightness(1.4);
    background-image: conic-gradient(
        rgba(0, 0, 0, 0) 0%,
        #a099d8,
        rgba(0, 0, 0, 0) 8%,
        rgba(0, 0, 0, 0) 50%,
        #dfa2da,
        rgba(0, 0, 0, 0) 58%
    );
    transition: all 2s;
}
.mvge-border {
    border-radius: 11px;
    filter: blur(0.5px);
}
.mvge-border::before {
    content: "";
    z-index: 0;
    text-align: center;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%) rotate(70deg);
    position: absolute;
    width: 600px;
    height: 600px;
    filter: brightness(1.3);
    background-repeat: no-repeat;
    background-position: 0 0;
    background-image: conic-gradient(
        #1c191c,
        #402fb5 5%,
        #1c191c 14%,
        #1c191c 50%,
        #cf30aa 60%,
        #1c191c 64%
    );
    transition: all 2s;
}
.mvge-dark-border-bg::before {
    content: "";
    z-index: 0;
    text-align: center;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%) rotate(82deg);
    position: absolute;
    width: 600px;
    height: 600px;
    background-repeat: no-repeat;
    background-position: 0 0;
    background-image: conic-gradient(
        rgba(0, 0, 0, 0),
        #18116a,
        rgba(0, 0, 0, 0) 10%,
        rgba(0, 0, 0, 0) 50%,
        #6e1b60,
        rgba(0, 0, 0, 0) 60%
    );
    transition: all 2s;
}
.mvge-poda:hover > .mvge-dark-border-bg::before {
    transform: translate(-50%, -50%) rotate(262deg);
}
.mvge-poda:hover > .mvge-glow::before {
    transform: translate(-50%, -50%) rotate(240deg);
}
.mvge-poda:hover > .mvge-white::before {
    transform: translate(-50%, -50%) rotate(263deg);
}
.mvge-poda:hover > .mvge-border::before {
    transform: translate(-50%, -50%) rotate(250deg);
}
.mvge-poda:focus-within > .mvge-dark-border-bg::before {
    transform: translate(-50%, -50%) rotate(442deg);
    transition: all 4s;
}
.mvge-poda:focus-within > .mvge-glow::before {
    transform: translate(-50%, -50%) rotate(420deg);
    transition: all 4s;
}
.mvge-poda:focus-within > .mvge-white::before {
    transform: translate(-50%, -50%) rotate(443deg);
    transition: all 4s;
}
.mvge-poda:focus-within > .mvge-border::before {
    transform: translate(-50%, -50%) rotate(430deg);
    transition: all 4s;
}
.mvge-glow {
    overflow: hidden;
    /* Calibrated pair: 12px blur + >=30px wrapper padding on the clipped
       sides so the fringe decays to ~0 before the chat column's
       overflow:hidden wall. Clipping a live fringe reads as a hard edge
       (measured ΔB≈10 with 16px blur / 24px padding). */
    filter: blur(12px);
    opacity: 0.4;
}
.mvge-glow::before {
    content: "";
    z-index: 0;
    text-align: center;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%) rotate(60deg);
    position: absolute;
    width: 999px;
    height: 999px;
    background-repeat: no-repeat;
    background-position: 0 0;
    background-image: conic-gradient(
        #000,
        #402fb5 5%,
        #000 38%,
        #000 50%,
        #cf30aa 60%,
        #000 87%
    );
    transition: all 2s;
}
.mvge-send-border {
    height: 42px;
    width: 40px;
    position: absolute;
    overflow: hidden;
    top: 5px;
    right: 5px;
    border-radius: 10px;
    z-index: 1;
    pointer-events: none;
}
.mvge-send-border::before {
    content: "";
    text-align: center;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%) rotate(90deg);
    position: absolute;
    width: 600px;
    height: 600px;
    background-repeat: no-repeat;
    background-position: 0 0;
    filter: brightness(1.35);
    background-image: conic-gradient(
        rgba(0, 0, 0, 0),
        #3d3a4f,
        rgba(0, 0, 0, 0) 50%,
        rgba(0, 0, 0, 0) 50%,
        #3d3a4f,
        rgba(0, 0, 0, 0) 100%
    );
    animation: mvge-rotate 4s linear infinite;
}
@keyframes mvge-rotate {
    100% {
        transform: translate(-50%, -50%) rotate(450deg);
    }
}
.mvge-send-btn {
    position: absolute !important;
    top: 6px !important;
    right: 6px !important;
    width: 38px !important;
    height: 40px !important;
    min-height: 40px !important;
    min-width: 38px !important;
    padding: 0 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    z-index: 2 !important;
    border-radius: 10px !important;
    background: linear-gradient(180deg, #161329, black, #1d1b4b) !important;
    border: 1px solid transparent !important;
    color: #d6d6e6 !important;
    cursor: pointer !important;
    isolation: isolate;
    overflow: hidden;
}
.mvge-send-btn:hover {
    filter: brightness(1.5);
}
.mvge-send-btn .q-icon {
    font-size: 20px !important;
}
.mvge-send-btn.mvge-stop {
    background: linear-gradient(180deg, #3a1118, #7f1d1d, #1a0a0d) !important;
    color: #fecaca !important;
}
.mvge-composer-toolbar .q-field__control {
    background: transparent !important;
}
"""


def inject_theme() -> None:
    """Inject the Void theme stylesheet and Quasar palette into NiceGUI."""
    ui.add_head_html(GOOGLE_FONTS_HTML)
    ui.add_css(VOID_THEME_CSS)
    ui.add_css(CURVY_COMPOSER_CSS)
    ui.colors(primary="#7b6cf6")
    ui.dark_mode().enable()
