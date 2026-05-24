from pathlib import Path


def test_operator_ui_is_recent_clip_showcase_not_live_radio() -> None:
    index_html = Path("private-ui/index.html").read_text(encoding="utf-8")
    app_js = Path("private-ui/main.js").read_text(encoding="utf-8")

    assert "/api/clips/recent" in app_js
    assert "/api/operator/session" not in app_js
    assert "/api/live/channels" not in app_js
    assert "/api/live/" not in app_js
    assert "live-audio" not in index_html
    assert "Operator token" not in index_html
    assert 'type="password"' not in index_html
    assert "clip-list" in index_html
