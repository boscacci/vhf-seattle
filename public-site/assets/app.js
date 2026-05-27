const clipPageSize = 6;
const liveClipUrl = `/api/clips/recent?limit=${clipPageSize}`;
const manifestUrl = "/public_manifest.json";
const lexicalAnalysisUrl = "/api/analysis/lexical";
const lexicalManifestUrl = "/analysis/lexical.json";
const performanceUrl = "/api/live/performance";
const topicClusterFallbackUrl = "/analysis/topic_clusters.html";
const liveChannelsUrl = "/api/live/channels";
const defaultLiveStreamUrl = "/api/live/current.mp3";
const systemMediaControlsStorageKey = "talkingboats.systemMediaControls";
const systemMediaControlsDefault = false;
const unknownPlaybackTimeLabel = "—";
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
const liveStatusPollMs = 2000;
const performanceRefreshMs = 10000;
const quietTransmissionDelayMs = 5000;
const performanceHostLabel = "OptiPlex live proxy";
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
  "13": "Bridge-to-bridge",
  "14": "VTS / Seattle Traffic",
  "16": "Distress / Calling",
  "22A": "USCG Liaison",
  "66A": "Port Operations",
  "68": "Recreational",
  "69": "Non-commercial",
  "71": "Non-commercial",
  "72": "Ship-to-ship",
  "74": "Port Operations",
};

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
  "13": "#6ab8ff",
  "14": "#40e0bf",
  "16": "#ff7777",
  "22A": "#f0b85a",
  "66A": "#c084fc",
  "68": "#8bd867",
  "69": "#f58fb2",
  "71": "#a5b4fc",
  "72": "#f7cf5d",
  "74": "#5eead4",
};

const clipList = document.querySelector("#clips");
const clipPagination = document.querySelector("#clip-pagination");
const clipStatus = document.querySelector("#clip-status");
const channelFilter = document.querySelector("#channel-filter");
const refreshButton = document.querySelector("#refresh-clips");
const stats = document.querySelector("#stats");
const tabs = [...document.querySelectorAll(".tab")];
const languageTab = document.querySelector("#tab-language");
const performanceTab = document.querySelector("#tab-performance");
const panels = {
  clips: document.querySelector("#panel-clips"),
  live: document.querySelector("#panel-live"),
  language: document.querySelector("#panel-language"),
  performance: document.querySelector("#panel-performance"),
};
const liveAudio = document.querySelector("#live-audio");
const liveStatus = document.querySelector("#live-status");
const liveChannel = document.querySelector("#live-channel");
const liveChannelPicker = document.querySelector("#live-channel-picker");
const liveFrequency = document.querySelector("#live-frequency");
const liveSignalDot = document.querySelector("#live-signal-dot");
const waveformPanel = document.querySelector("#waveform-panel");
const waveformCanvas = document.querySelector("#waveform-canvas");
const playLiveButton = document.querySelector("#play-live");
const systemMediaControlsToggle = document.querySelector("#system-media-controls");
const systemMediaNote = document.querySelector("#system-media-note");
const languageStatus = document.querySelector("#language-status");
const lexicalAnalysis = document.querySelector("#lexical-analysis");
const performanceStatus = document.querySelector("#performance-status");
const performanceDashboard = document.querySelector("#performance-dashboard");

let liveRetryTimer = null;
let liveStatusTimer = null;
let liveStatusAbortController = null;
let lastLiveStatusId = null;
let audioContext = null;
let analyser = null;
let analyserSource = null;
let waveformData = null;
let waveformAnimationId = null;
let currentClipPlayback = null;
let quietSince = null;
let selectedChannel = "all";
let selectedClipPage = 1;
let selectedLiveChannel = "14";
let activeTab = "clips";
let languagePayloadLoaded = false;
let performancePayloadLoaded = false;
let performanceRefreshTimer = null;
let systemMediaControlsEnabled = systemMediaControlsDefault;
let liveChannels = [
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
];
let currentChannelLabels = { ...defaultChannelLabels };

try {
  systemMediaControlsEnabled = window.localStorage.getItem(systemMediaControlsStorageKey) === "enabled";
} catch {
  systemMediaControlsEnabled = systemMediaControlsDefault;
}

if (languageTab) {
  languageTab.hidden = !languageDashboardEnabled;
}
if (performanceTab) {
  performanceTab.hidden = !performanceDashboardEnabled;
}

configureLiveAudioElement();
clearBrowserMediaSession();
updateSystemMediaControlsUi();

refreshButton.addEventListener("click", () => {
  if (activeTab === "performance") {
    loadAndRenderPerformance({ showLoading: false });
  } else {
    loadAndRender();
  }
});

