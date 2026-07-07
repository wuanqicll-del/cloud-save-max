from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SharePreviewIn(BaseModel):
    shareurl: str = Field(min_length=1)
    account_name: str | None = Field(default=None, max_length=128)
    pdir_fid: str | None = None
    max_items: int = Field(default=200, ge=1, le=2000)
    taskname: str | None = Field(default=None, max_length=255)
    pattern: str | None = Field(default=None, max_length=255)
    replace: str | None = Field(default=None, max_length=255)
    savepath: str | None = Field(default=None, max_length=1024)
    ignore_extension: bool | None = None
    min_size: str | None = Field(default=None, max_length=32)
    filter_words: str | None = Field(default=None, max_length=1024)
    file_filter: str | None = Field(default=None, max_length=1024)
    file_filter_mode: str | None = Field(default=None, max_length=8)
    file_min_date: str | None = Field(default=None, max_length=16)
    dir_min_date: str | None = Field(default=None, max_length=16)
    folder_filter: str | None = Field(default=None, max_length=1024)
    folder_exclude: str | None = Field(default=None, max_length=1024)
    folder_filter_mode: str | None = Field(default=None, max_length=8)
    folder_exclude_mode: str | None = Field(default=None, max_length=8)
    folder_priority: str | None = Field(default=None, max_length=1024)
    folder_priority_mode: str | None = Field(default=None, max_length=8)
    tmdb_id: int | None = None
    tmdb_media_type: str | None = Field(default=None, max_length=16)


class SharePreviewItemOut(BaseModel):
    fid: str
    fid_token: str | None = None
    name: str
    name_re: str | None = None
    is_dir: bool
    updated_at: Any | None = None
    size: int | None = None
    children_count: int | None = None
    file_name: str | None = None
    file_name_re: str | None = None
    file_name_saved: str | None = None
    filtered_by_size: bool | None = None
    filtered_by_keyword: bool | None = None
    filtered_by_file_filter: bool | None = None
    filtered_by_file_date: bool | None = None
    filtered_by_folder: str | None = None
    filtered_by_search: bool | None = None
    priority_match: bool | None = None
    dir: bool | None = None
    include_items: int | None = None


class SharePreviewOut(BaseModel):
    drive_type: str
    suggested_account_name: str | None = None
    pwd_id: str | None = None
    pdir_fid: str | None = None
    share_author_name: str | None = None
    items: list[SharePreviewItemOut] = []


class SharePreviewBatchIn(BaseModel):
    shareurls: list[str] = Field(min_length=1, max_length=50)
    account_name: str | None = Field(default=None, max_length=128)


class ShareValidateIn(BaseModel):
    shareurls: list[str] = Field(min_length=1)


class ShareValidateItemOut(BaseModel):
    shareurl: str
    ok: bool
    share_author_name: str | None = None
    message: str | None = None


class ShareValidateOut(BaseModel):
    items: list[ShareValidateItemOut] = []


class SharePreviewBatchLatestOut(BaseModel):
    fid: str | None = None
    name: str | None = None
    updated_at: Any | None = None
    size: int | None = None
    season: int | None = None
    episode: int | None = None


class SharePreviewBatchItemOut(BaseModel):
    shareurl: str
    drive_type: str | None = None
    ok: bool
    message: str | None = None
    suggested_account_name: str | None = None
    pdir_fid: str | None = None
    resolved_pdir_fid: str | None = None
    latest_video: SharePreviewBatchLatestOut | None = None
    share_author_name: str | None = None


class SharePreviewBatchOut(BaseModel):
    items: list[SharePreviewBatchItemOut] = []


class DriveBrowseIn(BaseModel):
    dir_path: str = Field(min_length=1, max_length=1024)
    account_name: str | None = Field(default=None, max_length=128)
    shareurl: str | None = None
    max_items: int = Field(default=200, ge=1, le=2000)


class DriveBrowseItemOut(BaseModel):
    fid: str
    name: str
    is_dir: bool
    updated_at: Any | None = None
    size: int | None = None
    include_items: int | None = None
    file_name: str | None = None
    dir: bool | None = None


class DriveBrowsePathOut(BaseModel):
    fid: str
    name: str


class DriveBrowseOut(BaseModel):
    account_name: str
    drive_type: str | None = None
    dir_path: str
    exists: bool = True
    pdir_fid: str | None = None
    items: list[DriveBrowseItemOut] = []
    paths: list[DriveBrowsePathOut] = []


class DriveMkdirIn(BaseModel):
    dir_path: str = Field(min_length=1, max_length=1024)
    account_name: str | None = Field(default=None, max_length=128)
    shareurl: str | None = None


class DriveMkdirOut(BaseModel):
    account_name: str
    dir_path: str
    response: dict[str, Any] = {}
