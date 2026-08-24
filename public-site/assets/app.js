const clipBatchSize = 24;
const continuousClipPlaybackGapMs = 2000;
const publicAppHosts = new Set(["seattleboatradio.com"]);
const devAppHosts = new Set(["dev.seattleboatradio.com"]);
const publicAppHost = publicAppHosts.has(window.location.hostname);
const devAppHost = devAppHosts.has(window.location.hostname);
const generatedAnalysisHost = publicAppHost || devAppHost;
const localAppHost = ["localhost", "127.0.0.1", ""].includes(window.location.hostname);
const tailnetHostSuffix = ".tailbea63b.ts.net";
const tailnetAppHost = window.location.hostname.endsWith(tailnetHostSuffix);
const privateAppHost = localAppHost || tailnetAppHost || devAppHost;
const quarantineClipLaneEnabled = privateAppHost;
const systemDashboardEnabled = devAppHost || localAppHost || tailnetAppHost;
const privateApiBaseUrl = "";
const publicLiveApiTimeoutMs = 8000;
const clipPlaybackUrl = apiUrl("/api/clips/playback");
const clipAudioUrl = apiUrl("/api/clips/audio");
const clipSearchUrl = apiUrl("/api/clips/search");
const clipFeaturesUrl = apiUrl("/api/clips/features");
const clipArchiveUrl = apiUrl("/api/clips/archive");
const manifestUrl = "/public_manifest.json";
const recentClipsSnapshotUrl = "/recent_clips.json";
const lexicalAnalysisUrl = apiUrl("/api/analysis/lexical");
const lexicalManifestUrl = "/analysis/lexical.json";
const performanceUrl = apiUrl("/api/live/performance");
const aisReceiverStatusUrl = "/ais-catcher/ships.json";
const aisCatcherFrameUrl = "/ais-catcher/?lat=47.6190158&lon=-122.3595353&zoom=13&setcoord=false&welcome=false&tab=map";
const aisCatcherFallbackUrl = "https://aiscatcher.org/";
const topicClusterFallbackUrl = "/analysis/topic_clusters.html";
const topicPlotRotationMessageType = "talkingboats-topic-plot-rotation";
const liveChannelsUrl = apiUrl("/api/live/channels");
const liveQueueUrl = apiUrl(
  "/api/clips/recent?limit=24&include_playback_url=true&verify_playback_exists=false&include_counts=false",
);
const defaultLiveStreamUrl = apiUrl("/api/live/current.mp3");
const systemMediaControlsStorageKey = "talkingboats.systemMediaControls";
const recentClipsCacheKeyPrefix = "talkingboats.recentClipsCache.v1";
const recentClipsCacheMaxAgeMs = 5 * 60 * 1000;
const recentClipPlaceholderLimit = 6;
const searchRecencyOptions = [
  { label: "24h", value: "24h" },
  { label: "7d", value: "7d" },
  { label: "30d", value: "30d" },
  { label: "90d", value: "90d" },
  { label: "All", value: "all" },
];
const searchLimitOptions = [5, 10, 20, 50];
const fallbackSearchSuggestionGroups = [
  {
    label: "Popular terms",
    caption: "Frequent radio words",
    items: [
      { query: "seattle traffic" },
      { query: "roger" },
      { query: "southbound" },
      { query: "northbound" },
      { query: "traffic check" },
    ],
  },
  {
    label: "Common phrases",
    caption: "Useful transcript pairs",
    items: [
      { query: "tug barge" },
      { query: "vessel traffic" },
      { query: "elliott bay" },
      { query: "west waterway" },
      { query: "pilot transfer" },
    ],
  },
  {
    label: "Observed entities",
    caption: "Stations and vessel names",
    items: [
      { query: "Seattle Traffic" },
      { query: "United States Coast Guard" },
      { query: "Tacoma Traffic" },
      { query: "Puget Sound" },
    ],
  },
  {
    label: "Nautical terms",
    caption: "Marine radio vocabulary",
    items: [
      { query: "pan pan" },
      { query: "securite" },
      { query: "bridge to bridge" },
      { query: "tug and tow" },
      { query: "making knots" },
    ],
  },
];
const searchSuggestionGroupLimit = 4;
const searchSuggestionItemLimit = 6;
const systemMediaControlsDefault = defaultSystemMediaControlsEnabled();
const unknownPlaybackTimeLabel = "—";
const everythingLiveChannel = "everything";
const allButTrafficLiveChannel = "all-but-traffic";
const defaultRealtimeLiveChannel = "14";
const everythingInitialQueueLimit = 3;
const everythingCatchUpLabel = "Catching up on latest 3 transmissions";
const trafficChannelIds = new Set(["14"]);
const hallOfFameRouteSegment = "hall-of-fame";
const languageDashboardEnabled = [
  "seattleboatradio.com",
  "dev.seattleboatradio.com",
  "localhost",
  "127.0.0.1",
  "",
].includes(
  window.location.hostname,
);
const performanceDashboardEnabled = systemDashboardEnabled;
const aisDashboardEnabled = true;
const featureClipWriteEnabled = privateAppHost;
const archiveClipDeleteEnabled = privateAppHost;
const tabRouteSegments = {
  clips: "clips",
  search: "search",
  live: "live",
  map: "ais",
  language: "analysis",
  performance: "performance",
  about: "about",
};
const tabRouteAliases = {
  clips: "clips",
  "hall-of-fame": "clips",
  search: "search",
  live: "live",
  ais: "map",
  map: "map",
  analysis: "language",
  language: "language",
  performance: "performance",
  about: "about",
};
const siteCanonicalOrigin = "https://seattleboatradio.com";
const defaultSiteDescription =
  "Live Elliott Bay marine VHF radio audio, recent receiver clips, transcript search, AIS vessel map, and channel analysis.";
const routeMetadata = {
  clips: {
    title: "Recent Elliott Bay VHF Clips",
    description:
      "Recent public Elliott Bay marine VHF receiver clips with transcripts, channel labels, and playback.",
    url: `${siteCanonicalOrigin}/clips/`,
  },
  "hall-of-fame": {
    title: "Elliott Bay VHF Hall of Fame",
    description:
      "Featured public Elliott Bay marine VHF radio clips selected from the receiver archive.",
    url: `${siteCanonicalOrigin}/hall-of-fame/`,
  },
  quarantine: {
    title: "Quarantined Elliott Bay VHF Clips",
    description:
      "Receiver clips held aside by automatic audio and transcript quality checks for operator review.",
    url: `${siteCanonicalOrigin}/clips/?quality=quarantined`,
  },
  search: {
    title: "Elliott Bay VHF Transcript Search",
    description:
      "Semantic search across public Elliott Bay marine VHF transcript meaning, channels, and recent receiver clips.",
    url: `${siteCanonicalOrigin}/search/`,
  },
  live: {
    title: "Live Elliott Bay VHF Audio",
    description:
      "Live Elliott Bay marine VHF receiver audio with current channel state and recent transmission queue.",
    url: `${siteCanonicalOrigin}/live/`,
  },
  map: {
    title: "Elliott Bay AIS Vessel Map",
    description:
      "Local AIS-catcher vessel map for nearby Elliott Bay marine traffic heard by the receiver.",
    url: `${siteCanonicalOrigin}/ais/`,
  },
  language: {
    title: "Elliott Bay VHF Channel Analysis",
    description:
      "Public Elliott Bay marine VHF lexical analysis, channel activity, timing rhythms, and topic clusters.",
    url: `${siteCanonicalOrigin}/analysis/`,
  },
  about: {
    title: "About Elliott Bay VHF",
    description:
      "Project notes for the Elliott Bay marine VHF monitor, radio edge, AIS receiver, processing path, and public app.",
    url: `${siteCanonicalOrigin}/about/`,
  },
  performance: {
    title: "Elliott Bay VHF Performance",
    description: "Dev-only receiver and processing performance telemetry for Elliott Bay VHF.",
    url: `${siteCanonicalOrigin}/performance/`,
  },
};
const liveStatusPollMs = 2000;
const liveActivityPollMs = 15000;
const liveQueuePollMs = 5000;
const liveQueueSeedTimeoutMs = 2500;
const clipStatsInitialPollMs = 5000;
const clipStatsPollMs = 15000;
const clipPlaybackRefreshLeadMs = 45000;
const performanceRefreshMs = 10000;
const quietTransmissionDelayMs = 5000;
const performanceHostLabel = "Ubuntu Micro-Computer";
const fallbackDecoderHostLabel = "Raspberry Pi Decoder";
const legacyPerformanceRoleLabels = new Map([
  [["Opti", "Plex live proxy"].join(""), performanceHostLabel],
  [["Opti", "Plex ASR Box"].join(""), performanceHostLabel],
  [["Raspberry", "Pi", "edge", "radio"].join(" "), fallbackDecoderHostLabel],
]);
const performanceRangeOptions = [
  { label: "30m", hours: 0.5 },
  { label: "2h", hours: 2 },
  { label: "24h", hours: 24 },
  { label: "3d", hours: 72 },
];
const pacificTimeZone = "America/Los_Angeles";
const pacificDateTimeFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: pacificTimeZone,
  month: "short",
  day: "numeric",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZoneName: "short",
});
const performanceDateTimeFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: pacificTimeZone,
  month: "short",
  day: "numeric",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
  second: "2-digit",
  timeZoneName: "short",
});
const performanceDayTickFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: pacificTimeZone,
  month: "short",
  day: "numeric",
  hour: "numeric",
});
const pacificShortTimeFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: pacificTimeZone,
  hour: "numeric",
  minute: "2-digit",
});
const defaultChannelLabels = {
  "05A": "VTS / Port Ops",
  "06": "Intership Safety",
  "09": "Calling / Commercial",
  "10": "Commercial",
  "13": "Bridge-to-bridge",
  "14": "VTS / Seattle Traffic",
  "16": "Distress / Calling",
  "22A": "USCG Liaison",
  "65A": "Port Operations",
  "66A": "Port Operations",
  "67": "Commercial / Bridge",
  "68": "Recreational",
  "69": "Non-commercial",
  "71": "Non-commercial",
  "72": "Ship-to-ship",
  "73": "Port Operations",
  "74": "Port Operations",
  "77": "Ship-to-ship",
  "78A": "Non-commercial",
};
function apiUrl(path) {
  return privateApiBaseUrl ? `${privateApiBaseUrl}${path}` : path;
}

const fallbackManifest = {
  site: {
    title: "Elliott Bay VHF",
    subtitle: "Live Elliott Bay marine VHF audio and recent receiver clips.",
  },
  stats: {
    clip_count: 0,
    channel_counts: {},
    generated_at: null,
  },
  clips: [],
};
const channelColors = {
  "05A": "#78dcca",
  "06": "#67e8f9",
  "09": "#f9a8d4",
  "10": "#c4b5fd",
  "13": "#6ab8ff",
  "14": "#40e0bf",
  "16": "#ff7777",
  "22A": "#f0b85a",
  "65A": "#fcd34d",
  "66A": "#c084fc",
  "67": "#fca5a5",
  "68": "#8bd867",
  "69": "#f58fb2",
  "71": "#a5b4fc",
  "72": "#f7cf5d",
  "73": "#93c5fd",
  "74": "#5eead4",
  "77": "#fda4af",
  "78A": "#86efac",
};

const clipList = document.querySelector("#clips");
const clipPagination = document.querySelector("#clip-pagination");
const clipStatus = document.querySelector("#clip-status");
const clipDisplayControls = document.querySelector("#clip-display-controls");
const clipDatetimeForm = document.querySelector("#clip-datetime-form");
const clipDatetimeInput = document.querySelector("#clip-datetime-input");
const clearClipDatetimeButton = document.querySelector("#clear-clip-datetime");
const channelFilter = document.querySelector("#channel-filter");
const refreshButton = document.querySelector("#refresh-clips");
const stats = document.querySelector("#stats");
const tabs = [...document.querySelectorAll(".tab")];
const tabViewStart = document.querySelector("#tab-view-start");
const languageTab = document.querySelector("#tab-language");
const performanceTab = document.querySelector("#tab-performance");
const mapTab = document.querySelector("#tab-map");
const searchStatus = document.querySelector("#clip-search-status");
const searchForm = document.querySelector("#clip-search-form");
const searchQuery = document.querySelector("#clip-search-query");
const searchRecencyControl = document.querySelector("#clip-search-recency");
const searchLimitControl = document.querySelector("#clip-search-limit");
const searchSuggestions = document.querySelector("#clip-search-suggestions");
const searchResults = document.querySelector("#clip-search-results");
const panels = {
  clips: document.querySelector("#panel-clips"),
  search: document.querySelector("#panel-search"),
  live: document.querySelector("#panel-live"),
  map: document.querySelector("#panel-map"),
  language: document.querySelector("#panel-language"),
  performance: document.querySelector("#panel-performance"),
  about: document.querySelector("#panel-about"),
};
const liveAudio = document.querySelector("#live-audio");
const liveStatus = document.querySelector("#live-status");
const liveLastCommunication = document.querySelector("#live-last-communication");
const liveLatency = document.querySelector("#live-latency");
const liveChannel = document.querySelector("#live-channel");
const livePrimaryChannelPicker = document.querySelector("#live-primary-channel-picker");
const liveChannelPicker = document.querySelector("#live-channel-picker");
const liveQueuePanel = document.querySelector("#live-queue");
const liveFrequency = document.querySelector("#live-frequency");
const liveSignalDot = document.querySelector("#live-signal-dot");
const waveformPanel = document.querySelector("#waveform-panel");
const waveformCanvas = document.querySelector("#waveform-canvas");
const playLiveButton = document.querySelector("#play-live");
const playLiveLabel = playLiveButton?.querySelector(".play-label");
const playLiveSymbol = playLiveButton?.querySelector(".play-symbol");
const systemMediaControlsToggle = document.querySelector("#system-media-controls");
const systemMediaNote = document.querySelector("#system-media-note");
const mapStatus = document.querySelector("#map-status");
const aisCatcherFrame = document.querySelector("#ais-catcher-frame");
const aisCatcherUnavailable = document.querySelector("#ais-catcher-unavailable");
const aisFallbackLink = document.querySelector("#ais-fallback-link");
const languageStatus = document.querySelector("#language-status");
const lexicalAnalysis = document.querySelector("#lexical-analysis");
const performanceStatus = document.querySelector("#performance-status");
const performanceDashboard = document.querySelector("#performance-dashboard");
const clipsTitle = document.querySelector("#clips-title");

let liveRetryTimer = null;
let liveStatusTimer = null;
let liveActivityTimer = null;
let liveStatusAbortController = null;
let liveActivityAbortController = null;
let lastLiveStatusId = null;
let latestLiveStatus = null;
let lastCommunicationByChannel = {};
let liveQueue = [];
let liveQueueSeenClipIds = new Set();
let currentLiveQueueClip = null;
let everythingQueueEnabled = false;
let everythingQueueStartedAtMs = 0;
let everythingQueueSeeded = false;
let everythingCatchUpHandoffPending = false;
let liveQueueModeGeneration = 0;
let audioContext = null;
let analyser = null;
let analyserSource = null;
let waveformData = null;
let waveformAnimationId = null;
let currentClipPlayback = null;
let continuousClipPlaybackActive = false;
let continuousClipPlaybackGeneration = 0;
let continuousClipPlaybackTimer = null;
let continuousClipPlaybackIndex = -1;
let continuousClipPlaybackAudio = null;
let continuousClipPlaybackPhase = "idle";
let continuousClipPlaybackMessage = "";
const maxConcurrentClipWaveformLoads = 2;
const maxClipWaveformAudioBytes = 12 * 1024 * 1024;
const clipAudioPlayActions = new WeakMap();
const clipWaveformStates = new WeakMap();
const clipWaveformLoadQueue = [];
let activeClipWaveformLoads = 0;
let clipWaveformObserver = null;
let clipWaveformResizeObserver = null;
let quietSince = null;
let selectedChannels = new Set();
let selectedChannelPreset = "all";
let selectedClipPage = 1;
let selectedClipOffset = 0;
let selectedClipPageSize = clipBatchSize;
let clipSortDirection = "newest";
let selectedClipAround = "";
const initialRouteState = routeStateFromLocation();
let clipCollectionFilter = initialRouteState.clipCollectionFilter;
let currentClipPayload = null;
let currentPageClips = [];
let currentFilteredTotal = 0;
let clipRequestSequence = 0;
let clipPayloadAbortController = null;
let nextClipCursor = null;
let clipLoadMorePending = false;
let clipLoadMoreObserver = null;
let clipStatsTimer = null;
let clipStatsAbortController = null;
let globalClipStats = null;
let lastRenderedClipTotal = null;
let selectedLiveChannel = everythingLiveChannel;
let activeTab = initialRouteState.tab;
let mapPayloadLoaded = false;
let languagePayloadLoaded = false;
let performancePayloadLoaded = false;
let performanceRefreshTimer = null;
let latestPerformancePayload = null;
let latestLanguagePayload = null;
let hideAnalysisTrafficOutlier = true;
let selectedPerformanceRangeHours = 2;
let selectedSearchRecency = "7d";
let selectedSearchLimit = 10;
let latestSearchPayload = null;
let latestSearchSuggestions = null;
let searchSuggestionsLoaded = false;
let searchRequestSequence = 0;
let searchAbortController = null;
let systemMediaControlsEnabled = initialSystemMediaControlsEnabled();
let liveChannelsLoaded = false;
let liveChannels = [
  {
    channel: "05A",
    label: defaultChannelLabels["05A"],
    frequencyMhz: "156.250",
    streamPath: "/api/live/05A/current.mp3",
    statusPath: "/api/live/05A/status",
  },
  {
    channel: "06",
    label: defaultChannelLabels["06"],
    frequencyMhz: "156.300",
    streamPath: "/api/live/06/current.mp3",
    statusPath: "/api/live/06/status",
  },
  {
    channel: "09",
    label: defaultChannelLabels["09"],
    frequencyMhz: "156.450",
    streamPath: "/api/live/09/current.mp3",
    statusPath: "/api/live/09/status",
  },
  {
    channel: "10",
    label: defaultChannelLabels["10"],
    frequencyMhz: "156.500",
    streamPath: "/api/live/10/current.mp3",
    statusPath: "/api/live/10/status",
  },
  {
    channel: "13",
    label: defaultChannelLabels["13"],
    frequencyMhz: "156.650",
    streamPath: "/api/live/13/current.mp3",
    statusPath: "/api/live/13/status",
  },
  {
    channel: "14",
    label: defaultChannelLabels["14"],
    frequencyMhz: "156.700",
    streamPath: defaultLiveStreamUrl,
    statusPath: "/api/live/14/status",
  },
  {
    channel: "16",
    label: defaultChannelLabels["16"],
    frequencyMhz: "156.800",
    streamPath: "/api/live/16/current.mp3",
    statusPath: "/api/live/16/status",
  },
  {
    channel: "22A",
    label: defaultChannelLabels["22A"],
    frequencyMhz: "157.100",
    streamPath: "/api/live/22A/current.mp3",
    statusPath: "/api/live/22A/status",
  },
  {
    channel: "65A",
    label: defaultChannelLabels["65A"],
    frequencyMhz: "156.275",
    streamPath: "/api/live/65A/current.mp3",
    statusPath: "/api/live/65A/status",
  },
  {
    channel: "66A",
    label: defaultChannelLabels["66A"],
    frequencyMhz: "156.325",
    streamPath: "/api/live/66A/current.mp3",
    statusPath: "/api/live/66A/status",
  },
  {
    channel: "67",
    label: defaultChannelLabels["67"],
    frequencyMhz: "156.375",
    streamPath: "/api/live/67/current.mp3",
    statusPath: "/api/live/67/status",
  },
  {
    channel: "68",
    label: defaultChannelLabels["68"],
    frequencyMhz: "156.425",
    streamPath: "/api/live/68/current.mp3",
    statusPath: "/api/live/68/status",
  },
  {
    channel: "69",
    label: defaultChannelLabels["69"],
    frequencyMhz: "156.475",
    streamPath: "/api/live/69/current.mp3",
    statusPath: "/api/live/69/status",
  },
  {
    channel: "71",
    label: defaultChannelLabels["71"],
    frequencyMhz: "156.575",
    streamPath: "/api/live/71/current.mp3",
    statusPath: "/api/live/71/status",
  },
  {
    channel: "72",
    label: defaultChannelLabels["72"],
    frequencyMhz: "156.625",
    streamPath: "/api/live/72/current.mp3",
    statusPath: "/api/live/72/status",
  },
  {
    channel: "73",
    label: defaultChannelLabels["73"],
    frequencyMhz: "156.675",
    streamPath: "/api/live/73/current.mp3",
    statusPath: "/api/live/73/status",
  },
  {
    channel: "74",
    label: defaultChannelLabels["74"],
    frequencyMhz: "156.725",
    streamPath: "/api/live/74/current.mp3",
    statusPath: "/api/live/74/status",
  },
  {
    channel: "77",
    label: defaultChannelLabels["77"],
    frequencyMhz: "156.875",
    streamPath: "/api/live/77/current.mp3",
    statusPath: "/api/live/77/status",
  },
  {
    channel: "78A",
    label: defaultChannelLabels["78A"],
    frequencyMhz: "156.925",
    streamPath: "/api/live/78A/current.mp3",
    statusPath: "/api/live/78A/status",
  },
];
let currentChannelLabels = { ...defaultChannelLabels };

if (languageTab) {
  languageTab.hidden = !languageDashboardEnabled;
}
if (performanceTab) {
  performanceTab.hidden = !performanceDashboardEnabled;
}
if (mapTab) {
  mapTab.hidden = !aisDashboardEnabled;
}
if (panels.map && !aisDashboardEnabled) {
  panels.map.hidden = true;
}

configureLiveAudioElement();
clearBrowserMediaSession();
updateSystemMediaControlsUi();
renderSearchControls();

function closeChannelFilterMenu() {
  const menu = channelFilter.querySelector(".channel-filter-menu");
  if (menu) {
    menu.open = false;
  }
}

function closeChannelFilterOnOutsidePointer(event) {
  if (event.target instanceof Node && channelFilter.contains(event.target)) {
    return;
  }
  closeChannelFilterMenu();
}

function closeChannelFilterOnOutsideFocus(event) {
  if (event.target instanceof Node && channelFilter.contains(event.target)) {
    return;
  }
  closeChannelFilterMenu();
}

refreshButton?.addEventListener("click", () => {
  if (activeTab === "performance") {
    loadAndRenderPerformance({ showLoading: false });
  } else if (activeTab === "map") {
    loadAndRenderMap({ showLoading: false });
  } else {
    loadAndRender({ useCachedPayload: false });
  }
});

searchForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  performClipSearch();
});

searchQuery?.addEventListener("input", () => {
  if (activeTab === "search" && !searchQuery.value.trim()) {
    latestSearchPayload = null;
    searchStatus.textContent = "Ready";
    renderEmptySearchState();
  }
});

clipDatetimeForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!clipDatetimeInput?.value) {
    clipDatetimeInput?.reportValidity();
    return;
  }
  selectedClipAround = clipDatetimeInput.value;
  clipSortDirection = "newest";
  resetClipPagination();
  updateClipDatetimeNavigator();
  loadAndRender({ useCachedPayload: false, includeCounts: false });
});

clearClipDatetimeButton?.addEventListener("click", () => {
  selectedClipAround = "";
  clipSortDirection = "newest";
  clipDatetimeInput.value = "";
  resetClipPagination();
  updateClipDatetimeNavigator();
  loadAndRender({ useCachedPayload: false, includeCounts: false });
});

channelFilter.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target : null;
  const action = target?.closest(".channel-filter-action");
  if (!action || !channelFilter.contains(action)) {
    return;
  }
  if (action.dataset.preset === "all-but-traffic") {
    selectAllButTrafficChannels(action.dataset.channels || "");
    selectedChannelPreset = "all-but-traffic";
  } else {
    selectedChannels.clear();
    selectedChannelPreset = "all";
  }
  resetClipPagination();
  loadAndRender({ includeCounts: false });
});

channelFilter.addEventListener("change", (event) => {
  const input = event.target instanceof HTMLInputElement ? event.target : null;
  if (!input?.classList.contains("channel-filter-checkbox")) {
    return;
  }
  const channel = input.dataset.channel;
  if (!channel) {
    return;
  }
  if (input.checked) {
    selectedChannels.add(channel);
  } else {
    selectedChannels.delete(channel);
  }
  selectedChannelPreset = selectedChannels.size ? "custom" : "all";
  resetClipPagination();
  loadAndRender();
});

document.addEventListener("pointerdown", closeChannelFilterOnOutsidePointer);
document.addEventListener("focusin", closeChannelFilterOnOutsideFocus);

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    activateTab(tab.dataset.tab, { scrollToTab: true });
  });
});

playLiveButton.addEventListener("click", () => {
  toggleLivePlayback();
});

systemMediaControlsToggle?.addEventListener("change", () => {
  setSystemMediaControlsEnabled(systemMediaControlsToggle.checked);
});

document.addEventListener("visibilitychange", () => {
  if (document.hidden && !shouldPreserveLiveAudioSession()) {
    stopAllAudio();
  }
});

window.addEventListener("pagehide", () => {
  if (!shouldPreserveLiveAudioSession()) {
    stopAllAudio();
  }
});

window.addEventListener("popstate", () => {
  applyRouteStateFromLocation();
});

liveAudio.addEventListener("playing", () => {
  liveStatus.textContent = isQueuedLiveMode()
    ? currentLiveQueueClip?.catch_up
      ? "Catching up on recent transmission"
      : "Playing queued transmission"
    : "Streaming";
  setLivePlayButton("pause");
  updateLiveMediaSession("playing");
});

liveAudio.addEventListener("waiting", () => {
  liveStatus.textContent = queuedLivePlaybackStatus() || "Buffering";
});

liveAudio.addEventListener("pause", () => {
  if (isQueuedLiveMode() && everythingQueueEnabled) {
    renderEverythingQueuePanel();
    return;
  }
  setLivePlayButton("play");
  liveStatus.textContent = "Paused";
  updateLiveMediaSession("paused");
});

liveAudio.addEventListener("error", () => {
  if (isQueuedLiveMode()) {
    handleEverythingClipEnded();
    return;
  }
  liveStatus.textContent = "Reconnecting";
  updateLiveMediaSession("none");
  scheduleLiveReconnect();
});

liveAudio.addEventListener("ended", () => {
  if (isQueuedLiveMode()) {
    handleEverythingClipEnded();
    return;
  }
  liveStatus.textContent = "Reconnecting";
  updateLiveMediaSession("none");
  scheduleLiveReconnect();
});

