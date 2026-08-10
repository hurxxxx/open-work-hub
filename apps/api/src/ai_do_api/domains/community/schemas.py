from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


def _camel_config() -> ConfigDict:
    return ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


def _stripped_nonblank(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("must not be blank")
    return stripped


class CommunityChannelOut(BaseModel):
    model_config = _camel_config()

    id: str
    key: str
    name: str
    description: str
    position: int
    active: bool
    read_only: bool
    force_anonymous: bool
    admin_only_content: bool
    template_title: str
    template_body: str


class CommunityChannelsResponse(BaseModel):
    model_config = _camel_config()

    channels: list[CommunityChannelOut]


class CommunityChannelCreateRequest(BaseModel):
    model_config = _camel_config()

    key: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
    )
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(default="", max_length=5000)
    position: int = Field(default=0, ge=0)
    active: bool = True
    read_only: bool = False
    force_anonymous: bool = False
    admin_only_content: bool = False
    template_title: str = Field(default="", max_length=240)
    template_body: str = Field(default="", max_length=20000)

    _strip_required = field_validator("key", "name")(_stripped_nonblank)
    _strip_description = field_validator("description")(lambda value: value.strip())
    _strip_template_title = field_validator("template_title")(lambda value: value.strip())
    _strip_template_body = field_validator("template_body")(lambda value: value.strip())


class CommunityChannelUpdateRequest(CommunityChannelCreateRequest):
    pass


class CommunityCommentOut(BaseModel):
    model_config = _camel_config()

    id: str
    body: str
    is_anonymous: bool
    is_deleted: bool
    parent_comment_id: str | None = None
    author_name: str | None = None
    anon_seq: int | None = None
    can_modify: bool = False
    created_at: datetime
    updated_at: datetime


class CommunityPostOut(BaseModel):
    model_config = _camel_config()

    id: str
    channel_key: str
    title: str
    body: str
    is_anonymous: bool
    is_secret: bool
    locked: bool
    locked_reason: str | None = None
    is_read: bool
    is_mine: bool
    can_modify: bool
    author_name: str | None = None
    comment_count: int
    created_at: datetime
    updated_at: datetime


class CommunityPostDetail(CommunityPostOut):
    comments: list[CommunityCommentOut] = Field(default_factory=list)


class CommunityPostListResponse(BaseModel):
    model_config = _camel_config()

    posts: list[CommunityPostOut]
    total: int
    page: int
    page_size: int


class CommunityMediaResolveRequest(BaseModel):
    model_config = _camel_config()

    urls: list[str]
    password: str | None = Field(default=None, max_length=200)


class CommunityMediaResolveResponse(BaseModel):
    model_config = _camel_config()

    resolved: dict[str, str]


class CommunityPostCreateRequest(BaseModel):
    model_config = _camel_config()

    title: str = Field(..., min_length=1, max_length=240)
    body: str = Field(..., min_length=1, max_length=20000)
    is_anonymous: bool = False
    is_secret: bool = False
    password: str | None = Field(default=None, max_length=200)

    _strip = field_validator("title", "body")(_stripped_nonblank)


class CommunityPostUpdateRequest(BaseModel):
    model_config = _camel_config()

    title: str = Field(..., min_length=1, max_length=240)
    body: str = Field(..., min_length=1, max_length=20000)

    _strip = field_validator("title", "body")(_stripped_nonblank)


class CommunityUnlockRequest(BaseModel):
    model_config = _camel_config()

    password: str = Field(..., min_length=1, max_length=200)


class CommunityCommentCreateRequest(BaseModel):
    model_config = _camel_config()

    body: str = Field(..., min_length=1, max_length=10000)
    is_anonymous: bool = False
    password: str | None = Field(default=None, max_length=200)
    parent_comment_id: str | None = None

    _strip = field_validator("body")(_stripped_nonblank)


class CommunityCommentUpdateRequest(BaseModel):
    model_config = _camel_config()

    body: str = Field(..., min_length=1, max_length=10000)

    _strip = field_validator("body")(_stripped_nonblank)
