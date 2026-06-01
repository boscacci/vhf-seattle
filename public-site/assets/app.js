const defaultClipPageSize = 6;
const clipPageSizeOptions = [6, 12, 24, 48];
const clipPlaybackUrl = "/api/clips/playback";
const clipAudioUrl = "/api/clips/audio";
const manifestUrl = "/public_manifest.json";
const lexicalAnalysisUrl = "/api/analysis/lexical";
const lexicalManifestUrl = "/analysis/lexical.json";
const performanceUrl = "/api/live/performance";
const aisCatcherFrameUrl = "/ais-catcher/?lat=47.6190158&lon=-122.3595353&zoom=13&setcoord=false&welcome=false&tab=map";
const topicClusterFallbackUrl = "/analysis/topic_clusters.html";
const liveChannelsUrl = "/api/live/channels";
const liveQueueUrl = "/api/clips/recent?limit=24";
const defaultLiveStreamUrl = "/api/live/current.mp3";
const systemMediaControlsStorageKey = "talkingboats.systemMediaControls";
const systemMediaControlsDefault = defaultSystemMediaControlsEnabled();
const unknownPlaybackTimeLabel = "—";
const everythingLiveChannel = "everything";
const everythingInitialQueueLimit = 3;
const liveDspProfile = window.location.hostname === "vhf-dev.robertboscacci.com" ? "warm_voice" : "";
const languageDashboardEnabled = [
  "vhf.robertboscacci.com",
  "vhf-dev.robertboscacci.com",
  "localhost",
  "127.0.0.1",
  "",
].includes(
  window.location.hostname,
);
const liveLanguageAnalysisEnabled = window.location.hostname !== "vhf.robertboscacci.com";
const performanceDashboardEnabled = ["vhf-dev.robertboscacci.com", "localhost", "127.0.0.1", ""].includes(
  window.location.hostname,
);
const aisDashboardEnabled = !["vhf.robertboscacci.com"].includes(
  window.location.hostname,
);
const tabRouteSegments = {
  clips: "clips",
  live: "live",
  map: "ais",
  language: "analysis",
  performance: "performance",
};
const tabRouteAliases = {
  clips: "clips",
  live: "live",
  ais: "map",
  map: "map",
  analysis: "language",
  language: "language",
  performance: "performance",
};
const liveStatusPollMs = 2000;
const liveActivityPollMs = 15000;
const liveQueuePollMs = 5000;
const clipPlaybackRefreshLeadMs = 45000;
const performanceRefreshMs = 10000;
const quietTransmissionDelayMs = 5000;
const performanceHostLabel = "OptiPlex live proxy";
const performanceRangeOptions = [
  { label: "30m", hours: 0.5 },
  { label: "2h", hours: 2 },
  { label: "12h", hours: 12 },
  { label: "24h", hours: 24 },
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
const pacificShortTimeFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: pacificTimeZone,
  hour: "numeric",
  minute: "2-digit",
});
const defaultChannelLabels = {
  "05A": "VTS / Port Ops",
  "06": "Intership Safety",
  "09": "Calling / Commercial",
  "13": "Bridge-to-bridge",
  "14": "VTS / Seattle Traffic",
  "16": "Distress / Calling",
  "22A": "USCG Liaison",
  "66A": "Port Operations",
  "67": "Commercial / Bridge",
  "68": "Recreational",
  "69": "Non-commercial",
  "71": "Non-commercial",
  "72": "Ship-to-ship",
  "74": "Port Operations",
};
const monitoredAnalysisChannels = ["05A", "06", "09", "13", "14", "16", "22A", "67", "68", "69", "71", "72"];

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
  "13": "#6ab8ff",
  "14": "#40e0bf",
  "16": "#ff7777",
  "22A": "#f0b85a",
  "66A": "#c084fc",
  "67": "#fca5a5",
  "68": "#8bd867",
  "69": "#f58fb2",
  "71": "#a5b4fc",
  "72": "#f7cf5d",
  "74": "#5eead4",
};

const clipList = document.querySelector("#clips");
const clipPagination = document.querySelector("#clip-pagination");
const clipStatus = document.querySelector("#clip-status");
const clipDisplayControls = document.querySelector("#clip-display-controls");
const channelFilter = document.querySelector("#channel-filter");
const refreshButton = document.querySelector("#refresh-clips");
const stats = document.querySelector("#stats");
const tabs = [...document.querySelectorAll(".tab")];
const languageTab = document.querySelector("#tab-language");
const performanceTab = document.querySelector("#tab-performance");
const mapTab = document.querySelector("#tab-map");
const panels = {
  clips: document.querySelector("#panel-clips"),
  live: document.querySelector("#panel-live"),
  map: document.querySelector("#panel-map"),
  language: document.querySelector("#panel-language"),
  performance: document.querySelector("#panel-performance"),
};
const liveAudio = document.querySelector("#live-audio");
const liveStatus = document.querySelector("#live-status");
const liveLastCommunication = document.querySelector("#live-last-communication");
const liveLatency = document.querySelector("#live-latency");
const liveChannel = document.querySelector("#live-channel");
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
const languageStatus = document.querySelector("#language-status");
const lexicalAnalysis = document.querySelector("#lexical-analysis");
const performanceStatus = document.querySelector("#performance-status");
const performanceDashboard = document.querySelector("#performance-dashboard");

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
let audioContext = null;
let analyser = null;
let analyserSource = null;
let waveformData = null;
let waveformAnimationId = null;
let currentClipPlayback = null;
let quietSince = null;
let selectedChannels = new Set();
let selectedClipPage = 1;
let selectedClipPageSize = defaultClipPageSize;
let clipSortDirection = "newest";
let currentClipPayload = null;
let currentPageClips = [];
let currentFilteredTotal = 0;
let selectedLiveChannel = everythingLiveChannel;
let activeTab = "clips";
let mapPayloadLoaded = false;
let languagePayloadLoaded = false;
let performancePayloadLoaded = false;
let performanceRefreshTimer = null;
let latestPerformancePayload = null;
let selectedPerformanceRangeHours = 2;
let systemMediaControlsEnabled = initialSystemMediaControlsEnabled();
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
if (panels.map) {
  panels.map.hidden = !aisDashboardEnabled;
}

