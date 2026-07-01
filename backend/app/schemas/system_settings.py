from __future__ import annotations

from pydantic import BaseModel, Field


class SystemSettingOut(BaseModel):
    preferred_sharers: str = Field(default="", description="优选分享者列表，多个昵称用竖线分隔")
    blocked_sharers: str = Field(default="", description="屏蔽分享者列表，多个昵称用竖线分隔")
    validate_batch_size: int = Field(default=5, description="搜索验证并行数")
    preview_cache_ttl_seconds: int = Field(default=300, description="文件列表缓存时长（秒）")


class SystemSettingUpdateIn(BaseModel):
    preferred_sharers: str | None = Field(default=None, description="优选分享者列表，多个昵称用竖线分隔")
    blocked_sharers: str | None = Field(default=None, description="屏蔽分享者列表，多个昵称用竖线分隔")
    validate_batch_size: int | None = Field(default=None, description="搜索验证并行数")
    preview_cache_ttl_seconds: int | None = Field(default=None, description="文件列表缓存时长（秒）")
