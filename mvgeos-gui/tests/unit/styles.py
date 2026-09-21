"""Unit tests for the styles and design tokens."""

from __future__ import annotations

import re
from pathlib import Path
from typing import cast

import pytest
from nicegui import ui
from nicegui.elements.dark_mode import DarkMode
from nicegui.testing import User

from mvgeos_gui.styles import (
    CURVY_COMPOSER_CSS,
    GOOGLE_FONTS_HTML,
    LIGHT_THEME_CSS,
    VOID_THEME_CSS,
    apply_theme,
    inject_theme,
    theme_dataset_script,
)


def test_theme_css_and_fonts_constants() -> None:
    """Validate CSS and Google Fonts strings are non-empty and well-formed."""
    assert "--bg-canvas" in VOID_THEME_CSS
    assert "fonts.googleapis.com" in GOOGLE_FONTS_HTML


def test_void_theme_palette() -> None:
    """Void theme matches the curvy composer: near-black, violet, pink."""
    assert "--bg-canvas: #000000" in VOID_THEME_CSS
    assert "--bg-surface: #08080a" in VOID_THEME_CSS
    assert "--accent-primary: #7b6cf6" in VOID_THEME_CSS
    assert "--accent-pink: #cf30aa" in VOID_THEME_CSS
    assert "#3b82f6" not in VOID_THEME_CSS
    assert "#181a20" not in VOID_THEME_CSS


def test_curvy_composer_css_omits_search_icon() -> None:
    """Curvy composer adapts uiverse input without search icon."""
    assert ".mvge-poda" in CURVY_COMPOSER_CSS
    assert ".mvge-main" in CURVY_COMPOSER_CSS
    assert ".mvge-send-btn" in CURVY_COMPOSER_CSS
    assert ".mvge-send-border" in CURVY_COMPOSER_CSS
    assert "search-icon" not in CURVY_COMPOSER_CSS


def test_curvy_glow_blur_fits_wrapper_padding() -> None:
    """Glow blur fits wrapper padding."""
    assert "filter: blur(12px);" in CURVY_COMPOSER_CSS
    assert "blur(30px)" not in CURVY_COMPOSER_CSS


def test_composer_input_has_no_own_focus_glow() -> None:
    """Only the composer container glows on focus, not the textarea."""
    assert ".mvge-main textarea:focus-visible" in CURVY_COMPOSER_CSS
    assert "box-shadow: none !important;" in CURVY_COMPOSER_CSS


def test_glow_buttons_use_young_newt_glass() -> None:
    """Primary CTAs use the young-newt glass treatment, not a flat fill."""
    assert "--highlight-color-hue: 258deg" in VOID_THEME_CSS
    assert "inset 0px 1px 1px rgba(255, 255, 255, 0.2)" in VOID_THEME_CSS
    assert "#5b3df0" not in VOID_THEME_CSS


@pytest.mark.asyncio
async def test_inject_theme(user: User) -> None:
    """inject_theme should add head HTML and CSS without error."""

    @ui.page("/test_styles")
    def page() -> None:
        inject_theme()
        ui.label("Theme Injected")

    await user.open("/test_styles")
    await user.should_see("Theme Injected")


def _rule_block(css: str, selector: str) -> str:
    """Return the declaration block for a CSS selector, asserting presence."""
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert match is not None, f"missing CSS rule for {selector}"
    return match.group(1)


def test_composer_upload_chrome_collapsed() -> None:
    """Attach control collapses to an icon button, not the uploader chrome.

    Regression: the composer showed Quasar's gray uploader header
    ("0.0B / 0.00%") and file list in the toolbar. The theme hides the
    title/subtitle text and the list so only the "+" picker button remains.
    The picker button nests inside ``.q-uploader__header-content``, so that
    element itself must stay visible.
    """
    list_rules = _rule_block(CURVY_COMPOSER_CSS, ".mvge-upload-btn .q-uploader__list")
    assert "display" in list_rules
    assert "none" in list_rules
    title_rules = _rule_block(CURVY_COMPOSER_CSS, ".mvge-upload-btn .q-uploader__title")
    assert "display" in title_rules
    assert "none" in title_rules
    subtitle_rules = _rule_block(
        CURVY_COMPOSER_CSS, ".mvge-upload-btn .q-uploader__subtitle"
    )
    assert "display" in subtitle_rules
    assert "none" in subtitle_rules
    assert ".mvge-upload-btn .q-uploader__header-content" not in CURVY_COMPOSER_CSS


