from pathlib import Path


def test_public_site_is_recent_clip_app_with_dedicated_ais_catcher_tab() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    index_html = Path("public-site/index.html").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert "limit=${selectedClipPageSize}" in app_js
    assert "channel-filter" in index_html
    assert '<select id="channel-filter"' not in index_html
    assert 'id="channel-filter" class="channel-filter channel-multiselect"' in index_html
    assert "<summary" not in index_html
    assert "renderChannelFilter" in app_js
    assert "selectedChannels" in app_js
    assert "selectedChannelValues" in app_js
    assert "formatChannelFilterSummary" in app_js
    assert "channel-filter-trigger" in app_js
    assert "channel-filter-panel" in app_js
    assert "channel-filter-checkbox" in app_js
    assert "channel-filter-swatch" in app_js
    assert "channel-filter-frequency" in app_js
    assert "channel-filter-action" in app_js
    assert "channels=${encodeURIComponent(channel)}" in app_js
    assert "defaultClipPageSize = 6" in app_js
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
    assert "channelFilterButton" not in app_js
    assert "channel-filter-option" in app_js
    assert "aria-checked" in app_js
    assert "input.dataset.channel" in app_js
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
    assert 'const clipCorrectionsUrl = "/api/clips/corrections";' in app_js
    assert 'const operatorSessionUrl = "/api/operator/session";' in app_js
    assert "operatorReviewEnabled" in app_js
    assert 'window.location.pathname.startsWith("/operator")' in app_js
    assert 'hostname === "vhf-dev.robertboscacci.com"' in app_js
    assert 'dsp=warm_voice' not in app_js
    assert "/public_manifest.json" in app_js
    assert "Elliott Bay VHF" in index_html
    assert '<link rel="icon" href="/favicon.svg" type="image/svg+xml" />' in index_html
    assert "Seattle Marine Radio" not in index_html
    assert "Clip Review" in index_html
    assert "Live Monitor" in index_html
    assert "Map" in index_html
    assert ">AIS<" not in index_html
    assert "Elliott Bay Vessel Map" in index_html
    assert 'id="tab-map" type="button" data-tab="map"' in index_html
    assert "panel-map" in index_html
    assert "ais-catcher-frame" in index_html
    assert "map-status" in index_html
    assert "map-data-note" in index_html
    assert "local AIS receiver" in index_html
    assert "AIS-catcher" in index_html
    assert "shared public map" in index_html
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
    assert "dominantThemeSummary(topics)" in app_js
    assert "Largest non-outlier topic by analyzed clips" in app_js
    assert "busiestHoursSummary" not in app_js
    assert "renderExamplePlayer(clip)" in app_js
    assert "entityExampleWithAudio(entity)" in app_js
    assert "renderExamplePlayer(entity.examples?.[0] || {})" not in app_js
    assert "analysisAudioUrlForClip(example)" in app_js
    assert "example-player" in app_js
    assert "No playable clips are available" in app_js
    assert "loadedmetadata" in app_js
    assert 'className = "example-play"' not in app_js
    assert "📻" in Path("public-site/favicon.svg").read_text(encoding="utf-8")
    assert ".example-player" in styles_css
    assert ".example-play {" not in styles_css
    assert ".channel-filter-option" in styles_css
    assert ".channel-filter-trigger" in styles_css
    assert ".channel-filter-panel" in styles_css
    assert ".channel-filter-swatch" in styles_css
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
    assert "touch-action: pan-x pan-y pinch-zoom;" in styles_css
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
    assert "1-minute load average" not in app_js
    assert "Average over selected window" in app_js
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
    assert (
        'const aisCatcherFrameUrl = "/ais-catcher/?lat=47.6190158&lon=-122.3595353'
        '&zoom=13&setcoord=false&welcome=false&tab=map";'
    ) in app_js
    assert "renderAisCatcherFrame" in app_js
    assert "aisCatcherFrame.src = aisCatcherFrameUrl;" in app_js
    assert 'aisCatcherFrame.title = "AIS-catcher live map";' in app_js
    assert 'mapStatus.textContent = "Showing AIS-catcher live map";' in app_js
    assert ".tab-panel[hidden]" in styles_css
    assert "/api/ais/tracks" not in app_js
    assert "loadLiveAisTracks" not in app_js
    assert "mapPayloadWithLiveAis" not in app_js
    assert "renderAisMapDashboard" not in app_js
    assert "renderVesselMap" not in app_js
    assert "No AIS vessel positions received yet" not in app_js
    assert "Vessel positions in the public manifest" not in app_js
    assert "lexicalAnalysis.replaceChildren(cards, channelPanel, wordsPanel" in app_js
    assert "lexicalAnalysis.replaceChildren(cards, channelPanel, mapPanel" not in app_js
    assert ".ais-catcher-frame" in styles_css
    assert ".vessel-map-panel" not in styles_css
    assert ".nautical-map" not in styles_css
    assert ".vessel-marker" not in styles_css
    assert "bay-map" not in index_html
    assert "Nearby Signals" not in index_html
    assert "Play AIS" not in index_html
    assert "L.tileLayer" not in app_js


