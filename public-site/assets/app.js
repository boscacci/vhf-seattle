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
  minLat: 47.565,
  maxLat: 47.665,
  minLon: -122.44,
  maxLon: -122.315,
};

const noaaChart = {
  level: 12,
  tileSize: 256,
  originX: -20037508.342787,
  originY: 20037508.342787,
  worldSpanMeters: 40075016.685574,
  matrixWidth: 16385,
  matrixHeight: 12105,
  url(level, row, col) {
    return [
      "https://gis.charttools.noaa.gov/arcgis/rest/services",
      "MarineChart_Services/NOAACharts/MapServer/WMTS/tile/1.0.0",
      `MarineChart_Services_NOAACharts/default/default028mm/${level}/${row}/${col}.png`,
    ].join("/");
  },
};

let selectedClipId = null;

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
  renderClips(manifest.clips || []);
  renderMap(manifest.clips || []);
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
  const tooltip = document.querySelector("#map-tooltip");
  const plottedClips = clips.filter((clip) => clip.ais_context?.lat && clip.ais_context?.lon);
  renderChartTiles();
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
  const minX = lonToMercatorX(bounds.minLon);
  const maxX = lonToMercatorX(bounds.maxLon);
  return ((lonToMercatorX(Number(lon)) - minX) / (maxX - minX)) * 100;
}

function projectLat(lat) {
  const minY = latToMercatorY(bounds.minLat);
  const maxY = latToMercatorY(bounds.maxLat);
  return ((maxY - latToMercatorY(Number(lat))) / (maxY - minY)) * 100;
}

function renderChartTiles() {
  const tileLayer = document.querySelector("#chart-tile-layer");
  if (!tileLayer || tileLayer.dataset.rendered === "true") return;

  const level = noaaChart.level;
  const tileSpan = noaaChart.worldSpanMeters / noaaChart.matrixWidth;
  const minX = lonToMercatorX(bounds.minLon);
  const maxX = lonToMercatorX(bounds.maxLon);
  const minY = latToMercatorY(bounds.minLat);
  const maxY = latToMercatorY(bounds.maxLat);
  const minCol = clampTile(Math.floor((minX - noaaChart.originX) / tileSpan), noaaChart.matrixWidth);
  const maxCol = clampTile(Math.floor((maxX - noaaChart.originX) / tileSpan), noaaChart.matrixWidth);
  const minRow = clampTile(Math.floor((noaaChart.originY - maxY) / tileSpan), noaaChart.matrixHeight);
  const maxRow = clampTile(Math.floor((noaaChart.originY - minY) / tileSpan), noaaChart.matrixHeight);

  const tiles = [];
  for (let row = minRow; row <= maxRow; row += 1) {
    for (let col = minCol; col <= maxCol; col += 1) {
      const tileMinX = noaaChart.originX + col * tileSpan;
      const tileMaxX = noaaChart.originX + (col + 1) * tileSpan;
      const tileMaxY = noaaChart.originY - row * tileSpan;
      const tileMinY = noaaChart.originY - (row + 1) * tileSpan;
      tiles.push(`
        <img
          src="${noaaChart.url(level, row, col)}"
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
  tileLayer.dataset.rendered = "true";
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
  if (selectedClipId !== clip.id) tooltip.hidden = true;
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

function latToMercatorY(lat) {
  const boundedLat = Math.max(Math.min(Number(lat), 85.05112878), -85.05112878);
  const radians = (boundedLat * Math.PI) / 180;
  return 6378137 * Math.log(Math.tan(Math.PI / 4 + radians / 2));
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