async function loadAndRender({
  useCachedPayload = true,
  includeCounts = false,
} = {}) {
  const requestId = ++clipRequestSequence;
  const requestUrl = clipRequestUrl(selectedClipPage, { includeCounts });
  clipPayloadAbortController?.abort();
  const requestAbortController = new AbortController();
  clipPayloadAbortController = requestAbortController;
  const livePayloadPromise = loadClipPayload(requestUrl, {
    allowFallback: !selectedClipAround,
    signal: requestAbortController.signal,
  });
  const cachedPayload = useCachedPayload ? loadCachedRecentClipPayload(requestUrl) : null;
  if (cachedPayload) {
    currentClipPayload = includeCounts ? cachedPayload : payloadWithRetainedClipStats(cachedPayload, currentClipPayload);
    renderSite(currentClipPayload);
    clipList.setAttribute("aria-busy", "true");
    clipStatus.textContent = `${clipStatus.textContent} · refreshing`;
  } else if (useCachedPayload && shouldLoadPublishedManifestFirst()) {
    renderClipLoadingState();
    await renderPublishedClipsWhileRefreshing(requestId);
  } else if (!currentClipPayload || !currentPageClips.length) {
    renderClipLoadingState();
  } else {
    renderClipPagePendingState();
  }
  let payload;
  try {
    payload = await livePayloadPromise;
  } catch (error) {
    if (error.name === "AbortError") {
      return;
    }
    renderClipLoadFailure(error);
    return;
  } finally {
    if (clipPayloadAbortController === requestAbortController) {
      clipPayloadAbortController = null;
    }
  }
  if (requestId !== clipRequestSequence) {
    return;
  }
  if (!includeCounts) {
    payload = payloadWithRetainedClipStats(payload, currentClipPayload);
  }
  currentClipPayload = payload;
  renderSite(payload);
  if (payload.source === "live") {
    storeRecentClipPayload(requestUrl, payload);
  }
}

function shouldLoadPublishedManifestFirst() {
  return (
    currentClipPayload === null &&
    clipCollectionFilter === "recent" &&
    clipSortDirection === "newest" &&
    selectedClipPage === 1 &&
    selectedChannels.size === 0 &&
    selectedChannelPreset === "all" &&
    !selectedClipAround
  );
}

async function renderPublishedClipsWhileRefreshing(requestId) {
  const publishedPayload = await loadPublishedManifest();
  if (
    requestId !== clipRequestSequence ||
    currentClipPayload !== null ||
    !(publishedPayload.clips || []).length
  ) {
    return false;
  }
  currentClipPayload = publishedPayload;
  renderSite(currentClipPayload);
  clipList.setAttribute("aria-busy", "true");
  clipStatus.textContent = `${clipStatus.textContent} · refreshing`;
  return true;
}

async function loadMoreClips() {
  if (
    clipLoadMorePending ||
    !nextClipCursor ||
    !currentClipPayload ||
    currentClipPayload.source !== "live"
  ) {
    return;
  }
  clipLoadMorePending = true;
  renderClipPagination(currentFilteredTotal, { pending: true });
  const requestId = clipRequestSequence;
  const cursor = nextClipCursor;
  const requestUrl = clipRequestUrl(1, { includeCounts: false, cursor });
  try {
    const payload = await loadClipPayload(requestUrl, { allowFallback: false });
    if (requestId !== clipRequestSequence || cursor !== nextClipCursor) {
      return;
    }
    const existingIds = new Set(
      (currentClipPayload.clips || []).map((clip) => clipDomId(clip)),
    );
    const appended = (payload.clips || []).filter(
      (clip) => !existingIds.has(clipDomId(clip)),
    );
    currentClipPayload = payloadWithRetainedClipStats(
      {
        ...payload,
        clips: [...(currentClipPayload.clips || []), ...appended],
      },
      currentClipPayload,
    );
    renderSite(currentClipPayload);
  } catch (error) {
    if (error.name !== "AbortError") {
      renderClipPagination(currentFilteredTotal, { loadError: true });
    }
  } finally {
    clipLoadMorePending = false;
  }
}

async function loadClipPayload(requestUrl = clipRequestUrl(), { allowFallback = true, signal = null } = {}) {
  try {
    const payload = await fetchJsonWithTimeout(requestUrl, {
      timeoutMs: publicAppHost ? publicLiveApiTimeoutMs : 0,
      signal,
    });
    const normalizedPayload = normalizeLivePayload(payload);
    const requestedAround = new URL(requestUrl, window.location.href).searchParams.has("around");
    if (requestedAround && !normalizedPayload.around) {
      throw new Error("clip API does not support datetime navigation");
    }
    return normalizedPayload;
  } catch (error) {
    if (error.name === "AbortError") {
      throw error;
    }
    if (!allowFallback) {
      throw error;
    }
    return loadPublishedManifest();
  }
}

async function fetchJsonWithTimeout(url, { timeoutMs, signal = null } = {}) {
  const controller = new AbortController();
  const abortFromParent = () => controller.abort();
  if (signal?.aborted) {
    controller.abort();
  } else if (signal) {
    signal.addEventListener("abort", abortFromParent, { once: true });
  }
  const timeoutId =
    Number(timeoutMs) > 0
      ? window.setTimeout(() => controller.abort(), timeoutMs)
      : null;
  try {
    const response = await fetch(url, { cache: "no-store", signal: controller.signal });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return response.json();
  } finally {
    if (timeoutId) {
      window.clearTimeout(timeoutId);
    }
    if (signal) {
      signal.removeEventListener("abort", abortFromParent);
    }
  }
}

function renderSearchControls() {
  renderSegmentedSearchControl(searchRecencyControl, "Recency", searchRecencyOptions, selectedSearchRecency, (value) => {
    selectedSearchRecency = value;
    renderSearchControls();
    if (searchQuery?.value.trim()) {
      performClipSearch();
    }
  });
  renderSegmentedSearchControl(
    searchLimitControl,
    "Top N",
    searchLimitOptions.map((value) => ({ label: String(value), value: String(value) })),
    String(selectedSearchLimit),
    (value) => {
      selectedSearchLimit = Number(value);
      renderSearchControls();
      if (searchQuery?.value.trim()) {
        performClipSearch();
      }
    },
  );
}

function renderSegmentedSearchControl(container, labelText, options, selectedValue, onSelect) {
  if (!container) {
    return;
  }
  const group = document.createElement("div");
  group.className = "clip-control-group";
  const label = document.createElement("span");
  label.className = "clip-control-label";
  label.textContent = labelText;
  const segmented = document.createElement("div");
  segmented.className = "clip-segmented-control";
  options.forEach((option) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "clip-segment-button";
    button.textContent = option.label;
    button.classList.toggle("is-active", option.value === selectedValue);
    button.setAttribute("aria-pressed", String(option.value === selectedValue));
    button.addEventListener("click", () => onSelect(option.value));
    segmented.append(button);
  });
  group.append(label, segmented);
  container.replaceChildren(group);
}

async function loadAndRenderSearchSuggestions() {
  if (!searchSuggestions || searchSuggestionsLoaded) {
    return;
  }
  renderSearchSuggestions(latestSearchSuggestions || fallbackSearchSuggestionGroups);
  try {
    const payload = latestLanguagePayload || (await loadLanguagePayload());
    latestLanguagePayload = payload;
    latestSearchSuggestions = searchSuggestionGroupsFromPayload(payload);
    searchSuggestionsLoaded = true;
    if (!latestSearchPayload && !searchQuery?.value.trim()) {
      renderSearchSuggestions(latestSearchSuggestions);
    }
  } catch {
    latestSearchSuggestions = fallbackSearchSuggestionGroups;
    searchSuggestionsLoaded = true;
  }
}

function renderSearchSuggestions(groups = fallbackSearchSuggestionGroups) {
  if (!searchSuggestions) {
    return;
  }
  const visibleGroups = groups.filter((group) => Array.isArray(group.items) && group.items.length).slice(0, searchSuggestionGroupLimit);
  if (!visibleGroups.length) {
    searchSuggestions.hidden = true;
    searchSuggestions.replaceChildren();
    return;
  }
  searchSuggestions.hidden = false;
  const heading = document.createElement("div");
  heading.className = "search-suggestion-heading";
  const title = document.createElement("h3");
  title.textContent = "Search starters";
  const note = document.createElement("p");
  note.textContent = "Pulled from frequent transcript terms, entities, and marine vocabulary.";
  heading.append(title, note);
  const grid = document.createElement("div");
  grid.className = "search-suggestion-grid";
  grid.append(...visibleGroups.map(renderSearchSuggestionGroup));
  searchSuggestions.replaceChildren(heading, grid);
}

function renderSearchSuggestionGroup(group) {
  const card = document.createElement("article");
  card.className = "search-suggestion-group";
  const label = document.createElement("p");
  label.className = "language-label";
  label.textContent = group.label;
  const caption = document.createElement("span");
  caption.className = "search-suggestion-caption";
  caption.textContent = group.caption || "";
  const chips = document.createElement("div");
  chips.className = "search-suggestion-chips";
  chips.append(
    ...group.items.slice(0, searchSuggestionItemLimit).map((item) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "search-suggestion-chip";
      const label = document.createElement("span");
      label.textContent = item.query;
      button.append(label);
      button.addEventListener("click", () => applySearchSuggestion(item.query));
      if (Number.isFinite(Number(item.count)) && Number(item.count) > 0) {
        const count = document.createElement("span");
        count.className = "search-suggestion-count";
        count.setAttribute("aria-hidden", "true");
        count.textContent = Number(item.count).toLocaleString();
        button.append(count);
      }
      return button;
    }),
  );
  card.append(label, caption, chips);
  return card;
}

function searchSuggestionGroupsFromPayload(payload) {
  const terms = payload?.terms || {};
  const buckets = terms.semantic_buckets || {};
  const groups = [
    {
      label: "Popular terms",
      caption: "Frequent radio words",
      items: uniqueSearchSuggestions([
        ...(buckets.communication_markers || []),
        ...(buckets.movement || []),
        ...(buckets.places || []),
        ...(buckets.vessel_types || []),
      ]),
    },
    {
      label: "Common phrases",
      caption: "Useful transcript pairs",
      items: uniqueSearchSuggestions(terms.bigrams || []),
    },
    {
      label: "Observed entities",
      caption: "Stations and vessel names",
      items: uniqueSearchSuggestions(payload?.entities || []),
    },
    ...fallbackSearchSuggestionGroups.filter((group) => group.label === "Nautical terms"),
  ];
  return groups.map((group, index) => ({
    ...fallbackSearchSuggestionGroups[index],
    ...group,
    items: group.items.length ? group.items : fallbackSearchSuggestionGroups[index]?.items || [],
  }));
}

function uniqueSearchSuggestions(items) {
  const seen = new Set();
  const suggestions = [];
  for (const item of items) {
    const query = searchSuggestionText(item);
    if (!query) {
      continue;
    }
    const key = query.toLowerCase();
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    suggestions.push({ query, count: Number(item?.count || 0) });
    if (suggestions.length >= searchSuggestionItemLimit) {
      break;
    }
  }
  return suggestions;
}

function searchSuggestionText(item) {
  if (typeof item === "string") {
    return item.trim();
  }
  return String(item?.term || item?.name || item?.label || item?.text || "").trim();
}

function applySearchSuggestion(query) {
  if (!searchQuery) {
    return;
  }
  searchQuery.value = query;
  searchQuery.focus();
  performClipSearch();
}