configureLiveAudioElement();
clearBrowserMediaSession();
updateSystemMediaControlsUi();

refreshButton.addEventListener("click", () => {
  if (activeTab === "performance") {
    loadAndRenderPerformance({ showLoading: false });
  } else if (activeTab === "map") {
    loadAndRenderMap({ showLoading: false });
  } else {
    loadAndRender();
  }
});

channelFilter.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target : null;
  const action = target?.closest(".channel-filter-action");
  if (!action || !channelFilter.contains(action)) {
    return;
  }
  selectedChannels.clear();
  selectedClipPage = 1;
  loadAndRender();
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
  selectedClipPage = 1;
  loadAndRender();
});

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    activateTab(tab.dataset.tab);
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
  activateTab(tabFromLocation(), { updateRoute: false });
});

liveAudio.addEventListener("playing", () => {
  liveStatus.textContent = isEverythingLiveMode() ? "Playing queued transmission" : "Streaming";
  setLivePlayButton("pause");
  updateLiveMediaSession("playing");
});

liveAudio.addEventListener("waiting", () => {
  liveStatus.textContent = "Buffering";
});

liveAudio.addEventListener("pause", () => {
  if (isEverythingLiveMode() && everythingQueueEnabled) {
    renderEverythingQueuePanel();
    return;
  }
  setLivePlayButton("play");
  liveStatus.textContent = "Paused";
  updateLiveMediaSession("paused");
});

liveAudio.addEventListener("error", () => {
  if (isEverythingLiveMode()) {
    handleEverythingClipEnded();
    return;
  }
  liveStatus.textContent = "Reconnecting";
  updateLiveMediaSession("none");
  scheduleLiveReconnect();
});

liveAudio.addEventListener("ended", () => {
  if (isEverythingLiveMode()) {
    handleEverythingClipEnded();
    return;
  }
  liveStatus.textContent = "Reconnecting";
  updateLiveMediaSession("none");
  scheduleLiveReconnect();
});

async function loadAndRender() {
  clipStatus.textContent = "Loading clips...";
  const payload = await loadClipPayload();
  currentClipPayload = payload;
  renderSite(payload);
}

async function loadClipPayload() {
  try {
    const response = await fetch(clipRequestUrl(), { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`live clip HTTP ${response.status}`);
    }
    const payload = await response.json();
    return normalizeLivePayload(payload);
  } catch {
    return loadPublishedManifest();
  }
}

function clipRequestUrl() {
  const offset = `offset=${clipOffset()}`;
  const channels = selectedChannelValues();
  if (!channels.length) {
    return `/api/clips/recent?limit=${selectedClipPageSize}&${offset}`;
  }
  const channelParams = channels.map((channel) => `channels=${encodeURIComponent(channel)}`).join("&");
  return `/api/clips/recent?limit=${selectedClipPageSize}&${offset}&${channelParams}`;
}

async function loadPublishedManifest() {
  try {
    const response = await fetch(manifestUrl, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`manifest HTTP ${response.status}`);
    }
    return normalizePublishedManifest(await response.json());
  } catch {
    return normalizePublishedManifest(fallbackManifest);
  }
}

async function loadLanguagePayload() {
  if (!liveLanguageAnalysisEnabled) {
    return loadPublishedLanguagePayload();
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
  return {
    source: "live",
    site: fallbackManifest.site,
    stats: {
      clip_count: Number(
        payload.clip_count ?? totalAvailableClipsFromCounts(payload.channel_counts) ?? clips.length,
      ),
      filtered_clip_count: Number(payload.filtered_clip_count ?? clips.length),
      limit: Number(payload.limit ?? selectedClipPageSize),
      offset: Number(payload.offset ?? clipOffset()),
      channel_counts: payload.channel_counts || countBy(clips, (clip) => clip.channel || "?"),
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
      audio_public_filename: clip.audio_public_filename || "",
    })),
  };
}

function renderSite(payload) {
  const clips = payload.clips || [];
  currentChannelLabels = channelLabelsForPayload(payload);
  document.title = payload.site?.title || fallbackManifest.site.title;
  document.querySelector("#site-title").textContent = payload.site?.title || fallbackManifest.site.title;
  document.querySelector("#site-subtitle").textContent =
    payload.site?.subtitle || fallbackManifest.site.subtitle;
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
  const channelCounts = payload.stats?.channel_counts || countBy(clips, (clip) => clip.channel || "?");
  const channelTotal = Object.keys(channelCounts).length;
  const clipTotal = totalDatabaseClips(payload, clips);
  const latest = clips[0]?.started_at ? shortTime(clips[0].started_at) : "None";
  const statItems = [
    ["Clips", clipTotal],
    ["Channels", channelTotal],
    ["Latest", latest],
    ["Feed", payload.source === "live" ? "Live DB" : "Published export"],
  ];

  stats.replaceChildren(
    ...statItems.map(([label, value]) => {
      const item = document.createElement("div");
      item.className = "stat";
      const term = document.createElement("dt");
      term.textContent = label;
      const description = document.createElement("dd");
      description.textContent = String(value);
      item.append(term, description);
      return item;
    }),
  );
}

