from pathlib import Path


def test_public_map_selects_density_aware_chart_tiles() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert "tileSize: 256" in app_js
    assert "window.devicePixelRatio" in app_js
    assert "Math.max(1.75" in app_js
    assert "visibleWidthMeters" in app_js
    assert "targetPixelWidth" in app_js
    assert "chartBasemap.maxLevel" in app_js
    assert "Math.min(14, 10 + mapZoomStep)" not in app_js


def test_public_map_controls_use_plain_zoom_language() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    index_html = Path("public-site/index.html").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert '<span id="zoom-label">Zoom</span>' in index_html
    assert "Chart zoom" not in index_html
    assert "`Zoom ${mapZoomStep + 1} of 5`" in app_js
    assert "`Chart ${currentChartLevel()}`" not in app_js
    assert "setupMapPanAndWheel()" in app_js
    assert '"wheel"' in app_js
    assert 'map.addEventListener("pointerdown"' in app_js
    assert "zoomAtPoint" in app_js
    assert "panMapByPixels" in app_js
    assert "commitMapPan" in app_js
    assert "--map-pan-x" not in styles_css


def test_public_timestamps_include_year() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert 'year: "numeric"' in app_js


def test_public_map_mutes_busy_noaa_chart_background() -> None:
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert "filter: saturate(0.62) contrast(0.88) brightness(1.08);" in styles_css
    assert "rgba(247, 244, 237, 0.26)" in styles_css
    assert "opacity: 0.85;" in styles_css


def test_public_stats_fit_one_row_on_desktop() -> None:
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert "repeat(4, minmax(120px, 1fr))" in styles_css


def test_public_map_popups_are_click_driven_and_explicit() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")
    index_html = Path("public-site/index.html").read_text(encoding="utf-8")

    assert "activePopupClipId" in app_js
    assert "showMapPopup" in app_js
    assert "clearMapPopup" in app_js
    assert "Reviewed radio clip" in app_js
    assert 'aria-label="Close map detail"' in app_js
    assert 'tooltip.addEventListener("click"' in app_js
    assert "tooltip.replaceChildren()" in app_js
    assert "event.stopPropagation()" in app_js
    assert "addEventListener(\"mouseenter\"" not in app_js
    assert "addEventListener(\"mouseleave\"" not in app_js
    assert "showMapPreview" not in app_js
    assert 'document.addEventListener("keydown"' in app_js
    assert "clearMapPopup();" in app_js
    assert "scrollIntoView" not in app_js
    assert "radio-clip-marker" in app_js
    assert "pointer-events: auto;" in styles_css
    assert ".map-tooltip[hidden]" in styles_css
    assert "display: none;" in styles_css
    assert "Reviewed radio clips" in index_html
    assert "AIS vessels" in index_html
    assert "Recent AIS trail" in index_html


def test_public_map_removes_duplicate_place_labels() -> None:
    index_html = Path("public-site/index.html").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert "map-label" not in index_html
    assert ".map-label" not in styles_css


def test_public_map_uses_noaa_chart_display_tiles() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    index_html = Path("public-site/index.html").read_text(encoding="utf-8")

    assert "gis.charttools.noaa.gov" in app_js
    assert "MarineChart_Services/NOAACharts/MapServer/tile" in app_js
    assert "tileLevelOffset: 2" in app_js
    assert "maxLevel: 14" in app_js
    assert "NOAA ENC Chart Display" in index_html
    assert "Esri Ocean Basemap" not in index_html


def test_public_ais_playback_does_not_draw_week_long_straight_lines() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert "aisPlayback" in app_js
    assert "maxInterpolationGapMinutes" in app_js
    assert "trailWindowMinutes" in app_js
    assert "maxSegmentDistanceNm" in app_js
    assert "motionTrailAtTime" in app_js
    assert "segmentIsPlausible" in app_js
    assert "interpolated: true" in app_js
    assert "courseTailPoint" in app_js
    assert ".vessel-passenger::before" in styles_css
    assert ".vessel-tug::before" in styles_css
    assert ".vessel-cargo::before" in styles_css
