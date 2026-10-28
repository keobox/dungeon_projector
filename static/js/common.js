export async function request(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = Array.isArray(body?.detail)
      ? body.detail.map((error) => `${error.loc.slice(1).join(" → ")}: ${error.msg}`).join("; ")
      : body?.detail;
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return body;
}

export function connect(role, status, onMessage = () => {}, onConnection = () => {}) {
  const socket = new WebSocket(`${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/ws/${role}`);
  const update = (message, connected) => {
    status.textContent = message;
    status.dataset.connected = String(connected);
    onConnection(connected);
  };
  update("Connecting…", false);
  socket.addEventListener("open", () => update("Connected", true));
  socket.addEventListener("close", () => update("Disconnected. Refresh both views, then select an image again.", false));
  socket.addEventListener("error", () => update("Connection failed. Refresh both views, then select an image again.", false));
  socket.addEventListener("message", (event) => {
    try { onMessage(JSON.parse(event.data)); } catch { /* Ignore malformed messages. */ }
  });
  return socket;
}

export function uuid() {
  // randomUUID requires HTTPS; getRandomValues also works on a trusted LAN over HTTP.
  if (crypto.randomUUID) return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
