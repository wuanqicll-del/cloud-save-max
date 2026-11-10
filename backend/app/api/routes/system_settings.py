from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_permissions
from app.core.permissions import TASK_READ, TASK_WRITE
from app.db.session import get_db
from app.models.system_setting import SystemSetting
from app.schemas.system_settings import SystemSettingOut, SystemSettingUpdateIn

router = APIRouter()

_SETTINGS_DEFAULTS = {
    "preferred_sharers": "",
    "blocked_sharers": "",
    "validate_batch_size": "5",
    "preview_cache_ttl_seconds": "300",
}


def _get_setting(db: Session, key: str) -> str:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    return row.value if row else _SETTINGS_DEFAULTS.get(key, "")


def _set_setting(db: Session, key: str, value: str, description: str = "") -> None:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(SystemSetting(key=key, value=value, description=description))


@router.get("/sharer-filter", response_model=SystemSettingOut, dependencies=[Depends(require_permissions(TASK_READ))])
def get_sharer_filter_settings(db: Session = Depends(get_db)) -> SystemSettingOut:
    return SystemSettingOut(
        preferred_sharers=_get_setting(db, "preferred_sharers"),
        blocked_sharers=_get_setting(db, "blocked_sharers"),
        validate_batch_size=int(_get_setting(db, "validate_batch_size") or "5"),
        preview_cache_ttl_seconds=int(_get_setting(db, "preview_cache_ttl_seconds") or "300"),
    )


@router.patch("/sharer-filter", response_model=SystemSettingOut, dependencies=[Depends(require_permissions(TASK_WRITE))])
def update_sharer_filter_settings(
    payload: SystemSettingUpdateIn,
    db: Session = Depends(get_db),
) -> SystemSettingOut:
    if payload.preferred_sharers is not None:
        _set_setting(db, "preferred_sharers", payload.preferred_sharers, "优选分享者列表，多个昵称用竖线分隔")
    if payload.blocked_sharers is not None:
        _set_setting(db, "blocked_sharers", payload.blocked_sharers, "屏蔽分享者列表，多个昵称用竖线分隔")
    if payload.validate_batch_size is not None:
        v = max(1, min(20, int(payload.validate_batch_size)))
        _set_setting(db, "validate_batch_size", str(v), "搜索验证并行数")
    if payload.preview_cache_ttl_seconds is not None:
        v = max(30, min(3600, int(payload.preview_cache_ttl_seconds)))
        _set_setting(db, "preview_cache_ttl_seconds", str(v), "文件列表缓存时长（秒）")

    db.commit()

    return SystemSettingOut(
        preferred_sharers=_get_setting(db, "preferred_sharers"),
        blocked_sharers=_get_setting(db, "blocked_sharers"),
        validate_batch_size=int(_get_setting(db, "validate_batch_size") or "5"),
        preview_cache_ttl_seconds=int(_get_setting(db, "preview_cache_ttl_seconds") or "300"),
    )


# ---- 过滤词规则 ----

class FilterWordRule(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    keywords: str = Field(default="", max_length=1024)


class FilterWordRuleListOut(BaseModel):
    rules: list[FilterWordRule] = []


def _load_filter_rules(db: Session) -> list[dict]:
    raw = _get_setting(db, "filter_word_rules")
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


def _save_filter_rules(db: Session, rules: list[dict]) -> None:
    _set_setting(db, "filter_word_rules", json.dumps(rules, ensure_ascii=False), "关键词过滤规则列表")


@router.get("/filter-rules", response_model=FilterWordRuleListOut, dependencies=[Depends(require_permissions(TASK_READ))])
def get_filter_rules(db: Session = Depends(get_db)) -> FilterWordRuleListOut:
    rules = [FilterWordRule(name=r["name"], keywords=r.get("keywords", "")) for r in _load_filter_rules(db)]
    return FilterWordRuleListOut(rules=rules)


@router.put("/filter-rules", response_model=FilterWordRuleListOut, dependencies=[Depends(require_permissions(TASK_WRITE))])
def replace_filter_rules(payload: FilterWordRuleListOut, db: Session = Depends(get_db)) -> FilterWordRuleListOut:
    rules = [{"name": r.name, "keywords": r.keywords} for r in payload.rules]
    _save_filter_rules(db, rules)
    db.commit()
    return payload
