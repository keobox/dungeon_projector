# Dungeon Projector

A local image controller for tabletop games: build a campaign on your computer,
choose scenes on your phone, and display them on a tablet or projector.

## Run locally with uv

From this directory, with [uv](https://docs.astral.sh/uv/) installed:

```sh
uv sync --locked
cp .env.example .env  # first setup only; keep an existing .env
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

`uv` manages the virtual environment and Python 3.11, selected by `.python-version`.
Python 3.11+ is supported. Runtime and test dependencies are pinned in `uv.lock`.
There is no Node.js or internet requirement to run the local views after setup;
external images still need a network connection.

Open these views:

| View | URL | Purpose |
| --- | --- | --- |
| Builder | http://localhost:8000/builder | Add, edit, and delete dungeons, rooms, and image buttons |
| Director | http://localhost:8000/director | Select images and send Blackout |
| Projector | http://localhost:8000/projector | Display the selected image against black |

1. In the builder, add a dungeon and room, then an image button. Give each a name.
2. Upload a PNG, JPEG, GIF, or WebP (maximum 20 MiB), or select **Provide external
   URL** and paste a direct HTTP(S) image URL. Uploads appear in a preview.
3. **Save campaign**. Reloading the builder restores the saved hierarchy.
4. Open the projector first, then open or refresh the director and tap an image
   button. Tap **Blackout** to hide it; selecting an image shows it again.

On a phone or tablet on the same LAN, replace `localhost` with the Mac's LAN IP,
for example `http://192.168.1.20:8000/director`. Allow incoming connections if
macOS asks. Double-click/tap the projector to request fullscreen where supported.
Keep the display awake using the device's own settings.

Use one server worker, one editor, one director, and one projector. A director's
“Connected” indicator means its server connection is open; delivery has no
acknowledgements. Refresh the director after campaign edits. If a connection is
lost, refresh both views and select the image again. A new projector always
starts black, and restarting the server does not restore the current display.

This MVP has no authentication and is intended for a trusted local network.

## Data and configuration

Environment variables override `.env`. Relative filesystem paths are relative
to the directory where Uvicorn starts; run the commands from this project root.

| Variable | Local default | Meaning |
| --- | --- | --- |
| `IMAGE_STORAGE_PATH` | `./data/images` | Directory for uploaded image files |
| `IMAGE_BASE_URI` | `/images/` | Prefix used in returned upload URLs |
| `CAMPAIGN_PATH` | `./data/campaign.json` | Persistent campaign file |

Directories and a valid empty campaign (`{"dungeons": []}`) are created at startup.
Campaign saves validate the complete object before atomically replacing the
file. Invalid input leaves the saved campaign intact. A corrupt existing file
causes startup to fail so it can be repaired or restored, rather than erased.

A local `IMAGE_BASE_URI`, such as `/scenes/`, also changes the image-serving mount.
An absolute prefix such as `https://images.example.org/scenes/` changes returned
URLs, but uploads still write to `IMAGE_STORAGE_PATH` and remain available at
`/images/<filename>`. Making that remote address serve these files is your
responsibility; cloud uploads are outside this MVP. Keep `/images/` for normal
local and container use. Changing the prefix does not rewrite saved button URLs.

External images load directly in the browser, so use a reachable image URL that
allows embedding. An HTTPS deployment would also need HTTPS image URLs.
Images keep their aspect ratio and fit inside the display without cropping.
Removing a button does not delete its uploaded file; unused image cleanup is
manual. Back up the campaign JSON and its image directory together.

## Run with Podman Compose

On macOS, start your Podman VM (use `podman machine init` first if you do not have
one). The Compose provider can also run through uv:

```sh
podman machine start
mkdir -p local_data
uvx podman-compose up --build -d
```

Skip `podman machine start` if the VM is already running. If a Compose provider
is already installed, `podman compose up --build -d` works too. Open the same
URLs on port 8000. Stop a local Uvicorn process first if it is using that port,
or choose another with `DUNGEON_PORT=8080 uvx podman-compose up --build -d`.
Keep the same port/data environment overrides for subsequent Compose commands.

Compose binds `./local_data` to `/data`. The campaign is stored in
`local_data/campaign.json`, and uploads in `local_data/images/`. Mounting the
whole directory allows atomic campaign-file replacement; it also avoids having
to pre-create a JSON file. Local Uvicorn uses `data/`, so the two modes have
separate campaigns by default. Set `DUNGEON_DATA_DIR` to override the host
directory (for example an absolute path to an existing campaign directory).

```sh
uvx podman-compose logs --tail=50
uvx podman-compose down
uvx podman-compose up -d
```

Removing/recreating the container keeps the host data. Deleting `local_data`
deletes that persistent campaign and its uploads. Actual data, `.env`, test
artifacts, and `prompt.txt` are excluded from Git and the container build context.
The container uses `python:3.11-slim` and one Uvicorn worker. It installs the
runtime requirements exported from `uv.lock`; uv and Node.js are not needed in
the runtime image. ARM64 Podman was verified on this Mac. Raspberry Pi and
physical phone/tablet testing remain to be done.

## Verification and development

```sh
uv run pytest -q
uv run ruff check app tests
uv run ruff format --check app tests
```

The default tests use temporary data and in-process HTTP/WebSocket clients.
For real-browser tests and a real server restart test:

```sh
uv run playwright install chromium
RUN_BROWSER_TESTS=1 uv run pytest -q
```

Alternatively, reuse an installed Chrome without downloading a browser:

```sh
RUN_BROWSER_TESTS=1 \
PLAYWRIGHT_CHROMIUM_EXECUTABLE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
uv run pytest -q
```

Browser tests start an isolated Uvicorn server, exercise the complete builder /
director / projector flow, and write screenshots to `test-results/`. They use a
real [Python logo image](https://www.python.org/static/community_logos/python-logo.png)
to check external URLs; internet access is required for this check. Override
`EXTERNAL_IMAGE_URL` if needed. Set `TEST_BASE_URL=http://localhost:8000` to run
the browser tests against a container **with disposable data**: those tests
replace the campaign. See [VERIFICATION.md](VERIFICATION.md) for the manual
checklist, executed checks, and limits of the results.

Tailwind's generated CSS is committed, so frontend build tools are only needed
after changing HTML/JS utility classes or `static/css/source.css`:

```sh
npm ci
npm run build:css
```

This uses the [Tailwind CLI](https://tailwindcss.com/docs/installation/tailwind-cli)
to create a local stylesheet. There is no browser CDN dependency.

When changing Python dependencies, use `uv add` / `uv add --dev` (or edit
`pyproject.toml` and run `uv lock`), then refresh the container requirements:

```sh
uv sync --locked
uv export --frozen --no-dev --no-hashes --no-emit-project -o requirements.txt
```

Commit both lockfiles and the generated CSS/requirements when their inputs change.
The campaign schema and WebSocket contracts are in [PLAN.md](PLAN.md).