channelFilter.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target : null;
  const button = target?.closest(".channel-filter-option");
  if (!button || !channelFilter.contains(button)) {
    return;
  }
  selectedChannel = button.dataset.channel || "all";
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
  if (document.hidden) {
    stopAllAudio();
  }
});

window.addEventListener("pagehide", () => {
  stopAllAudio();
});

liveAudio.addEventListener("playing", () => {
  liveStatus.textContent = "Streaming";
  playLiveButton.textContent = "Pause";
  updateLiveMediaSession("playing");
});

liveAudio.addEventListener("waiting", () => {
  liveStatus.textContent = "Buffering";
});

liveAudio.addEventListener("pause", () => {
  playLiveButton.textContent = "Play";
  liveStatus.textContent = "Paused";
  updateLiveMediaSession("paused");
});

liveAudio.addEventListener("error", () => {
  liveStatus.textContent = "Reconnecting";
  updateLiveMediaSession("none");
  scheduleLiveReconnect();
});

liveAudio.addEventListener("ended", () => {
  liveStatus.textContent = "Reconnecting";
  updateLiveMediaSession("none");
  scheduleLiveReconnect();
});

async function loadAndRender() {
  clipStatus.textContent = "Loading clips...";
  const payload = await loadClipPayload();
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
  if (selectedChannel === "all") {
    return `${liveClipUrl}&${offset}`;
  }
  return `${liveClipUrl}&${offset}&channel=${encodeURIComponent(selectedChannel)}`;
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
    return await response.json();
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
      limit: Number(payload.limit ?? clipPageSize),
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
  renderChannelFilter(payload);
  const filteredClips = filterClipsByChannel(clips);
  const visibleClips = payload.source === "live" ? filteredClips : paginateClips(filteredClips);
  const filteredTotal = filteredClipCount(payload, filteredClips);
  renderStats(payload, visibleClips);
  renderClips(visibleClips);
  renderClipPagination(filteredTotal);
  clipStatus.textContent = statusText(payload, visibleClips, filteredTotal);
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
  const channelCounts = payload.stats?.channel_counts || countBy(payload.clips || [], (clip) => clip.channel || "?");
  const configuredChannels = Object.keys(payload.stats?.channel_labels || payload.channel_labels || {});
  const channels = [...new Set([...Object.keys(channelCounts), ...configuredChannels])].sort(compareChannels);
  if (selectedChannel !== "all" && !channels.includes(selectedChannel)) {
    channels.push(selectedChannel);
  }
  const buttons = [
    channelFilterButton("all", "All", channelFilterDetail("all", totalAvailableClipsFromCounts(channelCounts))),
    ...channels.map((channel) => channelFilterButton(channel, `VHF ${channel}`, channelFilterDetail(channel, channelCounts[channel]))),
  ];
  channelFilter.replaceChildren(...buttons);
}

function channelFilterDetail(channel, count) {
  const clipCount = Number(count || 0);
  const label = channel === "all" ? "All channels" : currentChannelLabels[channel] || defaultChannelLabels[channel] || "";
  if (!clipCount) {
    return label;
  }
  const noun = clipCount === 1 ? "clip" : "clips";
  return `${label} · ${clipCount} ${noun}`;
}

function channelFilterButton(value, label, detail) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "channel-filter-option";
  button.dataset.channel = value;
  button.setAttribute("aria-pressed", String(value === selectedChannel));
  if (value === selectedChannel) {
    button.classList.add("is-active");
  }
  const name = document.createElement("span");
  name.className = "channel-filter-name";
  name.textContent = label;
  const detailText = document.createElement("span");
  detailText.className = "channel-filter-detail";
  detailText.textContent = detail;
  button.append(name, detailText);
  return button;
}

function filterClipsByChannel(clips) {
  if (selectedChannel === "all") {
    return clips;
  }
  return clips.filter((clip) => clip.channel === selectedChannel);
}

function paginateClips(clips) {
  const start = clipOffset();
  return clips.slice(start, start + clipPageSize);
}

function clipOffset() {
  return (selectedClipPage - 1) * clipPageSize;
}

function renderClips(clips) {
  if (!clips.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "No transcribed clips are available yet.";
    clipList.replaceChildren(empty);
    return;
  }
  clipList.replaceChildren(...clips.map(renderClipCard));
}

