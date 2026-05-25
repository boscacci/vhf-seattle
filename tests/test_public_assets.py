from pathlib import Path


def test_public_site_is_recent_clip_app_without_map_or_ais_controls() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    index_html = Path("public-site/index.html").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert "limit=${clipPageSize}" in app_js
    assert "channel-filter" in index_html
    assert "renderChannelFilter" in app_js
    assert "selectedChannel" in app_js
    assert "clipPageSize = 6" in app_js
    assert "selectedClipPage" in app_js
    assert "offset=${clipOffset()}" in app_js
    assert "renderClipPagination" in app_js
    assert "clip-pagination" in index_html
    assert ".clip-pagination" in styles_css
    assert 'optionForChannel("all", "All channels")' in app_js
    assert "configuredChannels" in app_js
    assert "Bridge-to-bridge" in app_js
    assert "channel_label" in app_js
    assert "channelClassName" in app_js
    assert "channelColorForChannel" in app_js
    assert ".pill.channel-pill" in styles_css
    assert "VTS / Seattle Traffic" in app_js
    assert "tailnetLiveBase" not in app_js
    assert "tailbea63b.ts.net" not in app_js
    assert "America/Los_Angeles" in app_js
    assert "timeZoneName" in app_js
    assert "/api/live/current.mp3" in app_js
    assert "/api/live/channels" in app_js
    assert 'hostname === "vhf-dev.robertboscacci.com"' in app_js
    assert 'dsp=warm_voice' not in app_js
    assert "/public_manifest.json" in app_js
    assert "Elliott Bay VHF" in index_html
    assert "Seattle Marine Radio" not in index_html
    assert "Clip Review" in index_html
    assert "Live Monitor" in index_html
    assert "live-channel" in index_html
    assert "waveform-canvas" in index_html
    assert 'id="waveform-panel" class="waveform-panel"' in index_html
    assert 'id="play-live"' in index_html
    assert "Open stream" not in index_html
    assert "connect-live" not in index_html
    assert "clip-list" in index_html
    assert "color-scheme: dark" in styles_css
    assert ".live-card" in styles_css
    assert ".waiting-indicator" in styles_css
    assert "AudioContext" in app_js
    assert "getByteTimeDomainData" in app_js
    assert "liveStatusPollMs = 2000" in app_js
    assert "quietTransmissionDelayMs = 5000" in app_js
    assert "startLiveStatusPolling" in app_js
    assert "setTimeout(pollLiveStatus, liveStatusPollMs)" in app_js
    assert "closeLiveAudioStream" in app_js
    assert "liveAudio.removeAttribute(\"src\")" in app_js
    assert "closeLiveAudioStream();" in app_js
    assert "Waiting for transmission" in app_js
    assert '"Static"' not in app_js
    assert "static clips" not in app_js
    assert "Tailnet Protected" not in index_html
    assert "bay-map" not in index_html
    assert "Nearby Signals" not in index_html
    assert "Play AIS" not in index_html
    assert "ais_tracks" not in app_js
    assert "L.tileLayer" not in app_js
    assert ".map-panel" not in styles_css


def test_public_site_renders_db_clips_and_static_export_clips() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert "playback_url" in app_js
    assert "audio_public_filename" in app_js
    assert "transcript" in app_js
    assert "transcript_public" in app_js
    assert "formatDateTime" in app_js
    assert "channelLabel" in app_js


def test_public_site_uses_same_origin_live_api_urls() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert 'const defaultLiveStreamUrl = "/api/live/current.mp3";' in app_js
    assert (
        'const liveDspProfile = window.location.hostname === "vhf-dev.robertboscacci.com" '
        '? "warm_voice" : "";'
    ) in app_js
    assert 'return `/api/live/${encodeURIComponent(selectedLiveChannel)}/current.mp3`;' in app_js
    assert 'return `/api/live/${encodeURIComponent(selectedLiveChannel)}/status`;' in app_js
    assert "return withDspProfile(url);" in app_js
