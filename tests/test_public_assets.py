import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


def test_public_site_is_recent_clip_app_with_dedicated_ais_catcher_tab() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    index_html = Path("public-site/index.html").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert "limit=${selectedClipPageSize}" in app_js
    assert "recentClipsCacheKeyPrefix" in app_js
    assert "clipPagePrefetchRadius = 2" in app_js
    assert "prefetchNeighborClipPages(payload)" in app_js
    assert "clipPageMemoryCache" in app_js
    assert "prefetchedClipPagePayload(requestUrl)" in app_js
    assert "scheduleClipPagePrefetch" in app_js
    assert "requestIdleCallback" in app_js
    assert "prefetchClipPageAtOffset" in app_js
    assert "storeClipPageMemoryPayload(requestUrl, payload)" in app_js
    assert "renderClipLoadingState" in app_js
    assert "renderClipPlaceholders" in app_js
    assert "loadCachedRecentClipPayload" in app_js
    assert "storeRecentClipPayload" in app_js
    assert "storeRecentClipPayload(requestUrl, payload)" in app_js
    assert "loadClipPayload(requestUrl, { allowFallback: false })" in app_js
    assert "prefetchClipPageAtOffset(baseOffset + pageDelta * pageSize" in app_js
    assert ".clip-placeholder" in styles_css
    assert "channel-filter" in index_html
    assert '<select id="channel-filter"' not in index_html
    assert 'id="channel-filter" class="channel-filter channel-multiselect"' in index_html
    assert "More channel controls" in index_html
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
    assert "offset=${Math.max(0, Math.floor(Number(offset) || 0))}" in app_js
    assert "renderClipPagination" in app_js
    assert "clipPaginationItems" in app_js
    assert "paginationEllipsis" in app_js
    assert "goToClipPage" in app_js
    assert "clip-pagination" in index_html
    assert ".clip-pagination" in styles_css
    assert ".pagination-pages" in styles_css
    assert ".pagination-ellipsis" in styles_css
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
    assert "tailnetHostSuffix" in app_js
    assert ".tailbea63b.ts.net" in app_js
    assert "optiplex.tailbea63b.ts.net" not in app_js
    assert 'const privateApiBaseUrl = "";' in app_js
    assert "function apiUrl(path)" in app_js
    assert "America/Los_Angeles" in app_js
    assert "timeZoneName" in app_js
    assert "/live/current.m3u8" not in app_js
    assert 'const defaultLiveStreamUrl = apiUrl("/api/live/current.mp3");' in app_js
    assert 'const liveChannelsUrl = apiUrl("/api/live/channels");' in app_js
    assert 'const aisCatcherFrameUrl = "/ais-catcher/?lat=47.6190158&lon=-122.3595353' in app_js
    assert 'const aisCatcherFallbackUrl = "https://aiscatcher.org/";' in app_js
    assert 'const clipCorrectionsUrl = apiUrl("/api/clips/corrections");' in app_js
    assert 'const clipFeaturesUrl = apiUrl("/api/clips/features");' in app_js
    assert 'const hallOfFameRouteSegment = "hall-of-fame";' in app_js
    assert 'const reviewedRouteSegment = "reviewed";' in app_js
    assert "function routeStateFromLocation()" in app_js
    assert "clipCollectionFilter:" in app_js
    assert 'return "reviewed";' in app_js
    assert (
        "clipsTitle.textContent = clipCollectionTitle();"
        in app_js
    )
    assert "updateTabRoute(\"clips\"" in app_js
    assert "/api/operator/session" not in app_js
    assert "operatorReviewEnabled" in app_js
    assert "featureClipWriteEnabled" in app_js
    assert "const featureClipWriteEnabled = privateAppHost;" in app_js
    assert "fineTuningDashboardEnabled" not in app_js
    assert 'id="operator-labeling-link"' in index_html
    assert "Label clips" in index_html
    assert "operatorLabelingLink" in app_js
    assert "operatorLabelingLink.hidden = !privateAppHost || operatorReviewEnabled;" in app_js
    assert ".operator-labeling-link" in styles_css
    assert "\n[hidden] {\n  display: none !important;\n}" in styles_css
    assert 'const asrFeedbackStatusUrl = apiUrl("/api/asr-feedback/status");' in app_js
    assert "privateAppHost" in app_js
    assert "devAppHost" in app_js
    assert 'window.location.pathname.startsWith("/operator")' in app_js
    assert 'window.location.hostname === "vhf-dev.robertboscacci.com"' in app_js
    assert "All but traffic" in app_js
    assert 'const trafficChannelIds = new Set(["14"]);' in app_js
    assert 'allButTrafficAction.dataset.preset = "all-but-traffic";' in app_js
    assert "dsp=warm_voice" not in app_js
    assert "/public_manifest.json" in app_js
    assert "Elliott Bay VHF" in index_html
    assert '<link rel="icon" href="/favicon.svg" type="image/svg+xml" />' in index_html
    assert "Seattle Marine Radio" not in index_html
    assert "Clip Review" in index_html
    assert "Live Monitor" in index_html
    assert "Search" in index_html
    assert re.search(
        r'<button[^>]*id="tab-search"[^>]*type="button"[^>]*data-tab="search"',
        index_html,
        flags=re.S,
    )
    assert "panel-search" in index_html
    assert "clip-search-form" in index_html
    assert "clip-search-suggestions" in index_html
    assert "clip-search-results" in index_html
    assert "Map" in index_html
    assert ">AIS<" not in index_html
    assert "Elliott Bay Vessel Map" in index_html
    assert re.search(
        r'<button[^>]*id="tab-map"[^>]*type="button"[^>]*data-tab="map"',
        index_html,
        flags=re.S,
    )
    assert "panel-map" in index_html
    assert "ais-catcher-frame" in index_html
    assert "map-status" in index_html
    assert "map-data-note" in index_html
    assert "local AIS receiver" in index_html
    assert "AIS-catcher" in index_html
    assert "shared public map" in index_html
    assert "Analysis" in index_html
    assert "Analysis Dashboard" in index_html
    assert re.search(
        r'<button[^>]*id="tab-language"[^>]*type="button"[^>]*data-tab="language"[^>]*hidden',
        index_html,
        flags=re.S,
    )
    assert "panel-language" in index_html
    assert "lexical-analysis" in index_html
    assert "Fine Tuning" not in index_html
    assert "tab-fine-tuning" not in index_html
    assert "panel-fine-tuning" not in index_html
    assert "fine-tuning-dashboard" not in index_html
    assert "renderFineTuningDashboard" not in app_js
    assert "loadAndRenderFineTuning" not in app_js
    assert "Correction export" not in app_js
    assert "Nightly training" not in app_js
    assert ".fine-tuning-button" not in styles_css
    assert ".fine-tuning-status-list" not in styles_css
    assert "languageDashboardEnabled" in app_js
    assert '"vhf.robertboscacci.com"' in app_js
    assert '"seattleboatradio.com"' in app_js
    assert "/api/analysis/lexical" in app_js
    assert 'const clipSearchUrl = apiUrl("/api/clips/search");' in app_js
    assert "renderSearchSuggestions" in app_js
    assert "searchSuggestionGroupsFromPayload" in app_js
    assert "applySearchSuggestion" in app_js
    assert 'let selectedSearchRecency = "7d";' in app_js
    assert "let selectedSearchLimit = 10;" in app_js
    assert 'button.classList.toggle("is-active", option.value === selectedValue);' in app_js
    assert "/analysis/lexical.json" in app_js
    assert "liveLanguageAnalysisEnabled" not in app_js
    assert (
        "if (!liveLanguageAnalysisEnabled) {\n    return loadPublishedLanguagePayload();\n  }"
    ) not in app_js
    assert "return loadPublishedLanguagePayload();" in app_js
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
    assert "clipStatsPollMs = 10000" in app_js
    assert "startClipStatsPolling" in app_js
    assert "pollClipStats" in app_js
    assert "latest_started_at" in app_js
    assert "payload.stats?.latest_playable_started_at || payload.stats?.latest_started_at" in app_js
    assert "|| clips[0]?.started_at" in app_js
    assert '["Feed",' not in app_js
    assert '"Live DB"' not in app_js
    assert '"Published export"' not in app_js
    assert '["Playable clips", clipTotal]' in app_js
    assert '["Clips", clipTotal]' not in app_js
    assert '["Latest clip", latest]' in app_js
    assert "payload.stats?.playable_channel_counts ||" in app_js
    assert 'const clipNoun = filteredTotal === 1 ? "playable clip" : "playable clips";' in app_js
    assert '"Analyzed transcripts"' in app_js
    assert '"Intelligible transcript records; audio may age out"' in app_js
    assert 'languageCard("Transmissions", String(payload.source_clip_count || 0)' not in app_js
    assert "function formatStatValue(label, value)" in app_js
    assert "return Number(value).toLocaleString();" in app_js
    assert 'description.textContent = formatStatValue(label, value);' in app_js
    assert "minmax(142px, 1.35fr)" in styles_css
    assert "renderClipSummaryOnly(currentClipPayload);" in app_js
    assert 'clipList.querySelectorAll(".clip-card[data-clip-id]")' in app_js
    assert "existing?.dataset.clipSignature === signature" in app_js
    assert ".stat.is-live-updated" in styles_css
    assert "loadAndRenderPerformance({ showLoading: false });" in app_js
    assert "startPerformancePolling" in app_js
    assert "stopPerformancePolling" in app_js
    assert "CPU utilization" in app_js
    assert "1-minute load average" not in app_js
    assert "Average over selected window" in app_js
    assert "Ubuntu Micro-Computer" in app_js
    assert "Raspberry Pi Decoder" in app_js
    assert '[["Opti", "Plex ASR Box"].join(""), performanceHostLabel]' in app_js
    assert "OptiPlex ASR Box" not in app_js
    assert "OptiPlex live proxy" not in app_js
    assert "Raspberry Pi edge radio" not in app_js
    assert "Thermals" in app_js
    assert "performance-host-grid" in app_js
    assert "performanceHostPanel" in app_js
    assert "performanceMetricChart" in app_js
    assert "attachPerformanceChartTooltip" in app_js
    assert "performanceChartTimeTicks" in app_js
    assert "performance-chart-x-axis" in app_js
    assert '{ label: "3d", hours: 72 }' in app_js
    assert '{ label: "12h", hours: 12 }' not in app_js
    assert "performance-chart-tooltip" in app_js
    assert "performance-chart-hover-line" in app_js
    assert "performance-chart-hover-dot" in app_js
    assert "performance-chart-grid" in app_js
    assert "performanceRangeOptions" in app_js
    assert "selectedPerformanceRangeHours" in app_js
    assert '{ label: "30m", hours: 0.5 }' in app_js
    assert '{ label: "2h", hours: 2 }' in app_js
    assert '{ label: "24h", hours: 24 }' in app_js
    assert '{ label: "3d", hours: 72 }' in app_js
    assert '{ label: "6h", hours: 6 }' not in app_js
    assert "performance-range-control" in app_js
    assert "loadAsrFeedbackStatus" in app_js
    assert "speech-training-panel" in app_js
    assert "renderSpeechTrainingPanel" in app_js
    assert "Training examples" in app_js
    assert "correctionCount.toLocaleString()" in app_js
    assert "`${correctionCount} / ${minCorrections}`" not in app_js
    assert "trainingReadinessCaption" in app_js
    assert "No new labels since last trained run" in app_js
    assert "Last ASR run" in app_js
    assert ".speech-training-panel" in styles_css
    assert ".speech-training-grid" in styles_css
    assert "cpuUtilizationPercent" in app_js
    assert "memoryUsedPercent" in app_js
    assert "thermalTemperatureC" in app_js
    assert 'document.createElementNS("http://www.w3.org/2000/svg", "svg")' in app_js
    assert ".performance-chart-grid" in styles_css
    assert ".performance-chart-svg" in styles_css
    assert ".performance-chart-tooltip" in styles_css
    assert ".performance-chart-hover-line" in styles_css
    assert ".performance-chart-x-axis" in styles_css
    assert ".performance-chart-x-gridline" in styles_css
    assert ".performance-range-control" in styles_css
    assert ".clip-search-panel" in styles_css
    assert ".clip-search-form" in styles_css
    assert ".clip-search-suggestions" in styles_css
    assert ".search-suggestion-chip" in styles_css
    assert ".clip-search-control .clip-control-group" in styles_css
    assert "width: fit-content;" in styles_css
    assert ".clip-search-control .clip-segmented-control" in styles_css
    assert ".clip-search-control .clip-segment-button" in styles_css
    assert "flex: 0 0 auto;" in styles_css
    assert ".search-result-card" in styles_css
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
    assert 'liveAudio.removeAttribute("src")' in app_js
    assert "closeLiveAudioStream();" in app_js
    assert "Waiting for transmission" in app_js
    assert '"Static"' not in app_js
    assert "static clips" not in app_js
    assert "Tailnet Protected" not in index_html
    assert "loadAndRenderMap" in app_js
    assert 'const aisCatcherFrameUrl = "/ais-catcher/?lat=47.6190158&lon=-122.3595353' in app_js
    assert 'const aisCatcherFallbackUrl = "https://aiscatcher.org/";' in app_js
    assert "renderAisCatcherFrame" in app_js
    assert "aisCatcherFrame.src = aisCatcherFrameUrl;" in app_js
    assert 'aisCatcherFrame.title = "AIS-catcher live map";' in app_js
    assert 'mapStatus.textContent = "Showing AIS-catcher live map";' in app_js
    assert ".tab-panel[hidden]" in styles_css
    assert "/api/ais/tracks" not in app_js
    assert "loadLiveAisSnapshot" not in app_js
    assert "mapPayloadWithLiveAis" not in app_js
    assert "renderAisMapDashboard" not in app_js
    assert "renderVesselMap" not in app_js
    assert "No AIS vessel positions received yet" not in app_js
    assert "Vessel positions in the public manifest" not in app_js
    assert (
        "lexicalAnalysis.replaceChildren(cards, channelPanel, topicPanel, "
        "wordsPanel, entityPanel, educationPanel, referencePanel);"
    ) in app_js
    assert "lexicalAnalysis.replaceChildren(cards, channelPanel, wordsPanel" not in app_js
    assert "lexicalAnalysis.replaceChildren(cards, channelPanel, mapPanel" not in app_js
    assert ".ais-catcher-frame" in styles_css
    assert ".vessel-map-panel" in styles_css
    assert ".nautical-map" not in styles_css
    assert ".vessel-marker" not in styles_css
    assert "ais-catcher-frame" in index_html
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
    assert 'formatCountNoun(vhfCount, "channel", "channels")' in app_js
    assert "VHF channels with at least one analyzed clip" in app_js
    assert "monitoredAnalysisChannels" in app_js
    assert "channelCountsWithMonitoredChannels" in app_js
    assert (
        '["05A", "06", "09", "10", "13", "14", "16", "22A", "65A", "66A", '
        '"67", "68", "69", "71", "72", "73", "74", "77", "78A"]'
        in app_js
    )
    assert "activeAnalyzedChannelCount(channelCounts)" in app_js
    assert "Number(count || 0) > 0" in app_js
    assert ".filter(([, count]) => count > 0)" in app_js