async function performClipSearch() {
  if (!searchQuery || !searchStatus || !searchResults) {
    return;
  }
  const query = searchQuery.value.trim();
  if (!query) {
    searchAbortController?.abort();
    searchAbortController = null;
    searchRequestSequence += 1;
    searchStatus.textContent = "Enter a search string";
    renderEmptySearchState();
    return;
  }
  searchAbortController?.abort();
  const requestAbortController = new AbortController();
  searchAbortController = requestAbortController;
  const requestId = ++searchRequestSequence;
  searchStatus.textContent = "Searching clips...";
  if (searchSuggestions) {
    searchSuggestions.hidden = true;
  }
  searchResults.setAttribute("aria-busy", "true");
  searchResults.replaceChildren(...renderClipPlaceholders().slice(0, Math.min(3, selectedSearchLimit)));
  try {
    const params = new URLSearchParams({
      q: query,
      limit: String(selectedSearchLimit),
      recency: selectedSearchRecency,
    });
    const response = await fetch(`${clipSearchUrl}?${params.toString()}`, {
      cache: "no-store",
      signal: requestAbortController.signal,
    });
    if (!response.ok) {
      const error = new Error(`clip search HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    const payload = await response.json();
    if (requestId !== searchRequestSequence) {
      return;
    }
    latestSearchPayload = payload;
    renderSearchResults(payload);
  } catch (error) {
    if (error.name === "AbortError") {
      return;
    }
    if (requestId !== searchRequestSequence) {
      return;
    }
    const failure = clipSearchFailureContent(error);
    searchResults.removeAttribute("aria-busy");
    searchResults.replaceChildren(emptySearchMessage(failure.message));
    searchStatus.textContent = failure.status;
    if (searchSuggestions) {
      searchSuggestions.hidden = false;
      renderSearchSuggestions(latestSearchSuggestions || fallbackSearchSuggestionGroups);
    }
  } finally {
    if (searchAbortController === requestAbortController) {
      searchAbortController = null;
    }
  }
}

function clipSearchFailureContent(error) {
  const status = Number(error?.status || 0);
  if (status === 504) {
    return {
      status: "Search is warming up",
      message: "The transcript search is warming up. Try the same search again in a moment.",
    };
  }
  if (status === 503) {
    return {
      status: "Search index is rebuilding",
      message: "The transcript search index is rebuilding. Try again soon.",
    };
  }
  return {
    status: "Search temporarily unavailable",
    message: "Recent clips are still available while transcript search recovers.",
  };
}

function renderEmptySearchState() {
  if (!searchStatus || !searchResults) {
    return;
  }
  searchResults.removeAttribute("aria-busy");
  searchResults.replaceChildren(emptySearchMessage("Enter a search string to find related clips."));
  renderSearchSuggestions(latestSearchSuggestions || fallbackSearchSuggestionGroups);
  loadAndRenderSearchSuggestions();
}

function renderSearchResults(payload) {
  if (!searchStatus || !searchResults) {
    return;
  }
  const results = Array.isArray(payload?.results) ? payload.results : [];
  searchResults.removeAttribute("aria-busy");
  if (searchSuggestions) {
    searchSuggestions.hidden = true;
  }
  if (!results.length) {
    searchResults.replaceChildren(emptySearchMessage("No matching clips in that window."));
    searchStatus.textContent = `No matches for "${payload?.query || ""}"`;
    return;
  }
  searchResults.replaceChildren(...results.map(renderSearchResultCard));
  searchStatus.textContent = `${formatCountNoun(results.length, "semantic match", "semantic matches")} · ${searchRecencyLabel(payload?.recency)}`;
}

function renderSearchResultCard(result) {
  const clip = {
    channel: result.channel,
    channel_label: result.channel_label,
    started_at: result.started_at,
    ended_at: result.ended_at,
    duration_seconds: result.duration_seconds,
    transcript_public: result.transcript || "",
  };
  const article = renderClipCard(clip);
  article.classList.add("search-result-card");
  const score = renderPill(`${Math.round(Number(result.score || 0) * 100)}% match`);
  score.classList.add("search-score-pill");
  article.querySelector(".clip-meta")?.append(score);
  return article;
}

function emptySearchMessage(text) {
  const empty = document.createElement("p");
  empty.className = "muted-inline";
  empty.textContent = text;
  return empty;
}

function searchRecencyLabel(value) {
  return (
    {
      "24h": "last 24h",
      "7d": "last 7d",
      "30d": "last 30d",
      "90d": "last 90d",
      all: "all indexed clips",
    }[value] || "last 7d"
  );
}

function renderClipLoadingState() {
  renderClipDisplayControls();
  if (clipPagination) {
    clipPagination.hidden = true;
    clipPagination.replaceChildren();
  }
  clipList.setAttribute("aria-busy", "true");
  clipList.replaceChildren(...renderClipPlaceholders());
  clipStatus.textContent = selectedClipAround
    ? "Loading clips by date and time..."
    : "Loading recent clips...";
}

function renderClipLoadFailure(_error) {
  clipList.setAttribute("aria-busy", "false");
  const empty = document.createElement("div");
  empty.className = "empty";
  empty.textContent = selectedClipAround
    ? "Clips for that date and time are temporarily unavailable. Try again."
    : "Recent clips are temporarily unavailable. Try again.";
  clipList.replaceChildren(empty);
  clipStatus.textContent = "Clip loading failed";
  renderClipPagination(0);
}

function renderClipPagePendingState() {
  renderClipDisplayControls();
  if (currentFilteredTotal > 0) {
    renderClipPagination(currentFilteredTotal, { pending: true });
  }
  clipList.setAttribute("aria-busy", "true");
  clipStatus.textContent = `Loading page ${selectedClipPage}...`;
  renderClipPageLoadingBanner();
}

function renderClipPageLoadingBanner() {
  let banner = clipList.querySelector(".clip-page-loading-banner");
  if (!banner) {
    banner = document.createElement("div");
    banner.className = "clip-page-loading-banner";
    banner.setAttribute("role", "status");
    banner.setAttribute("aria-live", "polite");
  }
  banner.textContent = `Loading page ${selectedClipPage}...`;
  if (clipList.firstElementChild !== banner) {
    clipList.prepend(banner);
  }
}

function renderClipPlaceholders() {
  const placeholderCount = Math.max(3, Math.min(selectedClipPageSize, recentClipPlaceholderLimit));
  return Array.from({ length: placeholderCount }, (_value, index) => {
    const placeholder = document.createElement("article");
    placeholder.className = "clip-placeholder";
    placeholder.setAttribute("aria-hidden", "true");
    placeholder.dataset.placeholderIndex = String(index + 1);
    const meta = document.createElement("div");
    meta.className = "clip-placeholder-meta";
    meta.append(clipPlaceholderLine("short"), clipPlaceholderLine("time"));
    const title = clipPlaceholderLine("title");
    const transcript = clipPlaceholderLine("transcript");
    const audio = clipPlaceholderLine("audio");
    placeholder.append(meta, title, transcript, audio);
    return placeholder;
  });
}

function clipPlaceholderLine(kind) {
  const line = document.createElement("span");
  line.className = `clip-placeholder-line is-${kind}`;
  return line;
}

function loadCachedRecentClipPayload(requestUrl) {
  try {
    const raw = window.localStorage.getItem(recentClipsCacheKey(requestUrl));
    if (!raw) {
      return null;
    }
    const cached = JSON.parse(raw);
    const cachedAtMs = Number(cached.cached_at_ms || 0);
    if (!cachedAtMs || Date.now() - cachedAtMs > recentClipsCacheMaxAgeMs) {
      window.localStorage.removeItem(recentClipsCacheKey(requestUrl));
      return null;
    }
    if (cached.request_url !== requestUrl || !cached.payload) {
      return null;
    }
    return normalizeCachedRecentClipPayload(cached.payload);
  } catch {
    return null;
  }
}

function payloadWithRetainedClipStats(payload, previousPayload) {
  if (!previousPayload?.stats) {
    return payload;
  }
  return {
    ...payload,
    stats: {
      ...previousPayload.stats,
      limit: payload.stats?.limit ?? previousPayload.stats.limit,
      offset: payload.stats?.offset ?? previousPayload.stats.offset,
      page: payload.stats?.page ?? previousPayload.stats.page,
      featured: payload.stats?.featured ?? previousPayload.stats.featured,
    },
  };
}

function normalizeCachedRecentClipPayload(payload) {
  const clips = Array.isArray(payload.clips) ? payload.clips : [];
  if (!clips.length) {
    return null;
  }
  return {
    source: "live",
    next_cursor: typeof payload.next_cursor === "string" ? payload.next_cursor : null,
    around: payload.around || null,
    around_timezone: payload.around_timezone || null,
    site: fallbackManifest.site,
    stats: payload.stats || {},
    generated_at: payload.generated_at || null,
    clips: clips.map((clip) => ({
      id: clip.id || `${clip.channel}-${clip.started_at}`,
      public_title: clip.public_title || titleForClip(clip),
      channel: clip.channel || "?",
      channel_label: clip.channel_label || "",
      started_at: clip.started_at,
      ended_at: clip.ended_at,
      duration_seconds: clip.duration_seconds,
      transcript_public: clip.transcript_public || clip.transcript || "",
      quality_status: clip.quality_status || "unknown",
      quality_score: clip.quality_score ?? null,
      quality_reason: clip.quality_reason || "",
      quality_flags: Array.isArray(clip.quality_flags) ? clip.quality_flags : [],
      audio_metrics: clip.audio_metrics || {},
      featured: Boolean(clip.featured),
      featured_at: clip.featured_at || "",
      audio_url: clip.audio_url || "",
      audio_public_filename: clip.audio_public_filename || "",
    })),
  };
}

function storeRecentClipPayload(requestUrl, payload) {
  try {
    const cachePayload = {
      ...payload,
      clips: (payload.clips || []).map(cacheableRecentClip),
    };
    window.localStorage.setItem(
      recentClipsCacheKey(requestUrl),
      JSON.stringify({
        cached_at_ms: Date.now(),
        request_url: requestUrl,
        payload: cachePayload,
      }),
    );
  } catch {
    // Some private browsing modes and constrained webviews reject localStorage writes.
  }
}

function cacheableRecentClip(clip) {
  const {
    playback_url: _playbackUrl,
    playback_expires_in_seconds: _playbackExpiresInSeconds,
    playback_issued_at_ms: _playbackIssuedAtMs,
    ...cacheableClip
  } = clip;
  return cacheableClip;
}

function recentClipsCacheKey(requestUrl) {
  return `${recentClipsCacheKeyPrefix}:${requestUrl}`;
}

function startClipStatsPolling() {
  if (clipStatsTimer) {
    clearTimeout(clipStatsTimer);
    clipStatsTimer = null;
  }
  scheduleClipStatsPolling(clipStatsInitialPollMs);
}

function scheduleClipStatsPolling(delayMs = clipStatsPollMs) {
  if (clipStatsTimer) {
    clearTimeout(clipStatsTimer);
  }
  clipStatsTimer = setTimeout(pollClipStats, delayMs);
}

async function pollClipStats() {
  clipStatsAbortController?.abort();
  clipStatsAbortController = new AbortController();
  try {
    const response = await fetch(
      apiUrl(
        "/api/clips/recent?limit=1&include_playback_url=false&" +
          "verify_playback_exists=false&include_counts=false",
      ),
      {
        cache: "no-store",
        signal: clipStatsAbortController.signal,
      },
    );
    if (!response.ok) {
      throw new Error(`clip stats HTTP ${response.status}`);
    }
    const payload = normalizeLivePayload(await response.json());
    mergeLiveClipStats(payloadWithRetainedClipStats(payload, currentClipPayload));
  } catch (error) {
    if (error.name !== "AbortError") {
      // The main clip payload still has a published-manifest fallback.
    }
  } finally {
    scheduleClipStatsPolling();
  }
}

function mergeLiveClipStats(payload) {
  rememberGlobalClipStats(payload);
  let addedClipCount = 0;
  if (!currentClipPayload || currentClipPayload.source !== "live") {
    currentClipPayload = payload;
    addedClipCount = payload.clips?.length || 0;
  } else if (clipCollectionFilter === "recent" && selectedChannels.size === 0) {
    currentClipPayload = {
      ...currentClipPayload,
      stats: {
        ...currentClipPayload.stats,
        ...payload.stats,
      },
      generated_at: payload.generated_at,
    };
    if (payload.clips?.length) {
      const existingIds = new Set((currentClipPayload.clips || []).map((clip) => clip.id));
      const newClips = payload.clips.filter((clip) => !existingIds.has(clip.id));
      addedClipCount = newClips.length;
      if (newClips.length) {
        currentClipPayload.clips = [...newClips, ...(currentClipPayload.clips || [])];
      }
    }
  }
  if (activeTab === "clips" && clipOffset() === 0 && selectedChannels.size === 0) {
    if (clipCollectionFilter !== "recent") {
      renderStats(currentClipPayload || payload, currentPageClips.length ? currentPageClips : payload.clips || []);
      return;
    }
    if (addedClipCount > 0) {
      renderSite(currentClipPayload);
    } else {
      renderClipSummaryOnly(currentClipPayload);
    }
    return;
  }
  renderStats(currentClipPayload || payload, currentPageClips.length ? currentPageClips : payload.clips || []);
}

function clipRequestUrl(_page = 1, { includeCounts = true, cursor = null } = {}) {
  const params = [
    `limit=${clipBatchSize}`,
    "include_playback_url=false",
    "verify_playback_exists=false",
  ];
  if (cursor) {
    params.push(`cursor=${encodeURIComponent(cursor)}`);
  }
  if (!includeCounts) {
    params.push("include_counts=false");
  }
  if (clipCollectionFilter === "featured") {
    params.push("featured=true");
  }
  if (clipCollectionFilter === "quarantined") {
    params.push("quality=quarantined");
  }
  if (clipSortDirection === "oldest") {
    params.push("sort=oldest");
  }
  if (selectedClipAround) {
    params.push(`around=${encodeURIComponent(selectedClipAround)}`);
  }
  const excludedChannels = clipExcludedChannelValues();
  if (excludedChannels.length) {
    params.push(...excludedChannels.map((channel) => `exclude_channels=${encodeURIComponent(channel)}`));
  } else {
    const channels = selectedChannelValues();
    params.push(...channels.map((channel) => `channels=${encodeURIComponent(channel)}`));
  }
  return apiUrl(`/api/clips/recent?${params.join("&")}`);
}

async function loadPublishedManifest() {
  for (const publishedUrl of [recentClipsSnapshotUrl, manifestUrl]) {
    try {
      const response = await fetch(publishedUrl, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`manifest HTTP ${response.status}`);
      }
      return normalizePublishedManifest(await response.json());
    } catch {
      // Try the full manifest when the compact snapshot has not been generated yet.
    }
  }
  return normalizePublishedManifest(fallbackManifest);
}

async function loadLanguagePayload() {
  if (generatedAnalysisHost) {
    const payload = await loadPublishedLanguagePayload();
    if (payload?.status !== "missing") {
      return payload;
    }
  }
  try {
    const response = await fetch(lexicalAnalysisUrl, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`lexical analysis HTTP ${response.status}`);
    }
    const payload = await response.json();
    if (payload?.status === "missing") {
      return loadPublishedLanguagePayload();
    }
    return payload;
  } catch {
    return loadPublishedLanguagePayload();
  }
}

async function loadPublishedLanguagePayload() {
  try {
    const response = await fetch(lexicalManifestUrl, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`lexical manifest HTTP ${response.status}`);
    }
    return response.json();
  } catch {
    return {
      status: "missing",
      source_clip_count: 0,
      frequency: {},
      terms: {},
      entities: [],
      topics: { status: "missing", plot_url: topicClusterFallbackUrl, items: [] },
      education: [],
    };
  }
}

function normalizeLivePayload(payload) {
  const clips = Array.isArray(payload.clips) ? payload.clips : [];
  const latestStartedAt = payload.latest_started_at || clips[0]?.started_at || null;
  const payloadPage = Math.max(1, Math.floor(Number(payload.page ?? selectedClipPage) || 1));
  const payloadOffset = Math.max(
    0,
    Math.floor(Number(payload.offset ?? (payloadPage - 1) * selectedClipPageSize) || 0),
  );
  const rawPlayableChannelCounts = payload.playable_channel_counts || payload.stats?.playable_channel_counts;
  const playableChannelCounts =
    rawPlayableChannelCounts && Object.keys(rawPlayableChannelCounts).length
      ? rawPlayableChannelCounts
      : payload.channel_counts || payload.stats?.channel_counts || {};
  const analyzedClipCount = Number(
    payload.analyzed_clip_count ??
      payload.stats?.analyzed_clip_count ??
      payload.clip_count ??
      totalAvailableClipsFromCounts(payload.channel_counts) ??
      clips.length,
  );
  const receivedClipCount = Number(
    payload.received_clip_count ?? payload.stats?.received_clip_count ?? analyzedClipCount,
  );
  const playableClipCount = Number(
    payload.playable_clip_count ??
      payload.stats?.playable_clip_count ??
      payload.clip_count ??
      totalAvailableClipsFromCounts(payload.channel_counts) ??
      clips.length,
  );
  return {
    source: "live",
    next_cursor: typeof payload.next_cursor === "string" ? payload.next_cursor : null,
    around: payload.around || null,
    around_timezone: payload.around_timezone || null,
    site: fallbackManifest.site,
    stats: {
      clip_count: Number(
        payload.clip_count ?? totalAvailableClipsFromCounts(payload.channel_counts) ?? clips.length,
      ),
      received_clip_count: receivedClipCount,
      analyzed_clip_count: analyzedClipCount,
      filtered_clip_count: Number(payload.filtered_clip_count ?? clips.length),
      playable_clip_count: playableClipCount,
      filtered_playable_clip_count: Number(
        payload.filtered_playable_clip_count ?? payload.stats?.filtered_playable_clip_count ?? playableClipCount,
      ),
      featured: Boolean(payload.featured),
      latest_started_at: latestStartedAt,
      latest_playable_started_at:
        payload.latest_playable_started_at || payload.stats?.latest_playable_started_at || latestStartedAt,
      limit: Number(payload.limit ?? selectedClipPageSize),
      offset: payloadOffset,
      page: payloadPage,
      channel_counts: payload.channel_counts || countBy(clips, (clip) => clip.channel || "?"),
      playable_channel_counts: playableChannelCounts,
      counts_deferred: Boolean(payload.counts_deferred ?? payload.stats?.counts_deferred),
      channel_labels: payload.channel_labels || {},
    },
    generated_at: new Date().toISOString(),
    clips: clips.map((clip) => ({
      id: clip.key || `${clip.channel}-${clip.started_at}`,
      public_title: titleForClip(clip),
      channel: clip.channel || "?",
      channel_label: clip.channel_label || "",
      started_at: clip.started_at,
      ended_at: clip.ended_at,
      duration_seconds: clip.duration_seconds,
      transcript_public: clip.transcript || "",
      quality_status: clip.quality_status || "unknown",
      quality_score: clip.quality_score ?? null,
      quality_reason: clip.quality_reason || "",
      quality_flags: Array.isArray(clip.quality_flags) ? clip.quality_flags : [],
      audio_metrics: clip.audio_metrics || {},
      featured: Boolean(clip.featured),
      featured_at: clip.featured_at || "",
      audio_url: clip.audio_url || "",
      playback_url: clip.playback_url || "",
      playback_expires_in_seconds: clip.playback_expires_in_seconds,
      playback_issued_at_ms: Date.now(),
    })),
  };
}

function normalizePublishedManifest(payload) {
  const clips = Array.isArray(payload.clips) ? payload.clips : [];
  return {
    source: "published",
    site: {
      ...fallbackManifest.site,
      ...(payload.site || {}),
    },
    stats: payload.stats || fallbackManifest.stats,
    generated_at: payload.generated_at || payload.stats?.generated_at || null,
    clips: clips.map((clip) => ({
      id: clip.id || `${clip.channel}-${clip.started_at}`,
      public_title: clip.public_title || titleForClip(clip),
      channel: clip.channel || "?",
      channel_label: clip.channel_label || "",
      started_at: clip.started_at,
      ended_at: clip.ended_at,
      duration_seconds: clip.duration_seconds,
      transcript_public: clip.transcript_public || clip.transcript || "",
      quality_status: clip.quality_status || "unknown",
      quality_score: clip.quality_score ?? null,
      quality_reason: clip.quality_reason || "",
      quality_flags: Array.isArray(clip.quality_flags) ? clip.quality_flags : [],
      audio_metrics: clip.audio_metrics || {},
      featured: Boolean(clip.featured),
      featured_at: clip.featured_at || "",
      audio_public_filename: clip.audio_public_filename || "",
    })),
  };
}

function renderSite(payload) {
  const clips = payload.clips || [];
  nextClipCursor = payload.source === "live" ? payload.next_cursor || null : null;
  rememberGlobalClipStats(payload);
  currentChannelLabels = channelLabelsForPayload(payload);
  document.title = payload.site?.title || fallbackManifest.site.title;
  document.querySelector("#site-title").textContent = payload.site?.title || fallbackManifest.site.title;
  document.querySelector("#site-subtitle").textContent =
    payload.site?.subtitle || fallbackManifest.site.subtitle;
  renderClipHeading();
  renderClipDisplayControls();
  renderChannelFilter(payload);
  const filteredClips = filterClipsByChannel(clips);
  const pageClips = payload.source === "live" ? filteredClips : paginateClips(filteredClips);
  const filteredTotal = filteredClipCount(payload, filteredClips);
  currentPageClips = pageClips;
  currentFilteredTotal = filteredTotal;
  const visibleClips = applyClipSortForCurrentPage(currentPageClips);
  renderStats(payload, pageClips);
  renderClips(visibleClips);
  renderClipPagination(filteredTotal);
  clipStatus.textContent = statusText(payload, visibleClips, filteredTotal);
}

function renderClipSummaryOnly(payload) {
  const clips = payload.clips || [];
  rememberGlobalClipStats(payload);
  renderClipHeading();
  const filteredClips = filterClipsByChannel(clips);
  const pageClips = payload.source === "live" ? filteredClips : paginateClips(filteredClips);
  const filteredTotal = filteredClipCount(payload, filteredClips);
  currentPageClips = pageClips;
  currentFilteredTotal = filteredTotal;
  const visibleClips = applyClipSortForCurrentPage(currentPageClips);
  renderStats(payload, pageClips);
  renderClipPagination(filteredTotal);
  clipStatus.textContent = statusText(payload, visibleClips, filteredTotal);
}

function renderCurrentClipOrder() {
  if (!currentClipPayload) {
    loadAndRender();
    return;
  }
  renderClipDisplayControls();
  const visibleClips = applyClipSortForCurrentPage(currentPageClips);
  renderStats(currentClipPayload, currentPageClips);
  renderClips(visibleClips);
  renderClipPagination(currentFilteredTotal);
  clipStatus.textContent = statusText(currentClipPayload, visibleClips, currentFilteredTotal);
}

function renderStats(payload, clips) {
  if (!stats) {
    return;
  }
  const payloadStatsForHeader =
    payload.stats?.counts_deferred || payload.stats?.featured ? null : payload.stats || {};
  const headerStats = globalClipStats || payloadStatsForHeader;
  const channelCounts =
    headerStats?.playable_channel_counts ||
    headerStats?.channel_counts ||
    countBy(clips, (clip) => clip.channel || "?");
  const channelTotal = headerStats ? Object.keys(channelCounts).length : null;
  const clipTotal = headerStats ? totalPlayableClips({ ...payload, stats: headerStats }, clips) : null;
  const latestStartedAt =
    headerStats?.latest_playable_started_at || headerStats?.latest_started_at || clips[0]?.started_at;
  const latest = latestStartedAt ? shortTime(latestStartedAt) : headerStats ? "None" : null;
  const statItems = [
    ["Playable clips", clipTotal],
    ["Received", totalReceivedClips(payload)],
    ["Analyzed", totalAnalyzedClips(payload)],
    ["Channels", channelTotal],
    ["Latest clip", latest],
  ];

  stats.replaceChildren(
    ...statItems.map(([label, value]) => {
      const item = document.createElement("div");
      item.className = "stat";
      if (label === "Playable clips" && lastRenderedClipTotal !== null && Number(value) > lastRenderedClipTotal) {
        item.classList.add("is-live-updated");
      }
      const term = document.createElement("dt");
      term.textContent = label;
      const description = document.createElement("dd");
      description.textContent = formatStatValue(label, value);
      item.append(term, description);
      return item;
    }),
  );
  if (clipTotal !== null) {
    lastRenderedClipTotal = Number(clipTotal);
  }
}

function rememberGlobalClipStats(payload) {
  if (!payload?.stats || payload.stats.counts_deferred || payload.stats.featured) {
    return;
  }
  const clips = payload.clips || [];
  const channelCounts =
    payload.stats.playable_channel_counts ||
    payload.stats.channel_counts ||
    countBy(clips, (clip) => clip.channel || "?");
  globalClipStats = {
    ...payload.stats,
    clip_count: Number(
      payload.stats.clip_count ??
        totalAvailableClipsFromCounts(payload.stats.channel_counts) ??
        clips.length,
    ),
    playable_clip_count: Number(
      payload.stats.playable_clip_count ??
        payload.stats.clip_count ??
        totalAvailableClipsFromCounts(payload.stats.playable_channel_counts) ??
        totalAvailableClipsFromCounts(payload.stats.channel_counts) ??
        clips.length,
    ),
    channel_counts: {
      ...(payload.stats.channel_counts || channelCounts || {}),
    },
    playable_channel_counts: {
      ...(payload.stats.playable_channel_counts || channelCounts || {}),
    },
    latest_started_at: payload.stats.latest_started_at || clips[0]?.started_at || null,
    latest_playable_started_at:
      payload.stats.latest_playable_started_at || payload.stats.latest_started_at || clips[0]?.started_at || null,
    counts_deferred: false,
  };
}

function formatStatValue(label, value) {
  if (label === "Playable clips" || label === "Received" || label === "Analyzed" || label === "Channels") {
    if (value === null || value === undefined) {
      return "Loading";
    }
    return Number(value).toLocaleString();
  }
  return String(value);
}

function renderChannelFilter(payload) {
  const wasOpen = channelFilter.querySelector(".channel-filter-menu")?.open;
  const channelCountClips =
    clipCollectionFilter === "featured" && payload.source !== "live"
      ? (payload.clips || []).filter((clip) => clip.featured)
      : payload.clips || [];
  const channelCounts =
    payload.stats?.playable_channel_counts ||
    payload.stats?.channel_counts ||
    countBy(channelCountClips, (clip) => clip.channel || "?");
  const configuredChannels = Object.keys(payload.stats?.channel_labels || payload.channel_labels || {});
  const channels = [...new Set([...Object.keys(channelCounts), ...configuredChannels])].sort(compareChannels);
  for (const channel of selectedChannelValues()) {
    if (!channels.includes(channel)) {
      channels.push(channel);
    }
  }
  channels.sort(compareChannels);

  const menu = document.createElement("details");
  menu.className = "channel-filter-menu";
  menu.open = Boolean(wasOpen);

  const trigger = document.createElement("summary");
  trigger.className = "channel-filter-trigger";
  const triggerLabel = document.createElement("span");
  triggerLabel.className = "channel-filter-trigger-label";
  triggerLabel.textContent = "Channels";
  const triggerSummary = document.createElement("span");
  triggerSummary.className = "channel-filter-trigger-summary";
  triggerSummary.textContent = formatChannelFilterSummary(channelCounts);
  trigger.append(triggerLabel, triggerSummary);

  const panel = document.createElement("div");
  panel.className = "channel-filter-panel";
  panel.setAttribute("role", "group");
  panel.setAttribute("aria-labelledby", "channel-filter-label");

  const allAction = document.createElement("button");
  allAction.type = "button";
  allAction.className = "channel-filter-action";
  allAction.dataset.preset = "all";
  allAction.setAttribute("aria-pressed", String(selectedChannelPreset === "all" && selectedChannels.size === 0));
  const allName = document.createElement("span");
  allName.className = "channel-filter-name";
  allName.textContent = "All channels";
  const allDetail = document.createElement("span");
  allDetail.className = "channel-filter-detail";
  allDetail.textContent = channelClipCountText(totalAvailableClipsFromCounts(channelCounts));
  allAction.append(allName, allDetail);

  const nonTrafficChannels = channels.filter((channel) => !trafficChannelIds.has(channel));
  const allButTrafficAction = document.createElement("button");
  allButTrafficAction.type = "button";
  allButTrafficAction.className = "channel-filter-action";
  allButTrafficAction.dataset.preset = "all-but-traffic";
  allButTrafficAction.dataset.channels = nonTrafficChannels.join(",");
  allButTrafficAction.setAttribute(
    "aria-pressed",
    String(isAllButTrafficClipFilter(nonTrafficChannels)),
  );
  const allButTrafficName = document.createElement("span");
  allButTrafficName.className = "channel-filter-name";
  allButTrafficName.textContent = "All but traffic";
  const allButTrafficDetail = document.createElement("span");
  allButTrafficDetail.className = "channel-filter-detail";
  const allButTrafficCount = nonTrafficChannels.reduce(
    (total, channel) => total + Number(channelCounts[channel] || 0),
    0,
  );
  allButTrafficDetail.textContent = channelClipCountText(allButTrafficCount);
  allButTrafficAction.append(allButTrafficName, allButTrafficDetail);

  const options = document.createElement("div");
  options.className = "channel-filter-options";
  options.replaceChildren(...channels.map((channel) => channelFilterOption(channel, channelCounts[channel])));
  panel.append(allAction, allButTrafficAction, options);
  menu.append(trigger, panel);
  channelFilter.replaceChildren(menu);
}

function renderClipDisplayControls() {
  if (!clipDisplayControls) {
    return;
  }
  clipDisplayControls.replaceChildren(...renderClipDisplayControlSet());
  updateClipDatetimeNavigator();
}

function updateClipDatetimeNavigator() {
  if (clearClipDatetimeButton) {
    clearClipDatetimeButton.hidden = !selectedClipAround;
  }
  clipDatetimeForm?.classList.toggle("is-active", Boolean(selectedClipAround));
}

function renderClipHeading() {
  if (!clipsTitle) {
    return;
  }
  clipsTitle.textContent = clipCollectionTitle();
}

function clipCollectionTitle() {
  if (clipCollectionFilter === "featured") {
    return "Hall of Fame";
  }
  if (clipCollectionFilter === "quarantined") {
    return "Quarantined Clips";
  }
  return "Recent Clips";
}

function renderClipDisplayControlSet() {
  const collectionControls = [
    {
      label: "Recent",
      active: clipCollectionFilter === "recent",
      onClick: () => {
        if (clipCollectionFilter === "recent") {
          return;
        }
        clipCollectionFilter = "recent";
        resetClipPagination();
        updateTabRoute("clips");
        loadAndRender();
      },
    },
  ];
  if (quarantineClipLaneEnabled) {
    collectionControls.push({
      label: "Quarantine",
      active: clipCollectionFilter === "quarantined",
      onClick: () => {
        if (clipCollectionFilter === "quarantined") {
          return;
        }
        clipCollectionFilter = "quarantined";
        resetClipPagination();
        updateTabRoute("clips");
        loadAndRender();
      },
    });
  }
  collectionControls.push({
    label: "Hall of fame",
    active: clipCollectionFilter === "featured",
    onClick: () => {
      if (clipCollectionFilter === "featured") {
        return;
      }
      clipCollectionFilter = "featured";
      resetClipPagination();
      updateTabRoute("clips");
      loadAndRender();
    },
  });
  const featuredControl = segmentedControl("Show clips", collectionControls);
  const sortControl = segmentedControl(selectedClipAround ? "Browse from time" : "Flip page order", [
    {
      label: selectedClipAround ? "Earlier" : "Newest",
      active: clipSortDirection === "newest",
      onClick: () => {
        if (clipSortDirection === "newest") {
          return;
        }
        clipSortDirection = "newest";
        resetClipPagination();
        loadAndRender({ useCachedPayload: false, includeCounts: false });
      },
    },
    {
      label: selectedClipAround ? "Later" : "Oldest",
      active: clipSortDirection === "oldest",
      onClick: () => {
        if (clipSortDirection === "oldest") {
          return;
        }
        clipSortDirection = "oldest";
        resetClipPagination();
        loadAndRender({ useCachedPayload: false, includeCounts: false });
      },
    },
  ]);
  const controls = [featuredControl, sortControl];
  if (clipCollectionFilter === "recent") {
    controls.push(renderContinuousClipPlaybackControl());
  }
  return controls;
}

function resetClipPagination() {
  stopContinuousClipPlayback();
  selectedClipOffset = 0;
  selectedClipPage = 1;
  nextClipCursor = null;
  clipLoadMorePending = false;
}

function segmentedControl(labelText, options) {
  const wrapper = document.createElement("div");
  wrapper.className = "clip-control-group";
  const label = document.createElement("span");
  label.className = "clip-control-label";
  label.textContent = labelText;
  const controls = document.createElement("div");
  controls.className = "clip-segmented-control";
  controls.setAttribute("role", "group");
  controls.setAttribute("aria-label", labelText);
  for (const option of options) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "clip-segment-button";
    button.classList.toggle("is-active", option.active);
    button.setAttribute("aria-pressed", String(option.active));
    button.textContent = option.label;
    button.addEventListener("click", option.onClick);
    controls.append(button);
  }
  wrapper.append(label, controls);
  return wrapper;
}

function renderContinuousClipPlaybackControl() {
  const wrapper = document.createElement("div");
  wrapper.className = "clip-control-group clip-play-all-control";
  const label = document.createElement("span");
  label.className = "clip-control-label";
  label.textContent = "Continuous play";
  const actions = document.createElement("div");
  actions.className = "clip-play-all-actions";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "clip-play-all-button";
  button.addEventListener("click", toggleContinuousClipPlayback);
  const status = document.createElement("span");
  status.className = "clip-play-all-status";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  actions.append(button, status);
  wrapper.append(label, actions);
  updateContinuousClipPlaybackControl({ button, status });
  return wrapper;
}

function updateContinuousClipPlaybackControl(elements = {}) {
  const button = elements.button || clipDisplayControls?.querySelector(".clip-play-all-button");
  const status = elements.status || clipDisplayControls?.querySelector(".clip-play-all-status");
  const clipCount = continuousClipAudios().length;
  if (button) {
    button.classList.toggle("is-active", continuousClipPlaybackActive);
    button.setAttribute("aria-pressed", String(continuousClipPlaybackActive));
    button.disabled = !continuousClipPlaybackActive && clipCount === 0;
    if (continuousClipPlaybackActive) {
      button.setAttribute("aria-label", "Stop continuous clip playback");
      button.textContent = "■ Stop";
    } else {
      button.setAttribute("aria-label", "Play all recent clips");
      button.textContent = "▶ Play all";
    }
  }
  if (status) {
    status.textContent = continuousClipPlaybackStatusText(clipCount);
  }
}

function continuousClipPlaybackStatusText(clipCount) {
  if (continuousClipPlaybackActive) {
    if (continuousClipPlaybackPhase === "waiting") {
      return "Next clip in 2 seconds";
    }
    if (continuousClipPlaybackPhase === "loading") {
      return "Loading more clips…";
    }
    if (continuousClipPlaybackIndex >= 0) {
      return `Playing ${continuousClipPlaybackIndex + 1} of ${clipCount} loaded clips`;
    }
  }
  if (continuousClipPlaybackMessage) {
    return continuousClipPlaybackMessage;
  }
  const noun = clipCount === 1 ? "clip" : "clips";
  return `Loops ${clipCount} loaded ${noun} · 2s between clips`;
}

function continuousClipAudios() {
  if (!clipList) {
    return [];
  }
  return [...clipList.querySelectorAll(".clip-card .example-player audio")].filter(
    (audio) => audio instanceof HTMLAudioElement,
  );
}

function toggleContinuousClipPlayback() {
  if (continuousClipPlaybackActive) {
    stopContinuousClipPlayback();
    return;
  }
  startContinuousClipPlayback();
}

async function startContinuousClipPlayback() {
  const audios = continuousClipAudios();
  if (!audios.length) {
    continuousClipPlaybackMessage = "No playable Recent clips are loaded.";
    updateContinuousClipPlaybackControl();
    return;
  }
  stopCurrentClipPlayback();
  closeLiveAudioStream();
  continuousClipPlaybackActive = true;
  continuousClipPlaybackGeneration += 1;
  continuousClipPlaybackIndex = -1;
  continuousClipPlaybackPhase = "starting";
  continuousClipPlaybackMessage = "";
  const generation = continuousClipPlaybackGeneration;
  updateContinuousClipPlaybackControl();
  await playContinuousClipAt(0, generation);
}

async function playContinuousClipAt(index, generation) {
  if (!continuousClipPlaybackActive || generation !== continuousClipPlaybackGeneration) {
    return;
  }
  const audios = continuousClipAudios();
  const audio = audios[index];
  if (!audio) {
    stopContinuousClipPlayback({ message: "No playable Recent clips are loaded." });
    return;
  }
  continuousClipPlaybackIndex = index;
  continuousClipPlaybackAudio = audio;
  continuousClipPlaybackPhase = "starting";
  markContinuousClipPlaybackCard(audio);
  updateContinuousClipPlaybackControl();
  const playAction = clipAudioPlayActions.get(audio);
  const started = playAction ? await playAction() : await playAudioElement(audio);
  const playbackStillCurrent =
    continuousClipPlaybackActive &&
    generation === continuousClipPlaybackGeneration &&
    continuousClipPlaybackAudio === audio;
  if (!started || !playbackStillCurrent) {
    if (started && !audio.paused) {
      audio.pause();
    }
    if (continuousClipPlaybackActive && generation === continuousClipPlaybackGeneration) {
      stopContinuousClipPlayback({
        stopAudio: false,
        message: "Playback needs another tap to continue.",
      });
    }
    return;
  }
  continuousClipPlaybackPhase = "playing";
  updateContinuousClipPlaybackControl();
  const onFinished = () => {
    audio.removeEventListener("ended", onFinished);
    audio.removeEventListener("error", onFinished);
    if (
      continuousClipPlaybackActive &&
      generation === continuousClipPlaybackGeneration &&
      continuousClipPlaybackAudio === audio
    ) {
      scheduleNextContinuousClip(audio, generation);
    }
  };
  audio.addEventListener("ended", onFinished, { once: true });
  audio.addEventListener("error", onFinished, { once: true });
}

async function playAudioElement(audio) {
  try {
    await audio.play();
    return true;
  } catch {
    return false;
  }
}

function scheduleNextContinuousClip(completedAudio, generation) {
  if (!continuousClipPlaybackActive || generation !== continuousClipPlaybackGeneration) {
    return;
  }
  continuousClipPlaybackPhase = "waiting";
  updateContinuousClipPlaybackControl();
  continuousClipPlaybackTimer = window.setTimeout(
    () => {
      continuousClipPlaybackTimer = null;
      advanceContinuousClipPlayback(completedAudio, generation);
    },
    continuousClipPlaybackGapMs,
  );
}

async function advanceContinuousClipPlayback(completedAudio, generation) {
  if (!continuousClipPlaybackActive || generation !== continuousClipPlaybackGeneration) {
    return;
  }
  let audios = continuousClipAudios();
  const completedIndex = audios.indexOf(completedAudio);
  let nextIndex = completedIndex >= 0 ? completedIndex + 1 : continuousClipPlaybackIndex + 1;
  if (nextIndex >= audios.length && nextClipCursor) {
    continuousClipPlaybackPhase = "loading";
    updateContinuousClipPlaybackControl();
    await loadMoreClips();
    if (!continuousClipPlaybackActive || generation !== continuousClipPlaybackGeneration) {
      return;
    }
    audios = continuousClipAudios();
    const refreshedCompletedIndex = audios.indexOf(completedAudio);
    nextIndex = refreshedCompletedIndex >= 0 ? refreshedCompletedIndex + 1 : nextIndex;
  }
  if (nextIndex >= audios.length) {
    nextIndex = 0;
  }
  await playContinuousClipAt(nextIndex, generation);
}

function stopContinuousClipPlayback({ stopAudio = true, message = "" } = {}) {
  const audio = continuousClipPlaybackAudio;
  continuousClipPlaybackActive = false;
  continuousClipPlaybackGeneration += 1;
  if (continuousClipPlaybackTimer) {
    window.clearTimeout(continuousClipPlaybackTimer);
    continuousClipPlaybackTimer = null;
  }
  continuousClipPlaybackAudio = null;
  continuousClipPlaybackIndex = -1;
  continuousClipPlaybackPhase = "idle";
  continuousClipPlaybackMessage = message;
  markContinuousClipPlaybackCard(null);
  if (stopAudio && audio && !audio.paused) {
    audio.pause();
    try {
      audio.currentTime = 0;
    } catch {
      // Metadata may not be available for a failed playback attempt.
    }
  }
  updateContinuousClipPlaybackControl();
}

function markContinuousClipPlaybackCard(audio) {
  clipList?.querySelectorAll(".clip-card.is-continuous-playing").forEach((card) => {
    card.classList.remove("is-continuous-playing");
  });
  audio?.closest(".clip-card")?.classList.add("is-continuous-playing");
}

function channelFilterOption(channel, count) {
  const selected = selectedChannels.has(channel);
  const option = document.createElement("label");
  option.className = "channel-filter-option";
  option.setAttribute("aria-checked", String(selected));
  option.style.setProperty("--channel-color", channelColorForChannel(channel));
  if (selected) {
    option.classList.add("is-active");
  }

  const input = document.createElement("input");
  input.type = "checkbox";
  input.className = "channel-filter-checkbox";
  input.dataset.channel = channel;
  input.checked = selected;

  const swatch = document.createElement("span");
  swatch.className = "channel-filter-swatch";
  swatch.setAttribute("aria-hidden", "true");

  const copy = document.createElement("span");
  copy.className = "channel-filter-copy";
  const name = document.createElement("span");
  name.className = "channel-filter-name";
  name.textContent = `VHF ${channel}`;
  const detailText = document.createElement("span");
  detailText.className = "channel-filter-detail";
  detailText.textContent = channelFilterDetail(channel);
  const frequency = document.createElement("span");
  frequency.className = "channel-filter-frequency";
  const frequencyText = frequencyForChannel(channel);
  frequency.textContent = [frequencyText ? `${frequencyText} MHz` : "", channelClipCountText(count)]
    .filter(Boolean)
    .join(" · ");
  copy.append(name, detailText, frequency);

  option.append(input, swatch, copy);
  return option;
}

function channelFilterDetail(channel) {
  const label = currentChannelLabels[channel] || defaultChannelLabels[channel] || "Unlabeled";
  return label;
}

function selectAllButTrafficChannels(rawChannels) {
  selectedChannels.clear();
  for (const channel of rawChannels.split(",")) {
    if (channel && !trafficChannelIds.has(channel)) {
      selectedChannels.add(channel);
    }
  }
}

function channelSetMatches(selected, channels) {
  if (selected.size !== channels.length) {
    return false;
  }
  return channels.every((channel) => selected.has(channel));
}

function isAllButTrafficClipFilter(channels = selectedChannelValues()) {
  return selectedChannelPreset === "all-but-traffic" && (!selectedChannels.size || channelSetMatches(selectedChannels, channels));
}

function formatChannelFilterSummary(channelCounts) {
  const channels = selectedChannelValues();
  if (selectedChannelPreset === "all-but-traffic") {
    const selectedCount = channels.length
      ? channels.reduce((total, channel) => total + Number(channelCounts?.[channel] || 0), 0)
      : totalAvailableClipsFromCounts(channelCounts);
    return `All but traffic · ${channelClipCountText(selectedCount)}`;
  }
  if (!channels.length) {
    return `All channels · ${channelClipCountText(totalAvailableClipsFromCounts(channelCounts))}`;
  }
  const selectedCount = channels.reduce((total, channel) => total + Number(channelCounts?.[channel] || 0), 0);
  const countText = channelClipCountText(selectedCount);
  if (channels.length === 1) {
    return `${channelLabel(channels[0])} · ${countText}`;
  }
  return `${channels.length} channels selected · ${countText}`;
}

function filterClipsByChannel(clips) {
  let visibleClips = clips;
  if (clipCollectionFilter === "featured") {
    visibleClips = visibleClips.filter((clip) => clip.featured);
  } else if (clipCollectionFilter === "quarantined") {
    visibleClips = visibleClips.filter((clip) => clip.quality_status === "quarantined");
  }
  if (selectedChannelPreset === "all-but-traffic") {
    return visibleClips.filter((clip) => !trafficChannelIds.has(String(clip.channel || "").toUpperCase()));
  }
  if (!selectedChannels.size) {
    return visibleClips;
  }
  return visibleClips.filter((clip) => selectedChannels.has(clip.channel));
}

function paginateClips(clips) {
  const start = clipOffset();
  return clips.slice(start, start + selectedClipPageSize);
}

function applyClipSortForCurrentPage(clips) {
  if (currentClipPayload?.source !== "live" && clipSortDirection === "oldest") {
    return [...clips].reverse();
  }
  return clips;
}

function clipOffset() {
  return selectedClipOffset;
}

function renderClips(clips) {
  clipList.setAttribute("aria-busy", "false");
  if (!clips.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    if (clipCollectionFilter === "featured") {
      empty.textContent =
        selectedChannels.size === 0
          ? "No Hall of Fame clips yet."
          : "No Hall of Fame clips for the selected channels.";
    } else if (clipCollectionFilter === "quarantined") {
      empty.textContent =
        selectedChannels.size === 0
          ? "No quarantined clips yet."
          : "No quarantined clips for the selected channels.";
    } else {
      empty.textContent = selectedClipAround
        ? `No playable clips were found ${clipSortDirection === "oldest" ? "at or after" : "at or before"} that time.`
        : selectedChannels.size === 0
          ? "No playable clips are available yet."
          : "No playable clips are available for the selected channels.";
    }
    clipList.replaceChildren(empty);
    if (continuousClipPlaybackActive || clipCollectionFilter === "recent") {
      stopContinuousClipPlayback({ message: "No playable Recent clips are loaded." });
    }
    return;
  }
  if (
    !continuousClipPlaybackActive &&
    continuousClipPlaybackMessage === "No playable Recent clips are loaded."
  ) {
    continuousClipPlaybackMessage = "";
  }
  const existingCards = new Map(
    [...clipList.querySelectorAll(".clip-card[data-clip-id]")].map((card) => [
      card.dataset.clipId,
      card,
    ]),
  );
  clipList.replaceChildren(
    ...clips.map((clip) => {
      const clipId = clipDomId(clip);
      const signature = clipRenderSignature(clip);
      const existing = existingCards.get(clipId);
      if (existing?.dataset.clipSignature === signature) {
        return existing;
      }
      return renderClipCard(clip);
    }),
  );
  if (continuousClipPlaybackActive && continuousClipPlaybackAudio && !continuousClipPlaybackAudio.isConnected) {
    stopContinuousClipPlayback({ message: "The clip list changed. Press Play all to restart." });
    return;
  }
  updateContinuousClipPlaybackControl();
}

function renderClipPagination(_totalClips, { pending = false, loadError = false } = {}) {
  if (!clipPagination) {
    return;
  }
  clipLoadMoreObserver?.disconnect();
  clipLoadMoreObserver = null;
  if (!nextClipCursor && !pending && !loadError) {
    clipPagination.hidden = true;
    clipPagination.replaceChildren();
    return;
  }
  const button = document.createElement("button");
  button.type = "button";
  button.className = "pagination-button clip-load-more-button";
  button.textContent = pending
    ? "Loading 24 more…"
    : loadError
      ? "Retry loading 24 more"
      : "Load 24 more";
  button.disabled = pending || !nextClipCursor;
  button.addEventListener("click", loadMoreClips);
  const sentinel = document.createElement("div");
  sentinel.className = "clip-load-more-sentinel";
  sentinel.setAttribute("aria-hidden", "true");
  clipPagination.hidden = false;
  clipPagination.classList.toggle("is-pending", pending);
  if (pending) {
    clipPagination.setAttribute("aria-busy", "true");
  } else {
    clipPagination.removeAttribute("aria-busy");
  }
  clipPagination.replaceChildren(button, sentinel);
  if (
    nextClipCursor &&
    !pending &&
    "IntersectionObserver" in window
  ) {
    clipLoadMoreObserver = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          loadMoreClips();
        }
      },
      { rootMargin: "600px 0px" },
    );
    clipLoadMoreObserver.observe(sentinel);
  }
}

function renderClipCard(clip) {
  const article = document.createElement("article");
  article.className = "clip-card";
  article.dataset.clipId = clipDomId(clip);
  article.dataset.clipSignature = clipRenderSignature(clip);
  const canWriteClipFeature = featureClipWriteEnabled && canReviewClip(clip);
  const canDeleteArchivedClip = archiveClipDeleteEnabled && canReviewClip(clip);

  const meta = document.createElement("div");
  meta.className = "clip-meta";
  meta.append(renderChannelPill(clip.channel), renderPill(formatDateTime(clip.started_at)));
  if (clip.duration_seconds) {
    meta.append(renderPill(`${Math.round(Number(clip.duration_seconds))}s`));
  }
  if (clip.quality_status === "quarantined") {
    meta.append(renderQualityPill(clip));
    article.classList.add("is-quarantined");
  }
  if (clip.featured) {
    meta.append(renderFeaturedPill());
    article.classList.add("is-featured");
  }
  if (canWriteClipFeature) {
    meta.append(renderFeaturedClipAction(clip, article));
  }

  const title = document.createElement("h3");
  title.textContent = titleForClip(clip);

  const transcript = document.createElement("blockquote");
  transcript.textContent = clip.transcript_public || "";

  const audioUrl = audioUrlForClip(clip);
  article.append(meta, title, transcript);
  if (audioUrl) {
    article.append(renderExamplePlayer(clip));
  }
  if (canDeleteArchivedClip) {
    article.append(renderArchiveDeleteControl(clip, article));
  }
  return article;
}

function clipDomId(clip) {
  return String(clip.id || `${clip.channel || "?"}-${clip.started_at || ""}`);
}

function clipRenderSignature(clip) {
  return [
    clipDomId(clip),
    clip.channel || "",
    clip.channel_label || "",
    clip.started_at || "",
    clip.ended_at || "",
    clip.duration_seconds || "",
    clip.transcript_public || "",
    clip.quality_status || "unknown",
    clip.quality_score ?? "",
    clip.quality_reason || "",
    Array.isArray(clip.quality_flags) ? clip.quality_flags.join(",") : "",
    clip.featured ? "featured" : "standard",
    clip.featured_at || "",
    clipAudioSourceKind(clip),
    featureClipWriteEnabled && canReviewClip(clip) ? "feature-writable" : "feature-read-only",
    archiveClipDeleteEnabled && canReviewClip(clip) ? "archive-delete-writable" : "archive-delete-read-only",
  ].join("\u001f");
}

function clipAudioSourceKind(clip) {
  if (clip?.playback_url) {
    return "has-live-audio";
  }
  if (clip?.audio_public_filename) {
    return "has-static-audio";
  }
  if (clipAudioRequestUrl(clip)) {
    return "has-proxied-audio";
  }
  return "no-audio";
}

function canReviewClip(clip) {
  return Boolean(clip?.channel && clip?.started_at && clip?.transcript_public !== undefined);
}

function renderArchiveDeleteControl(clip, article) {
  const wrapper = document.createElement("div");
  wrapper.className = "archive-delete-control";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "archive-delete-button";
  button.textContent = "Delete clip forever";
  const status = document.createElement("span");
  status.className = "archive-delete-status";
  status.setAttribute("role", "status");
  button.addEventListener("click", async () => {
    await deleteArchivedClip(clip, { button, status, article });
  });
  wrapper.append(button, status);
  return wrapper;
}

async function deleteArchivedClip(clip, controls) {
  const { button, status, article } = controls;
  const typed = window.prompt("Type DELETE to permanently delete this clip from the archive.");
  if (typed !== "DELETE") {
    status.textContent = "Delete cancelled.";
    return;
  }
  button.disabled = true;
  status.textContent = "Deleting...";
  try {
    const response = await fetch(clipArchiveUrl, {
      method: "DELETE",
      credentials: "include",
      headers: operatorWriteHeaders(),
      body: JSON.stringify({
        channel: clip.channel,
        started_at: clip.started_at,
        confirm: "DELETE",
        deleted_by: "operator-ui",
        reason: "operator requested archive purge",
      }),
    });
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        status.textContent = "Open the operator page over Tailscale to delete archive clips.";
        return;
      }
      throw new Error(`archive delete HTTP ${response.status}`);
    }
    article.remove();
    status.textContent = "Clip deleted.";
    loadAndRender({ useCachedPayload: false }).catch((error) => console.error(error));
  } catch (error) {
    console.error(error);
    status.textContent = "Clip was not deleted.";
  } finally {
    button.disabled = false;
  }
}

function renderQualityPill(clip) {
  const label = clip.quality_reason ? `Quarantine: ${formatQualityReason(clip.quality_reason)}` : "Quarantined";
  const pill = renderPill(label);
  pill.classList.add("quality-pill");
  return pill;
}

function formatQualityReason(reason) {
  return String(reason || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function renderFeaturedPill() {
  const featured = renderPill("Featured");
  featured.classList.add("featured-pill");
  return featured;
}

function renderFeaturedClipAction(clip, article) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "feature-clip-button";
  setFeaturedClipButtonState(button, Boolean(clip.featured));
  button.addEventListener("click", async () => {
    await saveClipFeature(clip, !clip.featured, { button, article });
  });
  return button;
}

function setFeaturedClipButtonState(button, featured) {
  button.classList.toggle("is-active", featured);
  button.setAttribute("aria-pressed", String(featured));
  button.setAttribute("aria-label", featured ? "Remove from Hall of Fame" : "Add to Hall of Fame");
  button.textContent = featured ? "★" : "☆";
  button.title = featured ? "Remove from Hall of Fame" : "Add to Hall of Fame";
}

async function saveClipFeature(clip, featured, controls) {
  const { button, article } = controls;
  const previousFeatured = Boolean(clip.featured);
  const requestedFeatured = Boolean(featured);
  applyClipFeatureState(clip, article, button, requestedFeatured);
  button.disabled = true;
  button.classList.add("is-saving");
  try {
    const response = await postClipFeature(clip, requestedFeatured);
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        applyClipFeatureState(clip, article, button, previousFeatured);
        button.title = "Open the operator page over Tailscale to change Hall of Fame clips.";
        return;
      }
      throw new Error(`feature HTTP ${response.status}`);
    }
    const body = await response.json();
    applyClipFeatureState(clip, article, button, Boolean(body.featured));
    if (clipCollectionFilter === "featured" && !clip.featured) {
      loadAndRender();
    }
  } catch (error) {
    console.error(error);
    applyClipFeatureState(clip, article, button, previousFeatured);
  } finally {
    button.classList.remove("is-saving");
    button.disabled = false;
  }
}

function applyClipFeatureState(clip, article, button, featured) {
  clip.featured = Boolean(featured);
  setFeaturedClipButtonState(button, clip.featured);
  updateFeaturedClipCard(article, clip.featured);
}

function updateFeaturedClipCard(article, featured) {
  article.classList.toggle("is-featured", featured);
  const meta = article.querySelector(".clip-meta");
  const existingPill = meta?.querySelector(".featured-pill");
  if (featured && !existingPill) {
    const action = meta?.querySelector(".feature-clip-button");
    const pill = renderFeaturedPill();
    if (action) {
      meta.insertBefore(pill, action);
    } else {
      meta?.append(pill);
    }
  }
  if (!featured && existingPill) {
    existingPill.remove();
  }
}

function postClipFeature(clip, featured) {
  return fetch(clipFeaturesUrl, {
    method: "POST",
    credentials: "include",
    headers: operatorWriteHeaders(),
    body: JSON.stringify({
      channel: clip.channel,
      started_at: clip.started_at,
      featured,
      featured_by: "operator-ui",
    }),
  });
}

function operatorWriteHeaders() {
  const headers = { "Content-Type": "application/json" };
  if (privateAppHost) {
    headers["X-TalkingBoats-Tailnet-Dev"] = "1";
  }
  return headers;
}

function renderPill(text) {
  const pill = document.createElement("span");
  pill.className = "pill";
  pill.textContent = text;
  return pill;
}

function renderChannelPill(channel) {
  const pill = renderPill(channelLabel(channel));
  pill.classList.add("channel-pill", channelClassName(channel));
  pill.style.setProperty("--channel-color", channelColorForChannel(channel));
  return pill;
}

async function loadLiveChannels() {
  let loadedFromLiveApi = false;
  try {
    const response = await fetch(liveChannelsUrl, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`live channels HTTP ${response.status}`);
    }
    const payload = await response.json();
    const channels = normalizeLiveChannels(payload.channels);
    if (!channels.length) {
      throw new Error("live channels unavailable");
    }
    liveChannels = channels;
    loadedFromLiveApi = true;
    if (
      selectedLiveChannel !== everythingLiveChannel &&
      payload.defaultChannel &&
      liveChannels.some((item) => item.channel === payload.defaultChannel)
    ) {
      selectedLiveChannel = payload.defaultChannel;
    }
  } catch {
    liveChannels = normalizeLiveChannels(liveChannels);
  }
  liveChannelsLoaded = loadedFromLiveApi;
  for (const channel of liveChannels) {
    currentChannelLabels[channel.channel] = channel.label;
  }
  renderLiveChannelPicker();
  renderEverythingQueuePanel();
  if (liveAudio.src && !isQueuedLiveMode()) {
    liveAudio.src = liveStreamUrl();
    liveAudio.load();
  }
  if (languagePayloadLoaded && latestLanguagePayload) {
    renderLanguageDashboard(latestLanguagePayload);
  }
}

function normalizeLiveChannels(channels) {
  return (channels || [])
    .map((channel) => ({
      channel: String(channel.channel || "").toUpperCase(),
      label: channel.label || defaultChannelLabels[channel.channel] || "",
      frequencyMhz: channel.frequencyMhz || "",
      streamPath: channel.streamPath || "",
      statusPath: channel.statusPath || "",
    }))
    .filter((channel) => channel.channel && channel.label);
}

function renderLiveChannelPicker() {
  if (!liveChannelPicker || !livePrimaryChannelPicker) {
    return;
  }
  livePrimaryChannelPicker.replaceChildren(
    liveChannelOptionButton(everythingChannelOption(), { primary: true }),
    liveChannelOptionButton(allButTrafficChannelOption(), { primary: true }),
  );
  liveChannelPicker.replaceChildren();
  for (const channel of liveChannels) {
    liveChannelPicker.append(liveChannelOptionButton(channel));
  }
}

function everythingChannelOption() {
  return {
    channel: everythingLiveChannel,
    label: "Everything",
    frequencyMhz: "",
    streamPath: "",
    statusPath: "",
  };
}

function allButTrafficChannelOption() {
  return {
    channel: allButTrafficLiveChannel,
    label: "All but Traffic",
    frequencyMhz: "",
    streamPath: "",
    statusPath: "",
  };
}

function liveChannelOptionButton(channel, { primary = false } = {}) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "live-channel-option";
  button.classList.toggle("is-active", channel.channel === selectedLiveChannel);
  button.classList.toggle("is-everything", channel.channel === everythingLiveChannel);
  button.classList.toggle("is-primary", primary);
  button.dataset.channel = channel.channel;
  button.textContent = channelLabel(channel.channel);
  button.title =
    channel.channel === everythingLiveChannel
      ? "Queue transmissions from all monitored live channels"
      : channel.channel === allButTrafficLiveChannel
        ? "Queue monitored live channels except Seattle Traffic on VHF 14"
      : channelLabel(channel.channel);
  button.setAttribute("aria-pressed", String(channel.channel === selectedLiveChannel));
  button.addEventListener("click", () => selectLiveChannel(channel.channel));
  return button;
}

function selectLiveChannel(channel) {
  if (!channel || channel === selectedLiveChannel) {
    return;
  }
  const wasPlaying = !liveAudio.paused || everythingQueueEnabled;
  stopEverythingQueue({ clearQueue: true });
  selectedLiveChannel = channel;
  lastLiveStatusId = null;
  renderLiveChannelPicker();
  renderLiveStatus(findLiveChannel(channel));
  pollLiveActivity();
  liveAudio.pause();
  updateLiveMediaSession(wasPlaying ? "playing" : "paused");
  liveStatus.textContent = wasPlaying
    ? isQueuedLiveMode()
      ? `Starting ${channelLabel(selectedLiveChannel)} queue`
      : "Reconnecting"
    : isQueuedLiveMode()
      ? `${channelLabel(selectedLiveChannel)} queue ready`
      : "Warming stream";
  drawWaitingFrame({ showWaiting: false });
  pollLiveStatus();
  if (isQueuedLiveMode()) {
    liveAudio.removeAttribute("src");
    liveAudio.load();
    renderEverythingQueuePanel();
    if (wasPlaying) {
      connectEverythingLive();
    } else {
      prepareLiveAudio();
    }
    return;
  }
  if (wasPlaying) {
    liveAudio.src = withCacheBust(liveStreamUrl());
    liveAudio.load();
    connectLive();
  } else {
    prepareLiveAudio();
  }
}

function findLiveChannel(channel) {
  if (channel === everythingLiveChannel) {
    return everythingChannelOption();
  }
  if (channel === allButTrafficLiveChannel) {
    return allButTrafficChannelOption();
  }
  const selected = liveChannels.find((item) => item.channel === channel);
  if (selected) {
    return selected;
  }
  return { channel, label: defaultChannelLabels[channel] || "", frequencyMhz: "" };
}

function isEverythingLiveMode() {
  return selectedLiveChannel === everythingLiveChannel;
}

function isAllButTrafficLiveMode() {
  return selectedLiveChannel === allButTrafficLiveChannel;
}

function isQueuedLiveMode() {
  return isEverythingLiveMode() || isAllButTrafficLiveMode();
}

function normalizeTabName(name) {
  return tabRouteAliases[String(name || "").toLowerCase()] || "clips";
}

function routeStateFromLocation() {
  const url = new URL(window.location.href);
  const tabParam = url.searchParams.get("tab");
  const hashSegment = url.hash.replace(/^#\/?/, "");
  const pathSegments = url.pathname.split("/").filter(Boolean);
  const pathSegment = pathSegments[pathSegments.length - 1] || "";
  const routeName = tabParam || hashSegment || pathSegment || "clips";
  return {
    tab: normalizeTabName(routeName),
    clipCollectionFilter: collectionFilterFromRoute(routeName, url),
  };
}

function collectionFilterFromRoute(routeName, url) {
  const normalizedRouteName = String(routeName).toLowerCase();
  if (normalizedRouteName === hallOfFameRouteSegment || url.searchParams.get("featured") === "true") {
    return "featured";
  }
  if (quarantineClipLaneEnabled && url.searchParams.get("quality") === "quarantined") {
    return "quarantined";
  }
  return "recent";
}

function applyRouteStateFromLocation() {
  const routeState = routeStateFromLocation();
  const nextTab = enabledTabName(routeState.tab);
  const filterChanged = clipCollectionFilter !== routeState.clipCollectionFilter;
  clipCollectionFilter = routeState.clipCollectionFilter;
  if (filterChanged) {
    resetClipPagination();
  }
  activateTab(nextTab, { updateRoute: false });
  if (nextTab === "clips" && filterChanged) {
    loadAndRender();
  }
}

function tabRouteUrl(name) {
  const url = new URL(window.location.href);
  let routeSegment = tabRouteSegments[name] || tabRouteSegments.clips;
  if (name === "clips" && clipCollectionFilter === "featured") {
    routeSegment = hallOfFameRouteSegment;
  }
  url.pathname = `/${routeSegment}/`;
  url.search = "";
  if (
    quarantineClipLaneEnabled &&
    name === "clips" &&
    clipCollectionFilter === "quarantined"
  ) {
    url.searchParams.set("quality", "quarantined");
  }
  url.hash = "";
  return url;
}

function updateTabRoute(name, { replaceRoute = false } = {}) {
  if (!window.history || typeof window.history.pushState !== "function") {
    return;
  }
  const nextUrl = tabRouteUrl(name);
  if (nextUrl.href === window.location.href) {
    return;
  }
  const method = replaceRoute ? "replaceState" : "pushState";
  window.history[method]({ tab: name }, "", nextUrl);
}

function routeMetadataForTab(name) {
  const normalized = normalizeTabName(name);
  if (normalized === "clips" && clipCollectionFilter === "featured") {
    return routeMetadata[hallOfFameRouteSegment];
  }
  if (normalized === "clips" && clipCollectionFilter === "quarantined") {
    return routeMetadata.quarantine;
  }
  return routeMetadata[normalized] || routeMetadata.clips;
}

function updateDocumentMetadata(name) {
  const metadata = routeMetadataForTab(name);
  const title = metadata.title === "Elliott Bay VHF" ? metadata.title : `${metadata.title} | Elliott Bay VHF`;
  const description = metadata.description || defaultSiteDescription;
  document.title = title;
  setNamedMeta("description", description);
  setNamedMeta("twitter:title", title);
  setNamedMeta("twitter:description", description);
  setPropertyMeta("og:title", title);
  setPropertyMeta("og:description", description);
  setPropertyMeta("og:url", metadata.url);
  setCanonicalUrl(metadata.url);
}

function setNamedMeta(name, content) {
  let meta = document.querySelector(`meta[name="${name}"]`);
  if (!meta) {
    meta = document.createElement("meta");
    meta.setAttribute("name", name);
    document.head.append(meta);
  }
  meta.setAttribute("content", content);
}

function setPropertyMeta(property, content) {
  let meta = document.querySelector(`meta[property="${property}"]`);
  if (!meta) {
    meta = document.createElement("meta");
    meta.setAttribute("property", property);
    document.head.append(meta);
  }
  meta.setAttribute("content", content);
}

function setCanonicalUrl(url) {
  let canonical = document.querySelector('link[rel="canonical"]');
  if (!canonical) {
    canonical = document.createElement("link");
    canonical.setAttribute("rel", "canonical");
    document.head.append(canonical);
  }
  canonical.setAttribute("href", url);
}

function enabledTabName(name) {
  if (name === "language" && !languageDashboardEnabled) {
    return "clips";
  }
  if (name === "performance" && !performanceDashboardEnabled) {
    return "clips";
  }
  if (name === "map" && !aisDashboardEnabled) {
    return "clips";
  }
  return name;
}

function activateTab(
  name,
  { updateRoute = true, replaceRoute = false, scrollToTab = false } = {},
) {
  name = enabledTabName(normalizeTabName(name));
  const previousTab = activeTab;
  const shouldScrollToTab = scrollToTab && previousTab !== name;
  if (previousTab === "clips" && name !== "clips") {
    stopContinuousClipPlayback();
  }
  activeTab = name;
  tabs.forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.tab === name);
    tab.setAttribute("aria-selected", String(tab.dataset.tab === name));
  });
  Object.entries(panels).forEach(([panelName, panel]) => {
    const active = panelName === name;
    panel.classList.toggle("is-active", active);
    panel.hidden = !active;
  });
  updateDocumentMetadata(name);
  if (refreshButton) {
    refreshButton.hidden = !["clips", "map", "performance"].includes(name);
  }
  if (name === "live") {
    if (liveAudio.paused || !liveAudio.src) {
      prepareLiveAudio();
    }
    startLiveStatusPolling();
    startLiveActivityPolling();
    startWaveform();
  } else {
    suspendLiveView();
  }
  if (name === "language") {
    if (!languagePayloadLoaded) {
      loadAndRenderLanguage();
    } else {
      startTopicPlotRotation();
    }
  } else {
    stopTopicPlotRotation();
  }
  if (name === "search") {
    renderSearchControls();
    if (!latestSearchPayload) {
      renderEmptySearchState();
    }
  }
  if (name === "map") {
    loadAndRenderMap({ showLoading: !mapPayloadLoaded });
  }
  if (name === "performance") {
    loadAndRenderPerformance({ showLoading: !performancePayloadLoaded });
    startPerformancePolling();
  } else {
    stopPerformancePolling();
  }
  if (updateRoute) {
    updateTabRoute(name, { replaceRoute });
  }
  if (shouldScrollToTab) {
    scrollTabViewToTop();
  }
}

function scrollTabViewToTop() {
  if (!tabViewStart) {
    return;
  }
  window.scrollTo({ top: Math.max(0, tabViewStart.offsetTop), behavior: "auto" });
}

async function loadAndRenderLanguage() {
  if (!languageStatus || !lexicalAnalysis) {
    return;
  }
  languageStatus.textContent = "Loading analysis...";
  const payload = await loadLanguagePayload();
  languagePayloadLoaded = true;
  latestLanguagePayload = payload;
  renderLanguageDashboard(payload);
}

async function loadAndRenderMap({ showLoading = true } = {}) {
  if (!mapStatus || !aisCatcherFrame) {
    return;
  }
  if (showLoading || !mapPayloadLoaded) {
    mapStatus.textContent = "Loading AIS...";
  }
  mapPayloadLoaded = true;
  try {
    await probeAisCatcherViewer();
    renderAisCatcherFrame();
  } catch {
    renderAisCatcherUnavailable();
  }
}

async function probeAisCatcherViewer() {
  const response = await fetch(aisReceiverStatusUrl, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`AIS receiver returned ${response.status}`);
  }
  await response.json();
}

function renderAisCatcherFrame() {
  if (!aisCatcherFrame || !mapStatus) {
    return;
  }
  aisCatcherFrame.hidden = false;
  if (aisCatcherUnavailable) {
    aisCatcherUnavailable.hidden = true;
  }
  aisCatcherFrame.src = aisCatcherFrameUrl;
  aisCatcherFrame.title = "AIS-catcher live map";
  mapStatus.textContent = "Showing AIS-catcher live map";
  if (aisFallbackLink) {
    aisFallbackLink.href = aisCatcherFallbackUrl;
  }
}

function renderAisCatcherUnavailable() {
  if (!aisCatcherFrame || !mapStatus) {
    return;
  }
  aisCatcherFrame.removeAttribute("src");
  aisCatcherFrame.hidden = true;
  aisCatcherFrame.title = "AIS receiver unavailable";
  if (aisCatcherUnavailable) {
    aisCatcherUnavailable.hidden = false;
  }
  mapStatus.textContent = "AIS receiver is temporarily unavailable.";
  if (aisFallbackLink) {
    aisFallbackLink.href = aisCatcherFallbackUrl;
  }
}

function renderLanguageDashboard(payload) {
  stopTopicPlotRotation();
  const status = payload?.status || "missing";
  if (status === "missing") {
    languageStatus.textContent = "No analysis cache yet";
  } else {
    const generated = payload.generated_at ? `Analyzed ${formatDateTime(payload.generated_at)}` : "Analysis ready";
    languageStatus.textContent = generated;
  }

  const frequency = payload.frequency || {};
  const terms = payload.terms || {};
  const topics = payload.topics || {};
  const channelCounts = channelCountsForListenableChannels(
    payload.channels || frequency.by_channel || {},
  );
  const cards = document.createElement("div");
  cards.className = "language-grid";
  cards.append(
    languageCard(
      "Analyzed transcripts",
      Number(payload.source_clip_count || 0).toLocaleString("en-US"),
      "Intelligible transcript records; audio may age out",
    ),
    languageCard(
      "Analyzed channels",
      activeChannelSummary(channelCounts),
      "VHF channels with at least one analyzed clip",
    ),
    languageCard(
      "Dominant theme",
      dominantThemeSummary(topics),
      "Largest non-outlier topic by analyzed clips",
    ),
    languageCard("Topic model", topicStatus(topics), "Condensed topic clusters"),
  );

  const channelPanel = languagePanel("Analyzed transcript clips by VHF channel");
  const chartHeader = document.createElement("div");
  chartHeader.className = "chart-panel-header";
  const note = document.createElement("p");
  note.className = "muted-inline";
  note.textContent = "Seattle Traffic hidden so the other channels can scale up.";
  if (!hideAnalysisTrafficOutlier) {
    note.textContent = "Showing all analyzed channels.";
  }
  chartHeader.append(note, renderAnalysisTrafficToggle());
  channelPanel.append(chartHeader, channelActivityChart(channelCounts));

  const wordsPanel = languagePanel("Radio words");
  wordsPanel.append(
    termSection("Jargon", terms.semantic_buckets?.communication_markers || []),
    termSection("Movement", terms.semantic_buckets?.movement || []),
    termSection("Places", terms.semantic_buckets?.places || []),
    termSection("N-grams", terms.bigrams || []),
  );

  const topicPanel = languagePanel(
    "BERTopic transcript clusters",
    "3D BERTopic cluster map and representative topic cards from the analyzed transcript corpus.",
  );
  const topicFrame = document.createElement("iframe");
  topicFrame.className = "topic-frame";
  topicFrame.loading = "lazy";
  topicFrame.title = "BERTopic 3D cluster map";
  topicFrame.allowFullscreen = true;
  topicFrame.setAttribute("allow", "fullscreen");
  topicFrame.src = topics.plot_url || topicClusterFallbackUrl;
  const topicFrameShell = document.createElement("div");
  topicFrameShell.className = "topic-frame-shell";
  topicFrame.addEventListener("load", () => {
    hideUnavailableTopicFrame(topicFrame, topicFrameShell);
    if (activeTab === "language" && !topicFrameShell.hidden) {
      sendTopicPlotRotation(topicFrame, true);
    }
  });
  topicFrameShell.append(topicFrame);
  topicPanel.append(topicFrameShell, topicList(nonOutlierTopics(topics.items || [])));

  const entityPanel = languagePanel("Suspected vessels and entities");
  entityPanel.append(entityList(payload.entities || []));

  const educationPanel = languagePanel("Maritime radio references");
  educationPanel.append(educationGuideList(payload.education_guide || []));
  const referencePanel = referenceIndex(payload.education || []);

  lexicalAnalysis.replaceChildren(cards, channelPanel, topicPanel, wordsPanel, entityPanel, educationPanel, referencePanel);
}

function sendTopicPlotRotation(topicFrame, enabled) {
  if (!(topicFrame instanceof HTMLIFrameElement) || !topicFrame.contentWindow) {
    return;
  }
  topicFrame.contentWindow.postMessage(
    { type: topicPlotRotationMessageType, enabled },
    window.location.origin,
  );
}

function startTopicPlotRotation() {
  sendTopicPlotRotation(lexicalAnalysis?.querySelector(".topic-frame"), true);
}

function stopTopicPlotRotation() {
  sendTopicPlotRotation(lexicalAnalysis?.querySelector(".topic-frame"), false);
}

function hideUnavailableTopicFrame(topicFrame, topicFrameShell) {
  if (!(topicFrameShell instanceof HTMLElement)) {
    return;
  }
  let bodyText = "";
  try {
    bodyText = topicFrame.contentDocument?.body?.textContent?.trim() || "";
  } catch {
    return;
  }
  const notFoundPayload =
    bodyText === "Not Found" ||
    bodyText === '{"detail":"Not Found"}' ||
    bodyText === '{"detail":"asset not found"}' ||
    /^\{\s*"detail"\s*:\s*"(?:Not Found|asset not found)"\s*\}$/.test(bodyText);
  if (!notFoundPayload) {
    return;
  }
  topicFrameShell.hidden = true;
  topicFrameShell.setAttribute("aria-hidden", "true");
}

async function loadAndRenderPerformance({ showLoading = true } = {}) {
  if (!performanceStatus || !performanceDashboard) {
    return;
  }
  if (showLoading || !performancePayloadLoaded) {
    performanceStatus.textContent = "Loading performance...";
  }
  try {
    const [performanceResult, aisReceiverResult, liveChannelsResult] = await Promise.allSettled([
      loadPerformanceStatus(),
      loadAisReceiverStatus(),
      loadLiveChannelsStatus(),
    ]);
    if (performanceResult.status !== "fulfilled") {
      throw performanceResult.reason;
    }
    const payload = {
      ...performanceResult.value,
      aisReceiver:
        aisReceiverResult.status === "fulfilled"
          ? aisReceiverResult.value
          : systemKpiLoadUnavailable("AIS receiver", aisReceiverResult.reason),
      liveChannels:
        liveChannelsResult.status === "fulfilled"
          ? liveChannelsResult.value
          : systemKpiLoadUnavailable("Live channels", liveChannelsResult.reason),
    };
    performancePayloadLoaded = true;
    latestPerformancePayload = payload;
    renderPerformanceDashboard(payload);
  } catch {
    performanceStatus.textContent = "Performance unavailable";
    performanceDashboard.replaceChildren(emptyPerformanceState());
  }
}

async function loadPerformanceStatus() {
  const response = await fetch(performanceUrl, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`performance HTTP ${response.status}`);
  }
  return response.json();
}

async function loadAisReceiverStatus() {
  const response = await fetch(aisReceiverStatusUrl, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`AIS receiver HTTP ${response.status}`);
  }
  const payload = await response.json();
  const ships = Array.isArray(payload.ships) ? payload.ships : [];
  const count = Number(payload.count);
  const vesselCount = Number.isFinite(count) ? count : ships.length;
  return {
    status: vesselCount > 0 ? "ok" : "watch",
    vesselCount,
    station: payload.station || null,
  };
}

async function loadLiveChannelsStatus() {
  const response = await fetch(liveChannelsUrl, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`live channels HTTP ${response.status}`);
  }
  const payload = await response.json();
  const channels = Array.isArray(payload.channels) ? payload.channels : [];
  return {
    status: channels.length > 0 ? "ok" : "watch",
    channelCount: channels.length,
    defaultChannel: payload.defaultChannel || "",
  };
}

function systemKpiLoadUnavailable(label, reason = "") {
  return {
    status: "unknown",
    label,
    reason: String(reason || `${label} did not load`),
  };
}

function startPerformancePolling() {
  stopPerformancePolling();
  performanceRefreshTimer = setTimeout(pollPerformance, performanceRefreshMs);
}

function stopPerformancePolling() {
  if (performanceRefreshTimer) {
    clearTimeout(performanceRefreshTimer);
    performanceRefreshTimer = null;
  }
}

async function pollPerformance() {
  if (activeTab !== "performance") {
    return;
  }
  await loadAndRenderPerformance({ showLoading: false });
  startPerformancePolling();
}

function renderPerformanceDashboard(payload) {
  const generated = payload.generatedAt
    ? `Updated ${formatPerformanceDateTime(payload.generatedAt)}`
    : "Snapshot ready";
  performanceStatus.textContent = generated;
  const hosts = performanceHosts(payload);
  if (!hosts.length) {
    performanceDashboard.replaceChildren(emptyPerformanceState());
    return;
  }
  const rangeControl = performanceRangeControl();
  const systemKpis = renderSystemKpiPanel(payload, hosts);
  const hostGrid = document.createElement("div");
  hostGrid.className = "performance-host-grid";
  hostGrid.append(...hosts.map((host, index) => performanceHostPanel(host, index)));
  performanceDashboard.replaceChildren(rangeControl, systemKpis, hostGrid);
}

function renderSystemKpiPanel(payload, hosts) {
  const panel = document.createElement("section");
  panel.className = "system-kpi-panel";
  const title = document.createElement("h3");
  title.textContent = "System KPIs";
  const grid = document.createElement("div");
  grid.className = "system-kpi-grid";
  const liveChannels = payload.liveChannels || {};
  const aisReceiver = payload.aisReceiver || {};
  const piHost = piPerformanceHost(hosts);
  grid.append(
    systemKpiCard(
      "Live API",
      statusLabel(payload.status || "unknown"),
      payload.generatedAt
        ? `Telemetry updated ${formatPerformanceDateTime(payload.generatedAt)}`
        : "Telemetry endpoint responded",
      payload.status || "unknown",
    ),
    systemKpiCard(
      "Live channels",
      Number.isFinite(Number(liveChannels.channelCount))
        ? formatCountNoun(Number(liveChannels.channelCount), "channel", "channels")
        : "Unknown",
      liveChannels.defaultChannel ? `Default VHF ${liveChannels.defaultChannel}` : "Channel API status",
      liveChannels.status || "unknown",
    ),
    systemKpiCard(
      "AIS receiver",
      Number.isFinite(Number(aisReceiver.vesselCount))
        ? formatCountNoun(Number(aisReceiver.vesselCount), "vessel", "vessels")
        : "Unknown",
      aisReceiver.station ? "AIS-catcher station is responding" : "AIS-catcher station status",
      aisReceiver.status || "unknown",
    ),
    systemKpiCard(
      "AISFriends",
      "External UDP",
      "Edge feed is validated by receiver health checks, not browser fetches",
      aisReceiver.status === "ok" ? "ok" : "unknown",
    ),
    systemKpiCard(
      "Pi telemetry",
      statusLabel(piHost?.status || "unknown"),
      piTelemetryCaption(piHost),
      piHost?.status || "unknown",
    ),
    systemKpiCard(
      "Prod guard",
      systemDashboardEnabled ? "Dev only" : "Disabled",
      "System stats stay hidden on production and the API returns 404 there",
      systemDashboardEnabled ? "ok" : "unknown",
    ),
  );
  panel.append(title, grid);
  return panel;
}

function systemKpiCard(label, value, caption, status) {
  const card = performanceCard(label, value, caption, status);
  card.classList.add("system-kpi-card");
  return card;
}

function piPerformanceHost(hosts) {
  return (hosts || []).find((host, index) => hostRole(host, index) === fallbackDecoderHostLabel) || null;
}

function piTelemetryCaption(host) {
  if (!host) {
    return "Pi host is not present in this snapshot";
  }
  const thermal = host.thermal?.temperatureC;
  if (Number.isFinite(Number(thermal))) {
    return `Thermals ${formatMetricChartValue(Number(thermal), " C")}`;
  }
  if (host.reachable === false) {
    return "Pi telemetry read failed";
  }
  return "Pi telemetry snapshot received";
}

function performanceHosts(payload) {
  const hosts = Array.isArray(payload.hosts) ? payload.hosts.filter(Boolean) : [];
  if (hosts.length) {
    return hosts;
  }
  return payload.host ? [payload.host] : [];
}

function hostRole(host, index) {
  if (host?.role) {
    return performanceRoleLabel(host.role);
  }
  return index === 0 ? performanceHostLabel : fallbackDecoderHostLabel;
}

function performanceRoleLabel(role) {
  return legacyPerformanceRoleLabels.get(String(role)) || role;
}

function performanceHostPanel(host, index) {
  const role = hostRole(host, index);
  const panel = document.createElement("section");
  panel.className = "performance-host";
  const title = document.createElement("h3");
  title.textContent = role;
  const cards = document.createElement("div");
  cards.className = "performance-grid";
  const disks = host?.disks || [];
  const cpuSummary = performanceSummaryMetric(host, "cpuUtilizationPercent", "%", "cpu");
  const memorySummary = performanceSummaryMetric(host, "memoryUsedPercent", "%", "memory");
  const thermalSummary = performanceSummaryMetric(host, "thermalTemperatureC", " C", "thermal");
  cards.append(
    performanceCard(
      "CPU utilization",
      cpuSummary.label,
      performanceWindowCaption(cpuSummary.samples, `${host?.cpuCount || "?"} logical CPUs`),
      cpuSummary.status,
    ),
    performanceCard(
      "Memory",
      memorySummary.label,
      performanceWindowCaption(memorySummary.samples),
      memorySummary.status,
    ),
    performanceCard("Disk", diskSummary(disks), "Most used filesystem", worstItemStatus(disks)),
    performanceCard(
      "Thermals",
      thermalSummary.label,
      performanceWindowCaption(thermalSummary.samples),
      thermalSummary.status,
    ),
  );
  const charts = document.createElement("div");
  charts.className = "performance-chart-grid";
  charts.append(
    performanceMetricChart("CPU", host?.history, "cpuUtilizationPercent", "%", "cpu"),
    performanceMetricChart("Memory", host?.history, "memoryUsedPercent", "%", "memory"),
    performanceMetricChart("Thermals", host?.history, "thermalTemperatureC", " C", "thermal"),
  );
  panel.append(title, cards, charts);
  return panel;
}

function performanceCard(label, value, caption, status) {
  const card = document.createElement("article");
  card.className = `performance-card ${statusClass(status)}`;
  const heading = document.createElement("p");
  heading.className = "language-label";
  heading.textContent = label;
  const metric = document.createElement("strong");
  metric.textContent = value;
  const note = document.createElement("span");
  note.textContent = caption;
  card.append(heading, metric, note);
  return card;
}

function performanceRangeControl() {
  const control = document.createElement("div");
  control.className = "performance-range-control";
  performanceRangeOptions.forEach((option) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "performance-range-option";
    button.textContent = option.label;
    button.setAttribute("aria-pressed", String(option.hours === selectedPerformanceRangeHours));
    button.addEventListener("click", () => {
      selectedPerformanceRangeHours = option.hours;
      if (latestPerformancePayload) {
        renderPerformanceDashboard(latestPerformancePayload);
      }
    });
    control.append(button);
  });
  return control;
}

function performanceMetricChart(label, history, field, suffix, className) {
  const chart = document.createElement("article");
  chart.className = `performance-chart is-${className}`;
  const samples = performanceMetricSamples(history, field);
  const heading = document.createElement("div");
  heading.className = "performance-chart-header";
  const title = document.createElement("p");
  title.className = "language-label";
  title.textContent = label;
  const value = document.createElement("strong");
  value.className = "performance-chart-value";
  value.textContent = formatMetricChartValue(averageMetricValue(samples), suffix);
  heading.append(title, value);

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.classList.add("performance-chart-svg");
  svg.setAttribute("viewBox", "0 0 320 124");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `${label} time series`);
  const chartState = drawPerformanceMetricChart(svg, samples, suffix);

  const tooltip = document.createElement("span");
  tooltip.className = "performance-chart-tooltip";
  tooltip.hidden = true;
  attachPerformanceChartTooltip(chart, svg, tooltip, samples, suffix, chartState);

  const caption = document.createElement("span");
  caption.className = "performance-chart-caption";
  caption.textContent = performanceChartCaption(samples);
  chart.append(heading, svg, tooltip, caption);
  return chart;
}

function performanceMetricSamples(history, field) {
  const rows = Array.isArray(history) ? history : [];
  const samples = rows
    .map((sample) => {
      const value = Number(sample?.[field]);
      const time = performanceSampleTime(sample);
      if (!Number.isFinite(value) || !Number.isFinite(time)) {
        return null;
      }
      return { generatedAt: sample.generatedAt, time, value };
    })
    .filter(Boolean);
  const latestTime = samples.reduce((latest, sample) => Math.max(latest, sample.time), 0);
  const cutoff = latestTime - selectedPerformanceRangeHours * 60 * 60 * 1000;
  return samples.filter((sample) => sample.time >= cutoff);
}

function averageMetricValue(samples) {
  if (!samples.length) {
    return NaN;
  }
  const total = samples.reduce((sum, sample) => sum + sample.value, 0);
  return total / samples.length;
}

function drawPerformanceMetricChart(svg, samples, suffix) {
  const width = 320;
  const height = 124;
  const left = 34;
  const right = 12;
  const top = 12;
  const bottom = 26;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const maxValue = 100;
  svg.dataset.windowHours = String(selectedPerformanceRangeHours);
  [0, 50, 100].forEach((tick) => {
    const y = top + plotHeight - (tick / maxValue) * plotHeight;
    const line = performanceSvgElement("line");
    line.setAttribute("x1", left);
    line.setAttribute("x2", width - right);
    line.setAttribute("y1", y.toFixed(1));
    line.setAttribute("y2", y.toFixed(1));
    line.classList.add("performance-chart-gridline");
    svg.append(line);
    const label = performanceSvgElement("text");
    label.setAttribute("x", "4");
    label.setAttribute("y", (y + 4).toFixed(1));
    label.classList.add("performance-chart-axis");
    label.textContent = tick === 100 && suffix === " C" ? "100C" : `${tick}${suffix.trim()}`;
    svg.append(label);
  });
  if (!samples.length) {
    const empty = performanceSvgElement("text");
    empty.setAttribute("x", "160");
    empty.setAttribute("y", "66");
    empty.classList.add("performance-chart-empty");
    empty.textContent = "Waiting for samples";
    svg.append(empty);
    return { points: [], hoverLine: null, hoverDot: null };
  }
  const timeWindow = performanceChartTimeWindow(samples);
  drawPerformanceTimeAxis(svg, timeWindow, { left, right, top, bottom, width, height, plotWidth });
  const points = samples.map((sample) => {
    const ratio = Math.max(0, Math.min(1, (sample.time - timeWindow.start) / timeWindow.duration));
    const x = left + ratio * plotWidth;
    const clampedValue = Math.max(0, Math.min(maxValue, sample.value));
    const y = top + plotHeight - (clampedValue / maxValue) * plotHeight;
    return { x, y };
  });
  if (points.length > 1) {
    const path = performanceSvgElement("path");
    path.setAttribute(
      "d",
      points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" "),
    );
    path.classList.add("performance-chart-line");
    svg.append(path);
  }
  const dot = performanceSvgElement("circle");
  const latestPoint = points[points.length - 1];
  dot.setAttribute("cx", latestPoint.x.toFixed(1));
  dot.setAttribute("cy", latestPoint.y.toFixed(1));
  dot.setAttribute("r", "2.2");
  dot.classList.add("performance-chart-dot");
  svg.append(dot);
  const hoverLine = performanceSvgElement("line");
  hoverLine.setAttribute("y1", String(top));
  hoverLine.setAttribute("y2", String(height - bottom));
  hoverLine.classList.add("performance-chart-hover-line");
  hoverLine.hidden = true;
  const hoverDot = performanceSvgElement("circle");
  hoverDot.setAttribute("r", "3.4");
  hoverDot.classList.add("performance-chart-hover-dot");
  hoverDot.hidden = true;
  const hitArea = performanceSvgElement("rect");
  hitArea.setAttribute("x", String(left));
  hitArea.setAttribute("y", String(top));
  hitArea.setAttribute("width", String(plotWidth));
  hitArea.setAttribute("height", String(plotHeight));
  hitArea.classList.add("performance-chart-hit-area");
  svg.append(hoverLine, hoverDot, hitArea);
  return { points, hoverLine, hoverDot };
}

function performanceChartTimeWindow(samples) {
  const latest = samples.reduce((currentLatest, sample) => Math.max(currentLatest, sample.time), 0);
  const duration = Math.max(1, selectedPerformanceRangeHours * 60 * 60 * 1000);
  return {
    start: latest - duration,
    end: latest,
    duration,
  };
}

function drawPerformanceTimeAxis(svg, timeWindow, geometry) {
  for (const tick of performanceChartTimeTicks(timeWindow)) {
    const x = geometry.left + tick.ratio * geometry.plotWidth;
    const line = performanceSvgElement("line");
    line.setAttribute("x1", x.toFixed(1));
    line.setAttribute("x2", x.toFixed(1));
    line.setAttribute("y1", String(geometry.top));
    line.setAttribute("y2", String(geometry.height - geometry.bottom));
    line.classList.add("performance-chart-x-gridline");
    const label = performanceSvgElement("text");
    label.setAttribute("x", x.toFixed(1));
    label.setAttribute("y", String(geometry.height - 7));
    label.setAttribute("text-anchor", tick.anchor);
    label.classList.add("performance-chart-x-axis");
    label.textContent = formatPerformanceTickTime(tick.time);
    svg.append(line, label);
  }
}

function performanceChartTimeTicks(timeWindow) {
  return [0, 1 / 3, 2 / 3, 1].map((ratio, index) => ({
    ratio,
    anchor: index === 0 ? "start" : index === 3 ? "end" : "middle",
    time: timeWindow.start + ratio * timeWindow.duration,
  }));
}

function attachPerformanceChartTooltip(chart, svg, tooltip, samples, suffix, chartState) {
  if (!samples.length || !chartState.points.length) {
    return;
  }
  const setHover = (event) => {
    const bounds = svg.getBoundingClientRect();
    const x = ((event.clientX - bounds.left) / Math.max(1, bounds.width)) * 320;
    const nearest = nearestPerformancePoint(chartState.points, x);
    const sample = samples[nearest.index];
    chartState.hoverLine.hidden = false;
    chartState.hoverDot.hidden = false;
    chartState.hoverLine.setAttribute("x1", nearest.point.x.toFixed(1));
    chartState.hoverLine.setAttribute("x2", nearest.point.x.toFixed(1));
    chartState.hoverDot.setAttribute("cx", nearest.point.x.toFixed(1));
    chartState.hoverDot.setAttribute("cy", nearest.point.y.toFixed(1));
    tooltip.removeAttribute("hidden");
    tooltip.textContent = `${formatMetricChartValue(sample.value, suffix)} · ${formatPerformanceDateTime(sample.generatedAt)}`;
    tooltip.style.left = `${Math.max(8, Math.min(bounds.width - 8, (nearest.point.x / 320) * bounds.width)).toFixed(1)}px`;
  };
  svg.addEventListener("mousemove", setHover);
  svg.addEventListener("mouseenter", setHover);
  svg.addEventListener("pointermove", setHover);
  chart.addEventListener("mousemove", setHover);
  chart.addEventListener("mouseenter", setHover);
  chart.addEventListener("pointermove", setHover);
  chart.addEventListener("mouseleave", () => {
    chartState.hoverLine.hidden = true;
    chartState.hoverDot.hidden = true;
    tooltip.setAttribute("hidden", "");
  });
}

function nearestPerformancePoint(points, x) {
  return points.reduce(
    (nearest, point, index) => {
      const distance = Math.abs(point.x - x);
      return distance < nearest.distance ? { point, index, distance } : nearest;
    },
    { point: points[0], index: 0, distance: Math.abs(points[0].x - x) },
  );
}

function performanceSvgElement(name) {
  return document.createElementNS("http://www.w3.org/2000/svg", name);
}

function performanceSampleTime(sample) {
  if (!sample?.generatedAt) {
    return NaN;
  }
  const time = new Date(sample.generatedAt).getTime();
  return Number.isFinite(time) ? time : NaN;
}

function formatPerformanceTickTime(timestamp) {
  const date = new Date(timestamp);
  if (!Number.isFinite(date.getTime())) {
    return "";
  }
  if (selectedPerformanceRangeHours > 12) {
    return performanceDayTickFormatter.format(date);
  }
  return pacificShortTimeFormatter.format(date);
}

function formatMetricChartValue(value, suffix) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "Unknown";
  }
  return `${number.toFixed(1)}${suffix}`;
}

function performanceChartCaption(samples) {
  if (!samples.length) {
    return "Average over selected window";
  }
  if (samples.length < 2) {
    return `Average over selected window · ${formatPerformanceDateTime(samples[0].generatedAt)}`;
  }
  return `Average over selected window · ${formatPerformanceDateTime(samples[0].generatedAt)} - ${formatPerformanceDateTime(samples[samples.length - 1].generatedAt)}`;
}

function emptyPerformanceState() {
  const empty = document.createElement("p");
  empty.className = "muted-inline";
  empty.textContent = "No performance snapshot is available.";
  return empty;
}

function hostStatus(host, key) {
  return host?.[key]?.status || "unknown";
}

function performanceSummaryMetric(host, field, suffix, statusKey) {
  const samples = performanceSummarySamples(host, field);
  const value = averageMetricValue(samples);
  return {
    samples,
    value,
    label: formatMetricChartValue(value, suffix),
    status: performanceSummaryStatus(field, value, hostStatus(host, statusKey)),
  };
}

function performanceSummarySamples(host, field) {
  return performanceMetricSamples(host?.history, field);
}

function performanceSummaryStatus(field, value, fallbackStatus = "unknown") {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return fallbackStatus;
  }
  if (field === "thermalTemperatureC") {
    return thresholdStatus(number, 70, 85);
  }
  return thresholdStatus(number, 75, 90);
}

function thresholdStatus(value, watchAt, highAt) {
  if (value >= highAt) {
    return "high";
  }
  if (value >= watchAt) {
    return "watch";
  }
  return "ok";
}

function performanceWindowCaption(samples, extra = "") {
  const base = samples.length ? "Average over selected window" : "No samples in selected window";
  return extra ? `${base}; ${extra}` : base;
}

function diskSummary(disks) {
  const values = disks.map((disk) => Number(disk.usedPercent)).filter(Number.isFinite);
  if (!values.length) {
    return "Unknown";
  }
  return percentLabel(Math.max(...values));
}

function worstItemStatus(items) {
  const ranks = { high: 3, watch: 2, ok: 1, unknown: 0 };
  return items.reduce((worst, item) => (ranks[item.status] > ranks[worst] ? item.status : worst), "unknown");
}

function statusLabel(status) {
  return {
    high: "High",
    watch: "Watch",
    ok: "OK",
    unknown: "Unknown",
  }[status] || "Unknown";
}

function statusClass(status) {
  return `is-${statusLabel(status).toLowerCase()}`;
}

function percentLabel(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "Unknown";
  }
  return `${number.toFixed(1)}%`;
}

function languageCard(label, value, caption) {
  const card = document.createElement("article");
  card.className = "language-card";
  const heading = document.createElement("p");
  heading.className = "language-label";
  heading.textContent = label;
  const metric = document.createElement("strong");
  metric.textContent = value;
  const note = document.createElement("span");
  note.textContent = caption;
  card.append(heading, metric, note);
  return card;
}

function languagePanel(titleText, descriptionText = "") {
  const section = document.createElement("section");
  section.className = "language-panel";
  const title = document.createElement("h3");
  title.textContent = titleText;
  section.append(title);
  if (descriptionText) {
    const description = document.createElement("p");
    description.className = "language-panel-intro";
    description.textContent = descriptionText;
    section.append(description);
  }
  return section;
}

function sumCounts(items) {
  return (items || []).reduce((total, item) => total + Math.max(0, Number(item?.count || 0)), 0);
}

function activeChannelSummary(channelCounts) {
  const vhfCount = activeAnalyzedChannelCount(channelCounts);
  return formatCountNoun(vhfCount, "channel", "channels");
}

function activeAnalyzedChannelCount(channelCounts) {
  return Object.values(channelCounts || {}).filter((count) => Number(count || 0) > 0).length;
}

function formatCountNoun(count, singular, plural) {
  const value = Number(count || 0);
  return `${value.toLocaleString()} ${value === 1 ? singular : plural}`;
}

function listenableAnalysisChannelIds() {
  if (!liveChannelsLoaded) {
    return new Set();
  }
  return new Set(
    liveChannels
      .filter((channel) => channel.streamPath)
      .map((channel) => String(channel.channel || "").toUpperCase())
      .filter(Boolean),
  );
}

function channelCountsForListenableChannels(channelCounts) {
  const normalizedCounts = Object.fromEntries(
    Object.entries(channelCounts || {}).map(([channel, count]) => [
      String(channel || "").toUpperCase(),
      Number(count || 0),
    ]),
  );
  const merged = {};
  for (const channel of listenableAnalysisChannelIds()) {
    merged[channel] = normalizedCounts[channel] || 0;
  }
  return merged;
}

function termSection(title, items) {
  const wrapper = document.createElement("div");
  wrapper.className = "term-section";
  const label = document.createElement("p");
  label.className = "language-label";
  label.textContent = title;
  const list = document.createElement("div");
  list.className = "term-list";
  const terms = items.slice(0, 12);
  if (!terms.length) {
    const empty = document.createElement("span");
    empty.className = "muted-inline";
    empty.textContent = "No signals yet";
    list.append(empty);
  } else {
    list.append(...terms.map((item) => renderPill(`${item.term} ${item.count}`)));
  }
  wrapper.append(label, list);
  return wrapper;
}

function entityList(entities) {
  const list = document.createElement("div");
  list.className = "entity-list";
  if (!entities.length) {
    const empty = document.createElement("p");
    empty.className = "muted-inline";
    empty.textContent = "No suspected vessels yet.";
    list.append(empty);
    return list;
  }
  list.append(
    ...entities.slice(0, 10).map((entity) => {
      const item = document.createElement("article");
      item.className = "entity-card";
      const title = document.createElement("h4");
      title.textContent = entity.name || "Unknown";
      const meta = document.createElement("p");
      meta.className = "entity-meta";
      meta.textContent = `${entity.kind || "entity"} · ${entity.count || 0} mentions · ${confidenceText(entity.confidence)}`;
      const channels = document.createElement("div");
      channels.className = "clip-meta";
      for (const channel of Object.keys(entity.channels || {}).sort(compareChannels)) {
        channels.append(renderChannelPill(channel));
      }
      const playableExample = entityExampleWithAudio(entity);
      const displayedExample = playableExample || entity.examples?.[0] || {};
      const quote = document.createElement("blockquote");
      quote.textContent = displayedExample.text || "";
      item.append(title, meta, channels, quote);
      const player = renderExamplePlayer(playableExample || {});
      if (player) {
        item.append(player);
      }
      return item;
    }),
  );
  return list;
}

function entityExampleWithAudio(entity) {
  const examples = Array.isArray(entity?.examples) ? entity.examples : [];
  return examples.find((example) => analysisAudioUrlForClip(example)) || null;
}

function renderExamplePlayer(example) {
  const audioUrl = analysisAudioUrlForClip(example);
  if (!audioUrl) {
    return null;
  }

  const player = document.createElement("div");
  player.className = "example-player";

  const audio = document.createElement("audio");
  audio.controls = false;
  audio.preload = "none";
  audio.src = audioUrl;
  audio.setAttribute("controlslist", "nodownload noplaybackrate noremoteplayback");
  audio.setAttribute("disableremoteplayback", "");
  audio.setAttribute("x-webkit-airplay", "deny");

  const button = document.createElement("button");
  button.type = "button";
  button.className = "clip-play-button";
  button.setAttribute("aria-label", "Play clip");

  const progressControls = document.createElement("div");
  progressControls.className = "clip-progress-controls";
  const progress = document.createElement("input");
  progress.type = "range";
  progress.className = "clip-progress-input";
  progress.min = "0";
  progress.max = String(Math.max(1, Number(example.duration_seconds) || 0));
  progress.step = "0.01";
  progress.value = "0";
  progress.setAttribute("aria-label", "Clip playback position");
  const waveformShell = document.createElement("div");
  waveformShell.className = "clip-waveform-shell";
  const waveformCanvas = document.createElement("canvas");
  waveformCanvas.className = "clip-waveform-canvas";
  waveformCanvas.setAttribute("aria-hidden", "true");
  waveformShell.append(waveformCanvas, progress);
  const time = document.createElement("span");
  time.className = "example-player-time";
  progressControls.append(waveformShell, time);
  observeClipWaveform(waveformCanvas, audioUrl);
  updateClipPlaybackProgress(audio, progress, time, example.duration_seconds);

  setClipPlayButtonState(button, audio.paused);
  const playAudio = async () => {
    prioritizeClipWaveform(waveformCanvas);
    try {
      await audio.play();
      return true;
    } catch {
      await refreshClipAudioPlayback(example, audio, time, { force: true });
      try {
        await audio.play();
        return true;
      } catch {
        setClipPlayButtonState(button, true);
        time.textContent = "Tap to retry";
        return false;
      }
    }
  };
  clipAudioPlayActions.set(audio, playAudio);
  button.addEventListener("click", async () => {
    if (continuousClipPlaybackActive) {
      stopContinuousClipPlayback({ stopAudio: false });
    }
    if (!audio.paused) {
      audio.pause();
      return;
    }
    await playAudio();
  });

  audio.addEventListener("loadedmetadata", () => {
    updateClipPlaybackProgress(audio, progress, time, example.duration_seconds);
  });
  audio.addEventListener("durationchange", () => {
    updateClipPlaybackProgress(audio, progress, time, example.duration_seconds);
  });
  audio.addEventListener("timeupdate", () => {
    updateClipPlaybackProgress(audio, progress, time, example.duration_seconds);
  });
  progress.addEventListener("input", () => {
    const nextTime = Number(progress.value);
    if (!Number.isFinite(nextTime)) {
      return;
    }
    try {
      audio.currentTime = nextTime;
    } catch {
      return;
    }
    updateClipPlaybackProgress(audio, progress, time, example.duration_seconds);
  });
  audio.addEventListener("play", () => {
    setClipPlayButtonState(button, audio.paused);
    stopOtherAudio(audio);
    currentClipPlayback = audio;
    clearBrowserMediaSession();
    refreshClipAudioPlayback(example, audio, time);
  });
  audio.addEventListener("error", () => {
    refreshClipAudioPlayback(example, audio, time, { force: true });
  });
  audio.addEventListener("pause", () => {
    setClipPlayButtonState(button, audio.paused);
    if (currentClipPlayback === audio) {
      currentClipPlayback = null;
    }
  });
  audio.addEventListener("ended", () => {
    setClipPlayButtonState(button, true);
    updateClipPlaybackProgress(audio, progress, time, example.duration_seconds);
    if (currentClipPlayback === audio) {
      currentClipPlayback = null;
    }
  });

  player.append(button, audio, progressControls);
  return player;
}

function ensureClipWaveformObservers() {
  if (!clipWaveformObserver && "IntersectionObserver" in window) {
    clipWaveformObserver = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) {
            continue;
          }
          clipWaveformObserver.unobserve(entry.target);
          queueClipWaveform(entry.target);
        }
      },
      { rootMargin: "200px 0px" },
    );
  }
  if (!clipWaveformResizeObserver && "ResizeObserver" in window) {
    clipWaveformResizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const state = clipWaveformStates.get(entry.target);
        if (state?.peaks) {
          drawClipWaveform(entry.target, state.progressPercent);
        }
      }
    });
  }
}

function observeClipWaveform(canvas, audioUrl) {
  ensureClipWaveformObservers();
  clipWaveformStates.set(canvas, {
    audioUrl,
    peaks: null,
    progressPercent: 0,
    status: "observed",
  });
  canvas.dataset.waveformStatus = "pending";
  clipWaveformResizeObserver?.observe(canvas);
  if (clipWaveformObserver) {
    clipWaveformObserver.observe(canvas);
  } else {
    queueClipWaveform(canvas);
  }
}

function prioritizeClipWaveform(canvas) {
  const state = clipWaveformStates.get(canvas);
  if (!state || state.status === "loading" || state.status === "ready") {
    return;
  }
  clipWaveformObserver?.unobserve(canvas);
  if (state.status === "queued") {
    const queuedIndex = clipWaveformLoadQueue.indexOf(canvas);
    if (queuedIndex >= 0) {
      clipWaveformLoadQueue.splice(queuedIndex, 1);
    }
  }
  state.status = "observed";
  queueClipWaveform(canvas, { priority: true });
}

function queueClipWaveform(canvas, { priority = false } = {}) {
  const state = clipWaveformStates.get(canvas);
  if (!state || state.status !== "observed") {
    return;
  }
  state.status = "queued";
  if (priority) {
    clipWaveformLoadQueue.unshift(canvas);
  } else {
    clipWaveformLoadQueue.push(canvas);
  }
  drainClipWaveformLoadQueue();
}

function drainClipWaveformLoadQueue() {
  while (
    activeClipWaveformLoads < maxConcurrentClipWaveformLoads
    && clipWaveformLoadQueue.length
  ) {
    const canvas = clipWaveformLoadQueue.shift();
    const state = clipWaveformStates.get(canvas);
    if (!state || state.status !== "queued" || !canvas.isConnected) {
      continue;
    }
    activeClipWaveformLoads += 1;
    loadClipWaveform(canvas, state)
      .catch(() => {
        state.status = "unavailable";
        canvas.dataset.waveformStatus = "unavailable";
      })
      .finally(() => {
        activeClipWaveformLoads -= 1;
        drainClipWaveformLoadQueue();
      });
  }
}

async function loadClipWaveform(canvas, state) {
  state.status = "loading";
  canvas.dataset.waveformStatus = "loading";
  const response = await fetch(state.audioUrl, {
    cache: "force-cache",
    credentials: "same-origin",
  });
  if (!response.ok) {
    throw new Error(`waveform audio HTTP ${response.status}`);
  }
  const contentLength = Number(response.headers.get("content-length"));
  if (Number.isFinite(contentLength) && contentLength > maxClipWaveformAudioBytes) {
    throw new Error("waveform audio exceeds size limit");
  }
  const encodedAudio = await response.arrayBuffer();
  if (encodedAudio.byteLength > maxClipWaveformAudioBytes) {
    throw new Error("waveform audio exceeds size limit");
  }
  const audioBuffer = await decodeClipWaveformAudio(encodedAudio);
  state.peaks = computeClipWaveformPeaks(audioBuffer);
  state.status = "ready";
  canvas.dataset.waveformStatus = "ready";
  drawClipWaveform(canvas, state.progressPercent);
}

async function decodeClipWaveformAudio(encodedAudio) {
  const AudioContextConstructor = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextConstructor) {
    throw new Error("Web Audio is unavailable");
  }
  const decodingContext = new AudioContextConstructor();
  try {
    return await decodingContext.decodeAudioData(encodedAudio.slice(0));
  } finally {
    decodingContext.close().catch(() => {});
  }
}

function computeClipWaveformPeaks(audioBuffer, binCount = 512) {
  const sampleCount = audioBuffer.length;
  const channelCount = audioBuffer.numberOfChannels;
  if (!sampleCount || !channelCount) {
    return new Float32Array(binCount);
  }
  const channels = Array.from(
    { length: channelCount },
    (_, channelIndex) => audioBuffer.getChannelData(channelIndex),
  );
  const peaks = new Float32Array(binCount);
  let maximumPeak = 0;
  for (let binIndex = 0; binIndex < binCount; binIndex += 1) {
    const start = Math.floor((binIndex * sampleCount) / binCount);
    const end = Math.max(start + 1, Math.floor(((binIndex + 1) * sampleCount) / binCount));
    let squareSum = 0;
    let values = 0;
    for (const channel of channels) {
      for (let sampleIndex = start; sampleIndex < end && sampleIndex < sampleCount; sampleIndex += 1) {
        const sample = channel[sampleIndex];
        squareSum += sample * sample;
        values += 1;
      }
    }
    const peak = values ? Math.sqrt(squareSum / values) : 0;
    peaks[binIndex] = peak;
    maximumPeak = Math.max(maximumPeak, peak);
  }
  if (maximumPeak > 0) {
    for (let index = 0; index < peaks.length; index += 1) {
      peaks[index] /= maximumPeak;
    }
  }
  return peaks;
}

function drawClipWaveform(canvas, progressPercent = 0) {
  const state = clipWaveformStates.get(canvas);
  if (!state?.peaks) {
    return;
  }
  state.progressPercent = progressPercent;
  const bounds = canvas.getBoundingClientRect();
  if (bounds.width <= 0 || bounds.height <= 0) {
    return;
  }
  const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.max(1, Math.round(bounds.width * pixelRatio));
  canvas.height = Math.max(1, Math.round(bounds.height * pixelRatio));
  const context = canvas.getContext("2d");
  if (!context) {
    return;
  }
  context.scale(pixelRatio, pixelRatio);
  context.clearRect(0, 0, bounds.width, bounds.height);
  const rootStyles = getComputedStyle(document.documentElement);
  const playedColor = rootStyles.getPropertyValue("--teal").trim() || "#40e0bf";
  const waitingColor = rootStyles.getPropertyValue("--line-strong").trim() || "#36524b";
  const barCount = Math.min(
    state.peaks.length,
    Math.max(24, Math.floor(bounds.width / 4)),
  );
  const barStep = bounds.width / barCount;
  const barWidth = Math.max(1, barStep * 0.56);
  const centerY = bounds.height / 2;
  const playedWidth = bounds.width * Math.min(100, Math.max(0, progressPercent)) / 100;
  for (let barIndex = 0; barIndex < barCount; barIndex += 1) {
    const peakIndex = Math.min(
      state.peaks.length - 1,
      Math.floor((barIndex * state.peaks.length) / barCount),
    );
    const amplitude = state.peaks[peakIndex];
    const barHeight = Math.max(2, amplitude * (bounds.height - 8));
    const x = barIndex * barStep + (barStep - barWidth) / 2;
    context.globalAlpha = x <= playedWidth ? 0.95 : 0.72;
    context.fillStyle = x <= playedWidth ? playedColor : waitingColor;
    context.fillRect(x, centerY - barHeight / 2, barWidth, barHeight);
  }
  context.globalAlpha = 1;
}

function updateClipPlaybackProgress(audio, progress, time, fallbackDuration) {
  const metadataDuration = Number(audio.duration);
  const fallback = Number(fallbackDuration);
  const duration = Number.isFinite(metadataDuration) && metadataDuration > 0
    ? metadataDuration
    : (Number.isFinite(fallback) && fallback > 0 ? fallback : 0);
  const currentTime = Number.isFinite(Number(audio.currentTime))
    ? Math.max(0, Number(audio.currentTime))
    : 0;
  const rangeMaximum = duration > 0 ? duration : 1;
  const boundedCurrentTime = Math.min(currentTime, rangeMaximum);
  const progressPercent = Math.min(100, Math.max(0, (boundedCurrentTime / rangeMaximum) * 100));
  progress.max = String(rangeMaximum);
  progress.value = String(boundedCurrentTime);
  progress.style.setProperty("--clip-progress-percent", `${progressPercent}%`);
  const waveformCanvas = progress
    .closest(".clip-waveform-shell")
    ?.querySelector(".clip-waveform-canvas");
  if (waveformCanvas instanceof HTMLCanvasElement) {
    const waveformState = clipWaveformStates.get(waveformCanvas);
    if (waveformState) {
      waveformState.progressPercent = progressPercent;
      drawClipWaveform(waveformCanvas, progressPercent);
    }
  }
  const durationText = formatPlaybackTime(duration, { unknownLabel: unknownPlaybackTimeLabel });
  time.textContent = `${formatElapsedPlaybackTime(boundedCurrentTime)} / ${durationText}`;
  progress.setAttribute("aria-valuetext", time.textContent);
}

function formatElapsedPlaybackTime(seconds) {
  const value = Number(seconds);
  const totalSeconds = Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0;
  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = String(totalSeconds % 60).padStart(2, "0");
  return `${minutes}:${remainingSeconds}`;
}

function setClipPlayButtonState(button, paused) {
  const isPaused = Boolean(paused);
  const label = isPaused ? "Play clip" : "Pause clip";
  button.dataset.state = isPaused ? "paused" : "playing";
  button.setAttribute("aria-label", label);
  button.title = label;
  button.textContent = isPaused ? "▶" : "❚❚";
}

function analysisAudioUrlForClip(clip) {
  return clipAudioRequestUrl(clip) || audioUrlForClip(clip);
}

function stopOtherAudio(currentPlayback) {
  if (
    continuousClipPlaybackActive &&
    currentPlayback !== continuousClipPlaybackAudio
  ) {
    stopContinuousClipPlayback();
  }
  if (currentPlayback !== currentClipPlayback) {
    stopCurrentClipPlayback();
  }
  if (currentPlayback !== liveAudio) {
    closeLiveAudioStream();
  }
}

function stopAllAudio() {
  stopContinuousClipPlayback();
  stopCurrentClipPlayback();
  closeLiveAudioStream();
}

function suspendLiveView() {
  stopLiveStatusPolling();
  stopLiveActivityPolling();
  stopWaveform();
  closeLiveAudioStream();
}

function shouldPreserveLiveAudioSession() {
  if (isQueuedLiveMode() && everythingQueueEnabled) {
    return true;
  }
  return Boolean(liveAudio.src && !liveAudio.paused);
}

function stopCurrentClipPlayback() {
  if (!currentClipPlayback) {
    return;
  }
  const playback = currentClipPlayback;
  currentClipPlayback = null;
  playback.pause();
  try {
    playback.currentTime = 0;
  } catch {
    // Some remote streams do not allow seeking before metadata is ready.
  }
}

function topicList(topics) {
  const list = document.createElement("div");
  list.className = "topic-list";
  const visibleTopics = nonOutlierTopics(topics);
  if (!visibleTopics.length) {
    const empty = document.createElement("p");
    empty.className = "muted-inline";
    empty.textContent = "Topic summaries will appear when the corpus is large enough.";
    list.append(empty);
    return list;
  }
  list.append(
    ...visibleTopics.slice(0, 6).map((topic) => {
      const item = document.createElement("article");
      item.className = "topic-card";
      const title = document.createElement("h4");
      title.textContent = `${topicTitle(topic)} · ${topic.count || 0}`;
      const words = document.createElement("p");
      words.className = "entity-meta";
      words.textContent = topicKeywordWords(topic).join(", ");
      item.append(title, words);
      const examples = renderTopicExamples(topic);
      if (examples) {
        item.append(examples);
      }
      return item;
    }),
  );
  return list;
}

function renderTopicExamples(topic) {
  const example = topicExampleForDisplay(topic);
  if (!example) {
    return null;
  }
  const wrapper = document.createElement("div");
  wrapper.className = "topic-example";
  const label = document.createElement("p");
  label.className = "language-label";
  label.textContent = "Example";
  const quote = document.createElement("blockquote");
  quote.textContent = example.text || example.transcript_public || "";
  wrapper.append(label, quote);
  return wrapper;
}

function topicExampleForDisplay(topic) {
  const examples = Array.isArray(topic?.examples) ? topic.examples : [];
  return examples[0] || null;
}

function topicTitle(topic) {
  const words = topicKeywordWords(topic, 3);
  if (words.length) {
    return words.join(" / ");
  }
  const label = String(topic?.label || "").trim();
  if (!label || /^topic\s+\d+$/i.test(label)) {
    return "Keywords pending";
  }
  return label;
}

function topicKeywordWords(topic, limit = 12) {
  if (!Array.isArray(topic?.top_words)) {
    return [];
  }
  return topic.top_words.map((word) => String(word || "").trim()).filter(Boolean).slice(0, limit);
}

function nonOutlierTopics(topics) {
  return (topics || []).filter(
    (topic) => topic.id !== -1 && String(topic.label || "").toLowerCase() !== "outliers",
  );
}

function educationList(resources) {
  const list = document.createElement("div");
  list.className = "education-list";
  if (!resources.length) {
    const empty = document.createElement("p");
    empty.className = "muted-inline";
    empty.textContent = "Reference links will appear after analysis runs.";
    list.append(empty);
    return list;
  }
  list.append(
    ...resources.map((resource) => {
      const item = document.createElement("article");
      item.className = "education-card education-card-link";
      item.tabIndex = 0;
      item.setAttribute("role", "link");
      item.setAttribute(
        "aria-label",
        `Open ${resource.title || resource.source || "maritime radio reference"}`,
      );
      item.addEventListener("click", (event) => {
        if (event.target.closest("a")) {
          return;
        }
        openEducationReference(resource);
      });
      item.addEventListener("keydown", (event) => {
        if (event.target.closest("a")) {
          return;
        }
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openEducationReference(resource);
        }
      });
      const heading = document.createElement("div");
      heading.className = "education-card-heading";
      const url = resource.url || "#";
      const title = document.createElement("a");
      title.href = url;
      title.rel = "noopener noreferrer";
      title.target = "_blank";
      title.textContent = resource.title || resource.source || "Reference";
      const action = document.createElement("a");
      action.className = "education-card-action";
      action.href = url;
      action.rel = "noopener noreferrer";
      action.target = "_blank";
      action.setAttribute("aria-label", `Open ${title.textContent}`);
      const cue = document.createElement("span");
      cue.className = "reference-open-cue";
      cue.textContent = "Open ->";
      action.append(cue);
      heading.append(title, action);
      const chipRow = document.createElement("div");
      chipRow.className = "education-card-chip-row";
      [resource.source, resource.category].filter(Boolean).forEach((value) => {
        const chip = document.createElement("span");
        chip.className = "education-card-chip";
        chip.textContent = value;
        chipRow.append(chip);
      });
      const relevance = document.createElement("p");
      relevance.textContent = resource.local_relevance || "";
      item.append(heading, chipRow, relevance);
      return item;
    }),
  );
  return list;
}

function openEducationReference(resource) {
  const url = String(resource?.url || "").trim();
  if (!url || url === "#") {
    return;
  }
  window.open(url, "_blank", "noopener,noreferrer");
}

function educationGuideList(sections) {
  const wrapper = document.createElement("div");
  wrapper.className = "education-guide";
  if (!sections.length) {
    const empty = document.createElement("p");
    empty.className = "muted-inline";
    empty.textContent = "Field notes will appear after analysis runs.";
    wrapper.append(empty);
    return wrapper;
  }
  const intro = document.createElement("div");
  intro.className = "education-guide-intro";
  const label = document.createElement("p");
  label.className = "language-label";
  label.textContent = "Why they say it this way";
  const copy = document.createElement("p");
  copy.textContent = "Field notes for the clipped calls, place names, and handoff language in the transcripts.";
  intro.append(label, copy);

  const list = document.createElement("div");
  list.className = "education-guide-list";
  list.append(
    ...sections.map((section) => {
      const item = document.createElement("details");
      item.className = "education-guide-card";
      const summary = document.createElement("summary");
      const summaryCopy = document.createElement("span");
      summaryCopy.className = "guide-summary-copy";
      const title = document.createElement("h4");
      title.textContent = section.title || "Field note";
      const signals = document.createElement("span");
      signals.className = "guide-signals";
      signals.textContent = section.signals || "";
      summaryCopy.append(title, signals);
      const cue = document.createElement("span");
      cue.className = "guide-expand-cue";
      cue.textContent = "Tap for details";
      summary.append(summaryCopy, cue);
      const body = document.createElement("div");
      body.className = "guide-card-body";
      body.append(
        guideBodyRow("What you are hearing", section.what_it_explains || ""),
        guideBodyRow("Why it matters", section.why_it_matters || ""),
      );
      item.append(summary, body);
      return item;
    }),
  );
  wrapper.append(intro, list);
  return wrapper;
}

function guideBodyRow(labelText, bodyText) {
  const row = document.createElement("div");
  row.className = "guide-body-row";
  const label = document.createElement("p");
  label.className = "language-label";
  label.textContent = labelText;
  const body = document.createElement("p");
  body.textContent = bodyText;
  row.append(label, body);
  return row;
}

function referenceIndex(resources) {
  const wrapper = languagePanel("Reference index");
  wrapper.classList.add("reference-index");
  wrapper.append(educationList(resources));
  return wrapper;
}

function channelActivityChart(channels) {
  let entries = Object.entries(channels || {})
    .map(([channel, count]) => [channel, Number(count || 0)])
    .filter(([, count]) => count > 0)
    .sort((left, right) => right[1] - left[1] || compareChannels(left[0], right[0]));
  const hasTrafficOutlier = entries.some(([channel]) => trafficChannelIds.has(channel));
  if (hideAnalysisTrafficOutlier) {
    entries = entries.filter(([channel]) => !trafficChannelIds.has(channel));
  }
  const list = document.createElement("div");
  list.className = "channel-bar-list";
  if (!entries.length) {
    const empty = document.createElement("p");
    empty.className = "muted-inline";
    empty.textContent =
      hideAnalysisTrafficOutlier && hasTrafficOutlier
        ? "Only Seattle Traffic has analyzed clips; show it to view the bar."
        : "No analyzed transmissions on listenable channels yet";
    list.append(empty);
    return list;
  }
  const maxCount = Math.max(1, ...entries.map(([, count]) => count));
  list.append(
    ...entries.map(([channel, count]) => {
      const row = document.createElement("div");
      row.className = "channel-bar-row";
      row.setAttribute("aria-label", `${channelLabel(channel)}: ${count} analyzed transcript clips`);
      const label = document.createElement("span");
      label.className = "channel-bar-label";
      label.textContent = channelLabel(channel);
      const track = document.createElement("span");
      track.className = "channel-bar-track";
      const fill = document.createElement("span");
      fill.className = "channel-bar-fill";
      fill.style.width = count > 0 ? `${Math.max(5, (count / maxCount) * 100).toFixed(1)}%` : "0%";
      fill.style.setProperty("--channel-color", channelColorForChannel(channel));
      track.append(fill);
      const countLabel = document.createElement("span");
      countLabel.className = "channel-bar-count";
      countLabel.textContent = String(count);
      row.append(label, track, countLabel);
      return row;
    }),
  );
  return list;
}

function renderAnalysisTrafficToggle() {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "analysis-chart-toggle";
  button.textContent = hideAnalysisTrafficOutlier ? "Show Seattle Traffic" : "Hide Seattle Traffic";
  button.setAttribute("aria-pressed", String(!hideAnalysisTrafficOutlier));
  button.addEventListener("click", () => {
    hideAnalysisTrafficOutlier = !hideAnalysisTrafficOutlier;
    if (latestLanguagePayload) {
      renderLanguageDashboard(latestLanguagePayload);
    }
  });
  return button;
}

function dominantThemeSummary(topics) {
  const topic = nonOutlierTopics(topics?.items || []).sort(
    (left, right) => Number(right.count || 0) - Number(left.count || 0),
  )[0];
  if (!topic) {
    return "No topic model yet";
  }
  return `${topicTitle(topic)}\n${formatCountNoun(topic.count || 0, "clip", "clips")}`;
}

function topicStatus(topics) {
  if (!topics?.status || topics.status === "missing") {
    return "Missing";
  }
  if (topics.status === "ok") {
    return formatCountNoun(nonOutlierTopics(topics.items || []).length, "topic", "topics");
  }
  return "Classical only";
}

function confidenceText(value) {
  const confidence = Number(value || 0);
  if (!confidence) {
    return "confidence unknown";
  }
  return `${Math.round(confidence * 100)}% confidence`;
}

function configureLiveAudioElement() {
  liveAudio.preload = "auto";
  liveAudio.muted = true;
  liveAudio.disableRemotePlayback = true;
  liveAudio.setAttribute("controlslist", "nodownload noplaybackrate noremoteplayback");
  liveAudio.setAttribute("disableremoteplayback", "");
  liveAudio.setAttribute("playsinline", "");
  liveAudio.setAttribute("x-webkit-airplay", "deny");
}

function setSystemMediaControlsEnabled(enabled) {
  systemMediaControlsEnabled = Boolean(enabled);
  try {
    window.localStorage.setItem(systemMediaControlsStorageKey, systemMediaControlsEnabled ? "enabled" : "disabled");
  } catch {
    // Some private browsing modes can reject localStorage writes.
  }
  if (!systemMediaControlsEnabled) {
    clearBrowserMediaSession();
  } else if (!liveAudio.paused) {
    updateLiveMediaSession("playing");
  } else {
    updateLiveMediaSession("paused");
  }
  if (!panels.live.hidden && !liveAudio.src) {
    prepareLiveAudio();
  }
  updateSystemMediaControlsUi();
}

function updateSystemMediaControlsUi() {
  if (systemMediaControlsToggle) {
    systemMediaControlsToggle.checked = systemMediaControlsEnabled;
  }
  playLiveButton.disabled = false;
  playLiveButton.title = "";
  if (systemMediaNote) {
    const environmentLabel = systemMediaEnvironmentLabel();
    systemMediaNote.textContent = systemMediaControlsEnabled
      ? `System media controls can keep live radio playing on ${environmentLabel} when your device allows it.`
      : `Live radio stays inside this page on ${environmentLabel}.`;
  }
}

function initialSystemMediaControlsEnabled() {
  try {
    const storedSystemMediaControls = window.localStorage.getItem(systemMediaControlsStorageKey);
    if (storedSystemMediaControls === "enabled") {
      return true;
    }
    if (storedSystemMediaControls === "disabled") {
      return false;
    }
  } catch {
    // Some private browsing modes can reject localStorage reads.
  }
  return systemMediaControlsDefault;
}

function defaultSystemMediaControlsEnabled() {
  return isAndroidAudioEnvironment();
}

function isAndroidAudioEnvironment() {
  const userAgentData = navigator.userAgentData;
  const userAgent = navigator.userAgent || "";
  const platform = `${userAgentData?.platform || ""} ${navigator.platform || ""}`;
  return operatingSystemNameFromUserAgent(userAgent, platform) === "Android";
}

function systemMediaEnvironmentLabel() {
  const userAgentData = navigator.userAgentData;
  const userAgent = navigator.userAgent || "";
  const platform = `${userAgentData?.platform || ""} ${navigator.platform || ""}`;
  const browser = browserNameFromUserAgentData(userAgentData) || browserNameFromUserAgent(userAgent);
  const operatingSystem = operatingSystemNameFromUserAgent(userAgent, platform);
  if (browser && operatingSystem) {
    return `${browser} on ${operatingSystem}`;
  }
  return browser || operatingSystem || "this device";
}

function browserNameFromUserAgentData(userAgentData) {
  const brands = Array.isArray(userAgentData?.brands) ? userAgentData.brands : [];
  const brandText = brands.map((brand) => brand.brand).join(" ");
  if (/Edg/i.test(brandText)) {
    return "Edge";
  }
  if (/Chrome|Chromium/i.test(brandText)) {
    return "Chrome";
  }
  return "";
}

function browserNameFromUserAgent(userAgent) {
  if (/Edg\//.test(userAgent)) {
    return "Edge";
  }
  if (/Firefox\//.test(userAgent)) {
    return "Firefox";
  }
  if (/CriOS\//.test(userAgent)) {
    return "Chrome";
  }
  if (/Chrome\//.test(userAgent) && !/Chromium\//.test(userAgent)) {
    return "Chrome";
  }
  if (/Safari\//.test(userAgent) && !/Chrome\//.test(userAgent) && !/CriOS\//.test(userAgent)) {
    return "Safari";
  }
  return "";
}

function operatingSystemNameFromUserAgent(userAgent, platform) {
  const combined = `${userAgent} ${platform}`.toLowerCase();
  if (/iphone|ipad|ipod/.test(combined)) {
    return "iOS";
  }
  if (/android/.test(combined)) {
    return "Android";
  }
  if (/windows/.test(combined)) {
    return "Windows";
  }
  if (/macintosh|mac os|macintel|mac/.test(combined)) {
    return "macOS";
  }
  if (/linux/.test(combined)) {
    return "Linux";
  }
  return "";
}

function clearBrowserMediaSession() {
  if (!("mediaSession" in navigator)) {
    return;
  }
  try {
    navigator.mediaSession.metadata = null;
    navigator.mediaSession.playbackState = "none";
  } catch {
    return;
  }
  for (const action of ["play", "pause", "seekbackward", "seekforward", "previoustrack", "nexttrack", "stop"]) {
    try {
      navigator.mediaSession.setActionHandler(action, null);
    } catch {
      // Unsupported actions vary by browser.
    }
  }
}

function updateLiveMediaSession(playbackState = liveAudio.paused ? "paused" : "playing") {
  if (!systemMediaControlsEnabled) {
    clearBrowserMediaSession();
    return;
  }
  if (!("mediaSession" in navigator)) {
    return;
  }
  try {
    if ("MediaMetadata" in window) {
      navigator.mediaSession.metadata = new window.MediaMetadata({
        title: "Elliott Bay VHF",
        artist: isQueuedLiveMode()
          ? currentLiveQueueClip
            ? channelLabel(currentLiveQueueClip.channel)
            : channelLabel(selectedLiveChannel)
          : channelLabel(selectedLiveChannel),
        album: isQueuedLiveMode() ? `${channelLabel(selectedLiveChannel)} queue` : "Live radio",
      });
    }
    navigator.mediaSession.playbackState = playbackState;
    navigator.mediaSession.setActionHandler("play", () => {
      connectLive();
    });
    navigator.mediaSession.setActionHandler("pause", () => {
      liveAudio.pause();
    });
    navigator.mediaSession.setActionHandler("stop", () => {
      closeLiveAudioStream();
    });
  } catch {
    clearBrowserMediaSession();
  }
}

function prepareLiveAudio() {
  if (isQueuedLiveMode()) {
    configureEverythingQueueAudioElement({ muted: true });
    liveStatus.textContent = `${channelLabel(selectedLiveChannel)} queue ready`;
    setLivePlayButton("play");
    drawWaitingFrame({ showWaiting: true });
    renderLiveStatus(findLiveChannel(selectedLiveChannel));
    updateLiveMediaSession("paused");
    return;
  }
  const url = liveStreamUrl();
  liveAudio.crossOrigin = "anonymous";
  liveAudio.preload = "auto";
  liveAudio.muted = true;
  if (liveAudio.getAttribute("src") !== url) {
    liveAudio.src = url;
    liveAudio.load();
  }
  liveStatus.textContent = "Warming stream";
  setLivePlayButton("play");
  drawWaitingFrame({ showWaiting: true });
  updateLiveMediaSession("paused");
}

function closeLiveAudioStream() {
  clearTimeout(liveRetryTimer);
  liveRetryTimer = null;
  stopEverythingQueue({ clearQueue: true });
  liveAudio.pause();
  liveAudio.muted = true;
  liveAudio.removeAttribute("src");
  liveAudio.load();
  setLivePlayButton("play");
  liveStatus.textContent = "Ready";
  quietSince = null;
  drawWaitingFrame({ showWaiting: false });
  clearBrowserMediaSession();
}

function setLivePlayButton(mode) {
  const isPause = mode === "pause";
  const isConnecting = mode === "connecting";
  if (playLiveLabel) {
    playLiveLabel.textContent = isPause ? "Pause" : isConnecting ? "Tuning" : "Play";
  }
  if (playLiveSymbol) {
    playLiveSymbol.textContent = isPause ? "❚❚" : "▶";
  } else {
    playLiveButton.textContent = isPause ? "Pause" : isConnecting ? "▶ Tuning" : "▶ Play";
  }
  playLiveButton.classList.toggle("is-connecting", isConnecting);
  playLiveButton.setAttribute("aria-busy", String(isConnecting));
  liveSignalDot.classList.toggle("is-connecting", isConnecting);
}

function toggleLivePlayback() {
  if (isQueuedLiveMode()) {
    if (everythingQueueEnabled) {
      stopEverythingQueue({ clearQueue: true });
      liveAudio.pause();
      liveAudio.removeAttribute("src");
      liveAudio.load();
      setLivePlayButton("play");
      liveStatus.textContent = `${channelLabel(selectedLiveChannel)} queue paused`;
      renderEverythingQueuePanel();
      updateLiveMediaSession("paused");
      return;
    }
    connectEverythingLive();
    return;
  }
  if (!liveAudio.paused) {
    liveAudio.pause();
    return;
  }
  connectLive();
}

async function connectLive() {
  if (isQueuedLiveMode()) {
    return connectEverythingLive();
  }
  clearTimeout(liveRetryTimer);
  setLivePlayButton("connecting");
  liveStatus.textContent = "Connecting live stream";
  drawWaitingFrame({ showWaiting: true });
  const url = liveAudio.getAttribute("src") || withCacheBust(liveStreamUrl());
  liveAudio.crossOrigin = "anonymous";
  if (liveAudio.getAttribute("src") !== url) {
    liveAudio.src = url;
    liveAudio.load();
  }
  try {
    await startLiveWaveformForPlayback();
    stopOtherAudio(liveAudio);
    liveAudio.muted = false;
    await liveAudio.play();
  } catch {
    liveAudio.muted = true;
    setLivePlayButton("play");
    liveStatus.textContent = "Press play";
  }
}

async function connectEverythingLive() {
  clearTimeout(liveRetryTimer);
  everythingQueueEnabled = true;
  const queueGeneration = liveQueueModeGeneration;
  const queueChannel = selectedLiveChannel;
  const shouldCatchUp = !everythingQueueSeeded;
  everythingCatchUpHandoffPending = Boolean(isEverythingLiveMode() && shouldCatchUp);
  if (!everythingQueueStartedAtMs) {
    everythingQueueStartedAtMs = Date.now();
  }
  configureEverythingQueueAudioElement();
  setLivePlayButton("pause");
  liveStatus.textContent = shouldCatchUp ? everythingCatchUpLabel : "Waiting for queued transmission";
  drawWaitingFrame({ showWaiting: true });
  renderLiveStatus(findLiveChannel(selectedLiveChannel));
  try {
    stopOtherAudio(liveAudio);
    await pollEverythingQueue({
      playIfIdle: false,
      seedRecent: true,
      queueGeneration,
      queueChannel,
    });
    if (!isCurrentLiveQueueSession(queueGeneration, queueChannel)) {
      return;
    }
    await startLiveWaveformForPlayback();
    if (!isCurrentLiveQueueSession(queueGeneration, queueChannel)) {
      return;
    }
    if (!currentLiveQueueClip) {
      await playNextEverythingQueueClip({ queueGeneration, queueChannel });
    }
  } catch {
    liveStatus.textContent = "Everything queue waiting";
  } finally {
    renderEverythingQueuePanel();
    updateLiveMediaSession(everythingQueueEnabled ? "playing" : "paused");
  }
}

async function startLiveWaveformForPlayback() {
  try {
    ensureAudioAnalyser();
    if (audioContext?.state === "suspended") {
      await audioContext.resume();
    }
    startWaveform();
  } catch {
    // Playback should still work if the browser refuses the visualizer graph.
  }
}

function scheduleLiveReconnect() {
  clearTimeout(liveRetryTimer);
  liveRetryTimer = setTimeout(() => {
    if (!panels.live.hidden) {
      reconnectLiveStream();
    }
  }, 5000);
}

function startLiveStatusPolling() {
  clearTimeout(liveStatusTimer);
  pollLiveStatus();
}

function stopLiveStatusPolling() {
  clearTimeout(liveStatusTimer);
  liveStatusTimer = null;
  liveStatusAbortController?.abort();
  liveStatusAbortController = null;
}

function startLiveActivityPolling() {
  clearTimeout(liveActivityTimer);
  pollLiveActivity();
}

function stopLiveActivityPolling() {
  clearTimeout(liveActivityTimer);
  liveActivityTimer = null;
  liveActivityAbortController?.abort();
  liveActivityAbortController = null;
}

function liveStreamUrl() {
  return rawLiveStreamUrl();
}

function rawLiveStreamUrl() {
  if (isQueuedLiveMode()) {
    return currentLiveQueueClip?.playback_url || "";
  }
  if (selectedLiveChannel === "14") {
    return defaultLiveStreamUrl;
  }
  return apiUrl(`/api/live/${encodeURIComponent(selectedLiveChannel)}/current.mp3`);
}

function liveStatusUrl() {
  if (isQueuedLiveMode()) {
    return "";
  }
  return apiUrl(`/api/live/${encodeURIComponent(selectedLiveChannel)}/status`);
}

function lastCommunicationUrl() {
  if (isQueuedLiveMode()) {
    return liveQueueRequestUrl();
  }
  return apiUrl(
    `/api/clips/recent?limit=1&channel=${encodeURIComponent(
      selectedLiveChannel,
    )}&include_playback_url=false&verify_playback_exists=false&include_counts=false`,
  );
}

async function pollLiveStatus() {
  if (panels.live.hidden) {
    return;
  }
  if (isQueuedLiveMode()) {
    renderLiveStatus(findLiveChannel(selectedLiveChannel));
    liveStatusTimer = setTimeout(pollLiveStatus, liveStatusPollMs);
    return;
  }
  liveStatusAbortController?.abort();
  liveStatusAbortController = new AbortController();
  try {
    const response = await fetch(liveStatusUrl(), {
      cache: "no-store",
      signal: liveStatusAbortController.signal,
    });
    if (!response.ok) {
      throw new Error(`live status HTTP ${response.status}`);
    }
    const status = await response.json();
    latestLiveStatus = status;
    renderLiveStatus(status);
    if (lastLiveStatusId && status?.activeChannelId !== lastLiveStatusId && !liveAudio.paused) {
      reconnectLiveStream();
    }
    lastLiveStatusId = status?.activeChannelId || null;
  } catch (error) {
    if (error.name !== "AbortError") {
      liveFrequency.textContent = "Receiver status reconnecting";
    }
  } finally {
    if (!panels.live.hidden) {
      liveStatusTimer = setTimeout(pollLiveStatus, liveStatusPollMs);
    }
  }
}

async function pollLiveActivity() {
  const shouldPollHiddenEverythingQueue = isQueuedLiveMode() && everythingQueueEnabled;
  if (panels.live.hidden && !shouldPollHiddenEverythingQueue) {
    return;
  }
  liveActivityAbortController?.abort();
  liveActivityAbortController = new AbortController();
  try {
    if (isQueuedLiveMode()) {
      if (!everythingQueueEnabled) {
        return;
      }
      await pollEverythingQueue({ signal: liveActivityAbortController.signal });
      return;
    }
    const response = await fetch(lastCommunicationUrl(), {
      cache: "no-store",
      signal: liveActivityAbortController.signal,
    });
    if (!response.ok) {
      throw new Error(`last communication HTTP ${response.status}`);
    }
    const payload = await response.json();
    const clip = Array.isArray(payload.clips) ? payload.clips[0] : null;
    if (clip) {
      lastCommunicationByChannel[selectedLiveChannel] = {
        channel: clip.channel || selectedLiveChannel,
        started_at: clip.started_at,
        ended_at: clip.ended_at,
        duration_seconds: clip.duration_seconds,
      };
    }
  } catch (error) {
    if (error.name !== "AbortError") {
      liveLastCommunication.textContent = isQueuedLiveMode()
        ? "Queue: unavailable"
        : `Last ${selectedLiveChannel}: unavailable`;
    }
  } finally {
    renderLiveTelemetry();
    if (!panels.live.hidden || shouldPollHiddenEverythingQueue) {
      liveActivityTimer = setTimeout(
        pollLiveActivity,
        isQueuedLiveMode() ? liveQueuePollMs : liveActivityPollMs,
      );
    }
  }
}

async function pollEverythingQueue({
  signal = null,
  playIfIdle = true,
  seedRecent = false,
  queueGeneration = liveQueueModeGeneration,
  queueChannel = selectedLiveChannel,
} = {}) {
  const requestUrl = liveQueueRequestUrl();
  const payload = await loadEverythingQueuePayload(requestUrl, {
    signal,
    allowPublishedFallback: seedRecent,
  });
  if (!isCurrentLiveQueueSession(queueGeneration, queueChannel)) {
    return;
  }
  const clips = Array.isArray(payload.clips) ? payload.clips : [];
  if (seedRecent && !everythingQueueSeeded) {
    enqueueEverythingClips(clips, { includeBackfill: true });
    everythingQueueSeeded = true;
  } else {
    enqueueEverythingClips(clips);
  }
  renderLiveTelemetry();
  renderEverythingQueuePanel();
  if (playIfIdle && isCurrentLiveQueueSession(queueGeneration, queueChannel) && !currentLiveQueueClip && liveAudio.paused) {
    await playNextEverythingQueueClip({ queueGeneration, queueChannel });
  }
}

async function loadEverythingQueuePayload(requestUrl, { signal = null, allowPublishedFallback = false } = {}) {
  try {
    return await fetchJsonWithTimeout(requestUrl, {
      timeoutMs: allowPublishedFallback ? liveQueueSeedTimeoutMs : 0,
      signal,
    });
  } catch (error) {
    if (!allowPublishedFallback || signal?.aborted) {
      throw error;
    }
    return loadPublishedManifest();
  }
}

function liveQueueRequestUrl() {
  const channels = queueChannelsForMode();
  const excludedChannels = excludedQueueChannelsForMode();
  if (!channels.length) {
    if (!excludedChannels.length) {
      return liveQueueUrl;
    }
  }
  const params = new URLSearchParams({
    limit: "24",
    include_playback_url: "true",
    verify_playback_exists: "false",
    include_counts: "false",
  });
  for (const channel of channels) {
    params.append("channels", channel);
  }
  for (const channel of excludedChannels) {
    params.append("exclude_channels", channel);
  }
  return apiUrl(`/api/clips/recent?${params.toString()}`);
}

function queueChannelsForMode() {
  return [];
}

function excludedQueueChannelsForMode() {
  if (!isAllButTrafficLiveMode()) {
    return [];
  }
  return [...trafficChannelIds];
}

function enqueueEverythingClips(clips, { includeBackfill = false } = {}) {
  if (!includeBackfill && shouldSuppressRealtimeQueueDuringCatchUp()) {
    return;
  }
  let normalizedClips = clips
    .map(normalizeEverythingQueueClip)
    .filter(Boolean);
  if (includeBackfill) {
    normalizedClips = mostRecentEverythingQueueClips(normalizedClips, everythingInitialQueueLimit);
    normalizedClips = markEverythingQueueBackfill(normalizedClips);
  } else {
    normalizedClips = normalizedClips.filter(isEverythingQueueClipAfterStart);
  }
  normalizedClips.sort((left, right) => queueClipTime(left) - queueClipTime(right));
  for (const clip of normalizedClips) {
    if (liveQueueSeenClipIds.has(clip.id)) {
      continue;
    }
    liveQueueSeenClipIds.add(clip.id);
    liveQueue.push(clip);
  }
  liveQueue.sort((left, right) => queueClipTime(left) - queueClipTime(right));
  trimEverythingQueueSeenIds();
}

function shouldSuppressRealtimeQueueDuringCatchUp() {
  return Boolean(isEverythingLiveMode() && everythingCatchUpHandoffPending);
}

function mostRecentEverythingQueueClips(clips, limit) {
  return [...clips]
    .sort((left, right) => queueClipRelevantTime(right) - queueClipRelevantTime(left))
    .slice(0, limit);
}

function markEverythingQueueBackfill(clips) {
  return clips.map((clip) => ({ ...clip, catch_up: true }));
}

function isEverythingQueueClipAfterStart(clip) {
  if (!everythingQueueStartedAtMs) {
    return true;
  }
  return queueClipRelevantTime(clip) >= everythingQueueStartedAtMs;
}

function normalizeEverythingQueueClip(clip) {
  const sourceClip = clip || {};
  const playbackUrl = audioUrlForClip(sourceClip);
  const requestUrl = clipAudioRequestUrl(sourceClip);
  const audioUrl = sourceClip.audio_public_filename ? playbackUrl : requestUrl || playbackUrl;
  const channel = String(clip?.channel || "").toUpperCase();
  if (!audioUrl || !channel || !isQueueClipAllowedForCurrentMode({ channel })) {
    return null;
  }
  return {
    id: everythingQueueClipId(clip, playbackUrl),
    channel,
    channel_label: clip.channel_label || defaultChannelLabels[channel] || "",
    started_at: clip.started_at || "",
    ended_at: clip.ended_at || "",
    duration_seconds: clip.duration_seconds,
    audio_url: audioUrl,
    playback_url: playbackUrl,
    playback_expires_in_seconds: clip.playback_expires_in_seconds,
    playback_issued_at_ms: Date.now(),
    catch_up: Boolean(clip.catch_up),
  };
}

function everythingQueueClipId(clip, playbackUrl) {
  const stablePlaybackPath = String(playbackUrl || "").split("?")[0];
  return String(
    clip?.key ||
      clip?.id ||
      [clip?.channel, clip?.started_at, clip?.ended_at, clip?.audio_public_filename, stablePlaybackPath]
        .filter(Boolean)
        .join("|"),
  );
}

function queueClipTime(clip) {
  const value = clip?.started_at || clip?.ended_at || "";
  const time = new Date(value).getTime();
  return Number.isFinite(time) ? time : Date.now();
}

function queueClipRelevantTime(clip) {
  const value = clip?.ended_at || clip?.started_at || "";
  const time = new Date(value).getTime();
  return Number.isFinite(time) ? time : Date.now();
}

function trimEverythingQueueSeenIds() {
  if (liveQueueSeenClipIds.size <= 500) {
    return;
  }
  liveQueueSeenClipIds = new Set([...liveQueueSeenClipIds].slice(-300));
  if (currentLiveQueueClip) {
    liveQueueSeenClipIds.add(currentLiveQueueClip.id);
  }
  for (const clip of liveQueue) {
    liveQueueSeenClipIds.add(clip.id);
  }
}

function isCurrentLiveQueueSession(queueGeneration, queueChannel) {
  return (
    liveQueueModeGeneration === queueGeneration &&
    selectedLiveChannel === queueChannel &&
    everythingQueueEnabled &&
    isQueuedLiveMode()
  );
}

function isQueueClipAllowedForCurrentMode(clip) {
  const channel = String(clip?.channel || "").toUpperCase();
  return Boolean(channel && !excludedQueueChannelsForMode().includes(channel));
}

function nextLiveQueueClipForCurrentMode() {
  while (liveQueue.length) {
    const clip = liveQueue.shift();
    if (isQueueClipAllowedForCurrentMode(clip)) {
      return clip;
    }
  }
  return null;
}

async function playNextEverythingQueueClip({
  queueGeneration = liveQueueModeGeneration,
  queueChannel = selectedLiveChannel,
} = {}) {
  if (!isCurrentLiveQueueSession(queueGeneration, queueChannel)) {
    return;
  }
  currentLiveQueueClip = nextLiveQueueClipForCurrentMode();
  renderLiveStatus(findLiveChannel(selectedLiveChannel));
  renderEverythingQueuePanel();
  if (shouldFinishEverythingCatchUpBeforeNextClip(currentLiveQueueClip)) {
    everythingCatchUpHandoffPending = false;
  }
  if (!currentLiveQueueClip) {
    clearLiveQueueAudioSource();
    liveStatus.textContent = "Waiting for queued transmission";
    setLivePlayButton("pause");
    drawWaitingFrame({ showWaiting: true });
    updateLiveMediaSession("playing");
    return;
  }
  const playbackUrl =
    currentLiveQueueClip.audio_url || currentLiveQueueClip.playback_url || clipAudioRequestUrl(currentLiveQueueClip);
  if (!playbackUrl) {
    currentLiveQueueClip = null;
    liveStatus.textContent = "Skipping queued transmission";
    renderEverythingQueuePanel();
    window.setTimeout(() => {
      playNextEverythingQueueClip({ queueGeneration, queueChannel });
    }, 250);
    return;
  }
  const clipUrl = withCacheBust(playbackUrl);
  configureEverythingQueueAudioElement();
  if (liveAudio.getAttribute("src") !== clipUrl) {
    liveAudio.src = clipUrl;
    liveAudio.load();
  }
  liveStatus.textContent = currentLiveQueueClip.catch_up
    ? "Catching up on recent transmission"
    : `Playing ${channelLabel(currentLiveQueueClip.channel)}`;
  setLivePlayButton("pause");
  renderLiveTelemetry();
  updateLiveMediaSession("playing");
  try {
    await liveAudio.play();
  } catch {
    if (!isCurrentLiveQueueSession(queueGeneration, queueChannel)) {
      return;
    }
    currentLiveQueueClip = null;
    liveStatus.textContent = "Skipping queued transmission";
    renderEverythingQueuePanel();
    window.setTimeout(() => {
      playNextEverythingQueueClip({ queueGeneration, queueChannel });
    }, 250);
  }
}

function configureEverythingQueueAudioElement({ muted = false } = {}) {
  liveAudio.crossOrigin = "anonymous";
  liveAudio.preload = "auto";
  liveAudio.muted = muted;
}

function handleEverythingClipEnded() {
  const completedClip = currentLiveQueueClip;
  const queueGeneration = liveQueueModeGeneration;
  const queueChannel = selectedLiveChannel;
  currentLiveQueueClip = null;
  if (!everythingQueueEnabled) {
    setLivePlayButton("play");
    renderEverythingQueuePanel();
    return;
  }
  if (shouldFinishEverythingCatchUpAfterClip(completedClip)) {
    everythingCatchUpHandoffPending = false;
  }
  playNextEverythingQueueClip({ queueGeneration, queueChannel });
}

function shouldFinishEverythingCatchUpBeforeNextClip(nextClip) {
  return Boolean(isEverythingLiveMode() && everythingCatchUpHandoffPending && (!nextClip || !nextClip.catch_up));
}

function shouldFinishEverythingCatchUpAfterClip(completedClip) {
  if (!isEverythingLiveMode() || !everythingCatchUpHandoffPending) {
    return false;
  }
  if (!completedClip) {
    return true;
  }
  if (!completedClip.catch_up) {
    return true;
  }
  return !liveQueue.some((clip) => clip.catch_up);
}

function clearLiveQueueAudioSource() {
  liveAudio.pause();
  liveAudio.removeAttribute("src");
  liveAudio.load();
}

function stopEverythingQueue({ clearQueue = false } = {}) {
  liveQueueModeGeneration += 1;
  everythingQueueEnabled = false;
  everythingCatchUpHandoffPending = false;
  currentLiveQueueClip = null;
  if (clearQueue) {
    liveQueue = [];
    liveQueueSeenClipIds = new Set();
    everythingQueueStartedAtMs = 0;
    everythingQueueSeeded = false;
  }
  renderEverythingQueuePanel();
}

function renderLiveStatus(status) {
  if (isQueuedLiveMode()) {
    liveChannel.textContent = channelLabel(selectedLiveChannel);
    liveFrequency.textContent = isAllButTrafficLiveMode()
      ? "Queued active transmissions except Seattle Traffic"
      : "Queued active transmissions across monitored channels";
    renderLiveTelemetry();
    return;
  }
  const channel = status?.channel || selectedLiveChannel;
  liveChannel.textContent = channel ? channelLabel(channel) : "Current SDR feed";
  liveFrequency.textContent = status?.frequencyMhz ? `${status.frequencyMhz} MHz` : "";
  renderLiveTelemetry();
}

function renderLiveTelemetry() {
  if (isQueuedLiveMode()) {
    const activeClip = currentLiveQueueClip || liveQueue[0] || null;
    const heardAt = lastCommunicationTime(activeClip);
    liveLastCommunication.textContent = currentLiveQueueClip
      ? `Playing Ch ${currentLiveQueueClip.channel}: ${formatRelativeAge(heardAt)}`
      : liveQueue.length
        ? `Queue: ${liveQueue.length} waiting`
        : everythingQueueEnabled
          ? "Queue: listening across channels"
          : "Queue: ready";
    liveLatency.textContent = formatEverythingQueueDelay(activeClip);
    renderEverythingQueuePanel();
    return;
  }
  const clip = lastCommunicationByChannel[selectedLiveChannel];
  const heardAt = lastCommunicationTime(clip);
  liveLastCommunication.textContent = heardAt
    ? `Last Ch ${selectedLiveChannel}: ${formatRelativeAge(heardAt)}`
    : `Last Ch ${selectedLiveChannel}: checking`;
  liveLatency.textContent = formatLiveLatency(latestLiveStatus?.streamDelaySeconds);
}

function renderEverythingQueuePanel() {
  if (!liveQueuePanel) {
    return;
  }
  liveQueuePanel.hidden = !isQueuedLiveMode();
  if (liveQueuePanel.hidden) {
    liveQueuePanel.replaceChildren();
    return;
  }
  const mode = liveQueueItem(
    everythingQueueEnabled ? `${channelLabel(selectedLiveChannel)} mode on` : `${channelLabel(selectedLiveChannel)} mode ready`,
    hasEverythingQueueCatchUp() ? everythingCatchUpLabel : liveQueueModeDescription(),
  );
  const nowPlaying = currentLiveQueueClip
    ? liveQueueItem("Now playing", channelLabel(currentLiveQueueClip.channel))
    : liveQueueItem("Now playing", everythingQueueEnabled ? "Waiting for queued transmission" : "Press Play to start");
  const waiting = liveQueueItem("Queued", `${liveQueue.length} transmission${liveQueue.length === 1 ? "" : "s"}`);
  liveQueuePanel.replaceChildren(mode, nowPlaying, waiting);
}

function hasEverythingQueueCatchUp() {
  return Boolean(currentLiveQueueClip?.catch_up || liveQueue.some((clip) => clip.catch_up));
}

function liveQueueModeDescription() {
  return isAllButTrafficLiveMode()
    ? "Seattle Traffic is filtered out of this playback queue"
    : "All channels feed one playback queue";
}

function liveQueueItem(label, value) {
  const item = document.createElement("span");
  item.className = "live-queue-item";
  const name = document.createElement("span");
  name.className = "live-queue-label";
  name.textContent = label;
  const detail = document.createElement("span");
  detail.className = "live-queue-value";
  detail.textContent = value;
  item.append(name, detail);
  return item;
}

function lastCommunicationTime(clip) {
  return clip?.ended_at || clip?.started_at || null;
}

function formatEverythingQueueDelay(clip) {
  const heardAt = lastCommunicationTime(clip);
  if (!heardAt) {
    return `Queue delay: ${liveQueue.length} waiting`;
  }
  const heardTime = new Date(heardAt).getTime();
  if (!Number.isFinite(heardTime)) {
    return `Queue delay: ${liveQueue.length} waiting`;
  }
  const seconds = Math.max(0, Math.round((Date.now() - heardTime) / 1000));
  return `Queue delay: about ${formatDurationSeconds(seconds)} behind antenna; ${liveQueue.length} waiting`;
}

function formatLiveLatency(delay) {
  const minimum = Number(delay?.minimum);
  const maximum = Number(delay?.maximum);
  if (!Number.isFinite(minimum) || !Number.isFinite(maximum)) {
    return "Live delay: estimating";
  }
  return `Live delay: about ${formatDelaySeconds(minimum)}-${formatDelaySeconds(maximum)} behind antenna`;
}

function formatDelaySeconds(value) {
  const rounded = Math.max(0, Math.round(Number(value)));
  return `${rounded}s`;
}

function formatDurationSeconds(seconds) {
  const rounded = Math.max(0, Math.round(Number(seconds)));
  if (rounded < 60) {
    return `${rounded}s`;
  }
  const minutes = Math.floor(rounded / 60);
  const remainingSeconds = rounded % 60;
  if (minutes < 60) {
    return remainingSeconds ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
}

function formatRelativeAge(value) {
  const time = new Date(value).getTime();
  if (!Number.isFinite(time)) {
    return "unknown";
  }
  const seconds = Math.max(0, Math.round((Date.now() - time) / 1000));
  if (seconds < 60) {
    return `${seconds}s ago`;
  }
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }
  return formatDateTime(value);
}

function withCacheBust(url) {
  if (!url || isSignedPlaybackUrl(url)) {
    return url;
  }
  const joiner = url.includes("?") ? "&" : "?";
  return `${url}${joiner}t=${Date.now()}`;
}

function reconnectLiveStream() {
  liveAudio.src = withCacheBust(liveStreamUrl());
  liveAudio.load();
  connectLive();
}

function ensureAudioAnalyser() {
  if (analyser) {
    return;
  }
  const AudioContextConstructor = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextConstructor) {
    liveStatus.textContent = "Audio visualizer unavailable";
    return;
  }
  audioContext = new AudioContextConstructor();
  analyser = audioContext.createAnalyser();
  analyser.fftSize = 2048;
  analyser.smoothingTimeConstant = 0.35;
  waveformData = new Uint8Array(analyser.fftSize);
  analyserSource = audioContext.createMediaElementSource(liveAudio);
  analyserSource.connect(analyser);
  analyser.connect(audioContext.destination);
}

function startWaveform() {
  if (waveformAnimationId) {
    return;
  }
  drawWaveform();
}

function stopWaveform() {
  if (waveformAnimationId) {
    cancelAnimationFrame(waveformAnimationId);
    waveformAnimationId = null;
  }
}

function drawWaveform() {
  waveformAnimationId = requestAnimationFrame(drawWaveform);
  if (!analyser || !waveformData) {
    drawWaitingFrame({ showWaiting: false });
    return;
  }

  analyser.getByteTimeDomainData(waveformData);
  const rms = waveformRms(waveformData);
  const now = performance.now();
  const isReceiving = rms > 0.018;
  const queuedStatus = queuedLivePlaybackStatus();
  if (isReceiving) {
    quietSince = null;
    liveStatus.textContent = queuedStatus || "Receiving transmission";
  } else {
    quietSince ||= now;
    const quietDurationMs = now - quietSince;
    if (quietDurationMs >= quietTransmissionDelayMs && !liveAudio.paused) {
      liveStatus.textContent = queuedStatus || "Waiting for transmission";
    } else if (!liveAudio.paused && liveAudio.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
      liveStatus.textContent = queuedStatus || "Monitoring";
    }
  }
  const waitedThroughQuiet =
    !isReceiving && quietSince !== null && now - quietSince >= quietTransmissionDelayMs;
  waveformPanel.classList.toggle("is-waiting", waitedThroughQuiet);
  liveSignalDot.classList.toggle("is-active", isReceiving);
  renderWaveform(waveformData, { isReceiving, rms });
}

function queuedLivePlaybackStatus() {
  if (!isQueuedLiveMode() || liveAudio.paused || !currentLiveQueueClip) {
    return "";
  }
  return currentLiveQueueClip.catch_up ? "Catching up on recent transmission" : "Playing queued transmission";
}

function drawWaitingFrame({ showWaiting } = { showWaiting: true }) {
  const midpoint = new Uint8Array(128).fill(128);
  waveformPanel.classList.toggle("is-waiting", showWaiting);
  liveSignalDot.classList.remove("is-active");
  renderWaveform(midpoint, { isReceiving: false, rms: 0 });
}

function waveformRms(data) {
  let sum = 0;
  for (const value of data) {
    const centered = (value - 128) / 128;
    sum += centered * centered;
  }
  return Math.sqrt(sum / data.length);
}

function renderWaveform(data, { isReceiving, rms }) {
  const context = waveformCanvas.getContext("2d");
  const rect = waveformCanvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.floor(rect.width * ratio));
  const height = Math.max(1, Math.floor(rect.height * ratio));
  if (waveformCanvas.width !== width || waveformCanvas.height !== height) {
    waveformCanvas.width = width;
    waveformCanvas.height = height;
  }

  context.clearRect(0, 0, width, height);
  context.fillStyle = "#091411";
  context.fillRect(0, 0, width, height);
  context.strokeStyle = "rgba(117, 137, 131, 0.18)";
  context.lineWidth = ratio;
  for (let y = height * 0.25; y < height; y += height * 0.25) {
    context.beginPath();
    context.moveTo(0, y);
    context.lineTo(width, y);
    context.stroke();
  }

  const centerY = height / 2;
  const amplitude = Math.max(0.08, Math.min(1, rms * 7));
  const hasAudibleWaveform = rms > 0.002;
  const waveformGain = isReceiving ? 1 : quietWaveformGain(rms);
  context.lineWidth = isReceiving ? 2.5 * ratio : 1.6 * ratio;
  context.strokeStyle = hasAudibleWaveform ? "#40e0bf" : "rgba(244, 179, 80, 0.72)";
  context.shadowColor = hasAudibleWaveform ? "rgba(64, 224, 191, 0.7)" : "rgba(244, 179, 80, 0.35)";
  context.shadowBlur = hasAudibleWaveform ? 12 * ratio : 8 * ratio;
  context.beginPath();
  for (let index = 0; index < data.length; index += 1) {
    const x = (index / (data.length - 1)) * width;
    const normalized = (data[index] - 128) / 128;
    const idleSweep = Math.sin(index / 18 + performance.now() / 420) * 0.045;
    const y =
      centerY +
      (hasAudibleWaveform ? normalized * waveformGain * height * 0.38 : idleSweep * amplitude * height);
    if (index === 0) {
      context.moveTo(x, y);
    } else {
      context.lineTo(x, y);
    }
  }
  context.stroke();
  context.shadowBlur = 0;
}

function quietWaveformGain(rms) {
  const safeRms = Math.max(Number(rms) || 0, 0.001);
  return Math.min(10, Math.max(3, 0.08 / safeRms));
}

function audioUrlForClip(clip) {
  if (clip?.audio_url) {
    return clip.audio_url;
  }
  if (clip?.playback_url) {
    return clip.playback_url;
  }
  if (clip?.audio_public_filename) {
    return `/clips/${encodeURIComponent(clip.audio_public_filename)}`;
  }
  return clipAudioRequestUrl(clip);
}

function clipPlaybackRequestUrl(clip) {
  if (!clip?.channel || !clip.started_at) {
    return "";
  }
  const params = new URLSearchParams({
    channel: String(clip.channel),
    started_at: String(clip.started_at),
  });
  return `${clipPlaybackUrl}?${params.toString()}`;
}

function clipAudioRequestUrl(clip) {
  if (!clip?.channel || !clip.started_at) {
    return "";
  }
  const params = new URLSearchParams({
    channel: String(clip.channel),
    started_at: String(clip.started_at),
  });
  return `${clipAudioUrl}?${params.toString()}`;
}

function playbackUrlExpiresAtMs(clip) {
  const issuedAt = Number(clip?.playback_issued_at_ms || 0);
  const expiresInSeconds = Number(clip?.playback_expires_in_seconds || 0);
  if (!Number.isFinite(issuedAt) || !Number.isFinite(expiresInSeconds)) {
    return 0;
  }
  if (issuedAt <= 0 || expiresInSeconds <= 0) {
    return 0;
  }
  return issuedAt + expiresInSeconds * 1000;
}

function shouldRefreshPlaybackUrl(clip, { force = false } = {}) {
  if (!clip?.playback_url || !clipPlaybackRequestUrl(clip)) {
    return false;
  }
  if (force) {
    return true;
  }
  const expiresAt = playbackUrlExpiresAtMs(clip);
  return !expiresAt || Date.now() + clipPlaybackRefreshLeadMs >= expiresAt;
}

async function refreshPlaybackUrl(clip) {
  const requestUrl = clipPlaybackRequestUrl(clip);
  if (!requestUrl) {
    throw new Error("clip playback refresh unavailable");
  }
  const response = await fetch(requestUrl, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`clip playback refresh HTTP ${response.status}`);
  }
  const payload = await response.json();
  if (!payload?.playback_url) {
    throw new Error("clip playback refresh missing URL");
  }
  clip.playback_url = payload.playback_url;
  clip.playback_expires_in_seconds = payload.playback_expires_in_seconds;
  clip.playback_issued_at_ms = Date.now();
  return clip.playback_url;
}

async function ensureFreshPlaybackUrl(clip, options = {}) {
  if (shouldRefreshPlaybackUrl(clip, options)) {
    return refreshPlaybackUrl(clip);
  }
  return audioUrlForClip(clip);
}

async function refreshClipAudioPlayback(example, audio, time, options = {}) {
  if (!example?.playback_url || audio.dataset.refreshingPlayback === "true") {
    return;
  }
  if (!shouldRefreshPlaybackUrl(example, options)) {
    return;
  }
  audio.dataset.refreshingPlayback = "true";
  const shouldResume = !audio.paused;
  const previousTimeText = time.textContent;
  time.textContent = "Refreshing...";
  try {
    const refreshedUrl = await ensureFreshPlaybackUrl(example, { force: true });
    if (refreshedUrl && audio.src !== refreshedUrl) {
      audio.src = refreshedUrl;
      audio.load();
    }
    if (shouldResume) {
      await audio.play();
    }
    time.textContent = previousTimeText;
  } catch {
    time.textContent = shouldResume ? "Tap play to retry" : previousTimeText;
  } finally {
    delete audio.dataset.refreshingPlayback;
  }
}

function isSignedPlaybackUrl(url) {
  try {
    const parsed = new URL(url, window.location.href);
    return (
      parsed.searchParams.has("X-Amz-Signature") ||
      parsed.searchParams.has("Signature") ||
      parsed.searchParams.has("AWSAccessKeyId")
    );
  } catch {
    return false;
  }
}

function formatPlaybackTime(seconds, { unknownLabel = unknownPlaybackTimeLabel } = {}) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value <= 0) {
    return unknownLabel;
  }
  const totalSeconds = Math.max(1, Math.round(value));
  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = String(totalSeconds % 60).padStart(2, "0");
  return `${minutes}:${remainingSeconds}`;
}

function titleForClip(clip) {
  const channel = channelLabel(clip.channel);
  const date = formatDateTime(clip.started_at);
  return `${channel} · ${date}`;
}

function channelLabel(channel) {
  if (String(channel || "").toLowerCase() === everythingLiveChannel) {
    return "Everything";
  }
  if (String(channel || "").toLowerCase() === allButTrafficLiveChannel) {
    return "All but Traffic";
  }
  const channelText = `VHF ${channel || "?"}`;
  const label = currentChannelLabels[channel] || "";
  return label ? `${channelText} · ${label}` : channelText;
}

function channelClassName(channel) {
  return `channel-${String(channel || "unknown")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")}`;
}

function channelColorForChannel(channel) {
  const key = String(channel || "?").toUpperCase();
  if (channelColors[key]) {
    return channelColors[key];
  }
  let hash = 0;
  for (const character of key) {
    hash = (hash * 31 + character.charCodeAt(0)) % 360;
  }
  return `hsl(${hash} 72% 66%)`;
}

function channelLabelsForPayload(payload) {
  const labels = {
    ...defaultChannelLabels,
    ...(payload.channel_labels || {}),
    ...(payload.stats?.channel_labels || {}),
  };
  for (const clip of payload.clips || []) {
    if (clip.channel && clip.channel_label) {
      labels[clip.channel] = clip.channel_label;
    }
  }
  return labels;
}

function selectedChannelValues() {
  return [...selectedChannels].sort(compareChannels);
}

function clipExcludedChannelValues() {
  if (selectedChannelPreset !== "all-but-traffic") {
    return [];
  }
  return [...trafficChannelIds].sort(compareChannels);
}

function frequencyForChannel(channel) {
  return liveChannels.find((liveChannel) => liveChannel.channel === channel)?.frequencyMhz || "";
}

function channelClipCountText(count) {
  const clipCount = Number(count || 0);
  const noun = clipCount === 1 ? "clip" : "clips";
  return `${clipCount.toLocaleString()} ${noun}`;
}

function selectedChannelStatusScope() {
  const channels = selectedChannelValues();
  if (!channels.length) {
    return "";
  }
  if (selectedChannelPreset === "all-but-traffic") {
    return " excluding Seattle Traffic";
  }
  if (channels.length === 1) {
    return ` for ${channelLabel(channels[0])}`;
  }
  return " for selected channels";
}

function statusText(payload, clips, filteredTotal) {
  if (!filteredTotal) {
    if (clipCollectionFilter === "featured") {
      return selectedChannels.size === 0
        ? "No Hall of Fame clips yet"
        : "No Hall of Fame clips for the selected channels yet";
    }
    if (clipCollectionFilter === "quarantined") {
      return selectedChannels.size === 0
        ? "No quarantined clips yet"
        : "No quarantined clips for the selected channels yet";
    }
    if (payload.around) {
      const direction = clipSortDirection === "oldest" ? "at or after" : "at or before";
      return `No clips ${direction} ${formatDateTime(payload.around)}${selectedChannelStatusScope()}`;
    }
    return selectedChannels.size === 0 ? "No clips yet" : "No clips for the selected channels yet";
  }
  const scopeText = selectedChannelStatusScope();
  const countsDeferred = Boolean(payload.stats?.counts_deferred);
  const pageText = countsDeferred
    ? clips.length === filteredTotal
      ? `${clips.length}`
      : `${clips.length} of at least ${filteredTotal}`
    : clips.length === filteredTotal
    ? `${clips.length}`
    : `${clips.length} of ${filteredTotal}`;
  const clipNoun = filteredTotal === 1 ? "playable clip" : "playable clips";
  const collectionText =
    clipCollectionFilter === "featured"
      ? "featured "
      : clipCollectionFilter === "quarantined"
      ? "quarantined "
      : "";
  const totalsText = receivedAndAnalyzedStatusText(payload);
  if (payload.source === "live") {
    if (payload.around) {
      const direction = clipSortDirection === "oldest" ? "at or after" : "at or before";
      return `${pageText} ${collectionText}${clipNoun}${scopeText} ${direction} ${formatDateTime(payload.around)}${totalsText} from the live DB`;
    }
    return `${pageText} ${collectionText}${clipNoun}${scopeText}${totalsText} from the live DB`;
  }
  const generated = payload.generated_at ? ` · exported ${formatDateTime(payload.generated_at)}` : "";
  return `${pageText} published ${collectionText}${clipNoun}${scopeText}${totalsText}${generated}`;
}

function receivedAndAnalyzedStatusText(payload) {
  const received = totalReceivedClips(payload);
  const analyzed = totalAnalyzedClips(payload);
  const parts = [];
  if (Number.isFinite(analyzed) && analyzed > 0) {
    parts.push(`${analyzed.toLocaleString()} analyzed`);
  }
  if (Number.isFinite(received) && received > 0 && received !== analyzed) {
    parts.push(`${received.toLocaleString()} received`);
  }
  return parts.length ? ` · ${parts.join(" · ")}` : "";
}

function filteredClipCount(payload, clips) {
  if (payload.source === "live" && payload.around) {
    return clips.length;
  }
  if (payload.source === "live" && payload.stats?.counts_deferred && clipCollectionFilter === "recent" && globalClipStats) {
    if (selectedChannelPreset === "all-but-traffic") {
      const channelCounts = globalClipStats.playable_channel_counts || globalClipStats.channel_counts;
      if (channelCounts) {
        return Object.entries(channelCounts).reduce(
          (total, [channel, count]) =>
            total + (trafficChannelIds.has(String(channel).toUpperCase()) ? 0 : Number(count || 0)),
          0,
        );
      }
    }
    if (selectedChannels.size) {
      const channelCounts = globalClipStats.playable_channel_counts || globalClipStats.channel_counts;
      if (channelCounts) {
        return selectedChannelValues().reduce((total, channel) => total + Number(channelCounts[channel] || 0), 0);
      }
    }
    return totalPlayableClips({ ...payload, stats: globalClipStats }, clips);
  }
  if (selectedChannelPreset === "all-but-traffic") {
    const channelCounts = payload.stats?.playable_channel_counts || payload.stats?.channel_counts;
    if (channelCounts) {
      return Object.entries(channelCounts).reduce(
        (total, [channel, count]) =>
          total + (trafficChannelIds.has(String(channel).toUpperCase()) ? 0 : Number(count || 0)),
        0,
      );
    }
    return clips.filter((clip) => !trafficChannelIds.has(String(clip.channel || "").toUpperCase())).length;
  }
  if (payload.stats?.filtered_playable_clip_count !== undefined) {
    return Number(payload.stats.filtered_playable_clip_count);
  }
  if (
    (clipCollectionFilter === "featured" ||
      clipCollectionFilter === "quarantined") &&
    payload.source !== "live"
  ) {
    return clips.length;
  }
  if (selectedChannels.size) {
    const channelCounts = payload.stats?.playable_channel_counts || payload.stats?.channel_counts;
    if (channelCounts) {
      return selectedChannelValues().reduce((total, channel) => total + Number(channelCounts[channel] || 0), 0);
    }
    return Number(payload.stats?.filtered_clip_count ?? clips.length);
  }
  return Number(payload.stats?.filtered_clip_count ?? totalPlayableClips(payload, clips));
}

function totalPlayableClips(payload, clips) {
  return Number(
    payload.stats?.playable_clip_count ??
      payload.stats?.clip_count ??
      totalAvailableClipsFromCounts(payload.stats?.playable_channel_counts) ??
      totalAvailableClipsFromCounts(payload.stats?.channel_counts) ??
      clips.length,
  );
}

function totalReceivedClips(payload) {
  return Number(
    payload.stats?.received_clip_count ?? payload.received_clip_count ?? totalAnalyzedClips(payload),
  );
}

function totalAnalyzedClips(payload) {
  return Number(payload.stats?.analyzed_clip_count ?? payload.analyzed_clip_count ?? payload.stats?.clip_count ?? 0);
}

function totalAvailableClipsFromCounts(channelCounts) {
  if (!channelCounts) {
    return null;
  }
  return Object.values(channelCounts).reduce((total, count) => total + Number(count || 0), 0);
}

function compareChannels(left, right) {
  return left.localeCompare(right, undefined, { numeric: true });
}

function countBy(values, keyFunc) {
  return values.reduce((counts, value) => {
    const key = keyFunc(value);
    counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {});
}

function formatDateTime(value) {
  if (!value) {
    return "Unknown time";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Unknown time";
  }
  return pacificDateTimeFormatter.format(date);
}

function formatPerformanceDateTime(value) {
  if (!value) {
    return "Unknown time";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Unknown time";
  }
  return performanceDateTimeFormatter.format(date);
}

function shortTime(value) {
  if (!value) {
    return "None";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "None";
  }
  return pacificShortTimeFormatter.format(date);
}

loadLiveChannels();
loadAndRender();
startClipStatsPolling();
activateTab(initialRouteState.tab, { replaceRoute: true, updateRoute: false });