def test_public_site_analysis_copy_clarifies_frequency_metrics() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert "Analyzed transcript clips by VHF channel" in app_js
    assert "Dominant theme" in app_js
    assert "dominantThemeSummary(topics)" in app_js
    assert "Largest non-outlier topic by analyzed clips" in app_js
    assert "Busiest hours" not in app_js
    assert "busiestHoursSummary" not in app_js
    assert "No analyzed transmissions yet" in app_js
    assert "activeChannelSummary" in app_js
    assert "formatCountNoun(vhfCount, \"channel\", \"channels\")" in app_js
    assert "VHF channels with at least one analyzed clip" in app_js
    assert "monitoredAnalysisChannels" in app_js
    assert "channelCountsWithMonitoredChannels" in app_js
    assert '["05A", "06", "09", "13", "14", "16", "22A", "67", "68", "69", "71", "72"]' in app_js
    assert "activeAnalyzedChannelCount(channelCounts)" in app_js
    assert "Number(count || 0) > 0" in app_js
    assert ".filter(([, count]) => count > 0)" in app_js


def test_public_site_clip_review_page_size_and_sort_controls() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    index_html = Path("public-site/index.html").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert "const defaultClipPageSize = 6;" in app_js
    assert "const clipPageSizeOptions = [6, 12, 24, 48];" in app_js
    assert "let selectedClipPageSize = defaultClipPageSize;" in app_js
    assert "let clipSortDirection = \"newest\";" in app_js
    assert "limit=${selectedClipPageSize}" in app_js
    assert "renderClipDisplayControls()" in app_js
    assert "renderClipDisplayControlSet()" in app_js
    assert "mobileClipDisplayControls()" in app_js
    assert "const insertAfter = Math.min(6, cards.length);" in app_js
    assert "applyClipSortForCurrentPage" in app_js
    assert "clipSortDirection === \"oldest\"" in app_js
    assert "let currentPageClips = [];" in app_js
    assert "function renderCurrentClipOrder()" in app_js
    assert "clipSortDirection = \"newest\";\n        renderCurrentClipOrder();" in app_js
    assert "clipSortDirection = \"oldest\";\n        renderCurrentClipOrder();" in app_js
    assert "selectedClipPage = 1;" in app_js
    assert '"Flip page order"' in app_js
    assert 'id="clip-display-controls"' in index_html
    assert "clip-display-controls" in styles_css
    assert "clip-display-controls-inline" in styles_css
    assert "clip-segmented-control" in styles_css
    assert "#clip-display-controls {\n    display: none;" in styles_css
    assert ".clip-display-controls-inline {\n    display: grid;" in styles_css
    assert ".clip-display-controls {\n    display: grid;" in styles_css
    assert ".clip-control-group {\n    width: 100%;" in styles_css
    assert ".clip-segment-button {\n    flex: 1 1 0;" in styles_css


