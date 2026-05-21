from pathlib import Path


def test_public_map_selects_density_aware_chart_tiles() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert "tileSize: 256" in app_js
    assert "window.devicePixelRatio" in app_js
    assert "Math.max(1.75" in app_js
    assert "visibleWidthMeters" in app_js
    assert "targetPixelWidth" in app_js
    assert "Math.min(16" in app_js
    assert "Math.min(14, 10 + mapZoomStep)" not in app_js


def test_public_map_preview_is_cleared_by_map_level_dismissal() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert "activePreviewClipId" in app_js
    assert "setupMapPreviewDismissal()" in app_js
    assert 'map.addEventListener("pointerleave", clearMapPreview)' in app_js
    assert 'map.addEventListener("pointermove"' in app_js
    assert 'document.addEventListener("keydown"' in app_js
    assert "clearMapPreview();" in app_js
    assert "point.blur();" in app_js
    assert "pointer-events: none;" in styles_css
