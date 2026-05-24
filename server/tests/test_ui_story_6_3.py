"""Static checks for the Thread Visualizer tree layout and node cards."""
from pathlib import Path

import pytest


UI_HTML = Path(__file__).parent.parent.parent / "ui" / "index.html"


def _html() -> str:
    return UI_HTML.read_text(encoding="utf-8")


def test_tree_layout_uses_d3_hierarchy():
    html = _html()
    assert "d3.linkHorizontal()" in html
    assert "viewMode" in html
    assert "renderHome" in html
    assert "renderFocused" in html


def test_thread_cards_use_foreign_object():
    html = _html()
    assert "foreignObject" in html
    assert "thread-card" in html
    assert "tc-name" in html
    assert "tc-preview" in html
    assert "tc-footer" in html


def test_project_cards_present():
    html = _html()
    assert "project-card" in html
    assert "pc-name" in html
    assert "pc-info" in html


def test_status_classes_on_thread_cards():
    html = _html()
    assert "status-active" in html
    assert "status-awaiting" in html
    assert "status-running" in html
    assert "status-idle" in html
    assert "status-killed" in html


def test_no_silk_wave_animation():
    """Old silk wave animation was removed in favor of static d3.linkHorizontal."""
    html = _html()
    assert "function silkD(" not in html
    assert "function silkPath(" not in html
    assert "animateMotion" not in html
    assert "ring-pulse" not in html


def test_detail_panel_has_improved_structure():
    html = _html()
    assert "panel-resize" in html
    assert "jump-latest" in html
    assert "panel-msg-count" in html
    assert "panel-project" in html


def test_tree_renders_in_browser():
    """Integration test: loads index.html with mock data and checks nodes render."""
    import socket

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright is not installed")

    # Skip if the real UI server is running (it overwrites mock data via WS)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(0.5)
        sock.connect(("localhost", 8765))
        sock.close()
        pytest.skip("UI server running on :8765 — browser test needs offline mode")
    except (ConnectionRefusedError, OSError):
        sock.close()

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium is unavailable in this environment: {exc}")
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto(UI_HTML.resolve().as_uri(), wait_until="domcontentloaded", timeout=10000)
        # When server is unreachable, mock data renders after fetch fails
        page.wait_for_function("document.querySelectorAll('g.node').length >= 1", timeout=8000)

        assert page.locator("g.node").count() >= 1
        assert page.locator("foreignObject").count() >= 1
        assert errors == []
        browser.close()