def test_public_site_clip_review_page_size_and_sort_controls() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    index_html = Path("public-site/index.html").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert "const defaultClipPageSize = 6;" in app_js
    assert "const clipPageSizeOptions = [6, 12, 24];" in app_js
    assert "48" not in app_js.partition("const clipPageSizeOptions = [")[2].partition("];")[0]
    assert "let selectedClipPageSize = defaultClipPageSize;" in app_js
    assert "let selectedClipOffset = 0;" in app_js
    assert 'let clipSortDirection = "newest";' in app_js
    assert "const initialRouteState = routeStateFromLocation();" in app_js
    assert "let clipCollectionFilter = initialRouteState.clipCollectionFilter;" in app_js
    assert "limit=${selectedClipPageSize}" in app_js
    assert "featured=true" in app_js
    assert "reviewed=true" in app_js
    assert 'clipReviewedFilter = clipCollectionFilter === "reviewed";' in app_js
    assert 'params.push("reviewed=true");' in app_js
    assert "renderClipDisplayControls()" in app_js
    assert "renderClipDisplayControlSet()" in app_js
    assert "function setClipPageSize(pageSize)" in app_js
    assert "const firstVisibleClipOffset = clipOffset();" in app_js
    assert (
        "selectedClipOffset = firstVisibleClipOffset;"
        in app_js
    )
    assert "function goToClipOffset(offset)" in app_js
    assert "mobileClipDisplayControls()" not in app_js
    assert "const insertAfter = Math.min(6, cards.length);" not in app_js
    assert "clipList.replaceChildren(...clips.map(renderClipCard));" not in app_js
    assert "function clipRenderSignature(clip)" in app_js
    assert "applyClipSortForCurrentPage" in app_js
    assert 'clipSortDirection === "oldest"' in app_js
    assert "let currentPageClips = [];" in app_js
    assert "function renderCurrentClipOrder()" in app_js
    assert 'clipSortDirection = "newest";\n        renderCurrentClipOrder();' in app_js
    assert 'clipSortDirection = "oldest";\n        renderCurrentClipOrder();' in app_js
    assert "selectedClipPage = 1;" in app_js
    assert '"Show clips"' in app_js
    assert '"Hall of fame"' in app_js
    assert '"Reviewed"' in app_js
    assert '"Flip page order"' in app_js
    assert 'id="clip-display-controls"' in index_html
    assert "clip-display-controls" in styles_css
    assert "clip-display-controls-inline" not in styles_css
    assert "clip-segmented-control" in styles_css
    assert "#clip-display-controls {\n    display: none;" not in styles_css
    assert ".clip-display-controls {\n    display: grid;" in styles_css
    assert ".clip-control-group {\n    width: 100%;" in styles_css
    assert ".clip-segment-button {\n    flex: 1 1 0;" in styles_css


