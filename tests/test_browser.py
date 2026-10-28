"""Opt-in real-browser checks; run with RUN_BROWSER_TESTS=1 uv run pytest.

Set TEST_BASE_URL to test an already running container. Use only a disposable
campaign: these tests replace it. Otherwise an isolated local server is started.
"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from PIL import Image

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt in with RUN_BROWSER_TESTS=1"
)
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    external = os.environ.get("TEST_BASE_URL")
    if external:
        yield external
        return
    directory = tmp_path_factory.mktemp("server")
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]
    env = {
        **os.environ,
        "CAMPAIGN_PATH": str(directory / "campaign.json"),
        "IMAGE_STORAGE_PATH": str(directory / "images"),
        "IMAGE_BASE_URI": "/images/",
    }
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
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if httpx.get(f"{base}/api/campaign").status_code == 200:
                    break
            except httpx.TransportError:
                pass
            if process.poll() is not None:
                raise RuntimeError("Test server exited before startup")
            time.sleep(0.1)
        else:
            raise RuntimeError("Test server did not start")
        yield base
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.fixture
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        options = {"headless": True}
        if executable := os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE"):
            options["executable_path"] = executable
        browser = playwright.chromium.launch(**options)
        yield browser
        browser.close()


def test_builder_director_projector_flow(browser, server, tmp_path):
    from playwright.sync_api import expect

    httpx.post(f"{server}/api/campaign", json={"dungeons": []}).raise_for_status()
    png = tmp_path / "entrance.png"
    Image.new("RGB", (320, 180), "forestgreen").save(png)
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    errors = []
    context.on("weberror", lambda event: errors.append(str(event.error)))
    builder = context.new_page()
    builder.goto(f"{server}/builder")
    expect(builder.get_by_role("button", name="Save campaign")).to_be_enabled()
    builder.get_by_role("button", name="+ Add dungeon").click()
    builder.get_by_label("Dungeon name").fill("The Forgotten Keep")
    builder.get_by_role("button", name="+ Add room", exact=True).click()
    builder.get_by_label("Room name").fill("Entrance Hall")
    builder.get_by_role("button", name="+ Add image button").click()
    builder.get_by_label("Button label").fill("Show entrance")
    builder.get_by_label("Image file").set_input_files(png)
    expect(builder.locator("#status")).to_contain_text("Image uploaded")
    builder.get_by_role("button", name="Save campaign").click()
    expect(builder.locator("#status")).to_contain_text("Campaign saved")
    saved = httpx.get(f"{server}/api/campaign").json()
    builder.reload()
    expect(builder.get_by_label("Dungeon name")).to_have_value("The Forgotten Keep")
    expect(builder.get_by_label("Room name")).to_have_value("Entrance Hall")
    expect(builder.get_by_label("Button label")).to_have_value("Show entrance")
    builder.get_by_label("Room name").fill("Entrance & courtyard")
    builder.get_by_role("button", name="Save campaign").click()
    expect(builder.locator("#status")).to_contain_text("Campaign saved")
    edited = httpx.get(f"{server}/api/campaign").json()
    assert edited["dungeons"][0]["rooms"][0]["id"] == saved["dungeons"][0]["rooms"][0]["id"]

    projector = context.new_page()
    projector.goto(f"{server}/projector")
    expect(projector.locator("#connection")).to_have_text("Connected")
    expect(projector.locator("#scene")).to_be_hidden()
    assert (
        projector.locator("body").evaluate("el => getComputedStyle(el).backgroundColor")
        == "rgb(0, 0, 0)"
    )
    director = context.new_page()
    director.set_viewport_size({"width": 390, "height": 844})
    director.goto(f"{server}/director")
    expect(director.get_by_role("button", name="Show entrance")).to_be_enabled()
    expect(director.get_by_role("heading", name="Entrance & courtyard")).to_be_visible()
    director.get_by_role("button", name="Show entrance").click()
    expect(projector.locator("#scene")).to_be_visible()
    assert projector.locator("#scene").evaluate("el => el.naturalWidth") == 320
    director.get_by_role("button", name="Blackout").click()
    expect(projector.locator("#scene")).to_be_hidden()
    director.get_by_role("button", name="Show entrance").click()
    expect(projector.locator("#scene")).to_be_visible()

    external = os.environ.get(
        "EXTERNAL_IMAGE_URL", "https://www.python.org/static/community_logos/python-logo.png"
    )
    builder.get_by_role("button", name="+ Add image button").click()
    builder.get_by_label("Button label").nth(1).fill("Show external image")
    builder.get_by_label("Image source").nth(1).select_option("external")
    builder.get_by_label("External image URL").nth(1).fill(external)
    builder.get_by_role("button", name="Save campaign").click()
    expect(builder.locator("#status")).to_contain_text("Campaign saved")
    director.reload()
    expect(director.get_by_role("button", name="Show external image")).to_be_enabled()
    director.get_by_role("button", name="Show external image").click()
    expect(projector.locator("#scene")).to_have_attribute("src", external)
    expect(projector.locator("#scene")).to_be_visible(timeout=20000)
    assert projector.locator("#scene").evaluate("el => el.naturalWidth") > 0

    # A fresh projector receives no old display state.
    projector.reload()
    expect(projector.locator("#connection")).to_have_text("Connected")
    expect(projector.locator("#scene")).to_be_hidden()
    director.get_by_role("button", name="Show entrance").click()
    expect(projector.locator("#scene")).to_be_visible()
    for page in (builder, director):
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    artifacts = ROOT / "test-results"
    artifacts.mkdir(exist_ok=True)
    builder.screenshot(path=str(artifacts / "builder.png"), full_page=True)
    director.screenshot(path=str(artifacts / "director-mobile.png"), full_page=True)
    projector.screenshot(path=str(artifacts / "projector.png"))
    assert errors == []
    context.close()


def test_builder_delete_and_error_feedback(browser, server):
    from playwright.sync_api import expect

    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(f"{server}/builder")
    expect(page.locator("#save")).to_be_enabled()
    initial_dungeons = page.get_by_label("Dungeon name").count()
    page.get_by_role("button", name="+ Add dungeon").click()
    page.get_by_label("Dungeon name").last.fill("Disposable dungeon")
    dungeon = page.locator(".dungeon").last
    dungeon.get_by_role("button", name="+ Add room", exact=True).click()
    dungeon.get_by_label("Room name").fill("Disposable room")
    dungeon.get_by_role("button", name="+ Add image button").click()
    dungeon.get_by_label("Button label").fill("Disposable button")
    dungeon.get_by_label("Image file").set_input_files(
        {"name": "fake.png", "mimeType": "image/png", "buffer": b"not an image"}
    )
    expect(page.locator("#status")).to_contain_text("Choose a valid")
    expect(page.locator("#save")).to_be_enabled()
    page.on("dialog", lambda dialog: dialog.accept())
    dungeon.get_by_role("button", name="Delete button").click()
    expect(dungeon.locator(".image-button")).to_have_count(0)
    dungeon.get_by_role("button", name="Delete room").click()
    expect(dungeon.locator(".room")).to_have_count(0)
    dungeon.get_by_role("button", name="Delete dungeon").click()
    expect(page.get_by_label("Dungeon name")).to_have_count(initial_dungeons)
    page.get_by_role("button", name="Save campaign").click()
    expect(page.locator("#status")).to_contain_text("Campaign saved")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.close()