function renderClipPagination(totalClips) {
  if (!clipPagination) {
    return;
  }
  const totalPages = Math.max(1, Math.ceil(totalClips / clipPageSize));
  if (totalClips <= clipPageSize) {
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
    if (payload.defaultChannel && liveChannels.some((item) => item.channel === payload.defaultChannel)) {
      selectedLiveChannel = payload.defaultChannel;
    }
  } catch {
    liveChannels = normalizeLiveChannels(liveChannels);
  }
  for (const channel of liveChannels) {
    currentChannelLabels[channel.channel] = channel.label;
  }
  renderLiveChannelPicker();
  if (liveAudio.src) {
    liveAudio.src = liveStreamUrl();
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
  for (const channel of liveChannels) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "live-channel-option";
    button.classList.toggle("is-active", channel.channel === selectedLiveChannel);
    button.dataset.channel = channel.channel;
    button.textContent = channelLabel(channel.channel);
    button.title = channelLabel(channel.channel);
    button.setAttribute("aria-pressed", String(channel.channel === selectedLiveChannel));
    button.addEventListener("click", () => selectLiveChannel(channel.channel));
    liveChannelPicker.append(button);
  }
}

function selectLiveChannel(channel) {
  if (!channel || channel === selectedLiveChannel) {
    return;
  }
  const wasPlaying = !liveAudio.paused;
  selectedLiveChannel = channel;
  lastLiveStatusId = null;
  renderLiveChannelPicker();
  renderLiveStatus(findLiveChannel(channel));
  liveAudio.pause();
  liveAudio.src = withCacheBust(liveStreamUrl());
  liveAudio.load();
  updateLiveMediaSession(wasPlaying ? "playing" : "paused");
  liveStatus.textContent = wasPlaying ? "Reconnecting" : "Ready";
  drawWaitingFrame({ showWaiting: false });
  pollLiveStatus();
  if (wasPlaying) {
    connectLive();
  }
}

function findLiveChannel(channel) {
  const selected = liveChannels.find((item) => item.channel === channel);
  if (selected) {
    return selected;
  }
  return { channel, label: defaultChannelLabels[channel] || "", frequencyMhz: "" };
}