def test_public_site_channel_selector_closes_on_outside_interaction() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert "function closeChannelFilterMenu()" in app_js
    assert "function closeChannelFilterOnOutsidePointer(event)" in app_js
    assert "function closeChannelFilterOnOutsideFocus(event)" in app_js
    assert "channelFilter.contains(event.target)" in app_js
    assert 'document.addEventListener("pointerdown", closeChannelFilterOnOutsidePointer);' in app_js
    assert 'document.addEventListener("focusin", closeChannelFilterOnOutsideFocus);' in app_js
    assert 'const menu = channelFilter.querySelector(".channel-filter-menu");' in app_js
    assert "menu.open = false;" in app_js


def test_public_site_prod_degrades_to_published_manifest_before_live_api() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert (
        'const publicAppHosts = new Set(["vhf.robertboscacci.com", '
        '"seattleboatradio.com"]);'
        in app_js
    )
    assert "const publicAppHost = publicAppHosts.has(window.location.hostname);" in app_js
    assert "const publicLiveApiTimeoutMs = 2500;" in app_js
    assert "function shouldLoadPublishedManifestFirst()" in app_js
    assert (
        "return publicAppHost && clipCollectionFilter === "
        '"recent" && selectedChannels.size === 0;'
        in app_js
    )
    assert "const payload = await loadPublishedManifest();" in app_js
    assert "refreshLiveClipPayloadInBackground(requestUrl, requestId);" in app_js
    assert "async function refreshLiveClipPayloadInBackground(requestUrl, requestId)" in app_js
    assert "fetchJsonWithTimeout(requestUrl, { timeoutMs: publicLiveApiTimeoutMs })" in app_js
    assert "function fetchJsonWithTimeout(url, { timeoutMs } = {})" in app_js
    assert "new AbortController()" in app_js
    assert "window.setTimeout(() => controller.abort(), timeoutMs)" in app_js


