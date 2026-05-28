from pathlib import Path


def test_public_site_is_recent_clip_app_with_dedicated_ais_map() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    index_html = Path("public-site/index.html").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert "limit=${clipPageSize}" in app_js
    assert "channel-filter" in index_html
    assert '<select id="channel-filter"' not in index_html
    assert 'id="channel-filter" class="channel-filter" role="group"' in index_html
    assert "renderChannelFilter" in app_js
    assert "selectedChannel" in app_js
    assert "clipPageSize = 6" in app_js
    assert "selectedClipPage" in app_js
    assert "offset=${clipOffset()}" in app_js
    assert "renderClipPagination" in app_js
    assert "clip-pagination" in index_html
    assert ".clip-pagination" in styles_css
    assert "columns: 2 320px;" not in styles_css
    assert ".clip-list" in styles_css
    assert ".clip-list {\n  display: grid;\n  grid-template-columns: minmax(0, 1fr);" in styles_css
    assert "break-inside: avoid;" in styles_css
    assert "min-height: 244px" not in styles_css
    assert "channelFilterButton" in app_js
    assert "channel-filter-option" in app_js
    assert "aria-pressed" in app_js
    assert "button.dataset.channel" in app_js
    assert "optionForChannel" not in app_js
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
    assert '<link rel="icon" href="/favicon.svg" type="image/svg+xml" />' in index_html
    assert "Seattle Marine Radio" not in index_html
    assert "Clip Review" in index_html
    assert "Live Monitor" in index_html
    assert "AIS Map" in index_html
    assert 'id="tab-map" type="button" data-tab="map"' in index_html
    assert "panel-map" in index_html
    assert "ais-map-dashboard" in index_html
    assert "map-status" in index_html
    assert "Analysis" in index_html
    assert "Analysis Dashboard" in index_html
    assert 'id="tab-language" type="button" data-tab="language" hidden' in index_html
    assert "panel-language" in index_html
    assert "lexical-analysis" in index_html
    assert "languageDashboardEnabled" in app_js
    assert '"vhf.robertboscacci.com"' in app_js
    assert "/api/analysis/lexical" in app_js
    assert "/analysis/lexical.json" in app_js
    assert (
        'const liveLanguageAnalysisEnabled = window.location.hostname !== '
        '"vhf.robertboscacci.com";'
    ) in app_js
    assert (
        "if (!liveLanguageAnalysisEnabled) {\n"
        "    return loadPublishedLanguagePayload();\n"
        "  }"
    ) in app_js
    assert "renderLanguageDashboard" in app_js
    assert "topic_clusters.html" in app_js
    assert "Suspected vessels" in app_js
    assert "channelActivityChart" in app_js
    assert "channel-bar-list" in app_js
    assert "busiestHoursSummary" in app_js
    assert "Top Pacific hours by analyzed transcript clips" in app_js
    assert "formatHourLabel" in app_js
    assert "renderExamplePlayer(clip)" in app_js
    assert "renderExamplePlayer(entity.examples?.[0] || {})" in app_js
    assert "audioUrlForClip(example)" in app_js
    assert "example-player" in app_js
    assert "loadedmetadata" in app_js
    assert 'className = "example-play"' not in app_js
    assert "📻" in Path("public-site/favicon.svg").read_text(encoding="utf-8")
    assert ".example-player" in styles_css
    assert ".example-play {" not in styles_css
    assert ".channel-filter-option" in styles_css
    assert ".entity-list" in styles_css
    assert "columns: 2 300px;" in styles_css
    assert "Why they say it this way" in app_js
    assert "educationGuideList" in app_js
    assert 'document.createElement("details")' in app_js
    assert 'document.createElement("summary")' in app_js
    assert "guide-card-body" in app_js
    assert "Reference index" in app_js
    assert ".education-guide" in styles_css
    assert ".education-guide-card[open]" in styles_css
    assert "grid-column: 1 / -1;" in styles_css
    assert ".guide-card-body" in styles_css
    assert ".reference-index" in styles_css
    assert ".language-grid" in styles_css
    assert ".topic-frame" in styles_css
    assert "touch-action: none;" in styles_css
    assert "live-channel" in index_html
    assert "live-last-communication" in index_html
    assert "live-latency" in index_html
    assert "system-media-controls" in index_html
    assert "waveform-canvas" in index_html
    assert 'id="waveform-panel" class="waveform-panel"' in index_html
    assert 'id="play-live"' in index_html
    assert "play-symbol" in index_html
    assert "Open stream" not in index_html
    assert "connect-live" not in index_html
    assert "clip-list" in index_html
    assert "color-scheme: dark" in styles_css
    assert ".live-card" in styles_css
    assert ".live-telemetry" in styles_css
    assert ".waiting-indicator" in styles_css
    assert ".play-symbol" in styles_css
    assert ".system-media-block" in styles_css
    assert "AudioContext" in app_js
    assert "getByteTimeDomainData" in app_js
    assert "liveStatusPollMs = 2000" in app_js
    assert "liveActivityPollMs = 15000" in app_js
    assert "quietTransmissionDelayMs = 5000" in app_js
    assert "lastCommunicationUrl" in app_js
    assert "pollLiveActivity" in app_js
    assert "formatRelativeAge" in app_js
    assert "Live delay" in app_js
    assert "behind antenna" in app_js
    assert "performanceRefreshMs = 10000" in app_js
    assert "loadAndRenderPerformance({ showLoading: false });" in app_js
    assert "startPerformancePolling" in app_js
    assert "stopPerformancePolling" in app_js
    assert "CPU utilization" in app_js
    assert "1-minute load average" in app_js
    assert "OptiPlex live proxy" in app_js
    assert "Raspberry Pi edge radio" in app_js
    assert "Thermals" in app_js
    assert "performance-host-grid" in app_js
    assert "performanceHostPanel" in app_js
    assert "performanceMetricChart" in app_js
    assert "performance-chart-grid" in app_js
    assert "performanceRangeOptions" in app_js
    assert "selectedPerformanceRangeHours" in app_js
    assert '{ label: "30m", hours: 0.5 }' in app_js
    assert '{ label: "2h", hours: 2 }' in app_js
    assert '{ label: "12h", hours: 12 }' in app_js
    assert '{ label: "24h", hours: 24 }' in app_js
    assert '{ label: "6h", hours: 6 }' not in app_js
    assert "performance-range-control" in app_js
    assert "cpuUtilizationPercent" in app_js
    assert "memoryUsedPercent" in app_js
    assert "thermalTemperatureC" in app_js
    assert 'document.createElementNS("http://www.w3.org/2000/svg", "svg")' in app_js
    assert ".performance-chart-grid" in styles_css
    assert ".performance-chart-svg" in styles_css
    assert ".performance-range-control" in styles_css
    assert "serviceList" not in app_js
    assert "Services" not in app_js
    assert "Overall" not in app_js
    assert "OptiPlex CPU" not in app_js
    assert "Pi CPU" not in app_js
    assert "Auto-refreshes every 10s" not in app_js
    assert "formatPerformanceDateTime" in app_js
    assert 'second: "2-digit"' in app_js
    assert "resident memory" not in app_js
    assert "RSS" not in app_js
    assert "startLiveStatusPolling" in app_js
    assert "setTimeout(pollLiveStatus, liveStatusPollMs)" in app_js
    assert "closeLiveAudioStream" in app_js
    assert "liveAudio.removeAttribute(\"src\")" in app_js
    assert "closeLiveAudioStream();" in app_js
    assert "Waiting for transmission" in app_js
    assert '"Static"' not in app_js
    assert "static clips" not in app_js
    assert "Tailnet Protected" not in index_html
    assert "loadAndRenderMap" in app_js
    assert "renderAisMapDashboard" in app_js
    assert "renderVesselMap" in app_js
    assert "ais_tracks" in app_js
    assert "Elliott Bay AIS map" in app_js
    assert "No AIS vessel positions received yet" in app_js
    assert "lexicalAnalysis.replaceChildren(cards, channelPanel, wordsPanel" in app_js
    assert "lexicalAnalysis.replaceChildren(cards, channelPanel, mapPanel" not in app_js
    assert ".vessel-map-panel" in styles_css
    assert ".nautical-map" in styles_css
    assert ".vessel-marker" in styles_css
    assert "bay-map" not in index_html
    assert "Nearby Signals" not in index_html
    assert "Play AIS" not in index_html
    assert "L.tileLayer" not in app_js


