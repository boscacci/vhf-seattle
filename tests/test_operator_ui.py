from pathlib import Path


def test_repo_has_one_shared_browser_ui_root() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    index_html = Path("public-site/index.html").read_text(encoding="utf-8")

    assert not Path("private-ui").exists()
    assert "/api/clips/recent" in app_js
    assert "/api/live/current.mp3" in app_js
    assert "/api/operator/session" not in app_js
    assert "/api/live/channels" not in app_js
    assert "live-audio" in index_html
    assert "Operator token" not in index_html
    assert 'type="password"' not in index_html
