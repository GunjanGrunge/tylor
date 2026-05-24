"""Static checks for the Thread Visualizer background and performance."""
from pathlib import Path


UI_HTML = Path(__file__).parent.parent.parent / "ui" / "index.html"


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


def test_no_continuous_canvas_animation():
    """The redesigned UI uses a static CSS gradient, no canvas animation loops."""
    html = _html()
    assert "const STARS" not in html
    assert "bgCanvas" not in html
    assert "drawBg()" not in html
    assert "radial-gradient" in html


def test_no_force_simulation():
    """The redesigned UI uses d3.linkHorizontal() instead of force simulation."""
    html = _html()
    assert "d3.forceSimulation" not in html
    assert "d3.forceCenter" not in html
    assert "d3.forceManyBody" not in html
    assert "d3.linkHorizontal()" in html