def test_public_site_analysis_copy_clarifies_frequency_metrics() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert "Analyzed transcript clips by VHF channel" in app_js
    assert "Top Pacific hours by analyzed transcript clips" in app_js
    assert "busiestHoursSummary" in app_js
    assert "formatHourRangeLabel" in app_js
    assert "No analyzed transmissions yet" in app_js
    assert "activeChannelSummary" in app_js
    assert "AIS vessel tracks" in app_js
    assert "Radio channels plus AIS vessel tracks" in app_js


def test_public_site_performance_metric_values_average_selected_window() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert "averageMetricValue(samples)" in app_js
    assert "Average over selected window" in app_js
    assert "latest?.value" not in app_js


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


def test_public_site_stops_other_audio_before_playing_clip_or_live_radio() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert "function stopOtherAudio(currentPlayback)" in app_js
    assert "stopCurrentClipPlayback();" in app_js
    assert "currentPlayback !== currentClipPlayback" in app_js
    assert "currentPlayback !== liveAudio" in app_js
    assert "stopOtherAudio(audio);" in app_js
    assert "stopOtherAudio(liveAudio);" in app_js
    assert "await liveAudio.play();" in app_js


def test_public_site_stops_audio_when_browser_page_is_hidden_or_unloaded() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert 'document.addEventListener("visibilitychange"' in app_js
    assert "if (document.hidden && !shouldPreserveLiveAudioSession())" in app_js
    assert 'window.addEventListener("pagehide"' in app_js
    assert "function stopAllAudio()" in app_js
    assert "stopAllAudio();" in app_js
    assert "stopCurrentClipPlayback();" in app_js
    assert "closeLiveAudioStream();" in app_js