def test_static_shell_deploy_excludes_cloud_runtime_data_objects() -> None:
    deploy_shell = Path("scripts/deploy_static_shell.sh").read_text(encoding="utf-8")

    assert '--exclude "live/current.m3u8"' in deploy_shell
    assert '--exclude "live/channels.json"' in deploy_shell
    assert '--exclude "live/channels/*"' in deploy_shell
    assert '--exclude "ais/latest.json"' in deploy_shell
    assert "sonic-wake" not in deploy_shell


def test_public_site_analysis_topics_hide_outliers_and_explain_clusters() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert '"BERTopic transcript clusters"' in app_js
    assert "3D BERTopic cluster map" in app_js
    assert "Descriptive counts from the transcript analysis" not in app_js
    assert "Topic intelligence" not in app_js
    assert "Signal fingerprint" not in app_js
    assert "nonOutlierTopics(topics.items || [])" in app_js
    assert 'className = "topic-frame-shell"' in app_js
    assert "topicFrame.allowFullscreen = true" in app_js
    assert 'topicFrame.setAttribute("allow", "fullscreen")' in app_js
    assert "hideUnavailableTopicFrame(topicFrame, topicFrameShell)" in app_js
    assert 'topicFrame.addEventListener("load"' in app_js
    assert "asset not found" in app_js
    assert "renderTopicExamples(topic)" in app_js
    assert "function renderTopicExamples(topic) {" in app_js
    topic_examples_source = app_js[
        app_js.index("function renderTopicExamples(topic) {") : app_js.index(
            "function topicExampleForDisplay(topic) {"
        )
    ]
    assert "renderExamplePlayer" not in topic_examples_source
    assert "renderAnalysisExampleCorrection(reviewExample, quote, wrapper)" in topic_examples_source
    assert ".topic-frame-shell[hidden]" in styles_css
    assert "mobileNlpSummary" not in app_js
    assert "nlpSummaryRows" not in app_js
    assert "Descriptive NLP summary" not in app_js
    assert "Top observed terms" not in app_js
    assert 'termSection("Jargon", terms.semantic_buckets?.communication_markers || [])' in app_js
    assert "topicTitle(topic)" in app_js
    assert "topicKeywordWords(topic)" in app_js
    assert "title.textContent = `${topicTitle(topic)} · ${topic.count || 0}`;" in app_js
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


def test_public_site_analysis_layout_prioritizes_chart_bertopic_and_bottom_references() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    order = app_js[
        app_js.index("lexicalAnalysis.replaceChildren(") : app_js.index(
            "function hideUnavailableTopicFrame"
        )
    ]

    assert (
        "cards, channelPanel, topicPanel, wordsPanel, entityPanel, educationPanel, referencePanel"
        in order
    )
    assert order.index("channelPanel") < order.index("topicPanel")
    assert order.index("topicPanel") < order.index("entityPanel")
    assert order.index("referencePanel") > order.index("educationPanel")


