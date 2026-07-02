from __future__ import annotations

import logging
import os
import random
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

from cachetools import TTLCache
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.core.settings import settings
from app.db.session import SessionLocal
from app.extensions.runtime.account_manager import DatabaseAccountManager
from app.extensions.runtime.adapter_registry import AdapterRegistry
from app.models.drive_account import DriveAccount
from app.schemas.task_browse import SharePreviewBatchIn, SharePreviewBatchItemOut, SharePreviewBatchOut
from app.services.invalid_share_links import upsert_invalid_share_link
from app.services.share_preview_batch_cache import (
    get_cached_preview_batch_item,
    purge_old_preview_batch_cache,
    upsert_preview_batch_cache,
)


_share_preview_batch_cache = TTLCache(
    maxsize=max(1, int(getattr(settings, "tasks_share_preview_batch_cache_max_entries", 2000) or 2000)),
    ttl=max(1, int(getattr(settings, "tasks_share_preview_batch_cache_ttl_seconds", 300) or 300)),
)
_share_preview_batch_cache_lock = threading.Lock()

# 验证结果缓存
_validate_cache_ttl = 300
_validate_cache: TTLCache[str, Any] = TTLCache(maxsize=2000, ttl=_validate_cache_ttl)
_validate_cache_lock = threading.Lock()


def _get_validate_cache_ttl() -> int:
    try:
        from app.models.system_setting import SystemSetting
        with SessionLocal() as db:
            row = db.query(SystemSetting).filter(SystemSetting.key == "preview_cache_ttl_seconds").first()
            if row and row.value:
                return max(30, min(3600, int(row.value)))
    except Exception:
        pass
    return 300


def _update_validate_cache_ttl() -> None:
    global _validate_cache, _validate_cache_ttl
    ttl = _get_validate_cache_ttl()
    if ttl != _validate_cache_ttl:
        _validate_cache_ttl = ttl
        _validate_cache = TTLCache(maxsize=2000, ttl=ttl)


def cache_clear() -> None:
    with _share_preview_batch_cache_lock:
        _share_preview_batch_cache.clear()
    with _validate_cache_lock:
        _validate_cache.clear()


def _share_preview_batch_cache_get(*, shareurl: str) -> SharePreviewBatchItemOut | None:
    key = shareurl
    with _share_preview_batch_cache_lock:
        hit = _share_preview_batch_cache.get(key)
    if hit is None:
        return None
    return hit.model_copy()


def _share_preview_batch_cache_set(*, shareurl: str, item: SharePreviewBatchItemOut) -> None:
    key = shareurl
    with _share_preview_batch_cache_lock:
        _share_preview_batch_cache[key] = item


def _should_persist_invalid_share_link(message: str | None) -> bool:
    msg = str(message or "").strip()
    if not msg:
        return False
    lowered = msg.lower()
    if any(
        x in lowered
        for x in (
            "timeout",
            "timed out",
            "connectionerror",
            "connecterror",
            "readtimeout",
            "proxyerror",
            "connection reset",
            "name or service not known",
            "temporary failure",
        )
    ):
        return False
    if any(x in msg for x in ("超时", "连接超时", "网络", "连接失败", "连接被重置")):
        return False
    if "没有可用的驱动账号" in msg:
        return False
    if "指定账号不存在" in msg:
        return False
    if "登录失败" in msg:
        return False
    if "响应解析失败" in msg:
        return False
    if "cookie" in lowered and any(x in msg for x in ("失效", "过期", "被限流", "限流")):
        return False
    if any(x in msg for x in ("被限流", "限流")) or any(x in lowered for x in ("rate limit", "ratelimit", "too many requests")):
        return False
    return True


def _bool_is_dir(payload: dict) -> bool:
    if payload.get("is_dir") is not None:
        return bool(payload.get("is_dir"))
    if payload.get("isdir") is not None:
        return str(payload.get("isdir")) in ("1", "true", "True")
    if payload.get("dir") is not None:
        return bool(payload.get("dir"))
    if payload.get("kind") in ("folder", "dir", "directory"):
        return True
    if payload.get("kind") in ("file",):
        return False
    if payload.get("type") in ("folder", "dir"):
        return True
    if payload.get("type") in ("file",):
        return False
    if payload.get("file_type") is not None:
        value = str(payload.get("file_type"))
        if value in ("0", "dir", "folder"):
            return True
        if value in ("1", "file"):
            return False
    return False