def test_public_site_preserves_opted_in_live_audio_session_across_navigation() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert "function shouldPreserveLiveAudioSession()" in app_js
    assert "suspendLiveView();" in app_js
    assert "if (shouldPreserveLiveAudioSession())" in app_js
    assert "System media controls can keep live radio playing" in app_js
    assert "navigator.mediaSession.playbackState = playbackState" in app_js


def test_public_site_uses_native_audio_controls_for_clip_playback_and_metadata() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert 'document.createElement("audio")' in app_js
    assert "audio.controls = true" in app_js
    assert 'audio.preload = "metadata"' in app_js
    assert "audio.src = audioUrl" in app_js
    assert 'audio.addEventListener("play"' in app_js
    assert 'audio.addEventListener("loadedmetadata"' in app_js
    assert "formatPlaybackTime(example.duration_seconds" in app_js
    assert "decodeAudioData" not in app_js
    assert "function clearBrowserMediaSession()" in app_js


def test_public_site_keeps_clip_audio_controls_compact() -> None:
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert ".example-player audio" in styles_css
    assert "width: min(100%, 420px);" in styles_css
    assert "height: 36px;" in styles_css
    assert "min-height: 36px;" in styles_css
    assert "grid-template-columns: minmax(180px, 420px) auto" not in styles_css


def test_public_site_allows_live_radio_without_system_media_controls() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    index_html = Path("public-site/index.html").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert 'id="system-media-controls"' in index_html
    assert "systemMediaControlsDefault = false" in app_js
    assert "systemMediaControlsEnabled = systemMediaControlsDefault" in app_js
    assert "talkingboats.systemMediaControls" in app_js
    assert "function updateSystemMediaControlsUi()" in app_js
    assert "playLiveButton.disabled = !systemMediaControlsEnabled;" not in app_js
    assert "Enable system controls to play live" not in app_js
    assert "function updateLiveMediaSession" in app_js
    assert "function systemMediaEnvironmentLabel()" in app_js
    assert "navigator.userAgentData" in app_js
    assert "navigator.userAgent" in app_js
    assert "System media controls can keep live radio playing" in app_js
    assert "Live radio stays inside this page on" in app_js
    assert "Live radio may appear in macOS and browser media controls." not in app_js
    assert "Live radio plays in Firefox without publishing system media controls." not in app_js
    system_controls_off_gate = (
        'liveAudio.removeAttribute("src");\n'
        '    liveStatus.textContent = "System controls off";'
    )
    assert system_controls_off_gate not in app_js
    assert ".system-media-toggle" in styles_css


def test_public_site_warms_live_stream_and_acknowledges_play_immediately() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert 'liveAudio.preload = "auto";' in app_js
    assert 'liveAudio.preload = "none";' not in app_js
    assert "liveAudio.muted = true;" in app_js
    assert 'liveAudio.setAttribute("playsinline", "");' in app_js
    assert 'if (name === "live") {\n    if (liveAudio.paused || !liveAudio.src) {' in app_js
    assert "prepareLiveAudio();" in app_js
    assert "if (wasPlaying) {" in app_js
    assert "connectLive();" in app_js
    assert "} else {\n    prepareLiveAudio();" in app_js
    assert (
        "if (liveAudio.src) {\n"
        "    liveAudio.src = liveStreamUrl();\n"
        "    liveAudio.load();"
    ) in app_js
    assert 'liveStatus.textContent = "Warming stream";' in app_js
    assert 'setLivePlayButton("connecting");' in app_js
    assert 'liveStatus.textContent = "Connecting live stream";' in app_js
    assert "liveAudio.muted = false;" in app_js
    assert 'playLiveButton.classList.toggle("is-connecting", isConnecting);' in app_js
    assert ".live-play-button.is-connecting" in styles_css
    assert "@keyframes live-button-pulse" in styles_css
    assert ".signal-dot.is-connecting" in styles_css


def test_public_site_analysis_dashboard_uses_analyzed_clip_wording() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert "Analyzed transcript clips" in app_js
    assert "Cached transcript clips" not in app_js
    assert "Condensed topic clusters" in app_js
    assert "BERTopic / classical fallback" not in app_js


def test_public_site_does_not_render_unknown_clip_duration_as_zero() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert 'const unknownPlaybackTimeLabel = "—";' in app_js
    assert (
        "formatPlaybackTime(example.duration_seconds, "
        "{ unknownLabel: unknownPlaybackTimeLabel })"
    ) in app_js
    assert "if (!Number.isFinite(value) || value <= 0)" in app_js
    assert "return unknownLabel;" in app_js
    assert "Number(seconds) || 0" not in app_js


def test_public_site_education_reference_cards_use_aligned_grid_layout() -> None:
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert ".education-guide-list {\n  display: grid;" in styles_css
    assert "align-items: stretch;" in styles_css
    assert ".education-guide-card:not([open])" in styles_css
    assert "min-height: 128px;" in styles_css
    assert ".education-guide-card summary {\n  display: grid;" in styles_css
    assert "height: 100%;" in styles_css
    assert "grid-template-rows: minmax(2.5em, auto) auto;" in styles_css
    assert "justify-self: end;" in styles_css
