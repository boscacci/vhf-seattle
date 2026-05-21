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
const chartBasemap = {
  originX: -20037508.342789244,
  originY: 20037508.342789244,
  worldSpanMeters: 40075016.68557849,
  tileSize: 256,
  tileLevelOffset: 2,
  maxLevel: 14,
  maxTiles: 220,
  url(level, row, col) {
    return `https://gis.charttools.noaa.gov/arcgis/rest/services/MarineChart_Services/NOAACharts/MapServer/tile/${level}/${row}/${col}`;
  },
};

const aisPlayback = {
  maxInterpolationGapMinutes: 10,
  maxStaleMinutes: 10,
  trailWindowMinutes: 30,
  maxSegmentDistanceNm: 1.5,
  maxSegmentSpeedKnots: 35,
};

let selectedClipId = null;
let currentClips = [];
let currentTracks = [];
let timelineFrames = [];
let timelineIndex = 0;
let playbackTimer = null;
let mapZoomStep = 2;
let resizeTimer = null;
let activePopupClipId = null;
let mapCenterX = null;
let mapCenterY = null;
let activePanPointerId = null;
let panLastPoint = null;
let panPixelOffsetX = 0;
let panPixelOffsetY = 0;

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
  setupMapPopupDismissal();
  setupMapPanAndWheel();
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
  clearMapPopup();
  renderChartTiles(true);
  renderTrackPlayback(timelineIndex);
  map.querySelectorAll(".map-point").forEach((point) => point.remove());

  plottedClips.forEach((clip, index) => {
    const point = document.createElement("button");
    point.type = "button";
    point.className = `map-point radio-clip-marker ${clip.channel === "14" ? "business" : "fun"}`;
    point.style.left = `${projectLon(clip.ais_context.lon)}%`;
    point.style.top = `${projectLat(clip.ais_context.lat)}%`;
    const offset = markerOffset(index);
    point.style.setProperty("--point-offset-x", `${offset.x}px`);
    point.style.setProperty("--point-offset-y", `${offset.y}px`);
    point.textContent = String(index + 1);
    point.dataset.clipId = clip.id;
    point.setAttribute(
      "aria-label",
      `Reviewed radio clip ${index + 1}: ${clip.public_title}, VHF ${clip.channel}`,
    );
    point.addEventListener("click", () => {
      selectClipFromMap(clip, index);
      showMapPopup(clip, index, point, tooltip);
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
  if (!tileLayer) return;

  const visibleBounds = currentBounds();
  const level = currentChartLevel(visibleBounds);
  const renderKey = [
    level,
    visibleBounds.minLat.toFixed(5),
    visibleBounds.maxLat.toFixed(5),
    visibleBounds.minLon.toFixed(5),
    visibleBounds.maxLon.toFixed(5),
  ].join(":");
  if (!force && tileLayer.dataset.renderedFor === renderKey) return;

  const matrixSize = tileMatrixSize(level);
  const tileSpan = chartBasemap.worldSpanMeters / matrixSize;
  const minX = lonToMercatorX(visibleBounds.minLon);
  const maxX = lonToMercatorX(visibleBounds.maxLon);
  const minY = latToMercatorY(visibleBounds.minLat);
  const maxY = latToMercatorY(visibleBounds.maxLat);
  const minCol = clampTile(Math.floor((minX - chartBasemap.originX) / tileSpan), matrixSize);
  const maxCol = clampTile(Math.floor((maxX - chartBasemap.originX) / tileSpan), matrixSize);
  const minRow = clampTile(Math.floor((chartBasemap.originY - maxY) / tileSpan), matrixSize);
  const maxRow = clampTile(Math.floor((chartBasemap.originY - minY) / tileSpan), matrixSize);

  const tiles = [];
  for (let row = minRow; row <= maxRow; row += 1) {
    for (let col = minCol; col <= maxCol; col += 1) {
      const tileMinX = chartBasemap.originX + col * tileSpan;
      const tileMaxX = chartBasemap.originX + (col + 1) * tileSpan;
      const tileMaxY = chartBasemap.originY - row * tileSpan;
      const tileMinY = chartBasemap.originY - (row + 1) * tileSpan;
      tiles.push(`
        <img
          src="${chartBasemap.url(level, row, col)}"
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
  tileLayer.dataset.renderedFor = renderKey;
}

function currentBounds() {
  const zoomFactor = 2 ** (mapZoomStep - 2);
  const map = document.querySelector("#bay-map");
  const aspectRatio = map?.clientWidth && map?.clientHeight ? map.clientWidth / map.clientHeight : 16 / 9;

  const minX = lonToMercatorX(baseBounds.minLon);
  const maxX = lonToMercatorX(baseBounds.maxLon);
  const minY = latToMercatorY(baseBounds.minLat);
  const maxY = latToMercatorY(baseBounds.maxLat);
  const center = currentMapCenter();
  const baseWidth = maxX - minX;
  const baseHeight = maxY - minY;
  const width = Math.max(baseWidth, baseHeight * aspectRatio) / zoomFactor;
  const height = Math.max(baseHeight, baseWidth / aspectRatio) / zoomFactor;

  return {
    minLat: mercatorYToLat(center.y - height / 2),
    maxLat: mercatorYToLat(center.y + height / 2),
    minLon: mercatorXToLon(center.x - width / 2),
    maxLon: mercatorXToLon(center.x + width / 2),
  };
}

function currentMapCenter() {
  if (mapCenterX == null || mapCenterY == null) {
    mapCenterX = (lonToMercatorX(baseBounds.minLon) + lonToMercatorX(baseBounds.maxLon)) / 2;
    mapCenterY = (latToMercatorY(baseBounds.minLat) + latToMercatorY(baseBounds.maxLat)) / 2;
  }
  return { x: mapCenterX, y: mapCenterY };
}

function currentChartLevel(visibleBounds = currentBounds()) {
  const map = document.querySelector("#bay-map");
  const mapWidth = Math.max(map?.clientWidth || chartBasemap.tileSize, chartBasemap.tileSize);
  const displayScale = Math.max(1.75, Math.min(window.devicePixelRatio || 1, 2));
  const minX = lonToMercatorX(visibleBounds.minLon);
  const maxX = lonToMercatorX(visibleBounds.maxLon);
  const visibleWidthMeters = Math.max(maxX - minX, 1);
  const targetPixelWidth = mapWidth * displayScale;
  const targetMetersPerPixel = visibleWidthMeters / targetPixelWidth;
  const idealLevel = Math.ceil(
    Math.log2(chartBasemap.worldSpanMeters / (chartBasemap.tileSize * targetMetersPerPixel)),
  ) - chartBasemap.tileLevelOffset;
  let level = Math.max(8, Math.min(chartBasemap.maxLevel, idealLevel));

  while (level > 8 && estimatedTileCount(visibleBounds, level) > chartBasemap.maxTiles) {
    level -= 1;
  }

  return level;
}

function estimatedTileCount(visibleBounds, level) {
  const matrixSize = tileMatrixSize(level);
  const tileSpan = chartBasemap.worldSpanMeters / matrixSize;
  const minX = lonToMercatorX(visibleBounds.minLon);
  const maxX = lonToMercatorX(visibleBounds.maxLon);
  const minY = latToMercatorY(visibleBounds.minLat);
  const maxY = latToMercatorY(visibleBounds.maxLat);
  const minCol = clampTile(Math.floor((minX - chartBasemap.originX) / tileSpan), matrixSize);
  const maxCol = clampTile(Math.floor((maxX - chartBasemap.originX) / tileSpan), matrixSize);
  const minRow = clampTile(Math.floor((chartBasemap.originY - maxY) / tileSpan), matrixSize);
  const maxRow = clampTile(Math.floor((chartBasemap.originY - minY) / tileSpan), matrixSize);

  return (maxCol - minCol + 1) * (maxRow - minRow + 1);
}

function tileMatrixSize(level) {
  return 2 ** (level + chartBasemap.tileLevelOffset);
}

function setupControls() {
  const zoomIn = document.querySelector("#zoom-in");
  const zoomOut = document.querySelector("#zoom-out");
  const playButton = document.querySelector("#playback-toggle");
  const slider = document.querySelector("#time-slider");

  zoomIn.addEventListener("click", () => zoomAtPoint(mapZoomStep + 1));
  zoomOut.addEventListener("click", () => zoomAtPoint(mapZoomStep - 1));
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

function setupMapPopupDismissal() {
  const map = document.querySelector("#bay-map");
  const tooltip = document.querySelector("#map-tooltip");

  map.addEventListener("pointerdown", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target?.closest(".map-point") && !target?.closest("#map-tooltip")) clearMapPopup();
  });
  tooltip.addEventListener("pointerdown", (event) => event.stopPropagation());
  tooltip.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (target?.closest(".map-popup-close")) {
      event.stopPropagation();
      clearMapPopup();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") clearMapPopup();
  });
}

function setupMapPanAndWheel() {
  const map = document.querySelector("#bay-map");

  map.addEventListener(
    "wheel",
    (event) => {
      event.preventDefault();
      zoomAtPoint(mapZoomStep + (event.deltaY < 0 ? 1 : -1), event.clientX, event.clientY);
    },
    { passive: false },
  );
  map.addEventListener("pointerdown", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (target?.closest("button, input, .map-point, #map-tooltip")) return;
    activePanPointerId = event.pointerId;
    panLastPoint = { x: event.clientX, y: event.clientY };
    resetMapPanPreview();
    map.classList.add("is-panning");
  });
  document.addEventListener("pointermove", (event) => {
    if (event.pointerId !== activePanPointerId || !panLastPoint) return;
    panMapByPixels(event.clientX - panLastPoint.x, event.clientY - panLastPoint.y);
    panLastPoint = { x: event.clientX, y: event.clientY };
  });
  document.addEventListener("pointerup", endMapPan);
  document.addEventListener("pointercancel", endMapPan);
}

function endMapPan(event) {
  const map = document.querySelector("#bay-map");
  if (event?.pointerId !== activePanPointerId) return;
  commitMapPan();
  activePanPointerId = null;
  panLastPoint = null;
  map.classList.remove("is-panning");
}

function zoomAtPoint(nextStep, clientX, clientY) {
  const nextZoom = Math.max(0, Math.min(4, nextStep));
  if (nextZoom === mapZoomStep) return;
  const map = document.querySelector("#bay-map");
  const rect = map.getBoundingClientRect();
  const focusX = clientX ?? rect.left + rect.width / 2;
  const focusY = clientY ?? rect.top + rect.height / 2;
  const before = screenPointToMercator(focusX, focusY);
  mapZoomStep = nextZoom;
  const after = screenPointToMercator(focusX, focusY);
  mapCenterX += before.x - after.x;
  mapCenterY += before.y - after.y;
  updateZoomControls();
  renderMapNow();
}

function panMapByPixels(deltaX, deltaY) {
  panPixelOffsetX += deltaX;
  panPixelOffsetY += deltaY;
}

function commitMapPan() {
  if (!panPixelOffsetX && !panPixelOffsetY) return;
  const map = document.querySelector("#bay-map");
  const visibleBounds = currentBounds();
  const minX = lonToMercatorX(visibleBounds.minLon);
  const maxX = lonToMercatorX(visibleBounds.maxLon);
  const minY = latToMercatorY(visibleBounds.minLat);
  const maxY = latToMercatorY(visibleBounds.maxLat);
  const metersPerPixelX = (maxX - minX) / Math.max(map.clientWidth, 1);
  const metersPerPixelY = (maxY - minY) / Math.max(map.clientHeight, 1);
  currentMapCenter();
  mapCenterX -= panPixelOffsetX * metersPerPixelX;
  mapCenterY += panPixelOffsetY * metersPerPixelY;
  resetMapPanPreview();
  renderMapNow();
}

function resetMapPanPreview() {
  panPixelOffsetX = 0;
  panPixelOffsetY = 0;
}

function renderMapNow() {
  renderMap();
}

function screenPointToMercator(clientX, clientY) {
  const map = document.querySelector("#bay-map");
  const rect = map.getBoundingClientRect();
  const visibleBounds = currentBounds();
  const minX = lonToMercatorX(visibleBounds.minLon);
  const maxX = lonToMercatorX(visibleBounds.maxLon);
  const minY = latToMercatorY(visibleBounds.minLat);
  const maxY = latToMercatorY(visibleBounds.maxLat);
  const xRatio = (clientX - rect.left) / Math.max(rect.width, 1);
  const yRatio = (clientY - rect.top) / Math.max(rect.height, 1);
  return {
    x: minX + xRatio * (maxX - minX),
    y: maxY - yRatio * (maxY - minY),
  };
}

function updateZoomControls() {
  document.querySelector("#zoom-out").disabled = mapZoomStep <= 0;
  document.querySelector("#zoom-in").disabled = mapZoomStep >= 4;
  const zoomLabel = document.querySelector("#zoom-label");
  zoomLabel.textContent = `Zoom ${mapZoomStep + 1} of 5`;
  zoomLabel.title = `NOAA chart detail ${currentChartLevel()}`;
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

function renderTrackLayer(tracks, frameTime) {
  const trackLayer = document.querySelector("#track-layer");
  trackLayer.innerHTML = tracks
    .map((track) => ({ track, segment: motionTrailAtTime(track.points || [], frameTime) }))
    .filter(({ segment }) => segment?.length > 1)
    .map(({ track, segment }) => {
      const points = segment
        .map((point) => `${projectLon(point.lon).toFixed(2)},${projectLat(point.lat).toFixed(2)}`)
        .join(" ");
      const className = track.channel_hint === "68" ? "track-line fun" : "track-line business";
      return `<polyline class="${className}" points="${points}" />`;
    })
    .join("");
}

function renderTrackPlayback(frameIndex) {
  const vessels = document.querySelector("#playback-vessels");
  const frameTime = timelineFrames[frameIndex];
  renderTrackLayer(currentTracks, frameTime);
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
          class="playback-vessel ${track.channel_hint === "68" ? "fun" : "business"} ${vesselTypeClass(track)}"
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
  const sorted = normalizeTrackPoints(points);
  if (!sorted.length) return null;
  const firstTime = Date.parse(sorted[0].observed_at);
  const lastTime = Date.parse(sorted[sorted.length - 1].observed_at);
  const maxStaleMs = aisPlayback.maxStaleMinutes * 60 * 1000;
  const maxGapMs = aisPlayback.maxInterpolationGapMinutes * 60 * 1000;
  if (target <= firstTime) return firstTime - target <= maxStaleMs ? sorted[0] : null;
  if (target >= lastTime) return target - lastTime <= maxStaleMs ? sorted[sorted.length - 1] : null;

  for (let index = 1; index < sorted.length; index += 1) {
    const previous = sorted[index - 1];
    const next = sorted[index];
    const previousTime = Date.parse(previous.observed_at);
    const nextTime = Date.parse(next.observed_at);
    if (target === previousTime) return previous;
    if (target === nextTime) return next;
    if (target <= nextTime) {
      const gapMs = nextTime - previousTime;
      if (gapMs > maxGapMs || !segmentIsPlausible(previous, next)) {
        const nearest = target - previousTime <= nextTime - target ? previous : next;
        return Math.abs(Date.parse(nearest.observed_at) - target) <= maxStaleMs ? nearest : null;
      }
      const fraction = (target - previousTime) / (nextTime - previousTime);
      return {
        observed_at: frameTime,
        lat: Number(previous.lat) + (Number(next.lat) - Number(previous.lat)) * fraction,
        lon: Number(previous.lon) + (Number(next.lon) - Number(previous.lon)) * fraction,
        interpolated: true,
      };
    }
  }
  return sorted[sorted.length - 1];
}

function motionTrailAtTime(points, frameTime) {
  if (!frameTime) return null;
  const target = Date.parse(frameTime);
  const windowStart = target - aisPlayback.trailWindowMinutes * 60 * 1000;
  const current = positionAtTime(points, frameTime);
  if (!current) return null;

  const trail = normalizeTrackPoints(points).filter((point) => {
    const observedAt = Date.parse(point.observed_at);
    return observedAt >= windowStart && observedAt <= target;
  });
  if (current && !trail.some((point) => point.observed_at === current.observed_at)) {
    trail.push(current);
  }
  trail.sort((a, b) => Date.parse(a.observed_at) - Date.parse(b.observed_at));

  let currentSegment = [];
  trail.forEach((point) => {
    const previous = currentSegment[currentSegment.length - 1];
    if (previous && !segmentIsPlausible(previous, point)) {
      currentSegment = [];
    }
    currentSegment.push(point);
  });
  if (currentSegment.length > 1) return currentSegment;

  const tailPoint = courseTailPoint(current);
  return tailPoint ? [tailPoint, current] : null;
}

function courseTailPoint(point) {
  const courseDegrees = Number(point.course_degrees);
  if (!Number.isFinite(courseDegrees)) return null;
  const speedKnots = Math.max(Number(point.speed_knots) || 0, 2);
  const tailDistanceNm = Math.min(0.35, Math.max(0.08, speedKnots / 80));
  const tailBearing = (courseDegrees + 180) % 360;
  return destinationPoint(point, tailBearing, tailDistanceNm);
}

function destinationPoint(point, bearingDegrees, distanceNm) {
  const bearingRadians = (bearingDegrees * Math.PI) / 180;
  const lat = Number(point.lat);
  const lon = Number(point.lon);
  const latitudeCorrection = Math.max(Math.cos((lat * Math.PI) / 180), 0.1);
  return {
    lat: lat + (distanceNm / 60) * Math.cos(bearingRadians),
    lon: lon + (distanceNm / (60 * latitudeCorrection)) * Math.sin(bearingRadians),
    observed_at: point.observed_at,
  };
}

function vesselTypeClass(track) {
  return `vessel-${String(track.vessel_type || "unknown")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "") || "unknown"}`;
}

function normalizeTrackPoints(points) {
  return points
    .filter((point) => point.observed_at && point.lat != null && point.lon != null)
    .slice()
    .sort((a, b) => Date.parse(a.observed_at) - Date.parse(b.observed_at));
}

function segmentIsPlausible(previous, next) {
  const previousTime = Date.parse(previous.observed_at);
  const nextTime = Date.parse(next.observed_at);
  const gapHours = (nextTime - previousTime) / (60 * 60 * 1000);
  const distanceNm = haversineNm(previous, next);
  if (distanceNm > aisPlayback.maxSegmentDistanceNm) return false;
  if (gapHours <= 0) return false;
  return distanceNm / gapHours <= aisPlayback.maxSegmentSpeedKnots;
}

function showMapPopup(clip, index, point, tooltip) {
  clearMapPopup();
  activePopupClipId = clip.id;
  setClipHover(clip.id, true);
  tooltip.hidden = false;
  tooltip.innerHTML = `
    <button type="button" class="map-popup-close" aria-label="Close map detail">×</button>
    <span class="map-popup-kicker">Reviewed radio clip</span>
    <strong>Map ${index + 1}: ${escapeHtml(clip.public_title)}</strong>
    <span>VHF ${escapeHtml(clip.channel)} · ${escapeHtml(formatDate(clip.started_at))}</span>
    ${renderPopupVessel(clip)}
  `;
  placeTooltip(point, tooltip);
}

function clearMapPopup() {
  const tooltip = document.querySelector("#map-tooltip");
  if (activePopupClipId) setClipHover(activePopupClipId, false);
  activePopupClipId = null;
  if (tooltip) {
    tooltip.hidden = true;
    tooltip.replaceChildren();
    tooltip.removeAttribute("style");
  }
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

function renderPopupVessel(clip) {
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

function haversineNm(a, b) {
  const radiusNm = 3440.065;
  const lat1 = (Number(a.lat) * Math.PI) / 180;
  const lat2 = (Number(b.lat) * Math.PI) / 180;
  const dLat = lat2 - lat1;
  const dLon = ((Number(b.lon) - Number(a.lon)) * Math.PI) / 180;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * radiusNm * Math.asin(Math.sqrt(h));
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
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatDateTime(value) {
  if (!value) return "Unknown time";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
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