def test_public_site_analysis_examples_use_same_origin_clip_audio() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert "function analysisAudioUrlForClip(clip)" in app_js
    assert "return clipAudioRequestUrl(clip) || audioUrlForClip(clip);" in app_js
    assert "const audioUrl = analysisAudioUrlForClip(example);" in app_js
    assert 'const clipAudioUrl = apiUrl("/api/clips/audio");' in app_js
    assert "renderAnalysisExampleCorrection" in app_js
    assert "analysisTranscriptReviewEnabled && canReviewClip(example)" in app_js
    assert "const analysisTranscriptReviewEnabled = privateAppHost;" in app_js
    assert 'summary.textContent = "Review transcript";' in app_js
    assert "renderTranscriptCorrectionForm(example, transcriptElement, article)" in app_js
    assert ".analysis-correction" in styles_css


def test_public_site_analysis_audio_examples_are_limited_to_entities() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    entity_source = app_js[
        app_js.index("function entityList(entities) {") : app_js.index(
            "function entityExampleWithAudio(entity) {"
        )
    ]
    topic_source = app_js[
        app_js.index("function renderTopicExamples(topic) {") : app_js.index(
            "function topicExampleForDisplay(topic) {"
        )
    ]
    topic_picker_source = app_js[
        app_js.index("function topicExampleForDisplay(topic) {") : app_js.index(
            "function topicTitle(topic) {"
        )
    ]

    assert "renderExamplePlayer(playableExample || {})" in entity_source
    assert "renderAnalysisExampleCorrection(reviewExample, quote, item)" in entity_source
    assert "renderExamplePlayer" not in topic_source
    assert "renderAnalysisExampleCorrection(reviewExample, quote, wrapper)" in topic_source
    assert "analysisAudioUrlForClip" not in topic_picker_source
    assert "return examples[0] || null;" in topic_picker_source


def test_public_site_mobile_pagination_action_labels_stay_centered() -> None:
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert ".pagination-button {\n  display: inline-flex;" in styles_css
    assert "align-items: center;" in styles_css
    assert "justify-content: center;" in styles_css
    assert ".pagination-actions {\n    display: grid;" in styles_css
    assert "grid-template-columns: repeat(auto-fit, minmax(min(104px, 100%), 1fr));" in styles_css
    assert ".pagination-actions .pagination-button {\n    width: 100%;" in styles_css


def test_public_site_clip_pagination_scrolls_on_all_viewports_with_loading_banner() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert "scrollClipListToTopForPagination();" in app_js
    assert "scrollClipListToTopForMobilePagination" not in app_js
    assert "shouldScrollClipListAfterMobilePagination" not in app_js
    assert "renderClipPageLoadingBanner()" in app_js
    assert "clip-page-loading-banner" in app_js
    assert 'banner.setAttribute("role", "status");' in app_js
    assert ".clip-page-loading-banner" in styles_css
    assert "grid-column: 1 / -1;" in styles_css


def test_public_site_has_about_tab_linking_project_writeup() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    index_html = Path("public-site/index.html").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert 'id="tab-about"' in index_html
    assert 'data-tab="about"' in index_html
    assert 'id="panel-about"' in index_html
    assert 'about: "about"' in app_js
    assert 'about: document.querySelector("#panel-about")' in app_js
    assert "Elliott Bay Marine VHF Monitor" in index_html
    assert "https://robertboscacci.com/projects/elliott-bay-vhf/" in index_html
    assert "Raspberry Pi radio edge" in index_html
    assert "Ubuntu micro-computer" in index_html
    assert "OptiPlex" not in index_html
    assert "Whisper" in index_html
    assert "whisper-large-v3-turbo" in index_html
    assert "CTranslate2/faster-whisper" in index_html
    assert "dAISy-catcher receiver" in index_html
    assert "https://github.com/astuder" in index_html
    assert "Adrian Studer" in index_html
    assert "https://github.com/jvde-github" in index_html
    assert "Jasper" in index_html
    assert ".about-panel" in styles_css
    assert ".about-link" in styles_css


def test_public_site_keeps_sonic_wake_off_mainline_shell() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    index_html = Path("public-site/index.html").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert "Sonic Wake" not in index_html
    assert "sonicWake" not in app_js
    assert "sonic-wake" not in app_js
    assert "sonic-wake" not in styles_css


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

    assert 'dot.setAttribute("r", "2.2")' in app_js
    assert ".performance-chart-line" in styles_css
    assert "stroke-width: 1.35;" in styles_css
    assert "stroke-width: 2.4;" not in styles_css


