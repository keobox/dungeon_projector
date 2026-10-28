import asyncio
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app
from app.ws_manager import ConnectionManager


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        image_storage_path=tmp_path / "images",
        campaign_path=tmp_path / "campaign.json",
        image_base_uri="/images/",
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def png():
    image = io.BytesIO()
    Image.new("RGB", (48, 32), "forestgreen").save(image, "PNG")
    return image.getvalue()


def campaign(url="/images/entrance.png"):
    return {
        "dungeons": [
            {
                "id": "dungeon-1",
                "name": "The Keep",
                "rooms": [
                    {
                        "id": "room-1",
                        "name": "Entrance",
                        "buttons": [{"id": "button-1", "label": "Show entrance", "url": url}],
                    }
                ],
            }
        ]
    }


def test_initial_campaign_and_views(client, settings):
    assert client.get("/api/campaign").json() == {"dungeons": []}
    assert json.loads(settings.campaign_path.read_text()) == {"dungeons": []}
    assert client.get("/", follow_redirects=False).headers["location"] == "/director"
    for view in ("builder", "director", "projector"):
        response = client.get(f"/{view}")
        assert response.status_code == 200
        assert f"/static/js/{view}.js" in response.text
    assert client.get("/static/css/app.css").status_code == 200


def test_upload_save_and_restart(client, settings, png):
    response = client.post("/api/upload", files={"file": ("../../evil.html", png, "image/png")})
    assert response.status_code == 201
    url = response.json()["url"]
    assert url.startswith("/images/") and url.endswith(".png")
    assert "evil" not in url
    assert client.get(url).content == png
    other = client.post("/api/upload", files={"file": ("../../evil.html", png, "image/png")})
    assert other.json()["url"] != url
    saved = campaign(url)
    assert client.post("/api/campaign", json=saved).json() == saved
    assert client.get("/api/campaign").json() == saved
    # A new application instance reads the same data without resaving/uploading.
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get("/api/campaign").json() == saved
        assert restarted.get(url).content == png


@pytest.mark.parametrize(
    "invalid",
    [
        {},
        {"dungeons": None},
        {"dungeons": [], "extra": True},
        {"dungeons": [{"id": "", "name": "A", "rooms": []}]},
        {"dungeons": [{"id": "d", "name": "  ", "rooms": []}]},
        {"dungeons": [{"id": "d", "name": "A"}]},
        {
            "dungeons": [
                {"id": "d", "name": "A", "rooms": [{"id": "d", "name": "B", "buttons": []}]}
            ]
        },
        campaign("javascript:alert(1)"),
        campaign("//other-host/image.png"),
        campaign("/images/../campaign.json"),
        campaign("data:image/png;base64,abc"),
        campaign("https://"),
        campaign("https://example.com/a b.png"),
    ],
)
def test_invalid_campaign_does_not_overwrite(client, settings, invalid):
    client.post("/api/campaign", json=campaign())
    before = settings.campaign_path.read_bytes()
    assert client.post("/api/campaign", json=invalid).status_code == 422
    assert settings.campaign_path.read_bytes() == before


def test_external_url_and_order_roundtrip(client):
    saved = campaign("https://example.org/image.png?size=large&v=2")
    saved["dungeons"].append({"id": "empty", "name": "Empty dungeon", "rooms": []})
    saved["dungeons"][0]["rooms"].append({"id": "empty-room", "name": "Empty room", "buttons": []})
    assert client.post("/api/campaign", json=saved).status_code == 200
    assert client.get("/api/campaign").json() == saved
    assert client.post("/api/campaign", json={"dungeons": []}).status_code == 200


@pytest.mark.parametrize("data", [b"", b"<html>Not an image</html>", b"\x89PNG\r\n\x1a\ninvalid"])
def test_invalid_upload_is_removed(client, settings, data):
    response = client.post("/api/upload", files={"file": ("fake.png", data, "image/png")})
    assert response.status_code == 415
    assert list(settings.image_storage_path.iterdir()) == []