def _pick_name(payload: dict) -> str:
    return str(
        payload.get("file_name")
        or payload.get("server_filename")
        or payload.get("fileName")
        or payload.get("name")
        or payload.get("title")
        or payload.get("fid")
        or payload.get("fs_id")
        or ""
    )


def _pick_fid(payload: dict) -> str:
    return str(payload.get("fid") or payload.get("fs_id") or payload.get("file_id") or payload.get("id") or payload.get("fileId") or "")


def _pick_updated_at(payload: dict):
    return payload.get("updated_at") or payload.get("update_time") or payload.get("mtime") or payload.get("modified_at")


def _pick_size(payload: dict) -> int | None:
    if payload.get("size") is None:
        return None
    try:
        return int(payload.get("size"))
    except (TypeError, ValueError):
        return None


video_exts = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".webm",
    ".m4v",
    ".ts",
    ".m2ts",
    ".mpg",
    ".mpeg",
    ".3gp",
    ".cas",
}


def _is_video_name(name: str) -> bool:
    try:
        _base, _ext = os.path.splitext(str(name or ""))
    except Exception:
        return False
    return bool(_ext) and _ext.lower() in video_exts


def _to_ts(v):
    try:
        return float(v)
    except Exception:
        return None


def _auto_resolve_latest_video(adapter, pwd_id: str, stoken: str, start_fid: str) -> tuple[str, dict | None]:
    current_fid = str(start_fid or "").strip()
    latest: dict | None = None
    for _depth in range(10):
        detail = adapter.get_detail(pwd_id, stoken, current_fid)
        raw_items = (((detail or {}).get("data") or {}).get("list")) or []
        files = [x for x in raw_items if not _bool_is_dir(x)]
        videos = [x for x in files if _is_video_name(_pick_name(x))]
        if videos:
            videos.sort(key=lambda x: _to_ts(_pick_updated_at(x)) or 0, reverse=True)
            hit = videos[0]
            latest = {
                "fid": _pick_fid(hit) or None,
                "name": _pick_name(hit) or None,
                "updated_at": _pick_updated_at(hit),
                "size": _pick_size(hit),
            }
            break
        dirs = [x for x in raw_items if _bool_is_dir(x)]
        if not dirs:
            break
        if len(dirs) > 1:
            dirs.sort(key=lambda x: _to_ts(_pick_updated_at(x)) or 0, reverse=True)
        next_dir = dirs[0]
        next_fid = str(_pick_fid(next_dir) or "").strip()
        if not next_fid or next_fid == current_fid:
            break
        current_fid = next_fid
    return current_fid, latest