def test_public_site_renders_db_clips_and_static_export_clips() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert "playback_url" in app_js
    assert "audio_public_filename" in app_js
    assert 'const clipPlaybackUrl = apiUrl("/api/clips/playback");' in app_js
    assert "playback_issued_at_ms: Date.now()" in app_js
    assert "shouldRefreshPlaybackUrl" in app_js
    assert "refreshPlaybackUrl" in app_js
    assert "ensureFreshPlaybackUrl" in app_js
    assert "isSignedPlaybackUrl" in app_js
    assert "transcript" in app_js
    assert "transcript_public" in app_js
    assert "transcript_reviewed" in app_js
    assert "featured" in app_js
    assert "renderFeaturedClipAction" in app_js
    assert "saveClipFeature" in app_js
    assert "featureClipWriteEnabled && canReviewClip(clip)" in app_js
    assert "operatorReviewEnabled && canReviewClip(clip)" in app_js
    assert 'button.textContent = featured ? "★" : "☆";' in app_js
    assert (
        'button.setAttribute("aria-label", featured ? '
        '"Remove from Hall of Fame" : "Add to Hall of Fame");'
        in app_js
    )
    assert '"Starred"' not in app_js
    assert "Featured" in app_js
    assert "renderTranscriptCorrectionForm" in app_js
    assert "saveTranscriptCorrection" in app_js
    assert "deleteTranscriptCorrection" in app_js
    assert 'method: "DELETE"' in app_js
    assert "Remove correction" in app_js
    assert (
        'summary.textContent = clip.transcript_reviewed ? "Edit correction" : "Fix transcript";'
        in app_js
    )
    assert 'reviewer: "operator-ui"' in app_js
    assert 'credentials: "include"' in app_js
    assert "operatorWriteHeaders()" in app_js
    assert 'headers["X-TalkingBoats-Tailnet-Dev"] = "1";' in app_js
    assert 'headers: { "Content-Type": "application/json" }' not in app_js
    assert "X-TalkingBoats-Operator-Token" not in app_js
    assert "Saved for manual fine tuning." in app_js
    assert ".transcript-correction" in styles_css
    assert ".remove-correction-button" in styles_css
    assert ".reviewed-pill" in styles_css
    assert ".featured-pill" in styles_css
    assert ".feature-clip-button" in styles_css
    assert "width: 30px;" in styles_css
    assert "height: 30px;" in styles_css
    assert "formatDateTime" in app_js
    assert "channelLabel" in app_js


def test_public_site_uses_same_origin_live_api_urls() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert 'const defaultLiveStreamUrl = apiUrl("/api/live/current.mp3");' in app_js
    assert "liveDspProfile" not in app_js
    assert (
        "return apiUrl(`/api/live/${encodeURIComponent(selectedLiveChannel)}/current.mp3`);"
        in app_js
    )
    assert (
        "return apiUrl(`/api/live/${encodeURIComponent(selectedLiveChannel)}/status`);"
        in app_js
    )
    assert "return withDspProfile(url);" not in app_js


def test_public_site_shows_public_ais_tab() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    index_html = Path("public-site/index.html").read_text(encoding="utf-8")

    assert "aisDashboardEnabled" in app_js
    assert "const aisDashboardEnabled = true;" in app_js
    assert "mapTab.hidden = !aisDashboardEnabled" in app_js
    assert 'name === "map" && !aisDashboardEnabled' in app_js
    assert "panels.map.hidden = !aisDashboardEnabled" in app_js
    assert "renderAisCatcherFrame" in app_js
    assert "aisCatcherFallbackUrl" in app_js
    assert 'aisCatcherFrame.src = aisCatcherFrameUrl;' in app_js
    assert 'aisCatcherFrame.title = "AIS-catcher live map";' in app_js
    assert "if (privateAppHost) {\n    aisCatcherFrame.src = aisCatcherFrameUrl;" not in app_js
    assert re.search(
        r'<button[^>]*id="tab-map"[^>]*type="button"[^>]*data-tab="map"[^>]*hidden',
        index_html,
        flags=re.S,
    )


def test_public_site_cache_busts_app_module() -> None:
    index_html = Path("public-site/index.html").read_text(encoding="utf-8")

    assert '<script src="/assets/app.js?v=' in index_html
    assert '<script src="/assets/app.js" type="module"></script>' not in index_html


def test_public_site_has_indexable_default_metadata_and_json_ld() -> None:
    index_html = Path("public-site/index.html").read_text(encoding="utf-8")

    assert (
        '<meta name="description" content="Live Elliott Bay marine VHF radio audio, '
        "recent receiver clips, transcript search, AIS vessel map, and channel analysis"
        in index_html
    )
    assert '<meta name="robots" content="index,follow,max-image-preview:large" />' in index_html
    assert '<link rel="canonical" href="https://seattleboatradio.com/" />' in index_html
    assert '<link rel="sitemap" type="application/xml" href="/sitemap.xml" />' in index_html
    assert '<link rel="alternate" type="text/plain" href="/llms.txt" title="AI crawler context" />' in index_html
    assert '<meta property="og:url" content="https://seattleboatradio.com/" />' in index_html
    assert '<meta name="twitter:card" content="summary" />' in index_html

    match = re.search(
        r'<script id="site-structured-data" type="application/ld\+json">\s*(.*?)\s*</script>',
        index_html,
        flags=re.S,
    )
    assert match is not None
    graph = json.loads(match.group(1))["@graph"]
    graph_types = {item["@type"] for item in graph}
    assert {"WebSite", "WebApplication", "Dataset"}.issubset(graph_types)
    assert any(item.get("url") == "https://seattleboatradio.com/" for item in graph)
    assert any("VHF" in item.get("description", "") for item in graph)


def test_public_site_exposes_crawlable_internal_links_and_route_metadata() -> None:
    index_html = Path("public-site/index.html").read_text(encoding="utf-8")
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    for href in (
        "/clips/",
        "/hall-of-fame/",
        "/reviewed/",
        "/search/",
        "/live/",
        "/ais/",
        "/analysis/",
        "/about/",
    ):
        assert f'href="{href}"' in index_html

    assert 'role="tablist"' in index_html
    assert 'role="tab"' in index_html
    assert 'role="tabpanel"' in index_html
    assert 'tab.setAttribute("aria-selected", String(tab.dataset.tab === name));' in app_js
    assert "const routeMetadata =" in app_js
    assert "function updateDocumentMetadata(name)" in app_js
    assert "setCanonicalUrl(metadata.url);" in app_js
    assert "updateDocumentMetadata(name);" in app_js
    assert 'reviewed: {' in app_js
    assert 'url: `${siteCanonicalOrigin}/reviewed/`' in app_js


