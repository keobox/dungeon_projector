import { connect } from "./common.js";

const image = document.querySelector("#scene");
const error = document.querySelector("#image-error");
const connection = document.querySelector("#connection");
let showing = false;

image.addEventListener("load", () => { if (showing) image.hidden = false; });
image.addEventListener("error", () => { if (showing) { image.hidden = true; error.hidden = false; } });

connect("projector", connection, (message) => {
  if (message.action === "show" && typeof message.url === "string") {
    showing = true;
    error.hidden = true;
    image.hidden = true;
    image.removeAttribute("src");
    image.src = message.url;
  } else if (message.action === "blackout") {
    showing = false;
    error.hidden = true;
    image.hidden = true;
    image.removeAttribute("src");
  }
}, (connected) => {
  connection.hidden = connected || connection.textContent === "Connecting…";
});

// Keep the display empty; double-click/tap to request fullscreen where supported.
document.addEventListener("dblclick", () => {
  if (!document.fullscreenElement) document.documentElement.requestFullscreen?.().catch(() => {});
});
