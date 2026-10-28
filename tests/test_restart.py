"""Opt-in persistence check across two real Uvicorn processes."""

import io
import json
import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from PIL import Image
from websockets.sync.client import connect

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt in with RUN_BROWSER_TESTS=1"
)


def test_local_process_restart_preserves_campaign_and_image(tmp_path):
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "IMAGE_STORAGE_PATH": str(tmp_path / "images"),
        "CAMPAIGN_PATH": str(tmp_path / "campaign.json"),
        "IMAGE_BASE_URI": "/images/",
    }

    @contextmanager
    def running_server():
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=Path(__file__).resolve().parent.parent,
            env=env,
            stdout=subprocess.DEVNULL,
        )
        try:
            for _ in range(100):
                try:
                    if httpx.get(f"{base}/api/campaign").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                if process.poll() is not None:
                    raise RuntimeError("Server exited before startup")
                time.sleep(0.1)
            else:
                raise RuntimeError("Server did not start")
            yield
        finally:
            process.terminate()
            process.wait(timeout=10)

    data = io.BytesIO()
    Image.new("RGB", (32, 24), "darkorange").save(data, "PNG")
    png = data.getvalue()
    with running_server():
        response = httpx.post(f"{base}/api/upload", files={"file": ("scene.png", png, "image/png")})
        response.raise_for_status()
        url = response.json()["url"]
        campaign = {
            "dungeons": [
                {
                    "id": "d",
                    "name": "Keep",
                    "rooms": [
                        {
                            "id": "r",
                            "name": "Hall",
                            "buttons": [{"id": "b", "label": "Entrance", "url": url}],
                        }
                    ],
                }
            ]
        }
        httpx.post(f"{base}/api/campaign", json=campaign).raise_for_status()
    with running_server():
        assert httpx.get(f"{base}/api/campaign").json() == campaign
        assert httpx.get(base + url).content == png
        with (
            connect(f"ws://127.0.0.1:{port}/ws/projector") as projector,
            connect(f"ws://127.0.0.1:{port}/ws/director") as director,
        ):
            command = {"action": "show", "url": url}
            director.send(json.dumps(command))
            assert json.loads(projector.recv(timeout=5)) == command
