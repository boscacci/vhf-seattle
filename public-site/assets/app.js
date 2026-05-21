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
  ais_tracks: [],
};

const bounds = {
  minLat: 47.565,
  maxLat: 47.665,
  minLon: -122.44,
  maxLon: -122.315,
};

const baseBounds = { ...bounds };
const oceanBasemap = {
  originX: -20037508.342789244,
  originY: 20037508.342789244,
  worldSpanMeters: 40075016.68557849,
  url(level, row, col) {
    return `https://services.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/${level}/${row}/${col}`;
  },
};

let selectedClipId = null;
let currentClips = [];
let currentTracks = [];
let timelineFrames = [];
let timelineIndex = 0;
let playbackTimer = null;
let mapZoomStep = 2;
let resizeTimer = null;

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
  currentClips = manifest.clips || [];
  currentTracks = manifest.ais_tracks || [];
  timelineFrames = collectTimelineFrames(currentTracks);
  document.title = manifest.site?.title || "Talking Boats";
  document.querySelector("#site-title").textContent = manifest.site?.title || "Talking Boats";
  document.querySelector("#site-subtitle").textContent =
    manifest.site?.subtitle || "Reviewed marine-radio moments from Elliott Bay.";
  renderStats(manifest);
  renderClips(currentClips);
  setupControls();
  renderMap();
  window.addEventListener("resize", () => {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(renderMap, 120);
  });
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