def test_public_site_analysis_topics_hide_outliers_and_explain_clusters() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert 'const topicPanel = languagePanel("Transcript topics");' in app_js
    assert "Descriptive counts from the transcript analysis" not in app_js
    assert "Topic intelligence" not in app_js
    assert "Signal fingerprint" not in app_js
    assert "nonOutlierTopics(topics.items || [])" in app_js
    assert 'className = "topic-frame-shell"' in app_js
    assert "topicFrame.allowFullscreen = true" in app_js
    assert 'topicFrame.setAttribute("allow", "fullscreen")' in app_js
    assert "mobileNlpSummary" not in app_js
    assert "nlpSummaryRows" not in app_js
    assert "Descriptive NLP summary" not in app_js
    assert "Top observed terms" not in app_js
    assert 'termSection("Jargon", terms.semantic_buckets?.communication_markers || [])' in app_js
    assert "topicTitle(topic)" in app_js
    assert "topicKeywordWords(topic)" in app_js
    assert 'title.textContent = `${topicTitle(topic)} · ${topic.count || 0}`;' in app_js
    assert "topic.id !== -1" in app_js
    assert 'topic.label || "Topic" !== "Outliers"' not in app_js
    assert ".language-panel-intro" in styles_css
    assert ".mobile-nlp-panel" not in styles_css
    assert ".nlp-summary-grid" not in styles_css
    assert ".nlp-term-fill" not in styles_css
    assert "signal-score-orb" not in styles_css
    assert ".topic-frame-shell" in styles_css
    assert "touch-action: pan-x pan-y pinch-zoom;" in styles_css
    assert "height: min(72dvh, 620px);" in styles_css
    assert "@media (max-width: 760px)" in styles_css
    assert ".topic-frame-shell {\n    display: none;" in styles_css


def test_public_site_analysis_examples_use_same_origin_clip_audio() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert "function analysisAudioUrlForClip(clip)" in app_js
    assert "return clipAudioRequestUrl(clip) || audioUrlForClip(clip);" in app_js
    assert "const audioUrl = analysisAudioUrlForClip(example);" in app_js
    assert 'const clipAudioUrl = "/api/clips/audio";' in app_js


def test_public_site_performance_metric_values_average_selected_window() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert "averageMetricValue(samples)" in app_js
    assert 'performanceSummaryMetric(host, "cpuUtilizationPercent", "%", "cpu")' in app_js
    assert 'performanceSummaryMetric(host, "memoryUsedPercent", "%", "memory")' in app_js
    assert 'performanceSummaryMetric(host, "thermalTemperatureC", " C", "thermal")' in app_js
    assert "performanceSummarySamples(host, field)" in app_js
    assert "status: performanceSummaryStatus(field, value" in app_js
    assert "performanceWindowCaption(cpuSummary.samples" in app_js
    assert "performanceWindowCaption(memorySummary.samples)" in app_js
    assert "performanceWindowCaption(thermalSummary.samples)" in app_js
    assert "Average over selected window" in app_js
    assert "percentLabel(memory.usedPercent)" not in app_js
    assert "thermalSummary(thermal)" not in app_js
    assert "latest?.value" not in app_js


def test_public_site_performance_chart_traces_are_lightweight() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert "dot.setAttribute(\"r\", \"2.2\")" in app_js
    assert ".performance-chart-line" in styles_css
    assert "stroke-width: 1.35;" in styles_css
    assert "stroke-width: 2.4;" not in styles_css


def test_public_site_renders_db_clips_and_static_export_clips() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert "playback_url" in app_js
    assert "audio_public_filename" in app_js
    assert 'const clipPlaybackUrl = "/api/clips/playback";' in app_js
    assert "playback_issued_at_ms: Date.now()" in app_js
    assert "shouldRefreshPlaybackUrl" in app_js
    assert "refreshPlaybackUrl" in app_js
    assert "ensureFreshPlaybackUrl" in app_js
    assert "isSignedPlaybackUrl" in app_js
    assert "transcript" in app_js
    assert "transcript_public" in app_js
    assert "transcript_reviewed" in app_js
    assert "renderTranscriptCorrectionForm" in app_js
    assert "saveTranscriptCorrection" in app_js
    assert (
        'summary.textContent = clip.transcript_reviewed ? "Edit correction" : "Fix transcript";'
        in app_js
    )
    assert 'reviewer: "operator-ui"' in app_js
    assert 'credentials: "include"' in app_js
    assert 'headers: { "Content-Type": "application/json" }' in app_js
    assert 'headers: { "X-TalkingBoats-Operator-Token": token }' in app_js
    assert "Saved for nightly training." in app_js
    assert ".transcript-correction" in styles_css
    assert ".reviewed-pill" in styles_css
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