def fetch_share_file_list(
    db: Session,
    shareurl: str,
    account_name: str | None = None,
    max_depth: int = 3,
    folder_filter: str = "",
    folder_exclude: str = "",
    folder_filter_mode: str = "",
    folder_exclude_mode: str = "",
) -> tuple[list[dict[str, Any]], bool]:
    """获取分享链接的完整文件列表（只遍历前几层目录）"""
    from app.extensions.runtime.account_manager import DatabaseAccountManager

    drive_type = AdapterRegistry.detect_drive_type(shareurl)
    if drive_type is None:
        return [], False

    if not account_name:
        rows = (
            db.execute(select(DriveAccount).where(DriveAccount.enabled.is_(True), DriveAccount.drive_type == drive_type).order_by(DriveAccount.id.asc()))
            .scalars()
            .all()
        )
        rows.sort(
            key=lambda x: (
                0 if bool(getattr(x, "is_default", False)) else 1,
                0 if str(getattr(x, "runtime_status", "") or "") == "active" else 1,
                int(getattr(x, "id", 0) or 0),
            )
        )
        if not rows:
            return [], False
        account_name = str(getattr(rows[0], "name", "") or "").strip()

    manager = DatabaseAccountManager(db, no_login=True)
    task_payload = {"shareurl": shareurl, "account_name": account_name}
    adapter = manager.get_adapter_for_task(task_payload, allow_inactive=True)
    if adapter is None:
        return [], False

    if not bool(getattr(adapter, "is_active", False)):
        try:
            adapter.init()
        except Exception:
            return [], False

    try:
        pwd_id, passcode, extracted_pdir_fid, _ = adapter.extract_url(shareurl)
    except Exception:
        return [], False

    if not pwd_id:
        return [], False

    try:
        token_response = adapter.get_stoken(pwd_id, passcode or "")
    except Exception:
        return [], False

    stoken = ((token_response or {}).get("data") or {}).get("stoken")
    if not stoken:
        return [], False

    all_files: list[dict[str, Any]] = []
    changed = False
    folder_keywords = [kw.strip().lower() for kw in folder_filter.split("|") if kw.strip()] if folder_filter else []
    folder_exclude_keywords = [kw.strip().lower() for kw in folder_exclude.split("|") if kw.strip()] if folder_exclude else []
    folder_filter_is_any = str(folder_filter_mode or "all").strip().lower() == "any"
    folder_exclude_is_all = str(folder_exclude_mode or "any").strip().lower() == "all"

    def _collect_files(fid: str, depth: int, is_root: bool = True) -> None:
        nonlocal changed
        if depth > max_depth:
            return
        try:
            detail = adapter.get_detail(pwd_id, stoken, fid)
        except Exception:
            return
        raw_items = (((detail or {}).get("data") or {}).get("list")) or []
        if raw_items:
            changed = True
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            name = str(_pick_name(item) or "").strip()
            is_dir = bool(_bool_is_dir(item))
            if is_dir:
                sub_fid = str(_pick_fid(item) or "").strip()
                if not sub_fid or sub_fid == fid:
                    continue
                name_lower = name.lower()
                # 过滤：包含关键词的目录直接跳过，不进入
                if folder_exclude_keywords:
                    if folder_exclude_is_all:
                        if all(kw in name_lower for kw in folder_exclude_keywords):
                            continue
                    else:
                        if any(kw in name_lower for kw in folder_exclude_keywords):
                            continue
                # 递归进入子目录（无论是否匹配筛选词）
                _collect_files(sub_fid, depth + 1, is_root=False)
            else:
                all_files.append({
                    "file_name": name,
                    "is_dir": False,
                    "size": _pick_size(item),
                    "updated_at": _pick_updated_at(item),
                })

    _collect_files(extracted_pdir_fid or "", 1, is_root=True)
    return all_files, changed, extracted_pdir_fid


