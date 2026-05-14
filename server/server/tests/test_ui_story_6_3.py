"""Static checks for Story 6.3 silk thread SVG animation."""
from pathlib import Path

import pytest


UI_HTML = Path(__file__).parent.parent.parent.parent / "ui" / "index.html"


def _html() -> str:
    return UI_HTML.read_text(encoding="utf-8")


def test_silk_curve_css_and_gradient_defs_present():
    html = _html()
    assert ".thread-link" in html
    assert "stroke:rgba(139,92,246,0.35)" in html
    assert "stroke-width:1.5" in html
    assert "fill:none" in html
    assert "stroke-linecap:round" in html
    assert "id=\"active-thread-gradient\"" in html
    assert "stop-color=\"#8b5cf6\"" in html
    assert "stop-color=\"#22d3ee\"" in html
    assert ".thread-link.status-active" in html
    assert "opacity:.6" in html
    assert ".thread-link.status-killed" in html
    assert "opacity:.15" in html


def test_silk_path_uses_cubic_bezier_with_perpendicular_offset_and_tick_updates():
    html = _html()
    assert "function silkPath(t, now=performance.now())" in html
    assert "function threadAmplitude(status)" in html
    assert "const wave = Math.sin(now * 0.0014 + (t._phase || 0)) * threadAmplitude(t.status)" in html
    assert "const offset = dist * 0.22 + wave" in html
    assert "const px = -dy / dist" in html
    assert "const py = dx / dist" in html
    assert "return `M ${CX} ${CY} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${t.x} ${t.y}`" in html
    assert "renderSilkThreads()" in html
    assert ".attr('d', d => silkPath(d, now))" in html


def test_thread_bubbles_are_static_left_lanes_with_animated_thread_physics():
    html = _html()
    assert "function layoutThreadLanes()" in html
    assert "const laneX = Math.max(170, Math.min(260, W * 0.2))" in html
    assert "wrap.style.left = t.x + 'px'" in html
    assert "wrap.style.top = t.y + 'px'" in html
    assert "function animateThreadPhysics(now)" in html
    assert "requestAnimationFrame(animateThreadPhysics)" in html
    assert "d3.forceSimulation" not in html
    assert "d3.forceCenter" not in html


def test_silk_pulse_dots_use_animate_motion_after_two_seconds():
    html = _html()
    assert ".silk-dot" in html
    assert ".attr('r', 4)" in html
    assert ".attr('fill', 'rgba(255,255,255,0.6)')" in html
    assert ".append('animateMotion')" in html
    assert ".attr('repeatCount', 'indefinite')" in html
    assert "randomDuration(t)" in html
    assert "Math.random()*4 + 3" in html
    assert "randomBegin(t, index)" in html
    assert "setTimeout(() => graphSvg.classed('silk-ready', true), 2000)" in html


def test_silk_threads_render_paths_and_motion_dots_in_browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright is not installed")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium is unavailable in this environment: {exc}")
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.route(
            "**/api/threads",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=(
                    '[{"id":"active-one","title":"Active Thread","status":"active",'
                    '"created_at":"2026-05-13T00:00:00Z","message_count":3},'
                    '{"id":"idle-two","title":"Idle Thread","status":"idle",'
                    '"created_at":"2026-05-13T00:00:00Z","message_count":1}]'
                ),
            ),
        )
        page.route("**/ws/threads", lambda route: route.abort())
        page.goto(UI_HTML.resolve().as_uri(), wait_until="domcontentloaded", timeout=10000)
        page.wait_for_function("document.querySelectorAll('path.thread-link').length >= 2")
        page.wait_for_function("document.querySelectorAll('circle.silk-dot animateMotion').length >= 2")
        page.wait_for_timeout(2100)

        assert page.locator("#graph-svg.silk-ready").count() == 1
        assert page.locator("path.thread-link.status-active").count() >= 1
        assert page.locator("path.thread-link.status-idle").count() >= 1
        assert errors == []
        browser.close()
