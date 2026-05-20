const form = document.querySelector("#session-form");
const channels = document.querySelector("#channels");
const audio = document.querySelector("#live-audio");
const nowPlaying = document.querySelector("#now-playing");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const token = new FormData(form).get("token");
  const response = await fetch("/api/operator/session", {
    method: "POST",
    headers: { "X-TalkingBoats-Operator-Token": token },
  });
  if (!response.ok) {
    nowPlaying.textContent = "Session rejected";
    return;
  }
  form.reset();
  await loadChannels();
});

async function loadChannels() {
  const response = await fetch("/api/live/channels", { cache: "no-store" });
  if (!response.ok) {
    nowPlaying.textContent = "Start a private operator session";
    return;
  }
  const payload = await response.json();
  channels.innerHTML = payload.channels.map(renderChannel).join("");
  channels.querySelectorAll("button[data-channel]").forEach((button) => {
    button.addEventListener("click", () => tune(button.dataset.channel, button.dataset.label));
  });
}

function renderChannel(channel) {
  return `
    <button
      class="channel-button"
      type="button"
      data-channel="${escapeHtml(channel.channel)}"
      data-label="${escapeHtml(channel.label)}"
      ${channel.enabled ? "" : "disabled"}
    >
      VHF ${escapeHtml(channel.channel)} · ${escapeHtml(channel.label)} · ${escapeHtml(
        String(channel.frequency_mhz),
      )} MHz
    </button>
  `;
}

function tune(channel, label) {
  audio.src = `/api/live/${encodeURIComponent(channel)}/stream`;
  audio.play();
  nowPlaying.textContent = `VHF ${channel} · ${label}`;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => {
    const escapes = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" };
    return escapes[char];
  });
}

loadChannels();