def fetch_share_file_list_grouped(
    db: Session,
    shareurl: str,
    account_name: str | None = None,
    max_depth: int = 3,
    folder_filter: str = "",
    folder_exclude: str = "",
    folder_filter_mode: str = "",
    folder_exclude_mode: str = "",
) -> list[tuple[list[dict[str, Any]], str, Any]]:
    """按子目录分组返回文件列表和目录标识。
    链接有 fid 时返回一组，无 fid 时每个子目录一组。"""
    from app.extensions.runtime.account_manager import DatabaseAccountManager

    drive_type = AdapterRegistry.detect_drive_type(shareurl)
    if drive_type is None:
        return []

    if not account_name:
        rows = (
            db.execute(select(DriveAccount).where(DriveAccount.enabled.is_(True), DriveAccount.drive_type == drive_type).order_by(DriveAccount.id.asc()))
            .scalars()
            .all()
        )
        rows.sort(
            key=lambda x: (
                0 if bool(getattr(x, "is_default", False)) else 1,
                0 if str(getattr(x, "runtime_status", "") or "") == "active" else 1,
                int(getattr(x, "id", 0) or 0),
            )
        )
        if not rows:
            return []
        account_name = str(getattr(rows[0], "name", "") or "").strip()

    manager = DatabaseAccountManager(db, no_login=True)
    task_payload = {"shareurl": shareurl, "account_name": account_name}
    adapter = manager.get_adapter_for_task(task_payload, allow_inactive=True)
    if adapter is None:
        return []

    if not bool(getattr(adapter, "is_active", False)):
        try:
            adapter.init()
        except Exception:
            return []

    try:
        pwd_id, passcode, extracted_pdir_fid, _ = adapter.extract_url(shareurl)
    except Exception:
        return []

    if not pwd_id:
        return []

    try:
        token_response = adapter.get_stoken(pwd_id, passcode or "")
    except Exception:
        return []

    stoken = ((token_response or {}).get("data") or {}).get("stoken")
    if not stoken:
        return []

    folder_keywords = [kw.strip().lower() for kw in folder_filter.split("|") if kw.strip()] if folder_filter else []
    folder_exclude_keywords = [kw.strip().lower() for kw in folder_exclude.split("|") if kw.strip()] if folder_exclude else []
    folder_filter_is_any = str(folder_filter_mode or "all").strip().lower() == "any"
    folder_exclude_is_all = str(folder_exclude_mode or "any").strip().lower() == "all"

    def _collect_from_dir(fid: str, dir_ts: Any = None, dir_name: str = "") -> list[tuple[list[dict[str, Any]], str, Any]]:
        """收集目录下的文件，按层级分组返回。
        当目录同时有文件和子目录时，文件单独一组，子目录各自递归成组。
        不匹配筛选词的目录仍会递归进入，但不收集该层的文件。"""

        def _walk(f: str, depth: int, f_ts: Any, f_name: str = "", is_root: bool = True) -> list[tuple[list[dict[str, Any]], str, Any]]:
            groups: list[tuple[list[dict[str, Any]], str, Any]] = []
            if depth > max_depth:
                return groups
            try:
                detail = adapter.get_detail(pwd_id, stoken, f)
            except Exception:
                return groups
            raw_items = (((detail or {}).get("data") or {}).get("list")) or []
            local_files: list[dict[str, Any]] = []
            # 判断当前目录是否匹配筛选词
            collect_files = True
            if folder_keywords and f_name:
                name_lower = f_name.lower()
                if folder_filter_is_any:
                    collect_files = any(kw in name_lower for kw in folder_keywords)
                else:
                    collect_files = all(kw in name_lower for kw in folder_keywords)
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                name = str(_pick_name(item) or "").strip()
                is_dir = bool(_bool_is_dir(item))
                if is_dir:
                    sub_fid = str(_pick_fid(item) or "").strip()
                    if not sub_fid or sub_fid == f:
                        continue
                    name_lower = name.lower()
                    # 过滤：包含关键词的目录直接跳过，不进入
                    if folder_exclude_keywords:
                        if folder_exclude_is_all:
                            if all(kw in name_lower for kw in folder_exclude_keywords):
                                continue
                        else:
                            if any(kw in name_lower for kw in folder_exclude_keywords):
                                continue
                    # 递归进入子目录（无论是否匹配筛选词）
                    groups.extend(_walk(sub_fid, depth + 1, _pick_updated_at(item), f_name=name, is_root=False))
                else:
                    local_files.append({
                        "file_name": name,
                        "is_dir": False,
                        "size": _pick_size(item),
                        "updated_at": _pick_updated_at(item),
                    })
            if local_files and collect_files:
                groups.append((local_files, f, f_ts))
            return groups

        return _walk(fid, 1, dir_ts, f_name=dir_name, is_root=True)

    # 有 fid 的情况：跟原逻辑一样，返回一组
    if extracted_pdir_fid:
        groups = _collect_from_dir(extracted_pdir_fid)
        if groups:
            return groups
        return []

    # 无 fid 的情况：按根目录下的子目录分组
    try:
        detail = adapter.get_detail(pwd_id, stoken, "")
    except Exception:
        return []

    raw_items = (((detail or {}).get("data") or {}).get("list")) or []
    groups: list[tuple[list[dict[str, Any]], str, Any]] = []

    for item in raw_items:
        if not isinstance(item, dict):
            continue
        is_dir = bool(_bool_is_dir(item))
        if is_dir:
            sub_fid = str(_pick_fid(item) or "").strip()
            if not sub_fid:
                continue
            sub_name = str(_pick_name(item) or "").strip()
            sub_groups = _collect_from_dir(sub_fid, _pick_updated_at(item), dir_name=sub_name)
            for g in sub_groups:
                if g[0]:
                    groups.append(g)

    return groups


