import os
import tempfile
import warnings
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, UploadFile, WebSocket
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from app.config import Settings
from app.models import Campaign, Show, command_adapter
from app.ws_manager import ConnectionManager

ROOT = Path(__file__).resolve().parent.parent
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
IMAGE_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "GIF": ".gif", "WEBP": ".webp"}


def save_campaign(path: Path, campaign: Campaign):
    """Replace only after the complete, validated file has been written."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(campaign.model_dump_json(indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    manager = ConnectionManager()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.image_storage_path.mkdir(parents=True, exist_ok=True)
        settings.campaign_path.parent.mkdir(parents=True, exist_ok=True)
        if not settings.campaign_path.exists():
            save_campaign(settings.campaign_path, Campaign(dungeons=[]))
        # Fail clearly rather than silently discarding an unreadable saved campaign.
        Campaign.model_validate_json(settings.campaign_path.read_text(encoding="utf-8"))
        yield

    app = FastAPI(title="Dungeon Projector", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    image_mount = (
        settings.image_base_uri.rstrip("/")
        if settings.image_base_uri.startswith("/")
        else "/images"
    )
    app.mount(
        image_mount,
        StaticFiles(directory=settings.image_storage_path, check_dir=False),
        name="images",
    )

    @app.get("/")
    def home():
        return RedirectResponse("/director")

    @app.get("/builder")
    def builder():
        return FileResponse(ROOT / "app/templates/builder.html")

    @app.get("/director")
    def director():
        return FileResponse(ROOT / "app/templates/director.html")

    @app.get("/projector")
    def projector():
        return FileResponse(ROOT / "app/templates/projector.html")

    @app.get("/api/campaign", response_model=Campaign)
    def get_campaign():
        try:
            return Campaign.model_validate_json(settings.campaign_path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as exc:
            raise HTTPException(
                500, "Cannot read the saved campaign; check the server's data file"
            ) from exc

    @app.post("/api/campaign", response_model=Campaign)
    def post_campaign(campaign: Campaign):
        save_campaign(settings.campaign_path, campaign)
        return campaign

    @app.post("/api/upload", status_code=201)
    def upload(file: UploadFile):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=settings.image_storage_path, delete=False
            ) as stream:
                temporary = Path(stream.name)
                size = 0
                while chunk := file.file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(413, "Images must be 20 MiB or smaller")
                    stream.write(chunk)
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(temporary) as picture:
                        extension = IMAGE_FORMATS.get(picture.format)
                        picture.verify()
                if extension is None:
                    raise ValueError("Unsupported image format")
            except (
                UnidentifiedImageError,
                OSError,
                ValueError,
                SyntaxError,
                Image.DecompressionBombError,
                Image.DecompressionBombWarning,
            ) as exc:
                raise HTTPException(415, "Choose a valid PNG, JPEG, GIF, or WebP image") from exc
            filename = f"{uuid4().hex}{extension}"
            temporary.replace(settings.image_storage_path / filename)
            return {"url": settings.image_base_uri + filename}
        finally:
            file.file.close()
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @app.websocket("/ws/director")
    async def director_socket(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
                try:
                    command = command_adapter.validate_json(message.get("text", ""))
                except (ValidationError, ValueError):
                    await websocket.send_json({"error": "Send a valid show URL or blackout action"})
                    continue
                if isinstance(command, Show):
                    await manager.broadcast_image(command.url)
                else:
                    await manager.broadcast_command(command.action)
        except WebSocketDisconnect:
            pass

    @app.websocket("/ws/projector")
    async def projector_socket(websocket: WebSocket):
        await manager.connect(websocket)
        try:
            while True:
                # Projectors cannot send commands, but reading observes disconnects.
                if (await websocket.receive())["type"] == "websocket.disconnect":
                    break
        except WebSocketDisconnect:
            pass
        finally:
            manager.disconnect(websocket)

    return app


app = create_app()
