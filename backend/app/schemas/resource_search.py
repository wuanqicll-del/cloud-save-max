from __future__ import annotations

from pydantic import BaseModel, Field


class ResourceSearchSourceItemOut(BaseModel):
    key: str = Field(min_length=1, max_length=32)
    enabled: bool
    server: str | None = Field(default=None, max_length=512)
    username: str | None = Field(default=None, max_length=256)
    password: str | None = Field(default=None, max_length=256)
    token: str | None = Field(default=None, max_length=2048)


class ResourceSearchSourceListOut(BaseModel):
    sources: list[ResourceSearchSourceItemOut] = []


class ResourceSearchSourceUpdateIn(BaseModel):
    enabled: bool | None = None
    server: str | None = Field(default=None, max_length=512)
    username: str | None = Field(default=None, max_length=256)
    password: str | None = Field(default=None, max_length=256)
    token: str | None = Field(default=None, max_length=2048)


class TaskSuggestionItemOut(BaseModel):
    taskname: str = Field(default="", max_length=512)
    shareurl: str = Field(default="", max_length=2048)
    content: str | None = None
    datetime: str | None = None
    channel: str | None = None
    source: str | None = None
    share_author_name: str | None = None
    is_preferred_sharer: bool = Field(default=False, description="是否为优选分享者")


class TaskSuggestionListOut(BaseModel):
    success: bool = True
    data: list[TaskSuggestionItemOut] = []
    message: str | None = None