def test_oversize_upload_is_removed(client, settings, monkeypatch):
    monkeypatch.setattr("app.main.MAX_UPLOAD_BYTES", 16)
    response = client.post("/api/upload", files={"file": ("big.png", b"x" * 17, "image/png")})
    assert response.status_code == 413
    assert list(settings.image_storage_path.iterdir()) == []


@pytest.mark.parametrize("base", ["/assets/scenes/", "https://cdn.example.org/scenes/"])
def test_configurable_storage_and_uri(settings, png, base):
    settings.image_base_uri = base
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/upload", files={"file": ("test.png", png, "image/png")})
        url = response.json()["url"]
        assert url.startswith(base)
        filename = url.rsplit("/", 1)[1]
        assert (settings.image_storage_path / filename).read_bytes() == png
        local = url if base.startswith("/") else f"/images/{filename}"
        assert client.get(local).content == png


def test_settings_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("IMAGE_STORAGE_PATH", str(tmp_path / "custom"))
    monkeypatch.setenv("IMAGE_BASE_URI", "/pictures")
    monkeypatch.setenv("CAMPAIGN_PATH", str(tmp_path / "custom.json"))
    settings = Settings(_env_file=None)
    assert settings.image_storage_path == tmp_path / "custom"
    assert settings.image_base_uri == "/pictures/"
    assert settings.campaign_path == tmp_path / "custom.json"


@pytest.mark.parametrize("uri", ["/", "/api/images/", "//cdn.example.org/", "/images/?key=a"])
def test_invalid_base_uri(uri):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, image_base_uri=uri)


def test_corrupt_campaign_is_not_reset(settings):
    settings.campaign_path.write_text("corrupt JSON")
    with pytest.raises(ValidationError), TestClient(create_app(settings)):
        pass
    assert settings.campaign_path.read_text() == "corrupt JSON"


def test_websocket_commands_and_invalid_messages(client):
    with (
        client.websocket_connect("/ws/projector") as projector,
        client.websocket_connect("/ws/director") as director,
    ):
        for invalid in [
            "not JSON",
            "[]",
            "null",
            '{"action":"unsupported"}',
            '{"action":"show"}',
            '{"action":"show","url":"javascript:bad"}',
            '{"action":"blackout","url":"/images/a.png"}',
        ]:
            director.send_text(invalid)
            assert "error" in director.receive_json()
        director.send_bytes(b"invalid binary")
        assert "error" in director.receive_json()
        # If anything invalid was broadcast it would be received before this show.
        for message in [
            {"action": "show", "url": "/images/test.png"},
            {"action": "blackout"},
            {"action": "show", "url": "https://example.org/scene.jpg"},
        ]:
            director.send_json(message)
            assert projector.receive_json() == message


def test_projector_cannot_broadcast_and_disconnect_is_safe(client):
    with (
        client.websocket_connect("/ws/director") as director,
        client.websocket_connect("/ws/projector") as first,
    ):
        with client.websocket_connect("/ws/projector") as second:
            first.send_json({"action": "show", "url": "/images/forbidden.png"})
            director.send_json({"action": "blackout"})
            assert first.receive_json() == {"action": "blackout"}
            assert second.receive_json() == {"action": "blackout"}
        director.send_json({"action": "show", "url": "/images/after-disconnect.png"})
        assert first.receive_json()["url"] == "/images/after-disconnect.png"


def test_failed_broadcast_drops_dead_connection():
    class Socket:
        def __init__(self, broken=False):
            self.broken = broken
            self.messages = []

        async def send_json(self, message):
            if self.broken:
                raise OSError("Disconnected")
            self.messages.append(message)

    manager = ConnectionManager()
    good, broken = Socket(), Socket(broken=True)
    manager.connections.update({good, broken})
    asyncio.run(manager.broadcast_image("/images/test.png"))
    assert broken not in manager.connections
    assert good.messages == [{"action": "show", "url": "/images/test.png"}]
