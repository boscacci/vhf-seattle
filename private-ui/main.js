const clipList = document.querySelector("#clip-list");
const clipStatus = document.querySelector("#clip-status");
const refreshButton = document.querySelector("#refresh-clips");

refreshButton.addEventListener("click", () => {
  loadClips();
});

async function loadClips() {
  clipStatus.textContent = "Loading clips...";
  const response = await fetch("/api/clips/recent?limit=30", { cache: "no-store" });
  if (!response.ok) {
    clipStatus.textContent = "Clip feed unavailable";
    clipList.replaceChildren();
    return;
  }
  const payload = await response.json();
  const clips = Array.isArray(payload.clips) ? payload.clips : [];
  clipStatus.textContent = clips.length ? `${clips.length} clips` : "No transcribed clips yet";
  clipList.replaceChildren(...clips.map(renderClipCard));
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => {
    const escapes = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" };
    return escapes[char];
  });
}

function renderClipCard(clip) {
  const article = document.createElement("article");
  article.className = "clip-card";

  const meta = document.createElement("div");
  meta.className = "clip-meta";
  meta.append(
    renderPill(`VHF ${clip.channel || "?"}`),
    renderPill(formatDateTime(clip.started_at)),
  );
  if (clip.duration_seconds) {
    meta.append(renderPill(`${Math.round(clip.duration_seconds)}s`));
  }

  const transcript = document.createElement("blockquote");
  transcript.textContent = clip.transcript || "";

  const audio = document.createElement("audio");
  audio.controls = true;
  audio.preload = "none";
  audio.src = clip.playback_url || "";

  article.append(meta, transcript, audio);
  return article;
}

function renderPill(text) {
  const pill = document.createElement("span");
  pill.className = "pill";
  pill.textContent = text;
  return pill;
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
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

loadClips();