def test_public_site_hides_ais_tab_in_production() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    index_html = Path("public-site/index.html").read_text(encoding="utf-8")

    assert "aisDashboardEnabled" in app_js
    assert "mapTab.hidden = !aisDashboardEnabled" in app_js
    assert 'name === "map" && !aisDashboardEnabled' in app_js
    assert "panels.map.hidden = !aisDashboardEnabled" in app_js
    assert 'id="tab-map" type="button" data-tab="map" hidden' in index_html


def test_public_site_tabs_have_linkable_routes() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    deploy_shell = Path("scripts/deploy_static_shell.sh").read_text(encoding="utf-8")
    deploy_full = Path("scripts/deploy_public_site.sh").read_text(encoding="utf-8")

    assert 'clips: "clips"' in app_js
    assert 'live: "live"' in app_js
    assert 'map: "ais"' in app_js
    assert 'language: "analysis"' in app_js
    assert 'performance: "performance"' in app_js
    assert "tabFromLocation()" in app_js
    assert "updateTabRoute(name" in app_js
    assert "window.addEventListener(\"popstate\"" in app_js
    assert "activateTab(tabFromLocation(), { replaceRoute: true, updateRoute: false })" in app_js
    for route in ("clips", "live", "ais", "analysis", "performance"):
        assert f'"{route}/index.html"' in deploy_shell
        assert f'"{route}/index.html"' in deploy_full
        assert f'"{route}/"' in deploy_shell
        assert f'"{route}/"' in deploy_full
        assert f'"{route}"' in deploy_shell
        assert f'"{route}"' in deploy_full
    assert "aws s3api put-object" in deploy_shell
    assert "aws s3api put-object" in deploy_full


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
    assert "return Boolean(liveAudio.src && !liveAudio.paused);" in app_js
    assert "suspendLiveView();" in app_js
    assert "if (shouldPreserveLiveAudioSession())" in app_js
    assert "System media controls can keep live radio playing" in app_js
    assert "navigator.mediaSession.playbackState = playbackState" in app_js


def test_public_site_defaults_system_media_controls_on_android() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert "const systemMediaControlsDefault = defaultSystemMediaControlsEnabled();" in app_js
    assert "let systemMediaControlsEnabled = initialSystemMediaControlsEnabled();" in app_js
    assert "function initialSystemMediaControlsEnabled()" in app_js
    assert "window.localStorage.getItem(systemMediaControlsStorageKey)" in app_js
    assert 'storedSystemMediaControls === "enabled"' in app_js
    assert 'storedSystemMediaControls === "disabled"' in app_js
    assert "function defaultSystemMediaControlsEnabled()" in app_js
    assert "return isAndroidAudioEnvironment();" in app_js
    assert "function isAndroidAudioEnvironment()" in app_js
    assert 'return operatingSystemNameFromUserAgent(userAgent, platform) === "Android";' in app_js


def test_public_site_uses_native_audio_controls_for_clip_playback_and_metadata() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert 'document.createElement("audio")' in app_js
    assert "audio.controls = true" in app_js
    assert 'audio.preload = "metadata"' in app_js
    assert "audio.src = audioUrl" in app_js
    assert "refreshClipAudioPlayback(example, audio, time)" in app_js
    assert 'audio.addEventListener("error"' in app_js
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
    assert "systemMediaControlsDefault = defaultSystemMediaControlsEnabled()" in app_js
    assert "systemMediaControlsEnabled = initialSystemMediaControlsEnabled()" in app_js
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


