from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.models import image_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    image_storage_path: Path = Path("./data/images")
    image_base_uri: str = "/images/"
    campaign_path: Path = Path("./data/campaign.json")

    @field_validator("image_base_uri")
    @classmethod
    def valid_base_uri(cls, value: str) -> str:
        value = image_url(value)
        if "?" in value or "#" in value or value == "/":
            raise ValueError("IMAGE_BASE_URI must be a directory URI without query or fragment")
        if value.startswith("/") and value.rstrip("/").split("/")[1] in {
            "api",
            "static",
            "ws",
            "builder",
            "director",
            "projector",
            "docs",
            "redoc",
            "openapi.json",
        }:
            raise ValueError("IMAGE_BASE_URI conflicts with an application route")
        return value.rstrip("/") + "/"
