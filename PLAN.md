# Dungeon Projector: Implementation and Deployment Plan

This document serves as the master blueprint for developing and deploying the "Dungeon Projector" application. It is designed to be fed into an AI coding assistant (e.g., Codex Luna).

## 1. Project Overview & Architecture

* **Goal:** A local web application serving three main views: a "Builder" to construct scenarios, a "Director" view (mobile phone) to trigger images, and a "Projector" view (tablet) to display them.
* **Stack:** Python 3.11+, FastAPI, WebSockets (for realtime sync), HTML/Vanilla JS/TailwindCSS (frontend).
* **Environment:** Local Mac M4 (ARM64) using Podman for containerization. Raspberry Pi for eventual physical deployment.
* **Key Constraint:** Image storage location must be configurable via environment variables to allow seamless transitions between local testing, containerized volumes, and future cloud-hosted URIs.

## Part A: Code Implementation and Testing Plan

### A.1. Directory Structure

Instruct the AI to initialize the project with the following structure:

```text
dungeon-projector/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app and route definitions
│   ├── config.py            # Pydantic BaseSettings for env vars
│   ├── ws_manager.py        # WebSocket connection manager
│   ├── models.py            # Pydantic models for campaign JSON schema
│   └── templates/           # HTML files
│       ├── builder.html     # Campaign scenario builder & upload UI
│       ├── director.html    # Phone view (buttons)
│       └── projector.html   # Tablet view (image display)
├── static/
│   ├── css/
│   └── js/
│       ├── builder.js
│       ├── director.js
│       └── projector.js
├── data/
│   ├── images/              # Local image storage (ignored in git)
│   └── campaign.json        # Saved dungeon structure
├── tests/
│   └── test_main.py         # Pytest files
├── requirements.txt
└── .env                     # Local environment variables
```

### A.2. Backend Implementation (FastAPI)

1. **Configuration (`config.py`):**
   * Use `pydantic-settings`.
   * Define `IMAGE_STORAGE_PATH` (default: `./data/images`).
   * Define `IMAGE_BASE_URI` (default: `/images/` for local static serving).

2. **WebSocket Manager (`ws_manager.py`):**
   * Create a `ConnectionManager` class to hold active WebSocket connections.
   * Implement methods: `connect`, `disconnect`, `broadcast_image(url)`, `broadcast_command(cmd)`.

3. **API & Routing (`main.py`):**
   * Mount the `static` directory.
   * Dynamically mount the `IMAGE_STORAGE_PATH` to the `/images` route (if running locally/containerized) based on config.
   * **Endpoints:**
     * `GET /`: Redirect to `/director`.
     * `GET /director`: Return `director.html`.
     * `GET /projector`: Return `projector.html`.
     * `GET /builder`: Return `builder.html`.
     * `GET /api/campaign`: Return the current `campaign.json`.
     * `POST /api/campaign`: Save updates to `campaign.json`.
     * `POST /api/upload`: Accept `multipart/form-data` image uploads. Save the file to `IMAGE_STORAGE_PATH` and return the dynamically constructed image URI (e.g., `{"url": "/images/filename.jpg"}`).
     * `WS /ws/director` & `WS /ws/projector`: WebSocket endpoints.

### A.3. Frontend Implementation

1. **Builder View (`builder.html` / `builder.js`):**
   * **Purpose:** A visual tool to construct the `campaign.json` file and manage image assets without manually writing JSON.
   * **UI Structure:**
     * A tree or list view allowing the user to Add/Edit/Delete **Dungeons**, **Rooms** within Dungeons, and **Buttons** (Actions) within Rooms.
   * **Image Handling per Button:**
     * Provide a toggle: "Upload Local Image" vs "Provide External URL".
     * **External URL:** A simple text input for links (e.g., Imgur).
     * **Upload Local:** A file input. When a file is selected, use JS `FormData` to `POST /api/upload`. On success, store the returned URI in the button's data structure.
   * **Saving:** A global "Save Campaign" button that takes the current JS object representing the dungeon hierarchy and sends it via `POST /api/campaign` to overwrite the `campaign.json` file.

2. **Director View (`director.html` / `director.js`):**
   * Mobile-first responsive grid.
   * Fetches `/api/campaign` to render Dungeons -> Rooms -> Image Buttons.
   * Connects to `/ws/director`.
   * Tapping a button sends a JSON payload through the socket to broadcast the associated image URI.

3. **Projector View (`projector.html` / `projector.js`):**
   * Minimal UI. Black background. An `<img>` tag centered.
   * Connects to `/ws/projector`.
   * Listens for messages: `{ action: "show", url: "..." }` or `{ action: "blackout" }`. Applies CSS fade transitions.

### A.4. Local Testing Strategy (No Containers)

* **Setup:** Create a Python virtual environment (`python -m venv venv`), install requirements (`fastapi`, `uvicorn`, `websockets`, `pytest`, `python-multipart`).
* **Environment:** Create a `.env` file with `IMAGE_STORAGE_PATH=./data/images`. 
* **Run:** Execute `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`.
* **Test:**
  1. Open `http://localhost:8000/builder`, upload a test image, assign it to a room, and save.
  2. Open `http://localhost:8000/projector` in one browser window.
  3. Open `http://localhost:8000/director` in another.
  4. Verify the newly built room appears in the director view and clicking the button dynamically changes the projector window.

## Part B: Deployment Plan (Containerization)

This section ensures the app runs perfectly via Podman on a Mac M4, keeping the environment identical to the future Raspberry Pi deployment.

### B.1. Containerfile Instruction

Create a file named `Containerfile` (or `Dockerfile`) at the project root. Instruct the AI to use the following specifications:

* **Base Image:** `python:3.11-slim` (Ensures multi-arch support, lightweight).
* **Working Directory:** `/app`.
* **Dependencies:** Copy `requirements.txt` and run `pip install --no-cache-dir -r requirements.txt`.
* **Source Code:** Copy the `app`, `static`, and `data` (excluding actual images/json data) folders.
* **Environment Variables:** Set defaults (e.g., `ENV PORT=8000`).
* **Expose Port:** `EXPOSE 8000`.
* **Command:** `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`.

### B.2. Compose File Instruction

Create a `compose.yaml` (or `docker-compose.yml`) to manage the volume mounts. This is crucial for the configurable image directory and ensuring uploads via the Builder persist.

```yaml
version: '3.8'

services:
  dungeon-api:
    build: 
      context: .
      dockerfile: Containerfile
    ports:
      - "8000:8000"
    environment:
      # Instructs FastAPI to save/read images in the container's /data/images
      - IMAGE_STORAGE_PATH=/data/images
      - IMAGE_BASE_URI=/images/
    volumes:
      # Mounts your local Mac/Pi folder to the container for uploaded images
      - ./local_images:/data/images
      # Mounts the campaign JSON so Builder changes persist across container restarts
      - ./local_data/campaign.json:/app/data/campaign.json
    restart: unless-stopped
```

### B.3. Running with Podman on Mac M4

1. **Prepare Host Directories:**
   * `mkdir local_images` (This is where the Builder will upload files).
   * `mkdir local_data` and place an empty/initial `{}` inside a `campaign.json` file here.
2. **Build and Run:**
   * Run: `podman-compose up --build -d` (or `podman compose up --build -d`).
3. **Verify Architecture Compatibility:**
   * The Python slim image natively supports `linux/arm64` (Mac M4). When you later deploy to the Raspberry Pi (also ARM64), the exact same `Containerfile` and `compose.yaml` will work flawlessly.