def test_composer_upload_picker_button_stays_visible() -> None:
    """The attach picker button must not be hidden along with the chrome.

    Regression: the theme hid ``.q-uploader__header-content`` wholesale, but
    Quasar nests the file-picker button inside that element, so the attach
    control rendered as an invisible zero-size box in the toolbar. Only the
    title/subtitle text and the file list may be hidden.
    """
    assert ".mvge-upload-btn .q-uploader__header-content" not in CURVY_COMPOSER_CSS
    title_rules = _rule_block(CURVY_COMPOSER_CSS, ".mvge-upload-btn .q-uploader__title")
    assert "none" in title_rules
    subtitle_rules = _rule_block(
        CURVY_COMPOSER_CSS, ".mvge-upload-btn .q-uploader__subtitle"
    )
    assert "none" in subtitle_rules
    list_rules = _rule_block(CURVY_COMPOSER_CSS, ".mvge-upload-btn .q-uploader__list")
    assert "none" in list_rules


def test_composer_upload_picker_icon_matches_toolbar() -> None:
    """Attach picker icon uses the toolbar's muted violet tone."""
    btn_rules = _rule_block(CURVY_COMPOSER_CSS, ".mvge-upload-btn .q-btn")
    assert "var(--text-secondary)" in btn_rules


def test_send_button_vertically_centered_in_input_zone() -> None:
    """Send/stop button sits center-right of the input zone, not top-right.

    Regression: the button was pinned ``top: 6px`` in the input zone, so it
    rode high while the textarea autogrew. It must be vertically centered so
    it tracks the zone's height.
    """
    btn_rules = _rule_block(CURVY_COMPOSER_CSS, ".mvge-send-btn")
    assert "top: 50%" in btn_rules
    assert "translateY(-50%)" in btn_rules
    assert "top: 6px" not in btn_rules


def test_send_border_tracks_send_button() -> None:
    """Decorative send-border glow stays glued to the send button.

    Regression guard: ``.mvge-send-border`` is the rotating-border wrapper
    behind ``.mvge-send-btn``; parked at ``top: 5px`` it would detach from
    the centered button.
    """
    border_rules = _rule_block(CURVY_COMPOSER_CSS, ".mvge-send-border")
    assert "top: 50%" in border_rules
    assert "translateY(-50%)" in border_rules


def test_send_input_mask_tracks_send_button() -> None:
    """Text fade mask follows the send button to center-right.

    Regression guard: ``.mvge-input-mask`` fades prompt text sliding under
    the send button; parked at ``top: 16px`` it would leave a stray fade bar
    at the top and let text bleed behind the centered button.
    """
    mask_rules = _rule_block(CURVY_COMPOSER_CSS, "\n.mvge-input-mask")
    assert "top: 50%" in mask_rules
    assert "translateY(-50%)" in mask_rules


def test_composer_upload_button_centered_with_model_picker() -> None:
    """Attach control is vertically centered with the model picker.

    The toolbar row already centers its children via ``items-center``; this
    pins the alignment on the uploader itself so the "+" stays on the
    picker's axis even if the toolbar row classes change later.
    """
    btn_rules = _rule_block(CURVY_COMPOSER_CSS, ".mvge-upload-btn")
    assert "align-self: center" in btn_rules


def test_mobile_drawer_off_canvas() -> None:
    """Below 768px the sidebar becomes an off-canvas drawer (Major #4).

    The sidebar leaves the flex flow (fixed), slides out of view with
    translateX(-105%), and returns with .mobile-open. The hamburger and
    scrim exist but stay hidden on desktop.
    """
    assert "@media (max-width: 768px)" in VOID_THEME_CSS
    assert "translateX(-105%)" in VOID_THEME_CSS
    opened = _rule_block(VOID_THEME_CSS, ".sidebar-container.mobile-open")
    assert "translateX(0) !important" in opened
    scrim = _rule_block(VOID_THEME_CSS, ".sidebar-scrim.mobile-open")
    assert "display: block" in scrim
    assert "position: fixed" in scrim
    btn = _rule_block(VOID_THEME_CSS, ".mobile-menu-btn")
    assert "display: none" in btn
    assert "position: fixed" in btn


def test_settings_dialog_viewport_constrained() -> None:
    """Settings card is capped at the viewport; form rows stack (Major #5)."""
    card = _rule_block(VOID_THEME_CSS, ".settings-dialog-card")
    assert "max-width: calc(100vw - 2rem)" in card
    assert "min-width: 0" in card
    assert "@media (max-width: 560px)" in VOID_THEME_CSS
    assert "flex: 1 1 100%" in VOID_THEME_CSS


