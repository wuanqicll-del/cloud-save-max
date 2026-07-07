from __future__ import annotations

from pydantic import BaseModel, Field


class TMDBConfigOut(BaseModel):
    has_api_key: bool = False
    language: str = Field(default="zh-CN", max_length=32)
    poster_language: str = Field(default="zh-CN", max_length=32)


class TMDBConfigUpdateIn(BaseModel):
    api_key: str | None = Field(default=None, max_length=256)
    language: str | None = Field(default=None, max_length=32)
    poster_language: str | None = Field(default=None, max_length=32)
