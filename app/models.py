"""The campaign and the two commands shared by all three views."""

from typing import Annotated, Literal
from urllib.parse import unquote, urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    TypeAdapter,
    model_validator,
)


def image_url(value: str) -> str:
    if not value or any(c.isspace() or ord(c) < 32 for c in value) or "\\" in value:
        raise ValueError("Use a local image URI or a complete HTTP(S) image URL")
    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https"}:
        TypeAdapter(HttpUrl).validate_python(value)
        if not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("Image URLs must have a host and no credentials")
    elif (
        not value.startswith("/")
        or value.startswith("//")
        or parsed.scheme
        or parsed.netloc
        or any(part in {".", ".."} for part in unquote(parsed.path).split("/"))
    ):
        raise ValueError("Use a local image URI or a complete HTTP(S) image URL")
    return value


Nonempty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ImageURL = Annotated[str, AfterValidator(image_url)]


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImageButton(Schema):
    id: Nonempty
    label: Nonempty
    url: ImageURL


class Room(Schema):
    id: Nonempty
    name: Nonempty
    buttons: list[ImageButton]


class Dungeon(Schema):
    id: Nonempty
    name: Nonempty
    rooms: list[Room]


class Campaign(Schema):
    dungeons: list[Dungeon]

    @model_validator(mode="after")
    def unique_ids(self):
        ids = []
        for dungeon in self.dungeons:
            ids.append(dungeon.id)
            for room in dungeon.rooms:
                ids.append(room.id)
                ids.extend(button.id for button in room.buttons)
        if len(ids) != len(set(ids)):
            raise ValueError("Each dungeon, room, and button must have a unique ID")
        return self


class Show(Schema):
    action: Literal["show"]
    url: ImageURL


class Blackout(Schema):
    action: Literal["blackout"]


command_adapter = TypeAdapter(Annotated[Show | Blackout, Field(discriminator="action")])
