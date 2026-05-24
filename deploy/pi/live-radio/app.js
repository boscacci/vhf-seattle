const defaults = {
  label: "VHF 68",
  frequencyMhz: "156.425",
  streamPort: 8000,
  mountPath: "/talkingboats-live.mp3",
  streamUrl: "",
  transcriptUrl: "",
  retuneUrl: "",
  activeChannelId: "",
  channels: [],
};

const config = {
  ...defaults,
  ...(window.TALKINGBOATS_LIVE_RADIO || {}),
};

const player = document.querySelector("#live-player");
const statusBadge = document.querySelector("#stream-state");
const channelLabel = document.querySelector("#channel-label");
const frequency = document.querySelector("#frequency");
const captionPanel = document.querySelector("#caption-panel");
const captionState = document.querySelector("#caption-state");
const captionList = document.querySelector("#caption-list");
const channelMenu = document.querySelector("#channel-menu");
const channelSelect = document.querySelector("#channel-select");
const channelStatus = document.querySelector("#channel-status");

const mountPath = config.mountPath.startsWith("/") ? config.mountPath : `/${config.mountPath}`;
const streamUrl =
  config.streamUrl ||
  `${window.location.protocol}//${window.location.hostname}:${config.streamPort}${mountPath}`;

player.src = cacheBustStreamUrl();
channelLabel.textContent = config.label;
frequency.textContent = config.frequencyMhz;

if (Array.isArray(config.channels) && config.channels.length) {
  channelMenu.hidden = false;
  renderChannelMenu(config.channels);
}

function setState(state, label) {
  statusBadge.dataset.state = state;
  statusBadge.textContent = label;
}

player.addEventListener("playing", () => setState("live", "Live"));
player.addEventListener("waiting", () => setState("connecting", "Buffering"));
player.addEventListener("stalled", () => setState("connecting", "Buffering"));
player.addEventListener("pause", () => setState("idle", "Paused"));
player.addEventListener("error", () => setState("error", "Stream unavailable"));

if (config.transcriptUrl) {
  captionPanel.hidden = false;
  pollTranscript();
  window.setInterval(pollTranscript, 5000);
}

async function pollTranscript() {
  try {
    const response = await fetch(config.transcriptUrl, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    renderTranscript(await response.json());
  } catch {
    captionState.textContent = "Captions unavailable";
    captionState.dataset.state = "error";
  }
}

function renderTranscript(payload) {
  const entries = Array.isArray(payload.entries) ? payload.entries.slice(-4) : [];
  captionState.textContent = entries.length ? "Captions live" : "Listening";
  captionState.dataset.state = payload.status || "running";
  captionList.replaceChildren();
  for (const entry of entries) {
    const item = document.createElement("li");
    const time = document.createElement("time");
    const text = document.createElement("span");
    time.dateTime = entry.ended_at || "";
    time.textContent = formatCaptionTime(entry.ended_at);
    text.textContent = entry.text || "";
    item.append(time, text);
    captionList.append(item);
  }
}

function renderChannelMenu(channels) {
  channelSelect.replaceChildren();
  for (const channel of channels) {
    const option = document.createElement("option");
    option.value = channel.id;
    option.textContent = `${channel.channel} · ${channel.label}`;
    option.dataset.frequencyMhz = channel.frequencyMhz;
    option.dataset.label = channel.label;
    channelSelect.append(option);
  }
  channelSelect.value = config.activeChannelId || channels[0].id;
  updateSelectedChannelDisplay();
  channelSelect.addEventListener("change", () => {
    retuneChannel(channelSelect.value);
  });
}

function updateSelectedChannelDisplay() {
  const selected = channelSelect.selectedOptions[0];
  if (!selected) {
    return;
  }
  const selectedFrequency = selected.dataset.frequencyMhz || "";
  const selectedLabel = selected.dataset.label || selected.textContent;
  channelStatus.textContent = selected.value === config.activeChannelId ? "Current receiver" : "";
  frequency.textContent = selectedFrequency || frequency.textContent;
  channelLabel.textContent = selectedLabel || channelLabel.textContent;
}

async function retuneChannel(channelId) {
  if (!config.retuneUrl || !channelId) {
    return;
  }
  if (channelId === config.activeChannelId) {
    updateSelectedChannelDisplay();
    return;
  }
  const previousChannelId = config.activeChannelId;
  channelStatus.textContent = "Tuning...";
  channelSelect.disabled = true;
  setState("connecting", "Tuning");
  try {
    const response = await fetch(config.retuneUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: channelId }),
    });
    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }
    const payload = await response.json();
    config.activeChannelId = payload.activeChannelId || channelId;
    channelSelect.value = config.activeChannelId;
    if (payload.label) {
      channelLabel.textContent = payload.label;
    }
    if (payload.frequencyMhz) {
      frequency.textContent = payload.frequencyMhz;
    }
    channelStatus.textContent = "Switching stream...";
    const started = await reloadAndPlay();
    channelStatus.textContent = started ? "Streaming" : "Switched - tap audio";
    pollTranscript();
  } catch (error) {
    channelSelect.value = previousChannelId;
    updateSelectedChannelDisplay();
    channelStatus.textContent = error.message || "Retune failed";
    setState("error", "Retune failed");
  } finally {
    channelSelect.disabled = false;
  }
}

async function reloadAndPlay() {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    player.pause();
    player.src = cacheBustStreamUrl();
    player.load();
    if (await playCurrentStream()) {
      return true;
    }
    if (attempt < 2) {
      await sleep(900);
    }
  }
  setState("blocked", "Tap audio control");
  return false;
}

async function playCurrentStream() {
  try {
    await Promise.race([
      player.play(),
      sleep(2500).then(() => {
        throw new Error("playback start timed out");
      }),
    ]);
    return true;
  } catch {
    return false;
  }
}

function cacheBustStreamUrl() {
  const separator = streamUrl.includes("?") ? "&" : "?";
  return `${streamUrl}${separator}stream-version=${Date.now()}`;
}

function sleep(milliseconds) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, milliseconds);
  });
}

async function readErrorMessage(response) {
  try {
    const payload = await response.json();
    return payload.detail || "Retune failed";
  } catch {
    return "Retune failed";
  }
}

function formatCaptionTime(value) {
  if (!value) {
    return "--:--";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--:--";
  }
  return new Intl.DateTimeFormat([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}