function activateTab(name) {
  if (name === "language" && !languageDashboardEnabled) {
    return;
  }
  if (name === "performance" && !performanceDashboardEnabled) {
    return;
  }
  activeTab = name;
  tabs.forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.tab === name);
  });
  Object.entries(panels).forEach(([panelName, panel]) => {
    const active = panelName === name;
    panel.classList.toggle("is-active", active);
    panel.hidden = !active;
  });
  refreshButton.hidden = !["clips", "performance"].includes(name);
  if (name === "live" && !liveAudio.src) {
    prepareLiveAudio();
  }
  if (name === "live") {
    startLiveStatusPolling();
    startWaveform();
  } else {
    closeLiveAudioStream();
    stopLiveStatusPolling();
    stopWaveform();
  }
  if (name === "language" && !languagePayloadLoaded) {
    loadAndRenderLanguage();
  }
  if (name === "performance") {
    loadAndRenderPerformance({ showLoading: !performancePayloadLoaded });
    startPerformancePolling();
  } else {
    stopPerformancePolling();
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
  const cards = document.createElement("div");
  cards.className = "language-grid";
  cards.append(
    languageCard("Transmissions", String(payload.source_clip_count || 0), "Cached transcript clips"),
    languageCard("Channels", channelSummary(payload.channels || frequency.by_channel || {}), "VHF activity split"),
    languageCard("Busiest hour", busiestHour(frequency.by_hour_pacific || {}), "Pacific time"),
    languageCard("Topic model", topicStatus(topics), "BERTopic / classical fallback"),
  );

  const wordsPanel = languagePanel("Radio words");
  wordsPanel.append(
    termSection("Jargon", terms.semantic_buckets?.communication_markers || []),
    termSection("Movement", terms.semantic_buckets?.movement || []),
    termSection("Places", terms.semantic_buckets?.places || []),
    termSection("N-grams", terms.bigrams || []),
  );

  const entityPanel = languagePanel("Suspected vessels and entities");
  entityPanel.append(entityList(payload.entities || []));

  const topicPanel = languagePanel("3D topic clusters");
  const topicFrame = document.createElement("iframe");
  topicFrame.className = "topic-frame";
  topicFrame.loading = "lazy";
  topicFrame.title = "BERTopic 3D visual clustering";
  topicFrame.src = topics.plot_url || topicClusterFallbackUrl;
  topicPanel.append(topicFrame, topicList(topics.items || []));

  const educationPanel = languagePanel("Maritime radio references");
  educationPanel.append(
    educationGuideList(payload.education_guide || []),
    referenceIndex(payload.education || []),
  );

  lexicalAnalysis.replaceChildren(cards, wordsPanel, entityPanel, topicPanel, educationPanel);
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
  const hostGrid = document.createElement("div");
  hostGrid.className = "performance-host-grid";
  hostGrid.append(...hosts.map((host, index) => performanceHostPanel(host, index)));
  performanceDashboard.replaceChildren(hostGrid);
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
  const memory = host?.memory || {};
  const disks = host?.disks || [];
  const thermal = host?.thermal || {};
  cards.append(
    performanceCard("CPU utilization", cpuUtilizationSummary(host), cpuCaption(host), hostStatus(host, "cpu")),
    performanceCard("Memory", percentLabel(memory.usedPercent), bytesLabel(memory.availableBytes, "available"), memory.status),
    performanceCard("Disk", diskSummary(disks), "Most used filesystem", worstItemStatus(disks)),
    performanceCard("Thermals", thermalSummary(thermal), thermalCaption(thermal), thermal.status),
  );
  panel.append(title, cards);
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

function emptyPerformanceState() {
  const empty = document.createElement("p");
  empty.className = "muted-inline";
  empty.textContent = "No performance snapshot is available.";
  return empty;
}

function cpuUtilizationSummary(host) {
  return percentLabel(host?.cpu?.utilizationPercent);
}

function cpuCaption(host) {
  return `1-minute load average: ${formatLoad(host?.load || {})}; ${host?.cpuCount || "?"} logical CPUs`;
}

function hostStatus(host, key) {
  return host?.[key]?.status || "unknown";
}

function formatLoad(load) {
  if (!Number.isFinite(Number(load.perCpu))) {
    return "Unknown";
  }
  return `${Number(load.perCpu).toFixed(2)}x/core`;
}

function thermalSummary(thermal) {
  const temperature = Number(thermal?.temperatureC);
  if (!Number.isFinite(temperature)) {
    return "Unknown";
  }
  return `${temperature.toFixed(1)} C`;
}

function thermalCaption(thermal) {
  const throttled = thermal?.throttled || "unknown";
  if (throttled === "0x0") {
    return "No throttling reported";
  }
  return `Throttled: ${throttled}`;
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

function bytesLabel(value, suffix) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes)) {
    return suffix ? `Unknown ${suffix}` : "Unknown";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  let amount = bytes;
  let unitIndex = 0;
  while (amount >= 1024 && unitIndex < units.length - 1) {
    amount /= 1024;
    unitIndex += 1;
  }
  return `${amount.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]} ${suffix || ""}`.trim();
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

function languagePanel(titleText) {
  const section = document.createElement("section");
  section.className = "language-panel";
  const title = document.createElement("h3");
  title.textContent = titleText;
  section.append(title);
  return section;
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
      const example = document.createElement("blockquote");
      example.textContent = entity.examples?.[0]?.text || "";
      item.append(title, meta, channels, example);
      const player = renderExamplePlayer(entity.examples?.[0] || {});
      if (player) {
        item.append(player);
      }
      return item;
    }),
  );
  return list;
}