def preview_share_batch(db: Session, payload: SharePreviewBatchIn) -> tuple[SharePreviewBatchOut, bool]:
    def _short_tx(fn):
        with SessionLocal() as s:
            s.expire_on_commit = False
            try:
                out = fn(s)
                s.commit()
                return out
            except Exception:
                s.rollback()
                raise

    shareurls = [str(x or "").strip() for x in (payload.shareurls or [])]
    shareurls = [x for x in shareurls if x]
    shareurls = list(dict.fromkeys(shareurls))
    if not shareurls:
        return SharePreviewBatchOut(items=[]), False

    cache_changed = False
    try:
        purged = _short_tx(
            lambda s: purge_old_preview_batch_cache(
                s,
                retention_seconds=int(
                    getattr(settings, "tasks_share_preview_batch_db_cache_retention_seconds", 7 * 24 * 60 * 60)
                    or 7 * 24 * 60 * 60
                ),
            )
        )
        if purged > 0:
            cache_changed = True
    except Exception:
        purged = 0

    per_drive: dict[str, list[str]] = {}
    items: list[SharePreviewBatchItemOut] = []
    for url in shareurls:
        cached = _share_preview_batch_cache_get(shareurl=url)
        if cached is not None:
            items.append(cached)
            continue
        try:
            row, hit_changed = _short_tx(lambda s: get_cached_preview_batch_item(s, shareurl=url))
        except Exception:
            row, hit_changed = (None, False)
        if row is not None:
            if not bool(row.ok):
                out = SharePreviewBatchItemOut(shareurl=row.shareurl, drive_type=row.drive_type, ok=bool(row.ok), message=row.message)
                items.append(out)
                _share_preview_batch_cache_set(shareurl=url, item=out)
                if hit_changed:
                    cache_changed = True
                continue
            drive_type = AdapterRegistry.detect_drive_type(url) or row.drive_type
        else:
            drive_type = AdapterRegistry.detect_drive_type(url)
        if drive_type is None:
            items.append(SharePreviewBatchItemOut(shareurl=url, drive_type=None, ok=False, message="无法识别的网盘分享链接"))
            continue
        per_drive.setdefault(str(drive_type), []).append(url)

    if not per_drive:
        return SharePreviewBatchOut(items=items), cache_changed

    manager = DatabaseAccountManager(db, no_login=True)
    invalid_changed = False

    def _safe_error(e: Exception) -> str:
        text = f"{type(e).__name__}: {str(e)}"
        text = text.strip() or type(e).__name__
        if len(text) > 240:
            text = text[:120] + " ... " + text[-80:]
        return text

    def _candidate_accounts_for_drive(drive_type: str) -> list[DriveAccount]:
        rows = (
            db.execute(select(DriveAccount).where(DriveAccount.enabled.is_(True), DriveAccount.drive_type == drive_type).order_by(DriveAccount.id.asc()))
            .scalars()
            .all()
        )
        rows.sort(
            key=lambda x: (
                0 if bool(getattr(x, "is_default", False)) else 1,
                0 if str(getattr(x, "runtime_status", "") or "") == "active" else 1,
                int(getattr(x, "id", 0) or 0),
            )
        )
        if payload.account_name:
            specified = str(payload.account_name or "").strip()
            if specified:
                hit = next((x for x in rows if str(x.name) == specified), None)
                if hit is None:
                    raise not_found("DRIVE_ACCOUNT_NOT_FOUND", "指定账号不存在或不可用")
                rows = [hit] + [x for x in rows if str(x.name) != specified]
        return rows

    adapter_cache: dict[str, object] = {}

    def _get_ready_adapter(account: DriveAccount):
        name = str(getattr(account, "name", "") or "").strip()
        if not name:
            return None
        cached = adapter_cache.get(name)
        if cached is not None:
            return cached
        adapter = manager.manager.get_adapter(name)
        if adapter is None:
            return None
        if (not bool(getattr(adapter, "is_active", False))) and (not bool(getattr(adapter, "no_login", False))):
            try:
                ok = adapter.init()
            except Exception:
                ok = None
            if not ok:
                return None
        adapter_cache[name] = adapter
        return adapter

    for drive_type, urls in per_drive.items():
        try:
            candidates = _candidate_accounts_for_drive(drive_type)
        except Exception as e:
            message = _safe_error(e)
            for url in urls:
                items.append(SharePreviewBatchItemOut(shareurl=url, drive_type=drive_type, ok=False, message=message))
            continue
        if not candidates:
            for url in urls:
                items.append(SharePreviewBatchItemOut(shareurl=url, drive_type=drive_type, ok=False, message="没有可用的驱动账号"))
            continue
        for url in urls:
            try:
                ok = False
                last_error: str | None = None
                used_name: str | None = None
                resolved_pdir_fid: str | None = None
                latest_video: dict | None = None
                share_author_name: str = ""
                for account in candidates:
                    adapter = _get_ready_adapter(account)
                    if adapter is None:
                        last_error = f"账号 {str(getattr(account, 'name', '') or '').strip()}: 不可用"
                        continue
                    try:
                        pwd_id, passcode, extracted_pdir_fid, _ = adapter.extract_url(url)
                    except Exception as e:
                        last_error = _safe_error(e)
                        break
                    if not pwd_id:
                        last_error = "无法解析分享链接"
                        break
                    try:
                        token_response = adapter.get_stoken(pwd_id, passcode or "")
                    except Exception as e:
                        last_error = f"账号 {str(getattr(account, 'name', '') or '').strip()}: {_safe_error(e)}"
                        continue
                    stoken = ((token_response or {}).get("data") or {}).get("stoken")
                    # 提取分享者信息
                    author_obj = ((token_response or {}).get("data") or {}).get("author")
                    if isinstance(author_obj, dict):
                        share_author_name = (
                            author_obj.get("nick_name")
                            or author_obj.get("nickname")
                            or author_obj.get("user_name")
                            or author_obj.get("name")
                            or ""
                        ).strip()
                    else:
                        share_author_name = ""
                    if not stoken:
                        message = (token_response or {}).get("message") or "获取分享 token 失败"
                        last_error = f"账号 {str(getattr(account, 'name', '') or '').strip()}: {str(message)}"
                        continue
                    try:
                        resolved_pdir_fid, latest_video = _auto_resolve_latest_video(adapter, pwd_id, stoken, extracted_pdir_fid or "")
                    except Exception as e:
                        last_error = f"账号 {str(getattr(account, 'name', '') or '').strip()}: {_safe_error(e)}"
                        continue
                    if latest_video and latest_video.get("name"):
                        try:
                            from app.extensions.runtime.guessit_fallback import guessit_episode_numbers

                            s, e2 = guessit_episode_numbers(str(latest_video.get("name") or ""), trace_tag="preview_batch")
                            if s is not None and e2 is not None:
                                latest_video["season"] = int(s)
                                latest_video["episode"] = int(e2)
                        except Exception:
                            pass
                    ok = True
                    used_name = str(getattr(account, "name", "") or "").strip() or None
                    break
                out = SharePreviewBatchItemOut(
                    shareurl=url,
                    drive_type=drive_type,
                    ok=ok,
                    message=None if ok else (last_error or "没有可用账号"),
                    suggested_account_name=used_name,
                    pdir_fid=resolved_pdir_fid if ok else None,
                    resolved_pdir_fid=resolved_pdir_fid if ok else None,
                    latest_video=latest_video if ok else None,
                    share_author_name=share_author_name if ok else None,
                )
                items.append(out)
                _share_preview_batch_cache_set(shareurl=url, item=out)
                try:
                    if _short_tx(
                        lambda s: upsert_preview_batch_cache(
                            s,
                            shareurl=out.shareurl,
                            drive_type=out.drive_type,
                            ok=out.ok,
                            message=out.message,
                            ttl_seconds=int(
                                getattr(settings, "tasks_share_preview_batch_db_cache_ttl_seconds", 6 * 60 * 60) or 6 * 60 * 60
                            ),
                        )
                    ):
                        cache_changed = True
                except Exception:
                    pass
                if (not out.ok) and _should_persist_invalid_share_link(out.message):
                    try:
                        if _short_tx(
                            lambda s: upsert_invalid_share_link(
                                s, shareurl=out.shareurl, drive_type=out.drive_type, message=out.message
                            )
                        ):
                            invalid_changed = True
                    except Exception:
                        pass
            except Exception as e:
                out = SharePreviewBatchItemOut(shareurl=url, drive_type=drive_type, ok=False, message=_safe_error(e))
                items.append(out)
                _share_preview_batch_cache_set(shareurl=url, item=out)
                try:
                    if _short_tx(
                        lambda s: upsert_preview_batch_cache(
                            s,
                            shareurl=out.shareurl,
                            drive_type=out.drive_type,
                            ok=out.ok,
                            message=out.message,
                            ttl_seconds=int(
                                getattr(settings, "tasks_share_preview_batch_db_cache_ttl_seconds", 6 * 60 * 60) or 6 * 60 * 60
                            ),
                        )
                    ):
                        cache_changed = True
                except Exception:
                    pass
                if _should_persist_invalid_share_link(out.message):
                    try:
                        if _short_tx(
                            lambda s: upsert_invalid_share_link(
                                s, shareurl=out.shareurl, drive_type=out.drive_type, message=out.message
                            )
                        ):
                            invalid_changed = True
                    except Exception:
                        pass
            finally:
                time.sleep(random.uniform(0.06, 0.22))

    return SharePreviewBatchOut(items=items), bool(invalid_changed or cache_changed)