def test_public_site_live_audio_everything_mode_queues_transmissions() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    index_html = Path("public-site/index.html").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert 'id="live-queue" class="live-queue"' in index_html
    assert 'const everythingLiveChannel = "everything";' in app_js
    assert "let selectedLiveChannel = everythingLiveChannel;" in app_js
    assert "live-header-stack" in index_html
    assert index_html.index('class="live-actions"') < index_html.index('class="tuner-display"')
    assert ".live-header-stack" in styles_css
    assert "const liveQueuePollMs = 5000;" in app_js
    assert 'const liveQueueUrl = "/api/clips/recent?limit=24";' in app_js
    assert "const everythingInitialQueueLimit = 3;" in app_js
    assert "let liveQueue = [];" in app_js
    assert "let currentLiveQueueClip = null;" in app_js
    assert "let everythingQueueEnabled = false;" in app_js
    assert "let everythingQueueStartedAtMs = 0;" in app_js
    assert "let everythingQueueSeeded = false;" in app_js
    assert "isEverythingLiveMode()" in app_js
    assert "renderEverythingQueuePanel" in app_js
    assert "pollEverythingQueue" in app_js
    assert "enqueueEverythingClips" in app_js
    assert "seedRecent = false" in app_js
    assert "includeBackfill = false" in app_js
    assert "mostRecentEverythingQueueClips(normalizedClips, everythingInitialQueueLimit)" in app_js
    assert "isEverythingQueueClipAfterStart(clip)" in app_js
    assert "await pollEverythingQueue({ playIfIdle: false, seedRecent: true });" in app_js
    assert (
        'if (isEverythingLiveMode()) {\n'
        "      if (!everythingQueueEnabled) {\n"
        "        return;\n"
        "      }\n"
        "      await pollEverythingQueue({ signal: liveActivityAbortController.signal });\n"
        "      return;\n"
        "    }"
    ) in app_js
    assert "playNextEverythingQueueClip" in app_js
    assert "handleEverythingClipEnded" in app_js
    assert "configureEverythingQueueAudioElement" in app_js
    assert 'liveAudio.crossOrigin = "anonymous"' in app_js
    assert "liveQueue.shift()" in app_js
    assert "clipAudioRequestUrl(currentLiveQueueClip)" in app_js
    assert 'String(playbackUrl || "").split("?")[0]' in app_js
    assert "Everything" in app_js
    assert "Queued active transmissions across monitored channels" in app_js
    assert "Queue delay" in app_js
    assert "Waiting for queued transmission" in app_js
    assert 'if (isEverythingLiveMode()) {\n    return connectEverythingLive();\n  }' in app_js
    assert (
        'if (isEverythingLiveMode()) {\n'
        "    handleEverythingClipEnded();\n"
        "    return;\n"
        "  }"
    ) in app_js
    assert ".live-queue" in styles_css
    assert ".live-queue-item" in styles_css


def test_public_site_everything_mode_uses_same_origin_audio_for_waveform_samples() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert 'const clipAudioUrl = "/api/clips/audio";' in app_js
    assert "clipAudioRequestUrl(currentLiveQueueClip)" in app_js
    assert "currentLiveQueueClip.audio_url" in app_js
    assert "ensureAudioAnalyser();" in app_js
    assert "await audioContext.resume();" in app_js
    assert 'liveAudio.crossOrigin = "anonymous";' in app_js
    assert "startWaveform();" in app_js


def test_public_site_waveform_amplifies_quiet_real_audio_without_changing_playback() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert "const hasAudibleWaveform = rms > 0.002;" in app_js
    assert "const waveformGain = isReceiving ? 1 : quietWaveformGain(rms);" in app_js
    assert "function quietWaveformGain(rms)" in app_js
    assert "Math.min(10, Math.max(3, 0.08 / safeRms))" in app_js
    assert "hasAudibleWaveform ? normalized * waveformGain * height * 0.38" in app_js
    assert "liveAudio.volume" not in app_js


def test_public_site_everything_queue_survives_live_panel_navigation() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert (
        "if (isEverythingLiveMode() && everythingQueueEnabled) {\n"
        "    return true;\n"
        "  }"
    ) in app_js
    assert (
        "if (isEverythingLiveMode() && everythingQueueEnabled) {\n"
        "      startLiveActivityPolling();\n"
        "    } else {\n"
        "      stopLiveActivityPolling();\n"
        "    }"
    ) in app_js
    assert (
        "const shouldPollHiddenEverythingQueue = "
        "isEverythingLiveMode() && everythingQueueEnabled;"
    ) in app_js
    assert "if (panels.live.hidden && !shouldPollHiddenEverythingQueue)" in app_js


def test_public_site_live_monitor_desktop_layout_prioritizes_waveform() -> None:
    index_html = Path("public-site/index.html").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert "live-monitor-grid" in index_html
    assert "live-control-panel" in index_html
    assert index_html.index('id="waveform-panel"') < index_html.index('class="live-control-panel"')
    assert ".live-monitor-grid" in styles_css
    assert "grid-template-columns: minmax(420px, 1fr) minmax(280px, 360px);" in styles_css
    assert "height: clamp(240px, 32vw, 420px);" in styles_css
    assert "@media (max-width: 900px)" in styles_css


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
        "if (liveAudio.src && !isEverythingLiveMode()) {\n"
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
