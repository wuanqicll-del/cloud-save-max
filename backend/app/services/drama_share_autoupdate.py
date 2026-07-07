from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions.runtime.adapter_registry import AdapterRegistry
from app.extensions.runtime.magic_rename import MagicRename
from app.models.drive_account import DriveAccount
from app.services.resource_search import fetch_task_suggestions
from app.services.tmdb_cache import get_tmdb_detail_cached

logger = logging.getLogger(__name__)

_RE_SEASON_EPISODE = re.compile(r"\bS(\d{1,3})E(\d{1,4})\b", re.IGNORECASE)
_RE_EPISODE_ONLY = re.compile(r"\b(?:E(?:P(?:ISODE)?)?|第)\s*0*(\d{1,4})\s*(?:集)?\b", re.IGNORECASE)



def _extract_episode_from_file(file_name: str, *, mr: Any = None) -> tuple[int | None, int | None]:
    """用重命名规则替换文件名后提取季和集"""
    text = str(file_name or "").strip()
    if not text:
        return None, None
    if mr is None:
        return None, None
    resolved_pattern = str(getattr(mr, "_resolved_pattern", "") or "").strip()
    resolved_replace = str(getattr(mr, "_resolved_replace", "") or "").strip()
    if not resolved_pattern and not resolved_replace:
        return None, None
    renamed = mr.sub(resolved_pattern, resolved_replace, text)
    if match := _RE_SEASON_EPISODE.search(renamed):
        return int(match.group(1)), int(match.group(2))
    if match := _RE_EPISODE_ONLY.search(renamed):
        return None, int(match.group(1))
    return None, None


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


@dataclass(slots=True)
class _TMDBContext:
    names: list[str]
    detail: dict[str, Any] | None


def _task_extra(task: Any) -> dict[str, Any]:
    raw = getattr(task, "extra_json", None)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _task_addition(task: Any) -> dict[str, Any]:
    raw = getattr(task, "addition_json", None)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _is_auto_update_enabled(task: Any) -> bool:
    extra = _task_extra(task)
    return bool(extra.get("auto_update_shareurl") or extra.get("auto_update_115_shareurl"))


def _pick_drive_type(db: Session, task: Any) -> str | None:
    account_name = str(getattr(task, "account_name", "") or "").strip()
    if account_name:
        row = db.execute(select(DriveAccount.drive_type).where(DriveAccount.name == account_name)).scalars().first()
        if row:
            dt = str(row or "").strip()
            return dt or None
    detected = AdapterRegistry.detect_drive_type(str(getattr(task, "shareurl", "") or ""))
    return str(detected or "").strip() or None


def is_auto_update_task(db: Session, task: Any, *, respect_toggle: bool = True) -> bool:
    if str(getattr(task, "task_type", "") or "") != "drama":
        return False
    if not _pick_drive_type(db, task):
        return False
    if respect_toggle and not _is_auto_update_enabled(task):
        return False
    # 有TMDB时必须是tv类型，没TMDB时也允许自动换链
    tmdb_id = int(getattr(task, "tmdb_id", 0) or 0)
    if tmdb_id > 0:
        if str(getattr(task, "tmdb_media_type", "") or "").strip().lower() != "tv":
            return False
    return True


# 兼容旧调用
is_115_auto_update_task = is_auto_update_task


def _load_tmdb_context(db: Session, task: Any) -> _TMDBContext | None:
    try:
        tmdb_id = int(getattr(task, "tmdb_id", 0) or 0)
    except Exception:
        return None
    if tmdb_id <= 0:
        return None
    configured, detail, _update_weekdays, _episode_weekdays, _row = get_tmdb_detail_cached(db, media_type="tv", tmdb_id=tmdb_id)
    if not configured or not isinstance(detail, dict):
        return None
    names = _dedupe_preserve_order(
        [
            str(detail.get("name") or "").strip(),
            str(detail.get("original_name") or "").strip(),
        ]
    )
    if not names:
        return None
    return _TMDBContext(names=names, detail=detail)