def test_public_site_crawler_files_are_complete_and_conservative() -> None:
    robots = Path("public-site/robots.txt").read_text(encoding="utf-8")
    llms = Path("public-site/llms.txt").read_text(encoding="utf-8")
    sitemap = Path("public-site/sitemap.xml").read_text(encoding="utf-8")

    assert "User-agent: *\nAllow: /" in robots
    assert "Sitemap: https://seattleboatradio.com/sitemap.xml" in robots
    for crawler in (
        "Googlebot",
        "Bingbot",
        "GPTBot",
        "OAI-SearchBot",
        "ChatGPT-User",
        "ClaudeBot",
        "Claude-SearchBot",
        "Claude-User",
    ):
        assert f"User-agent: {crawler}" in robots
        assert f"User-agent: {crawler}\nAllow: /" in robots

    assert llms.startswith("# Elliott Bay VHF\n")
    assert "https://seattleboatradio.com/sitemap.xml" in llms
    assert "https://seattleboatradio.com/analysis/lexical.json" in llms
    assert "Public pages listed here are intentionally crawlable" in llms

    namespace = {"sitemap": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    root = ET.fromstring(sitemap)
    urls = [node.text for node in root.findall("sitemap:url/sitemap:loc", namespace)]
    assert urls == [
        "https://seattleboatradio.com/",
        "https://seattleboatradio.com/clips/",
        "https://seattleboatradio.com/hall-of-fame/",
        "https://seattleboatradio.com/reviewed/",
        "https://seattleboatradio.com/search/",
        "https://seattleboatradio.com/live/",
        "https://seattleboatradio.com/ais/",
        "https://seattleboatradio.com/analysis/",
        "https://seattleboatradio.com/about/",
    ]
    assert "performance" not in sitemap
    assert "operator" not in sitemap


def test_public_site_deploys_and_revalidates_crawler_assets() -> None:
    for path in ("scripts/deploy_static_shell.sh", "scripts/deploy_public_site.sh"):
        script = Path(path).read_text(encoding="utf-8")
        assert "upload_crawler_assets" in script
        assert '--key "${asset_path}"' in script
        assert "text/plain" in script
        assert "application/xml" in script
        assert "--cache-control \"no-store\"" in script
        assert '"reviewed/index.html"' in script
        assert '"reviewed/"' in script
        assert '"reviewed"' in script

    static_shell = Path("scripts/deploy_static_shell.sh").read_text(encoding="utf-8")
    for invalidation_path in ("/robots.txt", "/sitemap.xml", "/llms.txt", "/reviewed", "/reviewed/*"):
        assert f'"{invalidation_path}"' in static_shell


def test_public_site_tabs_have_linkable_routes() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    deploy_shell = Path("scripts/deploy_static_shell.sh").read_text(encoding="utf-8")
    deploy_full = Path("scripts/deploy_public_site.sh").read_text(encoding="utf-8")

    assert 'clips: "clips"' in app_js
    assert 'search: "search"' in app_js
    assert 'live: "live"' in app_js
    assert 'map: "ais"' in app_js
    assert 'language: "analysis"' in app_js
    assert 'performance: "performance"' in app_js
    assert 'about: "about"' in app_js
    assert "fineTuning" not in app_js
    assert "fine-tuning" not in app_js
    assert "routeStateFromLocation()" in app_js
    assert "applyRouteStateFromLocation()" in app_js
    assert "updateTabRoute(name" in app_js
    assert 'window.addEventListener("popstate"' in app_js
    assert (
        "activateTab(initialRouteState.tab, { replaceRoute: true, updateRoute: false })"
        in app_js
    )
    for route in ("clips", "hall-of-fame", "reviewed", "search", "live", "ais", "map", "analysis", "about"):
        assert f'"{route}/index.html"' in deploy_shell
        assert f'"{route}/index.html"' in deploy_full
        assert f'"{route}/"' in deploy_shell
        assert f'"{route}/"' in deploy_full
        assert f'"{route}"' in deploy_shell
        assert f'"{route}"' in deploy_full
    for route in ("performance", "operator"):
        assert f'"{route}/index.html"' in deploy_shell
        assert f'"{route}/index.html"' in deploy_full
        assert f'"{route}/"' in deploy_shell
        assert f'"{route}/"' in deploy_full
        assert f'"{route}"' in deploy_shell
        assert f'"{route}"' in deploy_full
    for script in (deploy_shell, deploy_full):
        assert "dev_only_route_index_paths" in script
        assert "dev_only_route_direct_paths" in script
        assert "prod_retired_route_paths" in script
        assert 'if [[ "${environment}" == "dev" ]]; then' in script
    assert "retired_route_paths" in deploy_shell
    assert "retired_route_paths" in deploy_full
    assert '"fine-tuning/index.html"' in deploy_shell
    assert '"fine-tuning/index.html"' in deploy_full
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
    assert 'audio.preload = "none"' in app_js
    assert 'audio.preload = "metadata"' not in app_js
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
        'liveAudio.removeAttribute("src");\n    liveStatus.textContent = "System controls off";'
    )
    assert system_controls_off_gate not in app_js
    assert ".system-media-toggle" in styles_css


def test_public_site_performance_explains_restricted_asr_feedback() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert (
        "const response = await fetch(asrFeedbackStatusUrl, {\n"
        '    cache: "no-store",\n'
        "    credentials: \"include\",\n"
        "    headers: operatorWriteHeaders(),\n"
        "  });"
    ) in app_js
    assert "asrFeedbackAccessUnavailable" in app_js
    assert "asrFeedbackLoadUnavailable" in app_js
    assert "Tailnet only" in app_js
    assert "Open the tailnet/private app to inspect ASR training examples" in app_js


