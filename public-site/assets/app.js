const liveClipUrl = "/api/clips/recent?limit=30";
const manifestUrl = "/public_manifest.json";

const fallbackManifest = {
  site: {
    title: "Talking Boats",
    subtitle: "Fresh transcribed marine-radio audio from the receiver.",
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
const refreshButton = document.querySelector("#refresh-clips");
const stats = document.querySelector("#stats");

refreshButton.addEventListener("click", () => {
  loadAndRender();
});

async function loadAndRender() {
  clipStatus.textContent = "Loading clips...";
  const payload = await loadClipPayload();
  renderSite(payload);
}

async function loadClipPayload() {
  try {
    const response = await fetch(liveClipUrl, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`live clip HTTP ${response.status}`);
    }
    const payload = await response.json();
    return normalizeLivePayload(payload);
  } catch {
    return loadStaticManifest();
  }
}

async function loadStaticManifest() {
  try {
    const response = await fetch(manifestUrl, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`manifest HTTP ${response.status}`);
    }
    return normalizeStaticManifest(await response.json());
  } catch {
    return normalizeStaticManifest(fallbackManifest);
  }
}

function normalizeLivePayload(payload) {
  const clips = Array.isArray(payload.clips) ? payload.clips : [];
  return {
    source: "live",
    site: fallbackManifest.site,
    generated_at: new Date().toISOString(),
    clips: clips.map((clip) => ({
      id: clip.key || `${clip.channel}-${clip.started_at}`,
      public_title: titleForClip(clip),
      channel: clip.channel || "?",
      started_at: clip.started_at,
      ended_at: clip.ended_at,
      duration_seconds: clip.duration_seconds,
      transcript_public: clip.transcript || "",
      playback_url: clip.playback_url || "",
      playback_expires_in_seconds: clip.playback_expires_in_seconds,
    })),
  };
}

function normalizeStaticManifest(payload) {
  const clips = Array.isArray(payload.clips) ? payload.clips : [];
  return {
    source: "static",
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
  document.title = payload.site?.title || fallbackManifest.site.title;
  document.querySelector("#site-title").textContent = payload.site?.title || fallbackManifest.site.title;
  document.querySelector("#site-subtitle").textContent =
    payload.site?.subtitle || fallbackManifest.site.subtitle;
  renderStats(payload);
  renderClips(clips);
  clipStatus.textContent = statusText(payload, clips);
}

function renderStats(payload) {
  const clips = payload.clips || [];
  const channelCounts = countBy(clips, (clip) => clip.channel || "?");
  const latest = clips[0]?.started_at ? formatDateTime(clips[0].started_at) : "None yet";
  const statItems = [
    ["Clips", payload.stats?.clip_count ?? clips.length],
    ["Channels", Object.keys(payload.stats?.channel_counts || channelCounts).length],
    ["Latest", latest],
    ["Source", payload.source === "live" ? "Live DB" : "Static"],
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
  meta.append(renderPill(`VHF ${clip.channel || "?"}`), renderPill(formatDateTime(clip.started_at)));
  if (clip.duration_seconds) {
    meta.append(renderPill(`${Math.round(Number(clip.duration_seconds))}s`));
  }

  const title = document.createElement("h3");
  title.textContent = clip.public_title || titleForClip(clip);

  const transcript = document.createElement("blockquote");
  transcript.textContent = clip.transcript_public || "";

  const audioUrl = audioUrlForClip(clip);
  article.append(meta, title, transcript);
  if (audioUrl) {
    const audio = document.createElement("audio");
    audio.controls = true;
    audio.preload = "none";
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
  const channel = clip.channel || "?";
  const date = formatDateTime(clip.started_at);
  return `VHF ${channel} - ${date}`;
}

function statusText(payload, clips) {
  if (!clips.length) {
    return "No clips yet";
  }
  if (payload.source === "live") {
    return `${clips.length} recent live clips`;
  }
  const generated = payload.generated_at ? `, exported ${formatDateTime(payload.generated_at)}` : "";
  return `${clips.length} static clips${generated}`;
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
  return new Intl.DateTimeFormat([], {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

loadAndRender();