def validate_share_links_streaming(db: Session, shareurls: list[str]):
    """生成器版本：验证完一个链接立即返回结果，不等全部完成。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from app.schemas.task_browse import ShareValidateItemOut
    from app.api.routes.system_settings import _get_setting

    urls = [str(x or "").strip() for x in shareurls]
    urls = [x for x in urls if x]
    urls = list(dict.fromkeys(urls))
    if not urls:
        return

    # 缓存查找
    _update_validate_cache_ttl()
    cached_items: list[ShareValidateItemOut] = []
    uncached_urls: list[str] = []
    with _validate_cache_lock:
        for url in urls:
            hit = _validate_cache.get(url)
            if hit is not None:
                cached_items.append(hit)
            else:
                uncached_urls.append(url)

    for item in cached_items:
        yield item

    if not uncached_urls:
        return

    def _safe_error(e: Exception) -> str:
        text = f"{type(e).__name__}: {str(e)}"
        return text.strip() or type(e).__name__

    # 非夸克网盘直接返回，无需验证
    per_drive: dict[str, list[str]] = {}
    for url in uncached_urls:
        drive_type = AdapterRegistry.detect_drive_type(url)
        if drive_type is None:
            yield ShareValidateItemOut(shareurl=url, ok=False, message="无法识别的网盘分享链接")
            continue
        # 115网盘：跳过验证，直接标记有效
        if drive_type == "115":
            yield ShareValidateItemOut(shareurl=url, ok=True)
            continue
        per_drive.setdefault(str(drive_type), []).append(url)

    if not per_drive:
        return

    # 预先查询所有可用账号（避免线程内访问数据库）
    accounts_by_drive: dict[str, list[DriveAccount]] = {}
    for drive_type in per_drive:
        try:
            rows = (
                db.execute(select(DriveAccount).where(DriveAccount.enabled.is_(True), DriveAccount.drive_type == drive_type).order_by(DriveAccount.id.asc()))
                .scalars()
                .all()
            )
            rows.sort(
                key=lambda x: (
                    0 if bool(getattr(x, "is_default", False)) else 1,
                    0 if str(getattr(x, "runtime_status", "") or "") == "active" else 1,
                    int(getattr(x, "id", 0) or 0),
                )
            )
            accounts_by_drive[drive_type] = rows
        except Exception:
            accounts_by_drive[drive_type] = []

    manager = DatabaseAccountManager(db, no_login=True)

    def _validate_single_url(url: str, drive_type: str) -> ShareValidateItemOut:
        """验证单个链接"""
        candidates = accounts_by_drive.get(drive_type, [])
        if not candidates:
            return ShareValidateItemOut(shareurl=url, ok=False, message="没有可用的驱动账号")

        ok = False
        author_name = ""
        last_error: str | None = None
        for account in candidates:
            name = str(getattr(account, "name", "") or "").strip()
            if not name:
                last_error = "账号名称为空"
                continue
            adapter = manager.manager.get_adapter(name)
            if adapter is None:
                last_error = f"账号 {name}: 不可用"
                continue
            if (not bool(getattr(adapter, "is_active", False))) and (not bool(getattr(adapter, "no_login", False))):
                try:
                    init_ok = adapter.init()
                except Exception:
                    init_ok = None
                if not init_ok:
                    last_error = f"账号 {name}: 初始化失败"
                    continue
            try:
                pwd_id, passcode, pdir_fid, _ = adapter.extract_url(url)
            except Exception as e:
                last_error = _safe_error(e)
                break
            if not pwd_id:
                last_error = "无法解析分享链接"
                break
            try:
                token_response = adapter.get_stoken(pwd_id, passcode or "")
            except Exception as e:
                last_error = f"账号 {name}: {_safe_error(e)}"
                continue
            stoken = ((token_response or {}).get("data") or {}).get("stoken")
            author_obj = ((token_response or {}).get("data") or {}).get("author")
            if isinstance(author_obj, dict):
                author_name = (
                    author_obj.get("nick_name")
                    or author_obj.get("nickname")
                    or author_obj.get("user_name")
                    or author_obj.get("name")
                    or ""
                ).strip()
            if not stoken:
                message = (token_response or {}).get("message") or "获取分享 token 失败"
                last_error = f"账号 {name}: {str(message)}"
                continue
            try:
                detail = adapter.get_detail(pwd_id, stoken, pdir_fid or "")
            except Exception as e:
                last_error = f"账号 {name}: {_safe_error(e)}"
                continue
            raw_items = (((detail or {}).get("data") or {}).get("list")) or []
            if raw_items:
                ok = True
                break
            else:
                last_error = detail.get("message") if isinstance(detail, dict) and detail.get("message") else "链接内容为空"
                continue

        result = ShareValidateItemOut(
            shareurl=url,
            ok=ok,
            share_author_name=author_name or None,
            message=None if ok else (last_error or "没有可用账号"),
        )
        # 缓存
        with _validate_cache_lock:
            _validate_cache[url] = result
        return result

    # 读取并行数配置
    try:
        batch_size = int(str(_get_setting(db, "validate_batch_size") or "5").strip())
    except Exception:
        batch_size = 5
    batch_size = max(1, min(batch_size, 20))

    # 并行验证，完成一个立即返回一个
    for drive_type, dt_urls in per_drive.items():
        if not accounts_by_drive.get(drive_type):
            for url in dt_urls:
                yield ShareValidateItemOut(shareurl=url, ok=False, message="没有可用的驱动账号")
            continue
        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            future_map = {executor.submit(_validate_single_url, url, drive_type): url for url in dt_urls}
            for future in as_completed(future_map):
                try:
                    result = future.result()
                    yield result
                except Exception as e:
                    url = future_map[future]
                    yield ShareValidateItemOut(shareurl=url, ok=False, message=_safe_error(e))


def validate_share_links(db: Session, shareurls: list[str]) -> ShareValidateOut:
    """轻量级验证：只检查链接有效性 + 提取分享者信息，不做视频解析。"""
    from app.schemas.task_browse import ShareValidateOut
    items = list(validate_share_links_streaming(db, shareurls))
    return ShareValidateOut(items=items)