def test_public_site_transcript_correction_form_collects_training_metadata() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert "training-metadata" in app_js
    assert "include_in_training" in app_js
    assert "training_quality" in app_js
    assert "training_split" in app_js
    assert "training_flags" in app_js
    assert "training_reason" in app_js
    assert (
        "include.checked = !clip.transcript_reviewed || clip.include_in_training !== false;"
        in app_js
    )
    assert 'value: clip.transcript_reviewed ? clip.training_quality || "good" : "good",' in app_js
    assert "static_or_no_speech" in app_js
    assert "truncated_start" in app_js


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
    assert 'const liveQueueUrl = apiUrl("/api/clips/recent?limit=24");' in app_js
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
    assert "markEverythingQueueBackfill(normalizedClips)" in app_js
    assert "Catching up on latest 3 transmissions" in app_js
    assert "Catching up on recent transmission" in app_js
    assert "startLiveWaveformForPlayback();" in app_js
    assert "function queuedLivePlaybackStatus()" in app_js
    assert "isEverythingQueueClipAfterStart(clip)" in app_js
    assert "await pollEverythingQueue({ playIfIdle: false, seedRecent: true });" in app_js
    connect_everything = app_js[
        app_js.index("async function connectEverythingLive()") : app_js.index(
            "function scheduleLiveReconnect()"
        )
    ]
    assert connect_everything.index(
        "await pollEverythingQueue({ playIfIdle: false, seedRecent: true });"
    ) < connect_everything.index("startLiveWaveformForPlayback();")
    assert (
        "if (isQueuedLiveMode()) {\n"
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
    assert "if (isQueuedLiveMode()) {\n    return connectEverythingLive();\n  }" in app_js
    assert (
        "if (isQueuedLiveMode()) {\n    handleEverythingClipEnded();\n    return;\n  }"
    ) in app_js
    assert ".live-queue" in styles_css
    assert ".live-queue-item" in styles_css


def test_public_site_live_audio_uses_compact_primary_channel_selector() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    index_html = Path("public-site/index.html").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert 'id="live-primary-channel-picker"' in index_html
    assert 'class="live-advanced-channel-selector"' in index_html
    assert "More channel controls" in index_html
    assert 'const allButTrafficLiveChannel = "all-but-traffic";' in app_js
    assert "allButTrafficChannelOption()" in app_js
    assert "liveQueueRequestUrl()" in app_js
    assert "queueChannelsForMode()" in app_js
    assert "trafficChannelIds.has(channel.channel)" in app_js
    assert "All but Traffic" in app_js
    assert ".live-primary-channel-picker" in styles_css
    assert ".live-advanced-channel-selector" in styles_css
    assert ".live-channel-picker" in styles_css


def test_public_site_everything_mode_uses_same_origin_audio_for_waveform_samples() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")

    assert 'const clipAudioUrl = apiUrl("/api/clips/audio");' in app_js
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
        "if (isQueuedLiveMode() && everythingQueueEnabled) {\n    return true;\n  }"
    ) in app_js
    assert (
        "if (isQueuedLiveMode() && everythingQueueEnabled) {\n"
        "      startLiveActivityPolling();\n"
        "    } else {\n"
        "      stopLiveActivityPolling();\n"
        "    }"
    ) in app_js
    assert (
        "const shouldPollHiddenEverythingQueue = isQueuedLiveMode() && everythingQueueEnabled;"
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
        "if (liveAudio.src && !isQueuedLiveMode()) {\n"
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
        "formatPlaybackTime(example.duration_seconds, { unknownLabel: unknownPlaybackTimeLabel })"
    ) in app_js
    assert "if (!Number.isFinite(value) || value <= 0)" in app_js
    assert "return unknownLabel;" in app_js
    assert "Number(seconds) || 0" not in app_js


def test_public_site_education_reference_cards_use_aligned_grid_layout() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert ".education-guide-list {\n  display: grid;" in styles_css
    assert "align-items: stretch;" in styles_css
    assert ".education-guide-card:not([open])" in styles_css
    assert "min-height: 128px;" in styles_css
    assert ".education-guide-card summary {\n  display: grid;" in styles_css
    assert "height: 100%;" in styles_css
    assert "grid-template-rows: minmax(2.5em, auto) auto;" in styles_css
    assert "justify-self: end;" in styles_css
    assert 'item.className = "education-card education-card-link";' in app_js
    assert 'item.tabIndex = 0;' in app_js
    assert 'item.setAttribute("role", "link");' in app_js
    assert "openEducationReference(resource);" in app_js
    assert 'cue.textContent = "Open ->";' in app_js
    assert 'action.className = "education-card-action";' in app_js
    assert 'chipRow.className = "education-card-chip-row";' in app_js
    assert 'chip.className = "education-card-chip";' in app_js
    assert 'cue.textContent = "Tap for details";' in app_js
    assert ".education-card-link" in styles_css
    assert ".reference-open-cue" in styles_css
    assert ".education-card-action" in styles_css
    assert ".education-card-chip-row" in styles_css
    assert ".education-card-chip" in styles_css
    assert ".education-guide-card summary:hover" in styles_css
    assert ".education-guide-card summary:focus-visible" in styles_css


def test_public_site_analysis_channel_chart_can_hide_traffic_outlier() -> None:
    app_js = Path("public-site/assets/app.js").read_text(encoding="utf-8")
    styles_css = Path("public-site/assets/styles.css").read_text(encoding="utf-8")

    assert "let hideAnalysisTrafficOutlier = true;" in app_js
    assert "renderAnalysisTrafficToggle()" in app_js
    assert (
        'button.textContent = hideAnalysisTrafficOutlier ? "Show Seattle Traffic" '
        ': "Hide Seattle Traffic";'
    ) in app_js
    assert 'entries = entries.filter(([channel]) => !trafficChannelIds.has(channel));' in app_js
    assert (
        'note.textContent = "Seattle Traffic hidden so the other channels can scale up.";'
        in app_js
    )
    assert ".chart-panel-header" in styles_css
    assert ".analysis-chart-toggle" in styles_css