def _rewrite_shareurl_with_fid(shareurl: str, fid: str | None) -> str:
    url = str(shareurl or "").strip()
    f = str(fid or "").strip()
    if "yun.139.com" in url or "caiyun.139.com" in url:
        parsed = urlsplit(url)
        if parsed.fragment:
            frag_path, frag_query = (parsed.fragment.split("?", 1) + [""])[:2]
            frag_pairs = [(k, v) for k, v in parse_qsl(frag_query, keep_blank_values=True) if str(k).lower() != "fid"]
            if f and f not in ("0", "root"):
                frag_pairs.append(("fid", f))
            rebuilt_fragment = frag_path if not frag_pairs else f"{frag_path}?{urlencode(frag_pairs)}"
            return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, rebuilt_fragment)).strip()
        query_pairs = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if str(k).lower() != "fid"]
        if f and f not in ("0", "root"):
            query_pairs.append(("fid", f))
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query_pairs), parsed.fragment)).strip()
    if not f or f == "0":
        return url.split("#")[0].strip()
    if f in url:
        return url
    return f"{url.split('#')[0].strip()}#/list/share/{f}"


def _pick_int(value: Any) -> int | None:
    try:
        number = int(value)
    except Exception:
        return None
    return number if number > 0 else None


def _pick_datetime_value(value: str | None) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(text, fmt).timestamp())
        except Exception:
            continue
    try:
        return int(datetime.fromisoformat(text).timestamp())
    except Exception:
        return 0


