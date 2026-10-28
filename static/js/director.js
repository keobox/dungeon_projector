import { connect, request } from "./common.js";

const container = document.querySelector("#campaign");
const status = document.querySelector("#status");
const blackout = document.querySelector("#blackout");
let connected = false;

function enableControls(value) {
  connected = value;
  blackout.disabled = !value;
  container.querySelectorAll("button").forEach((button) => { button.disabled = !value; });
}

const socket = connect("director", document.querySelector("#connection"), (message) => {
  if (message.error) status.textContent = message.error;
}, enableControls);

function send(message, label) {
  if (socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify(message));
  status.textContent = label;
}

blackout.onclick = () => {
  send({ action: "blackout" }, "Blackout sent");
  container.querySelectorAll("button").forEach((button) => button.setAttribute("aria-pressed", "false"));
};

function textElement(tag, text, className = "") {
  const element = document.createElement(tag);
  element.textContent = text;
  element.className = className;
  return element;
}

try {
  const campaign = await request("/api/campaign");
  let count = 0;
  for (const dungeon of campaign.dungeons) {
    const section = document.createElement("section");
    section.className = "panel space-y-6";
    section.append(textElement("h2", dungeon.name));
    if (!dungeon.rooms.length) section.append(textElement("p", "No rooms yet.", "muted"));
    for (const room of dungeon.rooms) {
      const roomSection = document.createElement("section");
      roomSection.append(textElement("h3", room.name, "room-heading"));
      const grid = document.createElement("div");
      grid.className = "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-3";
      if (!room.buttons.length) grid.append(textElement("p", "No image buttons yet.", "muted"));
      for (const image of room.buttons) {
        count++;
        const button = textElement("button", image.label, "scene-button");
        button.type = "button";
        button.disabled = !connected;
        button.setAttribute("aria-pressed", "false");
        button.onclick = () => {
          send({ action: "show", url: image.url }, `Image sent: ${image.label}`);
          container.querySelectorAll("button").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
        };
        grid.append(button);
      }
      roomSection.append(grid);
      section.append(roomSection);
    }
    container.append(section);
  }
  status.textContent = count ? `${count} image ${count === 1 ? "button" : "buttons"} ready` : "Add dungeons, rooms, and image buttons in the builder, then refresh this page.";
} catch (error) { status.textContent = `${error.message}. Refresh to try again.`; }