function renderExamplePlayer(example) {
  const audioUrl = audioUrlForClip(example);
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
  if (!topics.length) {
    const empty = document.createElement("p");
    empty.className = "muted-inline";
    empty.textContent = "Topic summaries will appear when the corpus is large enough.";
    list.append(empty);
    return list;
  }
  list.append(
    ...topics.slice(0, 6).map((topic) => {
      const item = document.createElement("article");
      item.className = "topic-card";
      const title = document.createElement("h4");
      title.textContent = `${topic.label || "Topic"} · ${topic.count || 0}`;
      const words = document.createElement("p");
      words.className = "entity-meta";
      words.textContent = (topic.top_words || []).join(", ");
      item.append(title, words);
      return item;
    }),
  );
  return list;
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

function channelSummary(channels) {
  const entries = Object.entries(channels);
  if (!entries.length) {
    return "None";
  }
  return entries
    .sort(([left], [right]) => compareChannels(left, right))
    .map(([channel, count]) => `Ch ${channel}: ${count}`)
    .join("\n");
}

function busiestHour(hours) {
  const entries = Object.entries(hours);
  if (!entries.length) {
    return "None";
  }
  entries.sort((left, right) => Number(right[1] || 0) - Number(left[1] || 0));
  return `${formatHourLabel(entries[0][0])} (${entries[0][1]})`;
}

function formatHourLabel(hourText) {
  const hour = Number(String(hourText || "").split(":")[0]);
  if (!Number.isFinite(hour)) {
    return hourText || "None";
  }
  const suffix = hour >= 12 ? "PM" : "AM";
  const hour12 = hour % 12 || 12;
  return `${hour12} ${suffix}`;
}

function topicStatus(topics) {
  if (!topics?.status || topics.status === "missing") {
    return "Missing";
  }
  if (topics.status === "ok") {
    return `${(topics.items || []).length} topics`;
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
  liveAudio.preload = "none";
  liveAudio.disableRemotePlayback = true;
  liveAudio.setAttribute("controlslist", "nodownload noplaybackrate noremoteplayback");
  liveAudio.setAttribute("disableremoteplayback", "");
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
    systemMediaNote.textContent = systemMediaControlsEnabled
      ? "Live radio may appear in macOS and browser media controls."
      : "Live radio plays in Firefox without publishing system media controls.";
  }
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
        artist: channelLabel(selectedLiveChannel),
        album: "Live radio",
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
  const url = liveStreamUrl();
  liveAudio.crossOrigin = "anonymous";
  liveAudio.src = url;
  liveStatus.textContent = "Ready";
  drawWaitingFrame({ showWaiting: false });
  updateLiveMediaSession("paused");
}

function closeLiveAudioStream() {
  clearTimeout(liveRetryTimer);
  liveRetryTimer = null;
  liveAudio.pause();
  liveAudio.removeAttribute("src");
  liveAudio.load();
  playLiveButton.textContent = "Play";
  liveStatus.textContent = "Ready";
  quietSince = null;
  drawWaitingFrame({ showWaiting: false });
  clearBrowserMediaSession();
}

function toggleLivePlayback() {
  if (!liveAudio.paused) {
    liveAudio.pause();
    return;
  }
  connectLive();
}

async function connectLive() {
  clearTimeout(liveRetryTimer);
  const url = liveAudio.src || withCacheBust(liveStreamUrl());
  liveAudio.crossOrigin = "anonymous";
  if (liveAudio.src !== url) {
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
    await liveAudio.play();
  } catch {
    liveStatus.textContent = "Press play";
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

function liveStreamUrl() {
  const url = rawLiveStreamUrl();
  return withDspProfile(url);
}

function rawLiveStreamUrl() {
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
  return `/api/live/${encodeURIComponent(selectedLiveChannel)}/status`;
}

async function pollLiveStatus() {
  if (panels.live.hidden) {
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

function renderLiveStatus(status) {
  const channel = status?.channel || selectedLiveChannel;
  liveChannel.textContent = channel ? channelLabel(channel) : "Current SDR feed";
  liveFrequency.textContent = status?.frequencyMhz ? `${status.frequencyMhz} MHz` : "";
}

function withCacheBust(url) {
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
  context.lineWidth = isReceiving ? 2.5 * ratio : 1.6 * ratio;
  context.strokeStyle = isReceiving ? "#40e0bf" : "rgba(244, 179, 80, 0.72)";
  context.shadowColor = isReceiving ? "rgba(64, 224, 191, 0.7)" : "rgba(244, 179, 80, 0.35)";
  context.shadowBlur = isReceiving ? 12 * ratio : 8 * ratio;
  context.beginPath();
  for (let index = 0; index < data.length; index += 1) {
    const x = (index / (data.length - 1)) * width;
    const normalized = (data[index] - 128) / 128;
    const idleSweep = Math.sin(index / 18 + performance.now() / 420) * 0.045;
    const y = centerY + (isReceiving ? normalized * height * 0.42 : idleSweep * amplitude * height);
    if (index === 0) {
      context.moveTo(x, y);
    } else {
      context.lineTo(x, y);
    }
  }
  context.stroke();
  context.shadowBlur = 0;
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

function statusText(payload, clips, filteredTotal) {
  if (!filteredTotal) {
    return selectedChannel === "all" ? "No clips yet" : `No clips for ${channelLabel(selectedChannel)} yet`;
  }
  const selectedLabel = selectedChannel === "all" ? "" : `${channelLabel(selectedChannel)} `;
  const pageText =
    clips.length === filteredTotal ? `${clips.length}` : `${clips.length} of ${filteredTotal}`;
  const clipNoun = filteredTotal === 1 ? "clip" : "clips";
  if (payload.source === "live") {
    return `${pageText} ${selectedLabel}${clipNoun} from the live DB`;
  }
  const generated = payload.generated_at ? ` · exported ${formatDateTime(payload.generated_at)}` : "";
  return `${pageText} ${selectedLabel}published ${clipNoun}${generated}`;
}

function filteredClipCount(payload, clips) {
  if (selectedChannel !== "all") {
    const channelCounts = payload.stats?.channel_counts;
    return Number(channelCounts?.[selectedChannel] ?? payload.stats?.filtered_clip_count ?? clips.length);
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
