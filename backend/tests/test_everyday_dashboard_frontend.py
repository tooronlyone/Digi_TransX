"""Static contracts for the Everyday dashboard presentation."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "frontend-react" / "src"


def _source(relative):
    return (FRONTEND / relative).read_text(encoding="utf-8")


def test_everyday_stat_icons_keep_their_tile_centering_contract():
    dashboard = _source("pages/everyday/EverydayDashboard.jsx")
    styles = _source("styles/pages/client.css")

    assert dashboard.count('className="everyday-stat__icon"') == 4
    assert dashboard.count('aria-hidden="true"') >= 4
    assert ".everyday-stat__icon {" in styles
    assert "display: inline-flex;" in styles
    assert "align-items: center;" in styles
    assert "justify-content: center;" in styles
    assert ".everyday-stat > div > span" in styles
    assert ".everyday-stat span" not in styles
    assert ".everyday-stat__icon > i" in styles
    assert "font-size: 20px;" in styles
    assert "line-height: 1;" in styles