function renderChannelFilter(payload) {
  const wasOpen = channelFilter.querySelector(".channel-filter-menu")?.open;
  const channelCounts = payload.stats?.channel_counts || countBy(payload.clips || [], (clip) => clip.channel || "?");
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
  allAction.setAttribute("aria-pressed", String(selectedChannels.size === 0));
  const allName = document.createElement("span");
  allName.className = "channel-filter-name";
  allName.textContent = "All channels";
  const allDetail = document.createElement("span");
  allDetail.className = "channel-filter-detail";
  allDetail.textContent = channelClipCountText(totalAvailableClipsFromCounts(channelCounts));
  allAction.append(allName, allDetail);

  const options = document.createElement("div");
  options.className = "channel-filter-options";
  options.replaceChildren(...channels.map((channel) => channelFilterOption(channel, channelCounts[channel])));
  panel.append(allAction, options);
  menu.append(trigger, panel);
  channelFilter.replaceChildren(menu);
}

function renderClipDisplayControls() {
  if (!clipDisplayControls) {
    return;
  }
  const pageSizeControl = segmentedControl(
    "Clips per page",
    clipPageSizeOptions.map((pageSize) => ({
      label: String(pageSize),
      active: selectedClipPageSize === pageSize,
      onClick: () => {
        if (selectedClipPageSize === pageSize) {
          return;
        }
        selectedClipPageSize = pageSize;
        selectedClipPage = 1;
        loadAndRender();
      },
    })),
  );
  const sortControl = segmentedControl("Flip page order", [
    {
      label: "Newest",
      active: clipSortDirection === "newest",
      onClick: () => {
        if (clipSortDirection === "newest") {
          return;
        }
        clipSortDirection = "newest";
        renderCurrentClipOrder();
      },
    },
    {
      label: "Oldest",
      active: clipSortDirection === "oldest",
      onClick: () => {
        if (clipSortDirection === "oldest") {
          return;
        }
        clipSortDirection = "oldest";
        renderCurrentClipOrder();
      },
    },
  ]);
  clipDisplayControls.replaceChildren(pageSizeControl, sortControl);
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

function formatChannelFilterSummary(channelCounts) {
  const channels = selectedChannelValues();
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
  if (!selectedChannels.size) {
    return clips;
  }
  return clips.filter((clip) => selectedChannels.has(clip.channel));
}

function paginateClips(clips) {
  const start = clipOffset();
  return clips.slice(start, start + selectedClipPageSize);
}

function applyClipSortForCurrentPage(clips) {
  if (clipSortDirection === "oldest") {
    return [...clips].reverse();
  }
  return clips;
}

function clipOffset() {
  return (selectedClipPage - 1) * selectedClipPageSize;
}

function renderClips(clips) {
  if (!clips.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent =
      selectedChannels.size === 0
        ? "No playable clips are available yet."
        : "No playable clips are available for the selected channels.";
    clipList.replaceChildren(empty);
    return;
  }
  clipList.replaceChildren(...clips.map(renderClipCard));
}

function renderClipPagination(totalClips) {
  if (!clipPagination) {
    return;
  }
  const totalPages = Math.max(1, Math.ceil(totalClips / selectedClipPageSize));
  if (totalClips <= selectedClipPageSize) {
    clipPagination.hidden = true;
    clipPagination.replaceChildren();
    return;
  }
  selectedClipPage = Math.min(Math.max(selectedClipPage, 1), totalPages);
  const previous = paginationButton("Previous", selectedClipPage <= 1, () => {
    selectedClipPage -= 1;
    loadAndRender();
  });
  const next = paginationButton("Next", selectedClipPage >= totalPages, () => {
    selectedClipPage += 1;
    loadAndRender();
  });
  const pageStatus = document.createElement("span");
  pageStatus.className = "clip-page-status";
  pageStatus.textContent = `Page ${selectedClipPage} of ${totalPages}`;
  clipPagination.hidden = false;
  clipPagination.replaceChildren(previous, pageStatus, next);
}

function paginationButton(label, disabled, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "pagination-button";
  button.disabled = disabled;
  button.textContent = label;
  button.addEventListener("click", onClick);
  return button;
}

function renderClipCard(clip) {
  const article = document.createElement("article");
  article.className = "clip-card";

  const meta = document.createElement("div");
  meta.className = "clip-meta";
  meta.append(renderChannelPill(clip.channel), renderPill(formatDateTime(clip.started_at)));
  if (clip.duration_seconds) {
    meta.append(renderPill(`${Math.round(Number(clip.duration_seconds))}s`));
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
  return article;
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
  for (const channel of liveChannels) {
    currentChannelLabels[channel.channel] = channel.label;
  }
  renderLiveChannelPicker();
  renderEverythingQueuePanel();
  if (liveAudio.src && !isEverythingLiveMode()) {
    liveAudio.src = liveStreamUrl();
    liveAudio.load();
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
  if (!liveChannelPicker) {
    return;
  }
  liveChannelPicker.replaceChildren();
  liveChannelPicker.append(liveChannelOptionButton(everythingChannelOption()));
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

function liveChannelOptionButton(channel) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "live-channel-option";
  button.classList.toggle("is-active", channel.channel === selectedLiveChannel);
  button.classList.toggle("is-everything", channel.channel === everythingLiveChannel);
  button.dataset.channel = channel.channel;
  button.textContent = channelLabel(channel.channel);
  button.title =
    channel.channel === everythingLiveChannel
      ? "Queue transmissions from all monitored live channels"
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
    ? isEverythingLiveMode()
      ? "Starting everything queue"
      : "Reconnecting"
    : isEverythingLiveMode()
      ? "Everything queue ready"
      : "Warming stream";
  drawWaitingFrame({ showWaiting: false });
  pollLiveStatus();
  if (isEverythingLiveMode()) {
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
  const selected = liveChannels.find((item) => item.channel === channel);
  if (selected) {
    return selected;
  }
  return { channel, label: defaultChannelLabels[channel] || "", frequencyMhz: "" };
}

function isEverythingLiveMode() {
  return selectedLiveChannel === everythingLiveChannel;
}

function normalizeTabName(name) {
  return tabRouteAliases[String(name || "").toLowerCase()] || "clips";
}

function tabFromLocation() {
  const url = new URL(window.location.href);
  const tabParam = url.searchParams.get("tab");
  const hashSegment = url.hash.replace(/^#\/?/, "");
  const pathSegments = url.pathname.split("/").filter(Boolean);
  const pathSegment = pathSegments[pathSegments.length - 1] || "";
  return normalizeTabName(tabParam || hashSegment || pathSegment || "clips");
}

function tabRouteUrl(name) {
  const url = new URL(window.location.href);
  const routeSegment = tabRouteSegments[name] || tabRouteSegments.clips;
  url.pathname = `/${routeSegment}/`;
  url.search = "";
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

function activateTab(name, { updateRoute = true, replaceRoute = false } = {}) {
  name = enabledTabName(normalizeTabName(name));
  activeTab = name;
  tabs.forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.tab === name);
  });
  Object.entries(panels).forEach(([panelName, panel]) => {
    const active = panelName === name;
    panel.classList.toggle("is-active", active);
    panel.hidden = !active;
  });
  refreshButton.hidden = !["clips", "map", "performance"].includes(name);
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
  if (name === "language" && !languagePayloadLoaded) {
    loadAndRenderLanguage();
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
}

async function loadAndRenderLanguage() {
  if (!languageStatus || !lexicalAnalysis) {
    return;
  }
  languageStatus.textContent = "Loading analysis...";
  const payload = await loadLanguagePayload();
  languagePayloadLoaded = true;
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
  renderAisCatcherFrame();
}

function renderAisCatcherFrame() {
  const expectedSrc = new URL(aisCatcherFrameUrl, window.location.href).href;
  if (aisCatcherFrame.src !== expectedSrc) {
    aisCatcherFrame.src = aisCatcherFrameUrl;
  }
  aisCatcherFrame.title = "AIS-catcher live map";
  mapStatus.textContent = "Showing AIS-catcher live map";
}

function renderLanguageDashboard(payload) {
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
  const channelCounts = channelCountsWithMonitoredChannels(payload.channels || frequency.by_channel || {});
  const cards = document.createElement("div");
  cards.className = "language-grid";
  cards.append(
    languageCard("Transmissions", String(payload.source_clip_count || 0), "Analyzed transcript clips"),
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
  channelPanel.append(channelActivityChart(channelCounts));

  const wordsPanel = languagePanel("Radio words");
  wordsPanel.append(
    termSection("Jargon", terms.semantic_buckets?.communication_markers || []),
    termSection("Movement", terms.semantic_buckets?.movement || []),
    termSection("Places", terms.semantic_buckets?.places || []),
    termSection("N-grams", terms.bigrams || []),
  );

  const entityPanel = languagePanel("Suspected vessels and entities");
  entityPanel.append(entityList(payload.entities || []));

  const topicPanel = languagePanel(
    "Topic intelligence",
    "Dominant clusters and radio signals from the current transcript sample.",
  );
  const topicFrame = document.createElement("iframe");
  topicFrame.className = "topic-frame";
  topicFrame.loading = "lazy";
  topicFrame.title = "BERTopic 3D visual clustering";
  topicFrame.allowFullscreen = true;
  topicFrame.setAttribute("allow", "fullscreen");
  topicFrame.src = topics.plot_url || topicClusterFallbackUrl;
  const topicFrameShell = document.createElement("div");
  topicFrameShell.className = "topic-frame-shell";
  topicFrameShell.append(topicFrame);
  topicPanel.append(
    mobileSignalFingerprint(payload, channelCounts, topics, terms),
    topicFrameShell,
    topicList(nonOutlierTopics(topics.items || [])),
  );

  const educationPanel = languagePanel("Maritime radio references");
  educationPanel.append(
    educationGuideList(payload.education_guide || []),
    referenceIndex(payload.education || []),
  );

  lexicalAnalysis.replaceChildren(cards, channelPanel, wordsPanel, entityPanel, topicPanel, educationPanel);
}

async function loadAndRenderPerformance({ showLoading = true } = {}) {
  if (!performanceStatus || !performanceDashboard) {
    return;
  }
  if (showLoading || !performancePayloadLoaded) {
    performanceStatus.textContent = "Loading performance...";
  }
  try {
    const response = await fetch(performanceUrl, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`performance HTTP ${response.status}`);
    }
    const payload = await response.json();
    performancePayloadLoaded = true;
    latestPerformancePayload = payload;
    renderPerformanceDashboard(payload);
  } catch {
    performanceStatus.textContent = "Performance unavailable";
    performanceDashboard.replaceChildren(emptyPerformanceState());
  }
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
  const hostGrid = document.createElement("div");
  hostGrid.className = "performance-host-grid";
  hostGrid.append(...hosts.map((host, index) => performanceHostPanel(host, index)));
  performanceDashboard.replaceChildren(rangeControl, hostGrid);
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
    return host.role;
  }
  return index === 0 ? performanceHostLabel : "Raspberry Pi edge radio";
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
  drawPerformanceMetricChart(svg, samples, suffix);

  const caption = document.createElement("span");
  caption.className = "performance-chart-caption";
  caption.textContent = performanceChartCaption(samples);
  chart.append(heading, svg, caption);
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
    return;
  }
  const points = samples.map((sample, index) => {
    const x = left + (samples.length === 1 ? plotWidth : (index / (samples.length - 1)) * plotWidth);
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

function mobileSignalFingerprint(payload, channelCounts, topics, terms) {
  const metrics = signalFingerprintMetrics(payload, channelCounts, topics, terms);
  const panel = document.createElement("div");
  panel.className = "mobile-signal-panel";

  const stage = document.createElement("div");
  stage.className = "signal-fingerprint-stage";

  const orb = document.createElement("div");
  orb.className = "signal-score-orb";
  orb.style.setProperty("--score-angle", `${metrics.score * 3.6}deg`);
  const scoreValue = document.createElement("span");
  scoreValue.className = "signal-score-value";
  const score = document.createElement("strong");
  score.textContent = String(metrics.score);
  const scale = document.createElement("span");
  scale.textContent = "/100";
  scoreValue.append(score, scale);
  orb.append(scoreValue);

  const copy = document.createElement("div");
  copy.className = "signal-fingerprint-copy";
  const label = document.createElement("p");
  label.className = "language-label";
  label.textContent = "Signal fingerprint";
  const title = document.createElement("h4");
  title.textContent = metrics.title;
  const summary = document.createElement("p");
  summary.className = "signal-fingerprint-summary";
  summary.textContent = metrics.summary;
  copy.append(label, title, summary);
  stage.append(orb, copy);

  const meters = document.createElement("div");
  meters.className = "signal-meter-grid";
  meters.append(
    signalMeter("Topic focus", metrics.topicFocusText, metrics.topicFocus),
    signalMeter("Channel spread", metrics.channelSpreadText, metrics.channelSpread),
    signalMeter("Named traffic", metrics.entityDensityText, metrics.entityDensity),
    signalMeter("Movement language", metrics.movementDensityText, metrics.movementDensity),
  );

  const chips = document.createElement("div");
  chips.className = "signal-chip-row";
  for (const signal of metrics.signals) {
    const chip = document.createElement("span");
    chip.className = "signal-chip";
    chip.textContent = signal;
    chips.append(chip);
  }

  panel.append(stage, meters, chips);
  return panel;
}

function signalFingerprintMetrics(payload, channelCounts, topics, terms) {
  const sourceClipCount = Math.max(0, Number(payload?.source_clip_count || 0));
  const visibleTopics = nonOutlierTopics(topics?.items || []);
  const sortedTopics = [...visibleTopics].sort(
    (left, right) => Number(right.count || 0) - Number(left.count || 0),
  );
  const dominantTopic = sortedTopics[0] || null;
  const topicTotal = sumCounts(visibleTopics);
  const dominantCount = Number(dominantTopic?.count || 0);
  const topicFocus = boundedRatio(dominantCount, topicTotal || sourceClipCount);
  const activeChannels = activeAnalyzedChannelCount(channelCounts);
  const channelSpread = boundedRatio(activeChannels, monitoredAnalysisChannels.length);
  const entities = Array.isArray(payload?.entities) ? payload.entities : [];
  const entityMentions = sumCounts(entities);
  const entityDensity = Math.min(boundedRatio(entityMentions, sourceClipCount), 1);
  const movementHits = sumCounts(terms?.semantic_buckets?.movement || []);
  const movementDensity = Math.min(boundedRatio(movementHits, sourceClipCount), 1);
  const score = Math.round(
    topicFocus * 42 + channelSpread * 22 + entityDensity * 22 + movementDensity * 14,
  );
  const title = dominantTopic ? topicTitle(dominantTopic) : "Signals still gathering";
  const summary = dominantTopic
    ? `${formatPercentRatio(topicFocus)} of clustered clips orbit ${topicTitle(dominantTopic)}.`
    : "The next analysis run will fill in topic focus, channel spread, and entity density.";
  return {
    score,
    title,
    summary,
    signals: signalFingerprintSignals(payload, terms, dominantTopic),
    topicFocus,
    topicFocusText: dominantTopic ? `${formatPercentRatio(topicFocus)} focus` : "Pending",
    channelSpread,
    channelSpreadText: `${activeChannels}/${monitoredAnalysisChannels.length} channels`,
    entityDensity,
    entityDensityText: `${entityMentions.toLocaleString()} mentions`,
    movementDensity,
    movementDensityText: `${movementHits.toLocaleString()} hits`,
  };
}

function signalFingerprintSignals(payload, terms, dominantTopic) {
  const signals = [];
  addSignal(signals, dominantTopic ? topicTitle(dominantTopic) : "");
  addSignal(signals, payload?.entities?.[0]?.name);
  addSignal(signals, terms?.semantic_buckets?.places?.[0]?.term);
  addSignal(signals, terms?.semantic_buckets?.movement?.[0]?.term);
  addSignal(signals, terms?.semantic_buckets?.communication_markers?.[0]?.term);
  addSignal(signals, terms?.bigrams?.[0]?.term);
  if (!signals.length) {
    signals.push("Awaiting analysis");
  }
  return signals.slice(0, 5);
}

function signalMeter(labelText, valueText, ratio) {
  const meter = document.createElement("div");
  meter.className = "signal-meter";
  const head = document.createElement("div");
  head.className = "signal-meter-head";
  const label = document.createElement("span");
  label.className = "signal-meter-label";
  label.textContent = labelText;
  const value = document.createElement("span");
  value.className = "signal-meter-value";
  value.textContent = valueText;
  head.append(label, value);
  const track = document.createElement("span");
  track.className = "signal-meter-track";
  const fill = document.createElement("span");
  fill.className = "signal-meter-fill";
  fill.style.width = `${Math.max(4, boundedPercent(ratio)).toFixed(1)}%`;
  track.append(fill);
  meter.append(head, track);
  return meter;
}

function addSignal(signals, value) {
  const text = String(value || "").trim();
  if (!text || signals.some((signal) => signal.toLowerCase() === text.toLowerCase())) {
    return;
  }
  signals.push(text);
}

function sumCounts(items) {
  return (items || []).reduce((total, item) => total + Math.max(0, Number(item?.count || 0)), 0);
}

function boundedRatio(numerator, denominator) {
  const value = Number(numerator || 0) / Number(denominator || 0);
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.min(1, Math.max(0, value));
}

function boundedPercent(ratio) {
  return boundedRatio(ratio, 1) * 100;
}

function formatPercentRatio(ratio) {
  return `${Math.round(boundedPercent(ratio))}%`;
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

function channelCountsWithMonitoredChannels(channelCounts) {
  const merged = {};
  for (const channel of monitoredAnalysisChannels) {
    merged[channel] = 0;
  }
  for (const [channel, count] of Object.entries(channelCounts || {})) {
    merged[channel] = Number(count || 0);
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
      const example = document.createElement("blockquote");
      example.textContent = displayedExample.text || "";
      item.append(title, meta, channels, example);
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
  audio.controls = true;
  audio.preload = "metadata";
  audio.src = audioUrl;
  audio.setAttribute("controlslist", "nodownload noplaybackrate noremoteplayback");
  audio.setAttribute("disableremoteplayback", "");
  audio.setAttribute("x-webkit-airplay", "deny");

  const time = document.createElement("span");
  time.className = "example-player-time";
  time.textContent = formatPlaybackTime(example.duration_seconds, { unknownLabel: unknownPlaybackTimeLabel });

  audio.addEventListener("loadedmetadata", () => {
    if (Number.isFinite(audio.duration)) {
      time.textContent = formatPlaybackTime(audio.duration, { unknownLabel: time.textContent });
    }
  });
  audio.addEventListener("play", () => {
    stopOtherAudio(audio);
    currentClipPlayback = audio;
    clearBrowserMediaSession();
    refreshClipAudioPlayback(example, audio, time);
  });
  audio.addEventListener("error", () => {
    refreshClipAudioPlayback(example, audio, time, { force: true });
  });
  audio.addEventListener("pause", () => {
    if (currentClipPlayback === audio) {
      currentClipPlayback = null;
    }
  });
  audio.addEventListener("ended", () => {
    if (currentClipPlayback === audio) {
      currentClipPlayback = null;
    }
  });

  player.append(audio, time);
  return player;
}

function analysisAudioUrlForClip(clip) {
  return clipAudioRequestUrl(clip) || audioUrlForClip(clip);
}

function stopOtherAudio(currentPlayback) {
  if (currentPlayback !== currentClipPlayback) {
    stopCurrentClipPlayback();
  }
  if (currentPlayback !== liveAudio) {
    closeLiveAudioStream();
  }
}

function stopAllAudio() {
  stopCurrentClipPlayback();
  closeLiveAudioStream();
}

function suspendLiveView() {
  stopLiveStatusPolling();
  stopWaveform();
  if (shouldPreserveLiveAudioSession()) {
    if (isEverythingLiveMode() && everythingQueueEnabled) {
      startLiveActivityPolling();
    } else {
      stopLiveActivityPolling();
    }
    updateLiveMediaSession("playing");
    return;
  }
  stopLiveActivityPolling();
  closeLiveAudioStream();
}

function shouldPreserveLiveAudioSession() {
  if (isEverythingLiveMode() && everythingQueueEnabled) {
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
      return item;
    }),
  );
  return list;
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
      item.className = "education-card";
      const title = document.createElement("a");
      title.href = resource.url || "#";
      title.rel = "noopener noreferrer";
      title.target = "_blank";
      title.textContent = resource.title || resource.source || "Reference";
      const meta = document.createElement("p");
      meta.className = "entity-meta";
      meta.textContent = [resource.source, resource.category].filter(Boolean).join(" · ");
      const relevance = document.createElement("p");
      relevance.textContent = resource.local_relevance || "";
      item.append(title, meta, relevance);
      return item;
    }),
  );
  return list;
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
      cue.textContent = "Details";
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
  const wrapper = document.createElement("div");
  wrapper.className = "reference-index";
  const title = document.createElement("h4");
  title.textContent = "Reference index";
  wrapper.append(title, educationList(resources));
  return wrapper;
}

function channelActivityChart(channels) {
  const entries = Object.entries(channels || {})
    .map(([channel, count]) => [channel, Number(count || 0)])
    .filter(([, count]) => count > 0)
    .sort((left, right) => right[1] - left[1] || compareChannels(left[0], right[0]));
  const list = document.createElement("div");
  list.className = "channel-bar-list";
  if (!entries.length) {
    const empty = document.createElement("p");
    empty.className = "muted-inline";
    empty.textContent = "No analyzed transmissions yet";
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
        artist: isEverythingLiveMode()
          ? currentLiveQueueClip
            ? channelLabel(currentLiveQueueClip.channel)
            : "Everything"
          : channelLabel(selectedLiveChannel),
        album: isEverythingLiveMode() ? "Everything queue" : "Live radio",
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
  if (isEverythingLiveMode()) {
    configureEverythingQueueAudioElement({ muted: true });
    liveStatus.textContent = "Everything queue ready";
    setLivePlayButton("play");
    drawWaitingFrame({ showWaiting: true });
    renderLiveStatus(everythingChannelOption());
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
  if (isEverythingLiveMode()) {
    if (everythingQueueEnabled) {
      stopEverythingQueue({ clearQueue: false });
      liveAudio.pause();
      setLivePlayButton("play");
      liveStatus.textContent = "Everything queue paused";
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
  if (isEverythingLiveMode()) {
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
    ensureAudioAnalyser();
    if (audioContext?.state === "suspended") {
      await audioContext.resume();
    }
    startWaveform();
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
  if (!everythingQueueStartedAtMs) {
    everythingQueueStartedAtMs = Date.now();
  }
  configureEverythingQueueAudioElement();
  setLivePlayButton("pause");
  liveStatus.textContent = "Waiting for queued transmission";
  drawWaitingFrame({ showWaiting: true });
  renderLiveStatus(everythingChannelOption());
  try {
    ensureAudioAnalyser();
    if (audioContext?.state === "suspended") {
      await audioContext.resume();
    }
    startWaveform();
    stopOtherAudio(liveAudio);
    await pollEverythingQueue({ playIfIdle: false, seedRecent: true });
    if (!currentLiveQueueClip) {
      await playNextEverythingQueueClip();
    }
  } catch {
    liveStatus.textContent = "Everything queue waiting";
  } finally {
    renderEverythingQueuePanel();
    updateLiveMediaSession(everythingQueueEnabled ? "playing" : "paused");
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
  const url = rawLiveStreamUrl();
  return withDspProfile(url);
}

function rawLiveStreamUrl() {
  if (isEverythingLiveMode()) {
    return currentLiveQueueClip?.playback_url || "";
  }
  if (selectedLiveChannel === "14") {
    return defaultLiveStreamUrl;
  }
  return `/api/live/${encodeURIComponent(selectedLiveChannel)}/current.mp3`;
}

function withDspProfile(url) {
  if (!liveDspProfile) {
    return url;
  }
  const joiner = url.includes("?") ? "&" : "?";
  return `${url}${joiner}dsp=${encodeURIComponent(liveDspProfile)}`;
}

function liveStatusUrl() {
  if (isEverythingLiveMode()) {
    return "";
  }
  return `/api/live/${encodeURIComponent(selectedLiveChannel)}/status`;
}

function lastCommunicationUrl() {
  if (isEverythingLiveMode()) {
    return liveQueueUrl;
  }
  return `/api/clips/recent?limit=1&channel=${encodeURIComponent(selectedLiveChannel)}`;
}

async function pollLiveStatus() {
  if (panels.live.hidden) {
    return;
  }
  if (isEverythingLiveMode()) {
    renderLiveStatus(everythingChannelOption());
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
  const shouldPollHiddenEverythingQueue = isEverythingLiveMode() && everythingQueueEnabled;
  if (panels.live.hidden && !shouldPollHiddenEverythingQueue) {
    return;
  }
  liveActivityAbortController?.abort();
  liveActivityAbortController = new AbortController();
  try {
    if (isEverythingLiveMode()) {
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
      liveLastCommunication.textContent = isEverythingLiveMode()
        ? "Queue: unavailable"
        : `Last ${selectedLiveChannel}: unavailable`;
    }
  } finally {
    renderLiveTelemetry();
    if (!panels.live.hidden || shouldPollHiddenEverythingQueue) {
      liveActivityTimer = setTimeout(
        pollLiveActivity,
        isEverythingLiveMode() ? liveQueuePollMs : liveActivityPollMs,
      );
    }
  }
}

async function pollEverythingQueue({
  signal = null,
  playIfIdle = true,
  seedRecent = false,
} = {}) {
  const response = await fetch(liveQueueUrl, {
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    throw new Error(`everything queue HTTP ${response.status}`);
  }
  const payload = await response.json();
  const clips = Array.isArray(payload.clips) ? payload.clips : [];
  if (seedRecent && !everythingQueueSeeded) {
    enqueueEverythingClips(clips, { includeBackfill: true });
    everythingQueueSeeded = true;
  } else {
    enqueueEverythingClips(clips);
  }
  renderLiveTelemetry();
  renderEverythingQueuePanel();
  if (playIfIdle && everythingQueueEnabled && !currentLiveQueueClip && liveAudio.paused) {
    await playNextEverythingQueueClip();
  }
}

function enqueueEverythingClips(clips, { includeBackfill = false } = {}) {
  let normalizedClips = clips
    .map(normalizeEverythingQueueClip)
    .filter(Boolean);
  if (includeBackfill) {
    normalizedClips = mostRecentEverythingQueueClips(normalizedClips, everythingInitialQueueLimit);
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

function mostRecentEverythingQueueClips(clips, limit) {
  return [...clips]
    .sort((left, right) => queueClipRelevantTime(right) - queueClipRelevantTime(left))
    .slice(0, limit);
}

function isEverythingQueueClipAfterStart(clip) {
  if (!everythingQueueStartedAtMs) {
    return true;
  }
  return queueClipRelevantTime(clip) >= everythingQueueStartedAtMs;
}

function normalizeEverythingQueueClip(clip) {
  const playbackUrl = audioUrlForClip(clip || {});
  const audioUrl = clipAudioRequestUrl(clip || {}) || playbackUrl;
  const channel = String(clip?.channel || "").toUpperCase();
  if (!audioUrl || !channel) {
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

async function playNextEverythingQueueClip() {
  if (!everythingQueueEnabled || !isEverythingLiveMode()) {
    return;
  }
  currentLiveQueueClip = liveQueue.shift() || null;
  renderLiveStatus(everythingChannelOption());
  renderEverythingQueuePanel();
  if (!currentLiveQueueClip) {
    liveStatus.textContent = "Waiting for queued transmission";
    setLivePlayButton("pause");
    drawWaitingFrame({ showWaiting: true });
    updateLiveMediaSession("playing");
    return;
  }
  const playbackUrl = clipAudioRequestUrl(currentLiveQueueClip) || currentLiveQueueClip.audio_url;
  if (!playbackUrl) {
    currentLiveQueueClip = null;
    liveStatus.textContent = "Skipping queued transmission";
    renderEverythingQueuePanel();
    window.setTimeout(() => {
      playNextEverythingQueueClip();
    }, 250);
    return;
  }
  const clipUrl = withCacheBust(playbackUrl);
  configureEverythingQueueAudioElement();
  if (liveAudio.getAttribute("src") !== clipUrl) {
    liveAudio.src = clipUrl;
    liveAudio.load();
  }
  liveStatus.textContent = `Playing ${channelLabel(currentLiveQueueClip.channel)}`;
  setLivePlayButton("pause");
  renderLiveTelemetry();
  updateLiveMediaSession("playing");
  try {
    await liveAudio.play();
  } catch {
    currentLiveQueueClip = null;
    liveStatus.textContent = "Skipping queued transmission";
    renderEverythingQueuePanel();
    window.setTimeout(() => {
      playNextEverythingQueueClip();
    }, 250);
  }
}

function configureEverythingQueueAudioElement({ muted = false } = {}) {
  liveAudio.crossOrigin = "anonymous";
  liveAudio.preload = "auto";
  liveAudio.muted = muted;
}

function handleEverythingClipEnded() {
  currentLiveQueueClip = null;
  if (!everythingQueueEnabled) {
    setLivePlayButton("play");
    renderEverythingQueuePanel();
    return;
  }
  playNextEverythingQueueClip();
}

function stopEverythingQueue({ clearQueue = false } = {}) {
  everythingQueueEnabled = false;
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
  if (isEverythingLiveMode()) {
    liveChannel.textContent = "Everything";
    liveFrequency.textContent = "Queued active transmissions across monitored channels";
    renderLiveTelemetry();
    return;
  }
  const channel = status?.channel || selectedLiveChannel;
  liveChannel.textContent = channel ? channelLabel(channel) : "Current SDR feed";
  liveFrequency.textContent = status?.frequencyMhz ? `${status.frequencyMhz} MHz` : "";
  renderLiveTelemetry();
}

function renderLiveTelemetry() {
  if (isEverythingLiveMode()) {
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
  liveQueuePanel.hidden = !isEverythingLiveMode();
  if (liveQueuePanel.hidden) {
    liveQueuePanel.replaceChildren();
    return;
  }
  const mode = liveQueueItem(
    everythingQueueEnabled ? "Everything mode on" : "Everything mode ready",
    "All channels feed one playback queue",
  );
  const nowPlaying = currentLiveQueueClip
    ? liveQueueItem("Now playing", channelLabel(currentLiveQueueClip.channel))
    : liveQueueItem("Now playing", everythingQueueEnabled ? "Waiting for queued transmission" : "Press Play to start");
  const waiting = liveQueueItem("Queued", `${liveQueue.length} transmission${liveQueue.length === 1 ? "" : "s"}`);
  liveQueuePanel.replaceChildren(mode, nowPlaying, waiting);
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
  if (isReceiving) {
    quietSince = null;
    liveStatus.textContent = "Receiving transmission";
  } else {
    quietSince ||= now;
    const quietDurationMs = now - quietSince;
    if (quietDurationMs >= quietTransmissionDelayMs && !liveAudio.paused) {
      liveStatus.textContent = "Waiting for transmission";
    } else if (!liveAudio.paused && liveAudio.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
      liveStatus.textContent = "Monitoring";
    }
  }
  const waitedThroughQuiet =
    !isReceiving && quietSince !== null && now - quietSince >= quietTransmissionDelayMs;
  waveformPanel.classList.toggle("is-waiting", waitedThroughQuiet);
  liveSignalDot.classList.toggle("is-active", isReceiving);
  renderWaveform(waveformData, { isReceiving, rms });
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
  if (clip.playback_url) {
    return clip.playback_url;
  }
  if (clip.audio_public_filename) {
    return `/clips/${encodeURIComponent(clip.audio_public_filename)}`;
  }
  return "";
}

function clipPlaybackRequestUrl(clip) {
  if (!clip?.playback_url || !clip.channel || !clip.started_at) {
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
  if (channels.length === 1) {
    return ` for ${channelLabel(channels[0])}`;
  }
  return " for selected channels";
}

function statusText(payload, clips, filteredTotal) {
  if (!filteredTotal) {
    return selectedChannels.size === 0 ? "No clips yet" : "No clips for the selected channels yet";
  }
  const scopeText = selectedChannelStatusScope();
  const pageText =
    clips.length === filteredTotal ? `${clips.length}` : `${clips.length} of ${filteredTotal}`;
  const clipNoun = filteredTotal === 1 ? "clip" : "clips";
  if (payload.source === "live") {
    return `${pageText} ${clipNoun}${scopeText} from the live DB`;
  }
  const generated = payload.generated_at ? ` · exported ${formatDateTime(payload.generated_at)}` : "";
  return `${pageText} published ${clipNoun}${scopeText}${generated}`;
}

function filteredClipCount(payload, clips) {
  if (selectedChannels.size) {
    const channelCounts = payload.stats?.channel_counts;
    if (channelCounts) {
      return selectedChannelValues().reduce((total, channel) => total + Number(channelCounts[channel] || 0), 0);
    }
    return Number(payload.stats?.filtered_clip_count ?? clips.length);
  }
  return Number(payload.stats?.filtered_clip_count ?? totalDatabaseClips(payload, clips));
}

function totalDatabaseClips(payload, clips) {
  return Number(
    payload.stats?.clip_count ?? totalAvailableClipsFromCounts(payload.stats?.channel_counts) ?? clips.length,
  );
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
activateTab(tabFromLocation(), { replaceRoute: true, updateRoute: false });