def test_model_select_ellipsizes() -> None:
    """Long model names ellipsize instead of clipping mid-word (Minor C1)."""
    rules = _rule_block(VOID_THEME_CSS, ".model-select .q-field__input")
    assert "text-overflow: ellipsis" in rules
    assert "white-space: nowrap" in rules
    assert "min-width: 0" in rules


def test_home_stats_row_stretches() -> None:
    """Stat cards share one row height (Minor C2).

    NiceGUI's .nicegui-row sets align-items: flex-start, so a card whose
    value wraps stands taller than its siblings without this override.
    """
    rules = _rule_block(VOID_THEME_CSS, ".home-stats-row")
    assert "align-items: stretch !important" in rules


def test_modal_backdrop_dims_page() -> None:
    """Modal backdrop is stronger than Quasar's 0.4 default (Minor C16)."""
    rules = _rule_block(VOID_THEME_CSS, ".q-dialog__backdrop")
    assert "rgba(0, 0, 0, 0.6)" in rules


def test_button_labels_keep_title_case() -> None:
    """One button voice: Quasar's uppercase transform is off (Nit C3)."""
    rules = _rule_block(VOID_THEME_CSS, ".q-btn")
    assert "text-transform: none !important" in rules


def test_glow_button_hover_clearly_visible() -> None:
    """Primary CTA hover is unmistakable: glow, brightness, border (Nit C17)."""
    rules = _rule_block(VOID_THEME_CSS, ".mvge-glow-btn:hover")
    assert "filter: brightness(1.3)" in rules
    assert "0 0 22px rgba(123, 108, 246, 0.5)" in rules


def _root_tokens(css: str) -> set[str]:
    """Token names declared in the ``:root`` block."""
    match = re.search(r":root\s*\{([^}]*)\}", css)
    assert match is not None, "missing :root block"
    return set(re.findall(r"(--[\w-]+)\s*:", match.group(1)))


def _light_tokens(css: str) -> set[str]:
    """Token names overridden in the light-theme block."""
    match = re.search(r'html\[data-theme="light"\]\s*\{([^}]*)\}', css)
    assert match is not None, "missing light theme override block"
    return set(re.findall(r"(--[\w-]+)\s*:", match.group(1)))


def test_light_theme_overrides_every_dark_token() -> None:
    """Every dark token must have a light value: no half-themed surfaces."""
    assert _light_tokens(LIGHT_THEME_CSS) == _root_tokens(VOID_THEME_CSS)


def test_light_theme_keeps_violet_brand() -> None:
    """Brand accents are identical in both themes."""
    for token in ("--accent-primary", "--accent-pink", "--border-active"):
        dark = re.search(re.escape(token) + r"\s*:\s*([^;]+);", VOID_THEME_CSS)
        light = re.search(re.escape(token) + r"\s*:\s*([^;]+);", LIGHT_THEME_CSS)
        assert dark is not None
        assert light is not None
        assert dark.group(1).strip() == light.group(1).strip()


def test_light_theme_text_readable_on_light_surfaces() -> None:
    """Light-theme text tokens must be dark (no light-on-light text)."""

    def luminance(hex_color: str) -> float:
        hex_color = hex_color.lstrip("#")
        r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    for token in ("--text-primary", "--text-secondary", "--text-muted"):
        match = re.search(
            re.escape(token) + r"\s*:\s*(#[0-9a-fA-F]{6})", LIGHT_THEME_CSS
        )
        assert match is not None, f"{token} missing from light theme"
        assert luminance(match.group(1)) < 0.45, f"{token} too light for a light theme"


def test_inject_theme_rejects_unknown_theme() -> None:
    """inject_theme validates the theme name before touching NiceGUI."""
    with pytest.raises(ValueError, match="unknown theme"):
        inject_theme("midnight")


def test_theme_dataset_script_names_theme() -> None:
    """The boot script stamps the chosen theme onto <html>."""
    assert 'setAttribute("data-theme", "light")' in theme_dataset_script("light")
    assert 'setAttribute("data-theme", "dark")' in theme_dataset_script("dark")


@pytest.mark.asyncio
async def test_inject_theme_light(user: User) -> None:
    """inject_theme("light") renders a page without error."""

    @ui.page("/test_styles_light")
    def page() -> None:
        inject_theme("light")
        ui.label("Light Theme Injected")

    await user.open("/test_styles_light")
    await user.should_see("Light Theme Injected")


