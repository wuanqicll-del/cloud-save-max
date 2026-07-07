from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.tmdb_setting import TMDBSetting


DEFAULT_TMDB_SETTING_ID = 1


def get_or_create_tmdb_setting(db: Session) -> TMDBSetting:
    item = db.get(TMDBSetting, DEFAULT_TMDB_SETTING_ID)
    if item is not None:
        return item
    item = TMDBSetting(id=DEFAULT_TMDB_SETTING_ID, config_json=json.dumps({}, ensure_ascii=False))
    db.add(item)
    db.flush()
    return item


def _load_json(payload: str | None) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        data = json.loads(payload)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def load_tmdb_config(item: TMDBSetting) -> dict[str, Any]:
    raw = _load_json(item.config_json)
    api_key = str(raw.get("api_key") or "").strip()
    return {
        "has_api_key": bool(api_key),
        "language": str(raw.get("language") or "zh-CN"),
        "poster_language": str(raw.get("poster_language") or "zh-CN"),
    }


def get_tmdb_runtime_config(item: TMDBSetting) -> dict[str, Any]:
    raw = _load_json(item.config_json)
    api_key = str(raw.get("api_key") or "").strip()
    return {
        "api_key": api_key,
        "language": str(raw.get("language") or "zh-CN"),
        "poster_language": str(raw.get("poster_language") or "zh-CN"),
    }


def update_tmdb_setting(db: Session, *, payload: dict[str, Any] | None = None) -> TMDBSetting:
    item = get_or_create_tmdb_setting(db)
    if payload is None:
        return item

    raw = _load_json(item.config_json)

    if "language" in payload and payload.get("language") is not None:
        raw["language"] = str(payload.get("language") or "").strip() or "zh-CN"

    if "poster_language" in payload and payload.get("poster_language") is not None:
        raw["poster_language"] = str(payload.get("poster_language") or "").strip() or "zh-CN"

    if "api_key" in payload:
        api_key = payload.get("api_key")
        if api_key is not None:
            value = str(api_key).strip()
            if value:
                raw["api_key"] = value



    item.config_json = json.dumps(raw, ensure_ascii=False)
    db.flush()
    return item
