# MVP verification

Verified on 2026-10-28 on this ARM64 Mac with Python 3.11.14, uv 0.9.2,
headless Google Chrome, Podman 5.6.2, and podman-compose 1.6.0. Podman reported
`arm64 linux`. The container used `python:3.11-slim`.

## Results

The interactive checklist below was exercised through actual browser automation
against both a local Uvicorn process and the Podman Compose service. These are
browser checks, not a claim of human testing on physical phones or tablets.

| Check from PLAN.md | Local Uvicorn | Podman Compose |
| --- | --- | --- |
| Start application; open builder, director, projector | Pass | Pass |
| Create dungeon, room, button; upload a real PNG; save | Pass | Pass |
| Reload builder; saved hierarchy and button remain | Pass | Pass |
| Select saved button; projector loads image at its original 320×180 dimensions | Pass | Pass |
| Blackout; select the image again | Pass | Pass |
| Save an external HTTP(S) URL and display its image | Pass | Pass |
| Restart application; campaign and uploaded image remain usable | Pass: new Uvicorn process, identical campaign/image, working WebSocket command | Pass: container removal/recreation, plus browser check |
| Remove/recreate container without deleting data; reuse saved image | Not applicable | Pass: new container ID, identical campaign/image bytes, browser display |

Additional checks passed:

- Editing a room preserves its ID. Deleting buttons, rooms, and dungeons works.
- Empty campaigns/dungeons/rooms work. Invalid JSON/schema, blank names/IDs,
  duplicate IDs, and unsupported URLs cannot overwrite a saved campaign.
- Upload names are generated independently of the supplied filename. Invalid,
  oversized, and non-image uploads fail without leaving partial files.
- Custom storage paths and local/absolute image URI prefixes behave as documented.
- Invalid WebSocket text/binary messages are rejected without reaching projectors;
  valid commands still work afterward. Projector messages cannot broadcast.
- Disconnected projectors do not prevent subsequent broadcasts.
- A refreshed projector starts black until another command arrives.
- The 390px-wide director has no horizontal overflow. The builder was checked
  at desktop and mobile widths, and screenshots were visually inspected.
- The local browser flow had no JavaScript page errors.

External image used: the reachable
[Python logo PNG](https://www.python.org/static/community_logos/python-logo.png).
The uploaded PNG was generated with Pillow and decoded by the browser; the tests
checked its actual pixel dimensions rather than just its `src` attribute.

The container test used project `dungeon-projector-check`, port 18080, and
`test-results/container-data/`. It was brought down after verification. Test
data and screenshots remain ignored by Git; normal local `data/` and Compose
`local_data/` were not populated with the test campaign.

The successful recreation changed the container ID from `dfb02d06ada3…` to
`bb1fc2bfef3f…`. The uploaded image retained SHA-256
`947bc5736fd0314f6c77cf671a62fe88199f4e4532acd18688d2695c5b4c71d9`.
An initial recreation probe ran before the forwarded port was ready; the probe
was corrected to retry transient transport errors and the complete check passed.

## Automated checks

```sh
uv run pytest -q
# 31 backend checks pass; 3 browser/live-process checks skip unless opted in.

RUN_BROWSER_TESTS=1 \
PLAYWRIGHT_CHROMIUM_EXECUTABLE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
uv run pytest -q
# 34 checks, including browser flow, delete/error feedback, and process restart.

uv run ruff check app tests
uv run ruff format --check app tests
```

The two browser tests also passed separately with
`TEST_BASE_URL=http://127.0.0.1:18080` against the container. The final recreation
probe compared the stored campaign and image bytes, loaded the saved builder,
then displayed the uploaded image, Blackout, and the external image in Chrome
without another upload or campaign save.

The pinned Starlette test client emits one upstream deprecation warning about
its `httpx` integration. The tests pass; this does not affect the runtime app.

## Manual acceptance checklist

Repeat this procedure when testing a new device or deployment. Setup commands
are in [README.md](README.md).

1. Start locally with `uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`.
2. Visit `/builder`. Add a dungeon, room, and labeled image button. Upload a PNG,
   JPEG, GIF, or WebP and save. Reload and confirm the names, preview, and button remain.
3. Open `/projector` on the display and `/director` on the controller. Select the
   saved image; confirm it is visible and fits without cropping.
4. Tap Blackout; the display should become black. Select the image again.
5. Add another button with a reachable external image URL, save, refresh the
   director, and select it. Confirm the external image appears.
6. Stop Uvicorn and restart it with the same paths. Refresh both views. Confirm
   the campaign is still present and the uploaded image displays without reuploading.
7. Stop local Uvicorn, start Compose, and repeat steps 2–5 for its separate data.
8. Run `uvx podman-compose down`, then `uvx podman-compose up -d`, keeping the
   same data directory and environment overrides. Refresh the views and select
   the saved image. Confirm it works without uploading or saving again.
9. On actual devices, verify LAN reachability, tapping controls, fullscreen
   support, and the display remaining awake. After a lost connection, refresh
   both views and select the image again.

## Not verified

- Physical phone/tablet browsers, fullscreen behavior, and LAN/firewall reachability
  from other devices. Mobile layout testing used a Chrome viewport.
- Raspberry Pi hardware or its operating system. The ARM64 Mac Podman VM passed.
- A real remote storage/CDN service behind an absolute `IMAGE_BASE_URI`; URI
  construction was tested. Cloud uploads are outside the MVP.

Authentication, concurrent editing, automatic reconnection, restored display
state, preloading, and transitions remain outside the agreed scope.