def test_apply_theme_rejects_unknown_theme() -> None:
    """apply_theme validates the theme name before touching the page."""
    with pytest.raises(ValueError, match="unknown theme"):
        apply_theme("midnight", cast("DarkMode", None))


@pytest.mark.asyncio
async def test_apply_theme_switches_to_light(
    user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """apply_theme("light") stamps <html data-theme> and disables Quasar dark."""
    scripts: list[str] = []
    monkeypatch.setattr(
        ui, "run_javascript", lambda code, **kwargs: scripts.append(code)
    )

    @ui.page("/test_apply_theme_light")
    def page() -> None:
        dark_mode = inject_theme("dark")
        assert dark_mode.value is True
        apply_theme("light", dark_mode)
        ui.label(f"dark-mode-value={dark_mode.value}")

    await user.open("/test_apply_theme_light")
    await user.should_see("dark-mode-value=False")
    assert len(scripts) == 1
    assert 'setAttribute("data-theme", "light")' in scripts[0]


@pytest.mark.asyncio
async def test_apply_theme_switches_to_dark(
    user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """apply_theme("dark") stamps <html data-theme> and enables Quasar dark."""
    scripts: list[str] = []
    monkeypatch.setattr(
        ui, "run_javascript", lambda code, **kwargs: scripts.append(code)
    )

    @ui.page("/test_apply_theme_dark")
    def page() -> None:
        dark_mode = inject_theme("light")
        assert dark_mode.value is False
        apply_theme("dark", dark_mode)
        ui.label(f"dark-mode-value={dark_mode.value}")

    await user.open("/test_apply_theme_dark")
    await user.should_see("dark-mode-value=True")
    assert len(scripts) == 1
    assert 'setAttribute("data-theme", "dark")' in scripts[0]


def _relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance for a ``#rrggbb`` color."""

    def channel(value: int) -> float:
        linear = value / 255
        if linear <= 0.04045:
            return linear / 12.92
        return ((linear + 0.055) / 1.055) ** 2.4

    red = int(hex_color[1:3], 16)
    green = int(hex_color[3:5], 16)
    blue = int(hex_color[5:7], 16)
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)


def _contrast_ratio(foreground: str, background: str) -> float:
    """WCAG contrast ratio between two ``#rrggbb`` colors."""
    lighter = max(_relative_luminance(foreground), _relative_luminance(background))
    darker = min(_relative_luminance(foreground), _relative_luminance(background))
    return (lighter + 0.05) / (darker + 0.05)


def test_placeholder_rule_covers_text_inputs() -> None:
    """Placeholder token applies to inputs as well as textareas.

    Regression: the rule only targeted ``textarea``, so single-line inputs
    (e.g. the Sessions search box) fell back to the browser default and
    rendered nearly invisible in the light theme.
    """
    assert "input::placeholder" in CURVY_COMPOSER_CSS
    assert ".q-field__native::placeholder" in CURVY_COMPOSER_CSS
    rule = re.search(r"input::placeholder[^{]*\{([^}]*)\}", CURVY_COMPOSER_CSS)
    assert rule is not None, "missing CSS rule covering input::placeholder"
    assert "var(--text-placeholder)" in rule.group(1)


def test_light_placeholder_token_contrast() -> None:
    """Light placeholder token stays readable on light input surfaces."""
    match = re.search(r"--text-placeholder:\s*(#[0-9a-fA-F]{6})", LIGHT_THEME_CSS)
    assert match is not None
    assert _contrast_ratio(match.group(1), "#efeaf7") >= 3.0


def test_dark_placeholder_token_contrast() -> None:
    """Dark placeholder token stays readable on dark input surfaces."""
    match = re.search(r"--text-placeholder:\s*(#[0-9a-fA-F]{6})", VOID_THEME_CSS)
    assert match is not None
    assert _contrast_ratio(match.group(1), "#16161d") >= 3.0


def test_no_fixed_dark_badge_colors_in_components() -> None:
    """Component badges must not pin a fixed dark Quasar palette color.

    Regression: ``color="grey-9"`` badges paired theme-adaptive
    ``text-[var(--text-secondary)]`` text with a fixed dark-gray
    background, rendering unreadable in the light theme. Badges now use
    theme tokens (``bg-[var(--bg-card)]``) instead.
    """
    components = (
        Path(__file__).resolve().parents[3] / "src" / "mvgeos_gui" / "components"
    )
    offenders = [
        path.name
        for path in sorted(components.glob("*.py"))
        if 'color="grey-9"' in path.read_text() or "color='grey-9'" in path.read_text()
    ]
    assert offenders == []
