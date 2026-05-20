const manifestUrl = "/public_manifest.json";

const fallbackManifest = {
  site: {
    title: "Talking Boats",
    subtitle: "Reviewed marine-radio moments from Elliott Bay.",
  },
  stats: {
    clip_count: 0,
    channel_counts: {},
    vessel_type_counts: {},
  },
  clips: [],
};

const bounds = {
  minLat: 47.55,
  maxLat: 47.68,
  minLon: -122.43,
  maxLon: -122.29,
};

async function loadManifest() {
  try {
    const response = await fetch(manifestUrl, { cache: "no-store" });
    if (!response.ok) throw new Error(`manifest HTTP ${response.status}`);
    return await response.json();
  } catch {
    return fallbackManifest;
  }
}

function renderSite(manifest) {
  document.title = manifest.site?.title || "Talking Boats";
  document.querySelector("#site-title").textContent = manifest.site?.title || "Talking Boats";
  document.querySelector("#site-subtitle").textContent =
    manifest.site?.subtitle || "Reviewed marine-radio moments from Elliott Bay.";
  renderStats(manifest);
  renderMap(manifest.clips || []);
  renderClips(manifest.clips || []);
}

function renderStats(manifest) {
  const stats = manifest.stats || {};
  const channelCounts = stats.channel_counts || {};
  const vesselTypeCounts = stats.vessel_type_counts || {};
  const statItems = [
    ["Reviewed Clips", stats.clip_count ?? (manifest.clips || []).length],
    ["VHF 68", channelCounts["68"] || 0],
    ["VHF 14", channelCounts["14"] || 0],
    ["Vessel Types", Object.keys(vesselTypeCounts).length],
  ];

  document.querySelector("#stats").innerHTML = statItems
    .map(
      ([label, value]) => `
        <div class="stat">
          <dt>${escapeHtml(label)}</dt>
          <dd>${escapeHtml(String(value))}</dd>
        </div>
      `,
    )
    .join("");
}

function renderMap(clips) {
  const map = document.querySelector("#bay-map");
  map.querySelectorAll(".map-point").forEach((point) => point.remove());

  clips
    .filter((clip) => clip.ais_context?.lat && clip.ais_context?.lon)
    .forEach((clip) => {
      const point = document.createElement("button");
      point.type = "button";
      point.className = `map-point ${clip.channel === "14" ? "business" : "fun"}`;
      point.style.left = `${projectLon(clip.ais_context.lon)}%`;
      point.style.top = `${projectLat(clip.ais_context.lat)}%`;
      point.title = clip.public_title;
      point.addEventListener("click", () => {
        document.querySelector(`[data-clip-id="${cssEscape(clip.id)}"]`)?.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
      });
      map.appendChild(point);
    });
}

function renderClips(clips) {
  const container = document.querySelector("#clips");
  if (!clips.length) {
    container.innerHTML = `<div class="empty">No reviewed public clips have been exported yet.</div>`;
    return;
  }

  container.innerHTML = clips
    .map((clip) => {
      const audio = clip.audio_public_filename
        ? `<audio controls preload="none" src="/clips/${encodeURIComponent(clip.audio_public_filename)}"></audio>`
        : "";
      const transcript = clip.transcript_public
        ? `<blockquote>${escapeHtml(clip.transcript_public)}</blockquote>`
        : "";
      return `
        <article class="clip-card" data-clip-id="${escapeHtml(clip.id)}">
          <div class="clip-meta">
            <span class="pill">VHF ${escapeHtml(clip.channel)}</span>
            <span class="pill">${escapeHtml(formatDate(clip.started_at))}</span>
            ${clip.duration_seconds ? `<span class="pill">${Math.round(clip.duration_seconds)}s</span>` : ""}
          </div>
          <h3>${escapeHtml(clip.public_title)}</h3>
          ${transcript}
          ${renderVessels(clip.vessel_context || [])}
          ${audio}
        </article>
      `;
    })
    .join("");
}

function renderVessels(vessels) {
  if (!vessels.length) return "";
  const labels = vessels
    .slice(0, 3)
    .map((vessel) => vessel.name || vessel.mmsi || "Unknown vessel")
    .join(", ");
  return `<p class="clip-meta">Nearby AIS: ${escapeHtml(labels)}</p>`;
}

function projectLon(lon) {
  return ((Number(lon) - bounds.minLon) / (bounds.maxLon - bounds.minLon)) * 100;
}

function projectLat(lat) {
  return (1 - (Number(lat) - bounds.minLat) / (bounds.maxLat - bounds.minLat)) * 100;
}

function formatDate(value) {
  if (!value) return "Unknown time";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => {
    const escapes = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" };
    return escapes[char];
  });
}

function cssEscape(value) {
  if (window.CSS?.escape) return window.CSS.escape(value);
  return value.replace(/[^a-zA-Z0-9_-]/g, "\\$&");
}

renderSite(await loadManifest());
