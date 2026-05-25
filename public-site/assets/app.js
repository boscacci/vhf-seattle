const liveClipUrl = "/api/clips/recent?limit=100";
const manifestUrl = "/public_manifest.json";
const liveChannelsUrl = "/api/live/channels";
const defaultLiveStreamUrl = "/api/live/current.mp3";
const liveDspProfile = window.location.hostname === "vhf-dev.robertboscacci.com" ? "warm_voice" : "";
const liveStatusPollMs = 2000;
const quietTransmissionDelayMs = 5000;
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
const pacificShortTimeFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: pacificTimeZone,
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZoneName: "short",
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

const clipList = document.querySelector("#clips");
const clipStatus = document.querySelector("#clip-status");
const channelFilter = document.querySelector("#channel-filter");
const refreshButton = document.querySelector("#refresh-clips");
const stats = document.querySelector("#stats");
const tabs = [...document.querySelectorAll(".tab")];
const panels = {
  clips: document.querySelector("#panel-clips"),
  live: document.querySelector("#panel-live"),
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

let liveRetryTimer = null;
let liveStatusTimer = null;
let liveStatusAbortController = null;
let lastLiveStatusId = null;
let audioContext = null;
let analyser = null;
let analyserSource = null;
let waveformData = null;
let waveformAnimationId = null;
let quietSince = null;
let selectedChannel = "all";
let selectedLiveChannel = "14";
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

refreshButton.addEventListener("click", () => {
  loadAndRender();
});

channelFilter.addEventListener("change", () => {
  selectedChannel = channelFilter.value;
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

liveAudio.addEventListener("playing", () => {
  liveStatus.textContent = "Streaming";
  playLiveButton.textContent = "Pause";
});

liveAudio.addEventListener("waiting", () => {
  liveStatus.textContent = "Buffering";
});

liveAudio.addEventListener("pause", () => {
  playLiveButton.textContent = "Play";
  liveStatus.textContent = "Paused";
});

liveAudio.addEventListener("error", () => {
  liveStatus.textContent = "Reconnecting";
  scheduleLiveReconnect();
});

liveAudio.addEventListener("ended", () => {
  liveStatus.textContent = "Reconnecting";
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
  if (selectedChannel === "all") {
    return liveClipUrl;
  }
  return `${liveClipUrl}&channel=${encodeURIComponent(selectedChannel)}`;
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

function normalizeLivePayload(payload) {
  const clips = Array.isArray(payload.clips) ? payload.clips : [];
  return {
    source: "live",
    site: fallbackManifest.site,
    stats: {
      clip_count: clips.length,
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
  const visibleClips = filterClipsByChannel(clips);
  renderStats(payload, visibleClips);
  renderClips(visibleClips);
  clipStatus.textContent = statusText(payload, visibleClips, totalAvailableClips(payload, clips));
}

function renderStats(payload, clips) {
  const channelCounts = countBy(clips, (clip) => clip.channel || "?");
  const channelTotal = Object.keys(channelCounts).length;
  const latest = clips[0]?.started_at ? shortTime(clips[0].started_at) : "None";
  const statItems = [
    ["Clips", clips.length],
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
  const options = [
    optionForChannel("all", "All channels"),
    ...channels.map((channel) =>
      optionForChannel(
        channel,
        channelOptionLabel(channel, channelCounts[channel]),
      ),
    ),
  ];
  channelFilter.replaceChildren(...options);
  channelFilter.value = selectedChannel;
}

function channelOptionLabel(channel, count) {
  const clipCount = Number(count || 0);
  if (!clipCount) {
    return channelLabel(channel);
  }
  const noun = clipCount === 1 ? "clip" : "clips";
  return `${channelLabel(channel)} (${clipCount} ${noun})`;
}

function optionForChannel(value, label) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  return option;
}

function filterClipsByChannel(clips) {
  if (selectedChannel === "all") {
    return clips;
  }
  return clips.filter((clip) => clip.channel === selectedChannel);
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

function renderClipCard(clip) {
  const article = document.createElement("article");
  article.className = "clip-card";

  const meta = document.createElement("div");
  meta.className = "clip-meta";
  meta.append(renderPill(channelLabel(clip.channel)), renderPill(formatDateTime(clip.started_at)));
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
    const audio = document.createElement("audio");
    audio.controls = true;
    audio.preload = "metadata";
    audio.src = audioUrl;
    article.append(audio);
  }
  return article;
}

function renderPill(text) {
  const pill = document.createElement("span");
  pill.className = "pill";
  pill.textContent = text;
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
  tabs.forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.tab === name);
  });
  Object.entries(panels).forEach(([panelName, panel]) => {
    const active = panelName === name;
    panel.classList.toggle("is-active", active);
    panel.hidden = !active;
  });
  refreshButton.hidden = name !== "clips";
  if (name === "live" && !liveAudio.src) {
    prepareLiveAudio();
  }
  if (name === "live") {
    startLiveStatusPolling();
    startWaveform();
  } else {
    stopLiveStatusPolling();
    stopWaveform();
  }
}

function prepareLiveAudio() {
  const url = liveStreamUrl();
  liveAudio.crossOrigin = "anonymous";
  liveAudio.src = url;
  liveStatus.textContent = "Ready";
  drawWaitingFrame({ showWaiting: false });
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

function statusText(payload, clips, totalAvailable) {
  if (!clips.length) {
    return selectedChannel === "all" ? "No clips yet" : `No clips for ${channelLabel(selectedChannel)} yet`;
  }
  const selectedLabel = selectedChannel === "all" ? "" : `${channelLabel(selectedChannel)} `;
  const availableText =
    selectedChannel === "all" && totalAvailable !== clips.length ? ` of ${totalAvailable}` : "";
  const clipNoun = clips.length === 1 ? "clip" : "clips";
  if (payload.source === "live") {
    return `${clips.length}${availableText} ${selectedLabel}${clipNoun} from the live DB`;
  }
  const generated = payload.generated_at ? ` · exported ${formatDateTime(payload.generated_at)}` : "";
  return `${clips.length}${availableText} ${selectedLabel}published ${clipNoun}${generated}`;
}

function totalAvailableClips(payload, clips) {
  const channelCounts = payload.stats?.channel_counts;
  if (!channelCounts) {
    return clips.length;
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
prepareLiveAudio();
loadAndRender();