def _pick_suggestions_for_preview(
    suggestions: list[dict[str, Any]],
    *,
    current_season: int | None,
    current_episode: int | None,
    tv_seasons: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    return [s for s in suggestions if isinstance(s, dict) and str(s.get("shareurl") or "").strip()]


def _search_candidates(db: Session, *, names: list[str], drive_type: str = "115", search_filter: str = "", search_exclude: str = "", search_date_from: str = "", search_filter_mode: str = "", search_exclude_mode: str = "") -> tuple[list[dict[str, Any]], bool, dict[str, Any]]:
    all_items: list[dict[str, Any]] = []
    db_changed = False
    for keyword in names:
        items, changed, _msg = fetch_task_suggestions(db, keyword=keyword, deep=1, drive_type=drive_type, search_filter=search_filter, search_exclude=search_exclude, search_date_from=search_date_from, search_filter_mode=search_filter_mode, search_exclude_mode=search_exclude_mode)
        if changed:
            db_changed = True
        if isinstance(items, list):
            all_items.extend([x for x in items if isinstance(x, dict)])
    stats: dict[str, Any] = {
        "keywords": [str(x or "").strip() for x in names if str(x or "").strip()],
        "fetched_total": len(all_items),
        "fetched_samples": [],
        "unique_shareurl_total": 0,
        "skip_wrong_drive": 0,
        "skip_tmdb_mismatch": 0,
        "kept": 0,
        "limit_reached": False,
    }
    filtered: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for item in all_items:
        shareurl = str(item.get("shareurl") or "").strip()
        if not shareurl or shareurl in seen_urls:
            continue
        stats["unique_shareurl_total"] = int(stats.get("unique_shareurl_total") or 0) + 1
        if len(stats["fetched_samples"]) < 50:
            stats["fetched_samples"].append(
                {
                    "shareurl": shareurl,
                    "taskname": str(item.get("taskname") or item.get("content") or "").strip(),
                    "source": str(item.get("source") or ""),
                    "channel": str(item.get("channel") or ""),
                    "datetime": str(item.get("datetime") or "").strip(),
                }
            )
        if AdapterRegistry.detect_drive_type(shareurl) != drive_type:
            stats["skip_wrong_drive"] = int(stats.get("skip_wrong_drive") or 0) + 1
            continue
        seen_urls.add(shareurl)
        filtered.append(item)
        stats["kept"] = int(stats.get("kept") or 0) + 1
    return filtered, db_changed, stats


def resolve_drama_shareurl_update(db: Session, task: Any, *, respect_toggle: bool = True, tried_shareurls: set[str] | None = None, fallback_candidates: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    task_id = int(getattr(task, "id", 0) or 0)
    task_uid = str(getattr(task, "task_uid", "") or "").strip()

    if not is_auto_update_task(db, task, respect_toggle=respect_toggle):
        return {"checked": False, "updated": False, "reason": "not_applicable"}

    logger.info("自动换链：开始")
    drive_type = _pick_drive_type(db, task) or "quark"

    addition = _task_addition(task)
    search_filter = str(addition.get("search_filter") or "").strip()
    search_exclude = str(addition.get("search_exclude") or "").strip()
    search_date_from = str(addition.get("search_date_from") or "").strip()
    search_filter_mode = str(addition.get("search_filter_mode") or "").strip()
    search_exclude_mode = str(addition.get("search_exclude_mode") or "").strip()
    folder_filter = str(addition.get("folder_filter") or "").strip()
    folder_exclude = str(addition.get("folder_exclude") or "").strip()
    folder_filter_mode = str(addition.get("folder_filter_mode") or "").strip()
    folder_exclude_mode = str(addition.get("folder_exclude_mode") or "").strip()
    folder_priority = str(addition.get("folder_priority") or "").strip()
    folder_priority_mode = str(addition.get("folder_priority_mode") or "").strip()
    dir_min_date = str(addition.get("dir_min_date") or "").strip()
    file_min_date = str(addition.get("file_min_date") or "").strip()
    file_filter_str = str(addition.get("file_filter") or "").strip()
    file_filter_words = [w.strip().lower() for w in file_filter_str.split("|") if w.strip()] if file_filter_str else []
    file_filter_is_any = str(addition.get("file_filter_mode") or "all").strip().lower() == "any"

    # 创建重命名实例，用于预览阶段提取集数
    task_pattern = str(getattr(task, "pattern", "") or "").strip()
    task_replace = str(getattr(task, "replace", "") or "").strip()
    mr: MagicRename | None = None
    if task_pattern or task_replace:
        try:
            mr = MagicRename()
            mr.taskname = str(getattr(task, "taskname", "") or "").strip()
            task_pattern, task_replace = mr.magic_regex_conv(task_pattern, task_replace)
            mr._resolved_pattern = task_pattern
            mr._resolved_replace = task_replace
        except Exception:
            return {"checked": False, "updated": False, "reason": "rename_rule_invalid"}


    tmdb_context = _load_tmdb_context(db, task)

    old_shareurl = str(getattr(task, "shareurl", "") or "").strip()
    if not old_shareurl:
        return {"checked": False, "updated": False, "reason": "shareurl_empty"}

    filter_words_count = len([w for w in str(addition.get("filter_words") or "").split("|") if w.strip()])
    file_filter_count = len([w for w in str(addition.get("file_filter") or "").split("|") if w.strip()])
    logger.info("  过滤规则：关键词=%d 文件筛选=%d 文件夹筛选=%s 文件夹排除=%s 文件夹优先=%s 时间=%s 大小=%s", filter_words_count, file_filter_count, folder_filter or "无", folder_exclude or "无", folder_priority or "无", file_min_date or "无", addition.get("min_size") or "无")
    current_season: int | None = None
    current_episode: int | None = None

    # 从快照获取当前已保存的实际进度
    from app.models.task_savepath_snapshot import TaskSavepathSnapshot
    from sqlalchemy import select as sa_select
    tv_seasons = tmdb_context.detail.get("seasons") if tmdb_context is not None and isinstance(tmdb_context.detail, dict) else None
    snapshot = db.execute(sa_select(TaskSavepathSnapshot).where(TaskSavepathSnapshot.task_uid == str(getattr(task, "task_uid", "") or "").strip())).scalars().first()
    if snapshot is not None:
        saved_season = getattr(snapshot, "saved_latest_season", None)
        saved_episode = getattr(snapshot, "saved_latest_episode", None)
        if saved_season is not None and saved_episode is not None:
            current_season = int(saved_season)
            current_episode = int(saved_episode)

    # 如果当前进度已到TMDB最新集数，不需要换链（没有TMDB时跳过此判断）
    if tmdb_context is not None:
        from app.services.drama_update_progress import resolve_tmdb_latest_aired_episode
        tmdb_detail = tmdb_context.detail if isinstance(tmdb_context.detail, dict) else {}
        tmdb_latest_season, tmdb_latest_episode, _ = resolve_tmdb_latest_aired_episode(tmdb_detail)
        logger.info("自动换链：当前已转存进度=第%d集，TMDB最新=第%d集", current_episode or 0, tmdb_latest_episode or 0)
        if tmdb_latest_season is not None and tmdb_latest_episode is not None:
            if current_season is not None and current_episode is not None:
                if (current_season or 0, current_episode) >= (tmdb_latest_season or 1, tmdb_latest_episode):
                    logger.info("自动换链：已到最新，跳过")
                    return {
                        "checked": True,
                        "updated": False,
                        "reason": "already_latest",
                        "current_season": current_season,
                        "current_episode": current_episode,
                    }


    # 搜索关键词：有TMDB用TMDB名称，没有用任务名称
    search_names = tmdb_context.names if tmdb_context is not None else [str(getattr(task, "taskname", "") or "").strip()]
    search_names = [n for n in search_names if n]
    if not search_names:
        return {"checked": False, "updated": False, "reason": "no_search_keyword"}

    suggestions, suggestions_changed, search_stats = _search_candidates(db, names=search_names, drive_type=drive_type, search_filter=search_filter, search_exclude=search_exclude, search_date_from=search_date_from, search_filter_mode=search_filter_mode, search_exclude_mode=search_exclude_mode)
    for i, s in enumerate(suggestions[:10]):
        pass
    if suggestions:
        # 验证链接有效性，过滤失效链接
        from app.services.share_preview_batch import validate_share_links_streaming
        shareurls_to_validate = [str(s.get("shareurl") or "").strip() for s in suggestions if str(s.get("shareurl") or "").strip()]
        if shareurls_to_validate:
            valid_urls = set()
            author_map: dict[str, str] = {}
            for item in validate_share_links_streaming(db, shareurls_to_validate):
                if item.ok:
                    valid_urls.add(item.shareurl)
                    author = str(item.share_author_name or "").strip()
                    if author:
                        author_map[item.shareurl] = author
            # 回写分享者名称到搜索结果
            for s in suggestions:
                url = str(s.get("shareurl") or "").strip()
                if url in author_map and not str(s.get("share_author_name") or "").strip():
                    s["share_author_name"] = author_map[url]
            before_count = len(suggestions)
            suggestions = [s for s in suggestions if str(s.get("shareurl") or "").strip() in valid_urls]
            removed = before_count - len(suggestions)
            if removed:
                search_stats["skip_invalid"] = removed
            # 只看优选分享者过滤
            preferred_only = bool(addition.get("preferred_only"))
            if preferred_only:
                from app.api.routes.system_settings import _get_setting
                preferred_str = str(_get_setting(db, "preferred_sharers") or "").strip()
                preferred_set = {s.strip() for s in preferred_str.split("|") if s.strip()} if preferred_str else set()
                if preferred_set:
                    before_count = len(suggestions)
                    suggestions = [s for s in suggestions if str(s.get("share_author_name") or "").strip() in preferred_set]
                    removed = before_count - len(suggestions)
                    if removed:
                        search_stats["skip_non_preferred"] = removed
            # 屏蔽分享者过滤（show_blocked=True 时跳过过滤，显示屏蔽分享者的结果）
            show_blocked = bool(addition.get("show_blocked"))
            if not show_blocked:
                from app.services.resource_search import filter_blocked_sharers
                before_count = len(suggestions)
                suggestions = filter_blocked_sharers(db, suggestions)
                removed = before_count - len(suggestions)
                if removed:
                    search_stats["skip_blocked"] = removed
    for i, s in enumerate(suggestions[:10]):
        pass
    if not suggestions:
        return {
            "checked": True,
            "updated": False,
            "reason": "no_candidates",
            "reason_detail": search_stats,
            "db_changed": bool(suggestions_changed),
        }

    preview_suggestions = _pick_suggestions_for_preview(
        suggestions,
        current_season=current_season,
        current_episode=current_episode,
        tv_seasons=tv_seasons if isinstance(tv_seasons, list) else None,
    )
    if not preview_suggestions:
        return {
            "checked": True,
            "updated": False,
            "reason": "no_better_candidate",
            "current_season": current_season,
            "current_episode": current_episode,
            "reason_detail": {
                "search": search_stats,
                "suggestions": len(suggestions),
            },
            "db_changed": bool(suggestions_changed),
        }

    # 读取过滤条件
    min_size_str = str(addition.get("min_size") or "").strip()
    filter_words_str = str(addition.get("filter_words") or "").strip()
    from app.services.drama_share_consecutive import _parse_size
    min_size = _parse_size(min_size_str) if min_size_str else 0
    filter_words = [w.strip() for w in filter_words_str.split("|") if w.strip()] if filter_words_str else []

    preview_stats: dict[str, Any] = {
        "preview_candidates": len(preview_suggestions),
        "resolved_candidates": 0,
        "skip_unpreviewable": 0,
        "skip_not_consecutive": 0,
        "skip_old_dir": 0,
    }

    # 读取优选分享者
    from app.api.routes.system_settings import _get_setting
    preferred_str = str(_get_setting(db, "preferred_sharers") or "").strip()
    preferred_set = {s.strip() for s in preferred_str.split("|") if s.strip()} if preferred_str else set()

    # 收集所有候选
    # 排序优先级：优选分享者 > 发布时间（最新优先）
    def _parse_dt(s: str) -> float:
        from datetime import datetime
        try:
            return datetime.fromisoformat(str(s or "").replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0

    valid_candidates: list[tuple[dict[str, Any], int, float]] = []
    for suggestion in preview_suggestions:
        shareurl = str(suggestion.get("shareurl") or "").strip()
        if not shareurl or shareurl == old_shareurl:
            continue
        if tried_shareurls and shareurl in tried_shareurls:
            continue
        author = str(suggestion.get("share_author_name") or "").strip()
        is_preferred = 1 if author in preferred_set else 0
        pub_ts = _parse_dt(str(suggestion.get("datetime") or ""))
        valid_candidates.append((suggestion, is_preferred, pub_ts))

    # 排序：优选优先 > 发布时间从新到旧
    valid_candidates.sort(key=lambda x: (x[1], x[2]), reverse=True)
    logger.info("自动换链：找到%d个候选", len(valid_candidates))
    for i, (s, pref, ts) in enumerate(valid_candidates):
        author_name = str(s.get("share_author_name") or "").strip()
        url = str(s.get("shareurl") or "").strip()[:50]
        title = str(s.get("taskname") or s.get("content") or "").strip()[:30]

    for i, (s, pref, ts) in enumerate(valid_candidates):
        author_name = str(s.get("share_author_name") or "").strip()
        title = str(s.get("taskname") or s.get("content") or "").strip()[:30]
        logger.info("  排序第%d 优选=%d 作者=%s", i+1, pref, author_name)

    # 依次尝试每个候选，获取文件列表检查连贯性
    from app.services.share_preview_batch import fetch_share_file_list_grouped
    from app.services.drama_share_consecutive import check_consecutive_episodes

    best_shareurl: str | None = None
    best_season: int | None = None
    best_episode: int | None = None
    best_pdir_fid: str | None = None
    best_taskname: str = ""
    best_ep_to_name: dict[int, str] = {}

    # 备用候选池：跨轮保留，连贯性检查失败但有缺口后面集数的链接
    if fallback_candidates is None:
        fallback_candidates = []
    current_ep_int = int(current_episode) if current_episode is not None else 0

    # 清理备选池：移除当前进度已超过的候选
    if fallback_candidates and current_ep_int > 0:
        before_count = len(fallback_candidates)
        fallback_candidates[:] = [fb for fb in fallback_candidates if int(fb.get("max_ep") or 0) > current_ep_int]
        removed_count = before_count - len(fallback_candidates)
        if removed_count > 0:
            logger.info("  备选池：移除%d个已过期候选，剩余%d个", removed_count, len(fallback_candidates))

    for i, (suggestion, _, _) in enumerate(valid_candidates):
        shareurl = str(suggestion.get("shareurl") or "").strip()
        title = str(suggestion.get("taskname") or suggestion.get("content") or "").strip()[:30]
        if tried_shareurls is not None and shareurl in tried_shareurls:
            logger.info("  候选%d：跳过已尝试", i+1)
            continue
        # 按子目录分组获取文件列表
        groups = fetch_share_file_list_grouped(db, shareurl, folder_filter=folder_filter, folder_exclude=folder_exclude, folder_filter_mode=folder_filter_mode, folder_exclude_mode=folder_exclude_mode, folder_priority=folder_priority, folder_priority_mode=folder_priority_mode)
        if not groups:
            logger.info("  候选%d：跳过无法获取", i+1)
            preview_stats["skip_unpreviewable"] = int(preview_stats.get("skip_unpreviewable") or 0) + 1
            if tried_shareurls is not None:
                tried_shareurls.add(shareurl)
            continue
        # 逐个子目录检查连贯性，选集数最高、时间最新的通过的那个
        candidate_best_fid: str | None = None
        candidate_max_ep: int = 0
        candidate_best_ts: int = 0
        candidate_has_later: bool = False
        candidate_later_max_ep: int = 0
        candidate_later_fid: str | None = None
        candidate_later_ts: int = 0
        candidate_later_ep_to_name: dict[int, str] = {}
        # 优先级关键词
        folder_priority_keywords = [w.strip().lower() for w in folder_priority.split("|") if w.strip()] if folder_priority else []
        folder_priority_is_any = str(folder_priority_mode or "all").strip().lower() == "any"
        # 优先级候选
        priority_candidate_best_fid: str | None = None
        priority_candidate_max_ep: int = 0
        priority_candidate_best_ts: int = 0
        for file_list, fid, dir_updated_at, dir_name in groups:
            if not file_list:
                continue
            # 目录时间过滤
            if dir_min_date and dir_updated_at is not None:
                try:
                    from datetime import datetime, timezone, timedelta
                    val = dir_updated_at
                    if isinstance(val, (int, float)) or (isinstance(val, str) and val.strip().isdigit()):
                        ts = int(float(val))
                        dir_date = datetime.fromtimestamp(ts, tz=timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
                    else:
                        dir_date = str(val)[:10]
                    if dir_date < dir_min_date:
                        preview_stats["skip_old_dir"] = int(preview_stats.get("skip_old_dir") or 0) + 1
                        continue
                except Exception:
                    pass
            is_consecutive, consecutive_episodes, max_ep = check_consecutive_episodes(
                file_list,
                current_episode=current_ep_int,
                min_size=min_size,
                filter_words=filter_words,
                file_filter_words=file_filter_words,
                file_filter_is_any=file_filter_is_any,
                file_min_date=file_min_date,
                mr=mr,
            )
            logger.info("  候选%d：文件夹：%s 文件数=%d %s", i+1, dir_name or fid[:8], len(file_list), "连贯 E%s-E%s" % (min(consecutive_episodes), max(consecutive_episodes)) if is_consecutive and consecutive_episodes else "不连贯")
            # 找最高集数对应的文件名
            ep_to_name: dict[int, str] = {}
            for f in file_list:
                fn = str(f.get("file_name") or f.get("name") or "").strip()
                if fn:
                    _, ep = _extract_episode_from_file(fn, mr=mr)
                    if ep is not None:
                        ep_to_name[ep] = fn
            group_ts = 0
            for f in file_list:
                try:
                    t = int(float(f.get("updated_at") or 0))
                    if t > group_ts:
                        group_ts = t
                except (TypeError, ValueError):
                    pass
            if is_consecutive and consecutive_episodes:
                ep = max(consecutive_episodes)
                # 检查是否匹配优先级关键词
                is_priority = False
                if folder_priority_keywords and dir_name:
                    name_lower = dir_name.lower()
                    if folder_priority_is_any:
                        is_priority = any(kw in name_lower for kw in folder_priority_keywords)
                    else:
                        is_priority = all(kw in name_lower for kw in folder_priority_keywords)
                if is_priority:
                    # 优先级候选：优先选择
                    if ep > priority_candidate_max_ep or (ep == priority_candidate_max_ep and group_ts > priority_candidate_best_ts):
                        priority_candidate_max_ep = ep
                        priority_candidate_best_ts = group_ts
                        priority_candidate_best_fid = fid
                        logger.info("  候选%d：文件夹：%s 匹配优先级关键词，集=%d", i+1, dir_name or fid[:8], ep)
                elif ep > candidate_max_ep or (ep == candidate_max_ep and group_ts > candidate_best_ts):
                    candidate_max_ep = ep
                    candidate_best_ts = group_ts
                    candidate_best_fid = fid
            elif max_ep > current_ep_int:
                # 连贯性失败但有缺口后面的集数，记录为备用
                if max_ep > candidate_later_max_ep or (max_ep == candidate_later_max_ep and group_ts > candidate_later_ts):
                    candidate_later_max_ep = max_ep
                    candidate_later_fid = fid
                    candidate_later_ts = group_ts
                    candidate_later_ep_to_name = ep_to_name
                    candidate_has_later = True
            else:
                pass

        # 优先使用优先级候选
        if priority_candidate_best_fid is not None:
            # 优先级候选通过，标记已尝试，立即使用
            if tried_shareurls is not None:
                tried_shareurls.add(shareurl)
            best_shareurl = shareurl
            best_pdir_fid = priority_candidate_best_fid
            best_taskname = str(suggestion.get("taskname") or suggestion.get("content") or "").strip()
            best_file_name = ep_to_name.get(priority_candidate_max_ep, "")
            if best_file_name:
                best_season, best_episode = _extract_episode_from_file(best_file_name, mr=mr)
            else:
                best_season, best_episode = None, None
            logger.info("  候选%d：优先级候选通过，集=%s", i+1, best_episode)
            break
        elif candidate_best_fid is not None:
            # 连贯性检查通过，标记已尝试，立即使用
            if tried_shareurls is not None:
                tried_shareurls.add(shareurl)
            best_shareurl = shareurl
            best_pdir_fid = candidate_best_fid
            best_taskname = str(suggestion.get("taskname") or suggestion.get("content") or "").strip()
            # 用最高集数对应的文件名提取季和集
            best_file_name = ep_to_name.get(candidate_max_ep, "")
            if best_file_name:
                best_season, best_episode = _extract_episode_from_file(best_file_name, mr=mr)
            else:
                best_season, best_episode = None, None
            logger.info("  候选%d：候选通过，集=%s", i+1, best_episode)
            break
        elif candidate_has_later:
            # 备用候选池：不标记已尝试
            later_file_name = candidate_later_ep_to_name.get(candidate_later_max_ep, "")
            if later_file_name:
                later_season, later_episode = _extract_episode_from_file(later_file_name, mr=mr)
            else:
                later_season, later_episode = None, None
            fallback_candidates.append({
                "suggestion": suggestion,
                "season": later_season,
                "episode": later_episode,
                "fid": candidate_later_fid,
                "max_ep": candidate_later_max_ep,
                "ts": candidate_later_ts,
            })
            if tried_shareurls is not None:
                tried_shareurls.add(shareurl)
            logger.info("  候选%d：进入备选池 集=%s", i+1, later_episode)
        else:
            # 没有用处的链接，标记已尝试
            if tried_shareurls is not None:
                tried_shareurls.add(shareurl)
            preview_stats["skip_not_consecutive"] = int(preview_stats.get("skip_not_consecutive") or 0) + 1

    # 主候选池没有找到，尝试备用候选池（同样的连贯性检查逻辑）
    if best_shareurl is None and fallback_candidates:
        logger.info("  主候选未通过，尝试备选池，备选数=%d", len(fallback_candidates))
        fallback_candidates.sort(key=lambda x: (x["max_ep"], x["ts"]), reverse=False)
        for fb in fallback_candidates:
            fb_url = str(fb["suggestion"].get("shareurl") or "").strip()
            # 备选池候选不检查已尝试，因为进入备选池时已标记
            # 重新获取文件列表，走同样的连贯性检查
            fb_groups = fetch_share_file_list_grouped(db, fb_url, folder_filter=folder_filter, folder_exclude=folder_exclude, folder_filter_mode=folder_filter_mode, folder_exclude_mode=folder_exclude_mode, folder_priority=folder_priority, folder_priority_mode=folder_priority_mode)
            if not fb_groups:
                continue
            fb_best_fid: str | None = None
            fb_max_ep: int = 0
            fb_best_ts: int = 0
            for file_list, fid, dir_updated_at, dir_name in fb_groups:
                if not file_list:
                    continue
                if dir_min_date and dir_updated_at is not None:
                    try:
                        from datetime import datetime, timezone, timedelta
                        val = dir_updated_at
                        if isinstance(val, (int, float)) or (isinstance(val, str) and val.strip().isdigit()):
                            ts = int(float(val))
                            dir_date = datetime.fromtimestamp(ts, tz=timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
                        else:
                            dir_date = str(val)[:10]
                        if dir_date < dir_min_date:
                            continue
                    except Exception:
                        pass
                is_consecutive, consecutive_episodes, max_ep = check_consecutive_episodes(
                    file_list,
                    current_episode=current_ep_int,
                    min_size=min_size,
                    filter_words=filter_words,
                    file_filter_words=file_filter_words,
                    file_filter_is_any=file_filter_is_any,
                    file_min_date=file_min_date,
                    mr=mr,
                )
                logger.info("  备选池：文件夹：%s 文件数=%d %s", dir_name or fid[:8], len(file_list), "连贯 E%s-E%s" % (min(consecutive_episodes), max(consecutive_episodes)) if is_consecutive and consecutive_episodes else "不连贯")
                # 找最高集数对应的文件名
                fb_ep_to_name: dict[int, str] = {}
                for f in file_list:
                    fn = str(f.get("file_name") or f.get("name") or "").strip()
                    if fn:
                        _, ep = _extract_episode_from_file(fn, mr=mr)
                        if ep is not None:
                            fb_ep_to_name[ep] = fn
                group_ts = 0
                for f in file_list:
                    try:
                        t = int(float(f.get("updated_at") or 0))
                        if t > group_ts:
                            group_ts = t
                    except (TypeError, ValueError):
                        pass
                if is_consecutive and consecutive_episodes:
                    ep = max(consecutive_episodes)
                    if ep > fb_max_ep or (ep == fb_max_ep and group_ts > fb_best_ts):
                        fb_max_ep = ep
                        fb_best_ts = group_ts
                        fb_best_fid = fid
            if fb_best_fid is not None:
                # 备用候选连贯性检查通过，标记已尝试，从备选池移除，使用
                if tried_shareurls is not None:
                    tried_shareurls.add(fb_url)
                fallback_candidates.remove(fb)
                best_shareurl = fb_url
                best_pdir_fid = fb_best_fid
                best_taskname = str(fb["suggestion"].get("taskname") or fb["suggestion"].get("content") or "").strip()
                candidate_max_ep = fb_max_ep
                # 用最高集数对应的文件名提取季和集
                fb_best_file_name = fb_ep_to_name.get(fb_max_ep, "")
                if fb_best_file_name:
                    best_season, best_episode = _extract_episode_from_file(fb_best_file_name, mr=mr)
                else:
                    best_season, best_episode = None, None
                logger.info("  备选池命中 集=%s", best_episode)
                break
            else:
                # 备用候选也没通过，不标记已尝试，下次还能用
                logger.info("  备选池未通过")

    if best_shareurl is None:
        logger.info("自动换链：未找到更好链接")
        return {
            "checked": True,
            "updated": False,
            "reason": "no_better_candidate",
            "current_season": current_season,
            "current_episode": current_episode,
            "reason_detail": {"search": search_stats, "preview": preview_stats},
            "db_changed": bool(suggestions_changed),
        }

    new_shareurl = _rewrite_shareurl_with_fid(
        best_shareurl,
        str(best_pdir_fid or ""),
    )
    if not new_shareurl or new_shareurl == old_shareurl:
        logger.info("自动换链：新旧链接相同")
        return {
            "checked": True,
            "updated": False,
            "reason": "same_shareurl",
            "current_season": current_season,
            "current_episode": current_episode,
            "db_changed": bool(suggestions_changed),
        }

    task.shareurl = new_shareurl
    db.flush()

    logger.info("自动换链：换链成功 集=%s", best_episode)
    return {
        "checked": True,
        "updated": True,
        "old_shareurl": old_shareurl,
        "new_shareurl": new_shareurl,
        "current_season": current_season,
        "current_episode": current_episode,
        "season": best_season,
        "episode": best_episode,
        "taskname": best_taskname,
        "db_changed": True,
    }
