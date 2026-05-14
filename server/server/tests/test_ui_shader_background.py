"""Static checks for the Thread Visualizer background layers."""
from pathlib import Path


UI_HTML = Path(__file__).parent.parent.parent.parent / "ui" / "index.html"


def _html() -> str:
    return UI_HTML.read_text(encoding="utf-8")


def test_thread_visualizer_does_not_use_fluid_shader_background():
    html = _html()
    assert "function initShaderBackground()" not in html
    assert "getContext('webgl'" not in html
    assert "precision highp float;" not in html
    assert "gl.drawArrays(gl.TRIANGLES, 0, 6)" not in html


def test_fluid_shader_fallback_and_pointer_interaction_were_removed():
    html = _html()
    assert "function drawStaticShaderFallback()" not in html
    assert "shaderPointer" not in html
    assert "window.addEventListener('pointermove'" not in html


def test_old_particle_background_was_removed():
    html = _html()
    assert "Background particle net" not in html
    assert "const DOTS = Array.from" not in html
    assert "function drawBg()" not in html


def test_sparkles_background_canvas_is_layered_behind_thread_graph():
    html = _html()
    assert '<canvas id="sparkles-canvas" aria-hidden="true"></canvas>' in html
    assert "#sparkles-canvas" in html
    assert "mix-blend-mode:screen" in html
    assert "#graph-svg  { position:fixed; inset:0; z-index:1; pointer-events:none; }" in html
    assert "/* bubble nodes appended to body at z-index:3 */" in html


def test_sparkles_background_has_particles_without_title_component():
    html = _html()
    assert "const SPARKLE_COUNT = 95" in html
    assert "function makeSparkle()" in html
    assert "function drawSparkle(ctx, x, y, r, opacity, color)" in html
    assert "function drawSparkles(now)" in html
    assert "sparklesCtx.globalCompositeOperation = 'lighter'" in html
    assert "requestAnimationFrame(drawSparkles)" in html
    assert "SparklesCore" not in html
    assert "sparkles-title" not in html
