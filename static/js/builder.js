import { request, uuid } from "./common.js";

const status = document.querySelector("#status");
const editor = document.querySelector("#editor");
const save = document.querySelector("#save");
const dungeons = document.querySelector("#dungeons");
const modes = new Map();
let campaign;
let dirty = false;

function message(text, error = false) {
  status.textContent = text;
  status.dataset.error = String(error);
}

function changed() {
  dirty = true;
  message("Unsaved changes");
}

function busy(value) {
  editor.disabled = value;
  save.disabled = value;
}

function clone(name) {
  return document.querySelector(`#${name}-template`).content.firstElementChild.cloneNode(true);
}

function bind(node, selector, item, key) {
  const input = node.querySelector(selector);
  input.value = item[key];
  input.addEventListener("input", () => { item[key] = input.value; changed(); });
  return input;
}

function remove(items, item, description) {
  if (!confirm(`Delete this ${description}? This takes effect when you save the campaign.`)) return;
  items.splice(items.indexOf(item), 1);
  changed();
  render();
}

function add(items, item) {
  items.push(item);
  changed();
  render();
  document.getElementById(item.id)?.querySelector("input")?.focus();
}

function renderButton(button, room) {
  const node = clone("button");
  node.id = button.id;
  bind(node, ".button-label", button, "label");
  const url = bind(node, ".url", button, "url");
  const source = node.querySelector(".source");
  const file = node.querySelector(".file");
  const preview = node.querySelector(".preview");
  const previewError = node.querySelector(".preview-error");
  source.value = modes.get(button.id) || (button.url.startsWith("http") ? "external" : "upload");
  function updateImage() {
    previewError.hidden = true;
    preview.hidden = !button.url;
    if (button.url) preview.src = button.url;
    else preview.removeAttribute("src");
    node.querySelector(".image-uri").textContent = button.url || "No image selected";
    file.required = source.value === "upload" && !button.url;
  }
  function updateSource() {
    const external = source.value === "external";
    node.querySelector(".upload-field").hidden = external;
    node.querySelector(".external-field").hidden = !external;
    file.disabled = external;
    url.disabled = !external;
    url.required = external;
    updateImage();
  }
  preview.addEventListener("error", () => { preview.hidden = true; previewError.hidden = false; });
  url.addEventListener("change", updateImage);
  source.addEventListener("change", () => {
    modes.set(button.id, source.value);
    button.url = "";
    url.value = "";
    file.value = "";
    changed();
    updateSource();
  });
  file.addEventListener("change", async () => {
    if (!file.files.length) return;
    const body = new FormData();
    body.append("file", file.files[0]);
    busy(true);
    message("Uploading image…");
    try {
      const result = await request("/api/upload", { method: "POST", body });
      button.url = result.url;
      url.value = result.url;
      changed();
      updateImage();
      message("Image uploaded. Save the campaign to keep this button.");
    } catch (error) {
      file.value = "";
      message(error.message, true);
    } finally { busy(false); }
  });
  node.querySelector(".delete-button").onclick = () => remove(room.buttons, button, "image button");
  updateSource();
  return node;
}

function render() {
  dungeons.replaceChildren();
  if (!campaign.dungeons.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Your story starts here. Add a dungeon, then a room and its image buttons.";
    dungeons.append(empty);
  }
  for (const dungeon of campaign.dungeons) {
    const node = clone("dungeon");
    node.id = dungeon.id;
    bind(node, ".dungeon-name", dungeon, "name");
    node.querySelector(".delete-dungeon").onclick = () => remove(campaign.dungeons, dungeon, "dungeon and all its rooms");
    node.querySelector(".add-room").onclick = () => add(dungeon.rooms, { id: uuid(), name: "", buttons: [] });
    for (const room of dungeon.rooms) {
      const roomNode = clone("room");
      roomNode.id = room.id;
      bind(roomNode, ".room-name", room, "name");
      roomNode.querySelector(".delete-room").onclick = () => remove(dungeon.rooms, room, "room and all its buttons");
      roomNode.querySelector(".add-button").onclick = () => add(room.buttons, { id: uuid(), label: "", url: "" });
      for (const button of room.buttons) roomNode.querySelector(".buttons").append(renderButton(button, room));
      node.querySelector(".rooms").append(roomNode);
    }
    dungeons.append(node);
  }
}

document.querySelector("#add-dungeon").onclick = () => add(campaign.dungeons, { id: uuid(), name: "", rooms: [] });
document.querySelector("#campaign-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  busy(true);
  message("Saving…");
  try {
    campaign = await request("/api/campaign", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(campaign),
    });
    dirty = false;
    render();
    message("Campaign saved. Refresh the director to load your changes.");
  } catch (error) { message(error.message, true); }
  finally { busy(false); }
});
window.addEventListener("beforeunload", (event) => {
  if (dirty) { event.preventDefault(); event.returnValue = ""; }
});

try {
  campaign = await request("/api/campaign");
  render();
  busy(false);
  message("Campaign loaded. Ready to edit.");
} catch (error) { message(`${error.message}. Refresh to try again.`, true); }