function renderMap() {
  const map = document.querySelector("#bay-map");
  const tooltip = document.querySelector("#map-tooltip");
  const plottedClips = currentClips.filter((clip) => clip.ais_context?.lat && clip.ais_context?.lon);
  renderChartTiles(true);
  renderTrackLayer(currentTracks);
  renderTrackPlayback(timelineIndex);
  map.querySelectorAll(".map-point").forEach((point) => point.remove());

  plottedClips.forEach((clip, index) => {
    const point = document.createElement("button");
    point.type = "button";
    point.className = `map-point ${clip.channel === "14" ? "business" : "fun"}`;
    point.style.left = `${projectLon(clip.ais_context.lon)}%`;
    point.style.top = `${projectLat(clip.ais_context.lat)}%`;
    const offset = markerOffset(index);
    point.style.setProperty("--point-offset-x", `${offset.x}px`);
    point.style.setProperty("--point-offset-y", `${offset.y}px`);
    point.textContent = String(index + 1);
    point.dataset.clipId = clip.id;
    point.setAttribute("aria-label", `${clip.public_title}, VHF ${clip.channel}`);
    point.addEventListener("mouseenter", () => showMapPreview(clip, index, point, tooltip));
    point.addEventListener("focus", () => showMapPreview(clip, index, point, tooltip));
    point.addEventListener("mouseleave", () => hideMapPreview(clip, tooltip));
    point.addEventListener("blur", () => hideMapPreview(clip, tooltip));
    point.addEventListener("click", () => selectClipFromMap(clip, index));
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
    .map((clip, index) => {
      const audio = clip.audio_public_filename
        ? `<audio controls preload="none" src="/clips/${encodeURIComponent(clip.audio_public_filename)}"></audio>`
        : "";
      const transcript = clip.transcript_public
        ? `<blockquote>${escapeHtml(clip.transcript_public)}</blockquote>`
        : "";
      return `
        <article class="clip-card" id="${escapeHtml(clipDomId(clip.id))}" data-clip-id="${escapeHtml(clip.id)}" tabindex="-1">
          <div class="clip-meta">
            <span class="pill clip-index">Map ${index + 1}</span>
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
  const visibleBounds = currentBounds();
  const minX = lonToMercatorX(visibleBounds.minLon);
  const maxX = lonToMercatorX(visibleBounds.maxLon);
  return ((lonToMercatorX(Number(lon)) - minX) / (maxX - minX)) * 100;
}

function projectLat(lat) {
  const visibleBounds = currentBounds();
  const minY = latToMercatorY(visibleBounds.minLat);
  const maxY = latToMercatorY(visibleBounds.maxLat);
  return ((maxY - latToMercatorY(Number(lat))) / (maxY - minY)) * 100;
}

function renderChartTiles(force = false) {
  const tileLayer = document.querySelector("#chart-tile-layer");
  const level = currentChartLevel();
  if (!tileLayer) return;
  if (!force && tileLayer.dataset.renderedFor === String(level)) return;

  const visibleBounds = currentBounds();
  const matrixSize = 2 ** level;
  const tileSpan = oceanBasemap.worldSpanMeters / matrixSize;
  const minX = lonToMercatorX(visibleBounds.minLon);
  const maxX = lonToMercatorX(visibleBounds.maxLon);
  const minY = latToMercatorY(visibleBounds.minLat);
  const maxY = latToMercatorY(visibleBounds.maxLat);
  const minCol = clampTile(Math.floor((minX - oceanBasemap.originX) / tileSpan), matrixSize);
  const maxCol = clampTile(Math.floor((maxX - oceanBasemap.originX) / tileSpan), matrixSize);
  const minRow = clampTile(Math.floor((oceanBasemap.originY - maxY) / tileSpan), matrixSize);
  const maxRow = clampTile(Math.floor((oceanBasemap.originY - minY) / tileSpan), matrixSize);

  const tiles = [];
  for (let row = minRow; row <= maxRow; row += 1) {
    for (let col = minCol; col <= maxCol; col += 1) {
      const tileMinX = oceanBasemap.originX + col * tileSpan;
      const tileMaxX = oceanBasemap.originX + (col + 1) * tileSpan;
      const tileMaxY = oceanBasemap.originY - row * tileSpan;
      const tileMinY = oceanBasemap.originY - (row + 1) * tileSpan;
      tiles.push(`
        <img
          src="${oceanBasemap.url(level, row, col)}"
          alt=""
          loading="lazy"
          style="
            left: ${((tileMinX - minX) / (maxX - minX)) * 100}%;
            top: ${((maxY - tileMaxY) / (maxY - minY)) * 100}%;
            width: ${((tileMaxX - tileMinX) / (maxX - minX)) * 100}%;
            height: ${((tileMaxY - tileMinY) / (maxY - minY)) * 100}%;
          "
        />
      `);
    }
  }

  tileLayer.innerHTML = tiles.join("");
  tileLayer.dataset.renderedFor = String(level);
}

function currentBounds() {
  const zoomFactor = 2 ** (mapZoomStep - 2);
  const map = document.querySelector("#bay-map");
  const aspectRatio = map?.clientWidth && map?.clientHeight ? map.clientWidth / map.clientHeight : 16 / 9;

  const minX = lonToMercatorX(baseBounds.minLon);
  const maxX = lonToMercatorX(baseBounds.maxLon);
  const minY = latToMercatorY(baseBounds.minLat);
  const maxY = latToMercatorY(baseBounds.maxLat);
  const centerX = (minX + maxX) / 2;
  const centerY = (minY + maxY) / 2;
  const baseWidth = maxX - minX;
  const baseHeight = maxY - minY;
  const width = Math.max(baseWidth, baseHeight * aspectRatio) / zoomFactor;
  const height = Math.max(baseHeight, baseWidth / aspectRatio) / zoomFactor;

  return {
    minLat: mercatorYToLat(centerY - height / 2),
    maxLat: mercatorYToLat(centerY + height / 2),
    minLon: mercatorXToLon(centerX - width / 2),
    maxLon: mercatorXToLon(centerX + width / 2),
  };
}

function currentChartLevel() {
  return Math.max(10, Math.min(14, 10 + mapZoomStep));
}

function setupControls() {
  const zoomIn = document.querySelector("#zoom-in");
  const zoomOut = document.querySelector("#zoom-out");
  const playButton = document.querySelector("#playback-toggle");
  const slider = document.querySelector("#time-slider");

  zoomIn.addEventListener("click", () => setMapZoom(mapZoomStep + 1));
  zoomOut.addEventListener("click", () => setMapZoom(mapZoomStep - 1));
  playButton.addEventListener("click", togglePlayback);
  slider.addEventListener("input", () => {
    stopPlayback();
    timelineIndex = Number(slider.value);
    renderTrackPlayback(timelineIndex);
  });

  slider.max = String(Math.max(timelineFrames.length - 1, 0));
  slider.disabled = timelineFrames.length === 0;
  playButton.disabled = timelineFrames.length === 0;
  updateZoomControls();
  updateTimeControls();
}

function setMapZoom(nextStep) {
  mapZoomStep = Math.max(0, Math.min(4, nextStep));
  updateZoomControls();
  renderMap();
}

function updateZoomControls() {
  document.querySelector("#zoom-out").disabled = mapZoomStep <= 0;
  document.querySelector("#zoom-in").disabled = mapZoomStep >= 4;
  document.querySelector("#zoom-label").textContent = `Chart ${currentChartLevel()}`;
}

function togglePlayback() {
  if (playbackTimer) {
    stopPlayback();
    return;
  }
  document.querySelector("#playback-toggle").textContent = "Pause AIS";
  playbackTimer = window.setInterval(() => {
    timelineIndex = (timelineIndex + 1) % Math.max(timelineFrames.length, 1);
    renderTrackPlayback(timelineIndex);
  }, 850);
}

function stopPlayback() {
  if (playbackTimer) window.clearInterval(playbackTimer);
  playbackTimer = null;
  document.querySelector("#playback-toggle").textContent = "Play AIS";
}

function updateTimeControls() {
  const slider = document.querySelector("#time-slider");
  const label = document.querySelector("#time-label");
  slider.value = String(timelineIndex);
  label.textContent = timelineFrames[timelineIndex]
    ? formatDateTime(timelineFrames[timelineIndex])
    : "No AIS track";
}

function collectTimelineFrames(tracks) {
  const frames = new Set();
  tracks.forEach((track) => {
    (track.points || []).forEach((point) => {
      if (point.observed_at) frames.add(point.observed_at);
    });
  });
  return Array.from(frames).sort();
}

function renderTrackLayer(tracks) {
  const trackLayer = document.querySelector("#track-layer");
  trackLayer.innerHTML = tracks
    .map((track) => {
      const points = (track.points || [])
        .map((point) => `${projectLon(point.lon).toFixed(2)},${projectLat(point.lat).toFixed(2)}`)
        .join(" ");
      if (!points) return "";
      const className = track.channel_hint === "68" ? "track-line fun" : "track-line business";
      return `<polyline class="${className}" points="${points}" />`;
    })
    .join("");
}

function renderTrackPlayback(frameIndex) {
  const vessels = document.querySelector("#playback-vessels");
  const frameTime = timelineFrames[frameIndex];
  if (!frameTime) {
    vessels.innerHTML = "";
    updateTimeControls();
    return;
  }

  vessels.innerHTML = currentTracks
    .map((track) => {
      const point = positionAtTime(track.points || [], frameTime);
      if (!point) return "";
      const left = projectLon(point.lon);
      const top = projectLat(point.lat);
      if (left < -5 || left > 105 || top < -5 || top > 105) return "";
      return `
        <div
          class="playback-vessel ${track.channel_hint === "68" ? "fun" : "business"}"
          style="left: ${left}%; top: ${top}%;"
          title="${escapeHtml(track.name)}"
        >
          <span>${escapeHtml(track.name)}</span>
        </div>
      `;
    })
    .join("");
  updateTimeControls();
}

function positionAtTime(points, frameTime) {
  const target = Date.parse(frameTime);
  const sorted = points
    .filter((point) => point.observed_at)
    .slice()
    .sort((a, b) => Date.parse(a.observed_at) - Date.parse(b.observed_at));
  if (!sorted.length) return null;
  if (target <= Date.parse(sorted[0].observed_at)) return sorted[0];
  if (target >= Date.parse(sorted[sorted.length - 1].observed_at)) return sorted[sorted.length - 1];

  for (let index = 1; index < sorted.length; index += 1) {
    const previous = sorted[index - 1];
    const next = sorted[index];
    const previousTime = Date.parse(previous.observed_at);
    const nextTime = Date.parse(next.observed_at);
    if (target <= nextTime) {
      const fraction = (target - previousTime) / (nextTime - previousTime);
      return {
        lat: Number(previous.lat) + (Number(next.lat) - Number(previous.lat)) * fraction,
        lon: Number(previous.lon) + (Number(next.lon) - Number(previous.lon)) * fraction,
      };
    }
  }
  return sorted[sorted.length - 1];
}

function showMapPreview(clip, index, point, tooltip) {
  setClipHover(clip.id, true);
  tooltip.hidden = false;
  tooltip.innerHTML = `
    <strong>Map ${index + 1}: ${escapeHtml(clip.public_title)}</strong>
    <span>VHF ${escapeHtml(clip.channel)} · ${escapeHtml(formatDate(clip.started_at))}</span>
    ${renderTooltipVessel(clip)}
  `;
  placeTooltip(point, tooltip);
}

function hideMapPreview(clip, tooltip) {
  setClipHover(clip.id, false);
  tooltip.hidden = true;
}

function selectClipFromMap(clip, index) {
  selectedClipId = clip.id;
  document.querySelectorAll(".clip-card.is-selected").forEach((card) => {
    card.classList.remove("is-selected");
  });
  document.querySelectorAll(".map-point.is-selected").forEach((point) => {
    point.classList.remove("is-selected");
  });

  const card = document.querySelector(`.clip-card[data-clip-id="${cssEscape(clip.id)}"]`);
  const point = document.querySelector(`.map-point[data-clip-id="${cssEscape(clip.id)}"]`);
  card?.classList.add("is-selected");
  point?.classList.add("is-selected");
  document.querySelector("#map-status").textContent =
    `Selected map point ${index + 1}: ${clip.public_title}`;
  card?.scrollIntoView({ behavior: "smooth", block: "center" });
  window.setTimeout(() => card?.focus({ preventScroll: true }), 280);
}

function setClipHover(clipId, enabled) {
  document
    .querySelector(`.clip-card[data-clip-id="${cssEscape(clipId)}"]`)
    ?.classList.toggle("is-hovered", enabled);
}

function placeTooltip(point, tooltip) {
  const map = document.querySelector("#bay-map");
  const mapBox = map.getBoundingClientRect();
  const pointBox = point.getBoundingClientRect();
  const left = pointBox.left - mapBox.left;
  const top = pointBox.top - mapBox.top;
  tooltip.style.left = `${Math.min(Math.max(left + 18, 12), mapBox.width - 260)}px`;
  tooltip.style.top = `${Math.max(top - 22, 12)}px`;
}

function renderTooltipVessel(clip) {
  const vessel = clip.vessel_context?.[0];
  if (!vessel) return "";
  const name = vessel.name || vessel.mmsi || "Nearby AIS";
  const distance = vessel.distance_nm ? ` · ${vessel.distance_nm} nm` : "";
  return `<span>${escapeHtml(name)}${escapeHtml(distance)}</span>`;
}

function markerOffset(index) {
  const offsets = [
    { x: 0, y: 0 },
    { x: 18, y: -12 },
    { x: -18, y: -10 },
    { x: 16, y: 14 },
    { x: -16, y: 14 },
    { x: 0, y: -22 },
  ];
  return offsets[index % offsets.length];
}

function lonToMercatorX(lon) {
  return 6378137 * (Number(lon) * Math.PI) / 180;
}

function mercatorXToLon(x) {
  return (Number(x) / 6378137) * (180 / Math.PI);
}

function latToMercatorY(lat) {
  const boundedLat = Math.max(Math.min(Number(lat), 85.05112878), -85.05112878);
  const radians = (boundedLat * Math.PI) / 180;
  return 6378137 * Math.log(Math.tan(Math.PI / 4 + radians / 2));
}

function mercatorYToLat(y) {
  return (Math.atan(Math.sinh(Number(y) / 6378137)) * 180) / Math.PI;
}

function clampTile(value, max) {
  return Math.max(0, Math.min(max - 1, value));
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

function formatDateTime(value) {
  if (!value) return "Unknown time";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
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

function clipDomId(clipId) {
  return `clip-${clipId}`;
}

renderSite(await loadManifest());
