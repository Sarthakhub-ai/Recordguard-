from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_web_accessibility_and_responsive_tokens_present():
    css = (ROOT / "apps" / "web" / "app" / "styles.css").read_text()
    assert ".skip" in css
    assert ":focus-visible" in css
    assert "prefers-reduced-motion" in css
    assert "@media(max-width:850px)" in css
    assert "@media(max-width:520px)" in css

def test_web_status_and_danger_semantics_present():
    css = (ROOT / "apps" / "web" / "app" / "styles.css").read_text()
    page = (ROOT / "apps" / "web" / "app" / "page.tsx").read_text()
    assert "badge-active" in css
    assert "badge-archived" in css
    assert "badge-admin-deleted" in css
    assert 'className="danger"' in page
    assert "aria-live=\"polite\"" in page

def test_desktop_intermediate_typography_level_present():
    ui = (ROOT / "core_ui.py").read_text(encoding="utf-8")
    assert 'Section.TLabel' in ui
