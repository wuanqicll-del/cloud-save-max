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
from app.extensions.runtime.guessit_fallback import guessit_title_episode_numbers
from app.extensions.runtime.magic_rename import MagicRename
from app.models.drive_account import DriveAccount
from app.services.resource_search import fetch_task_suggestions
from app.services.tmdb_cache import get_tmdb_detail_cached

logger = logging.getLogger(__name__)

_RE_NON_WORD = re.compile(r"[\s\W_]+", re.UNICODE)
_RE_SEASON_EPISODE = re.compile(r"\bS(\d{1,3})E(\d{1,4})\b", re.IGNORECASE)
_RE_EPISODE_ONLY = re.compile(r"\b(?:EP(?:ISODE)?|第)\s*0*(\d{1,4})\s*(?:集)?\b", re.IGNORECASE)
_RE_YEAR_BRACKETS = re.compile(r"[\(\[（【]\s*(?:19|20)\d{2}\s*[\)\]）】]")
_RE_SOURCE_PREFIX = re.compile(r"^\s*(?:电视剧|剧集|连续剧|网剧|韩剧|日剧|美剧|英剧|台剧|泰剧|动漫|动画|番剧)\s*[:：]\s*", re.IGNORECASE)
_RE_NOISE_TOKEN = re.compile(
    r"\b(?:4k|8k|2160p|1080p|720p|bluray|bdrip|web-?dl|webrip|hdtv|x264|x265|h\.?264|h\.?265|hevc|aac|dts|uhd)\b",
    re.IGNORECASE,
)
_RE_EMOJI = re.compile(
    r"[\U0001F1E6-\U0001F1FF]"
    r"|[\U0001F300-\U0001F5FF]"
    r"|[\U0001F600-\U0001F64F]"
    r"|[\U0001F680-\U0001F6FF]"
    r"|[\U0001F700-\U0001F77F]"
    r"|[\U0001F780-\U0001F7FF]"
    r"|[\U0001F800-\U0001F8FF]"
    r"|[\U0001F900-\U0001F9FF]"
    r"|[\U0001FA00-\U0001FAFF]"
    r"|[\U00002600-\U000026FF]"
    r"|[\U00002700-\U000027BF]"
    r"|[\u200D\uFE0F]",
    re.UNICODE,
)
_TITLE_SEGMENT_SEPARATORS = ("|", "｜", "/", "／")


@dataclass(slots=True)
class _TMDBContext:
    names: list[str]
    detail: dict[str, Any] | None


@dataclass(slots=True)
class _PreparedSuggestion:
    suggestion: dict[str, Any]
    shareurl: str
    taskname: str
    datetime_value: str
    season: int | None
    episode: int | None


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


def _normalize_text(value: str | None) -> str:
    return _RE_NON_WORD.sub("", str(value or "").strip()).lower()


def _normalize_ascii_words(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


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
    if str(getattr(task, "tmdb_media_type", "") or "").strip().lower() != "tv":
        return False
    try:
        return int(getattr(task, "tmdb_id", 0) or 0) > 0
    except Exception:
        return False


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


def _extract_season_episode_from_title(title: str) -> tuple[int | None, int | None]:
    text = str(title or "").strip()
    if not text:
        return None, None
    if match := _RE_SEASON_EPISODE.search(text):
        season = int(match.group(1))
        episode = int(match.group(2))
        # 处理集数范围，如 S01E01-E34 取最后一集
        rest = text[match.end():]
        if range_match := re.match(r"[-~～](?:E|e)?(\d{1,4})", rest):
            episode = int(range_match.group(1))
        return season, episode
    if match := _RE_EPISODE_ONLY.search(text):
        ep = int(match.group(1))
        rest = text[match.end():]
        if range_match := re.match(r"[-~～](?:第|EP|ep|E|e)?\s*(\d{1,4})", rest):
            ep = int(range_match.group(1))
        return None, ep
    return None, None


def _resolve_title_progress(title: str, *, tv_seasons: list[dict[str, Any]] | None = None) -> tuple[int | None, int | None]:
    season, episode = _extract_season_episode_from_title(title)
    if season is not None and episode is not None:
        return season, episode
    guessed_season, guessed_episode = guessit_title_episode_numbers(
        title,
        tv_seasons=tv_seasons,
        trace_tag="shareurl_autoupdate",
    )
    if guessed_season is not None or guessed_episode is not None:
        return guessed_season, guessed_episode
    return season, episode


def _cleanup_title_subject(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        import emoji as _emoji  # type: ignore

        text = _emoji.replace_emoji(text, replace=" ")
    except Exception:
        text = _RE_EMOJI.sub(" ", text)
    text = re.sub(r"^[\s\W_]+", "", text)
    text = _RE_SOURCE_PREFIX.sub("", text)
    text = re.sub(r"^[\s\W_]+", "", text)
    text = _RE_YEAR_BRACKETS.sub(" ", text)
    text = _RE_SEASON_EPISODE.sub(" ", text)
    text = re.sub(r"[-~～](?:E|e)?\d{1,4}\b", " ", text)  # 清理集数范围后半段，如 -E34
    text = _RE_EPISODE_ONLY.sub(" ", text)
    text = re.sub(r"[-~～](?:第|EP|ep|E|e)?\s*\d{1,4}\b", " ", text)  # 清理集数范围后半段
    text = _RE_NOISE_TOKEN.sub(" ", text)
    text = re.sub(r"[\(\[（【].*?[\)\]）】]", " ", text)
    text = re.sub(r"[:：\-_.,]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_title_subject_variants(value: str) -> list[str]:
    cleaned = _cleanup_title_subject(value)
    if not cleaned:
        return []
    variants = [cleaned]
    for separator in _TITLE_SEGMENT_SEPARATORS:
        if separator not in cleaned:
            continue
        parts = [x.strip() for x in cleaned.split(separator) if str(x or "").strip()]
        variants.extend(parts)
    return _dedupe_preserve_order(variants)


def _title_matches_tmdb_names(title: str, names: list[str]) -> bool:
    title_variants = _extract_title_subject_variants(title)
    if not title_variants:
        return False
    normalized_title_variants = {_normalize_text(x) for x in title_variants if _normalize_text(x)}
    normalized_ascii_variants = {_normalize_ascii_words(x) for x in title_variants if _normalize_ascii_words(x)}
    for raw_name in names:
        name = str(raw_name or "").strip()
        if not name:
            continue
        name_variants = _extract_title_subject_variants(name) or [name]
        for item in name_variants:
            normalized_name = _normalize_text(item)
            if normalized_name:
                for tv in normalized_title_variants:
                    if normalized_name in tv:
                        return True
            normalized_ascii_name = _normalize_ascii_words(item)
            if normalized_ascii_name:
                for tv in normalized_ascii_variants:
                    if normalized_ascii_name in tv:
                        return True
    return False


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


def _prepare_suggestion(
    suggestion: dict[str, Any],
    *,
    tv_seasons: list[dict[str, Any]] | None = None,
) -> _PreparedSuggestion | None:
    shareurl = str(suggestion.get("shareurl") or "").strip()
    if not shareurl:
        return None
    title = str(suggestion.get("taskname") or suggestion.get("content") or "").strip()
    season, episode = _resolve_title_progress(title, tv_seasons=tv_seasons)
    return _PreparedSuggestion(
        suggestion=suggestion,
        shareurl=shareurl,
        taskname=title,
        datetime_value=str(suggestion.get("datetime") or "").strip(),
        season=season,
        episode=episode,
    )


def _pick_suggestions_for_preview(
    suggestions: list[dict[str, Any]],
    *,
    current_season: int | None,
    current_episode: int | None,
    tv_seasons: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    prepared_items: list[_PreparedSuggestion] = []
    for suggestion in suggestions:
        prepared = _prepare_suggestion(suggestion, tv_seasons=tv_seasons)
        if prepared is not None:
            prepared_items.append(prepared)

    # 按集数从高到低排序，没有集数的排后面
    parsed = [item for item in prepared_items if item.season is not None and item.episode is not None]
    unknown = [item for item in prepared_items if item.season is None or item.episode is None]
    parsed.sort(key=lambda item: (int(item.season), int(item.episode)), reverse=True)
    unknown.sort(key=lambda item: _pick_datetime_value(item.datetime_value), reverse=True)
    return [item.suggestion for item in parsed + unknown]


def _search_candidates(db: Session, *, names: list[str], drive_type: str = "115", search_filter: str = "", search_exclude: str = "", search_date_from: str = "", search_filter_mode: str = "", search_exclude_mode: str = "") -> tuple[list[dict[str, Any]], bool, dict[str, Any]]:
    all_items: list[dict[str, Any]] = []
    db_changed = False
    for keyword in names:
        items, changed, _msg = fetch_task_suggestions(db, keyword=keyword, deep=1, drive_type=drive_type, search_filter=search_filter, search_exclude=search_exclude, search_date_from=search_date_from, search_filter_mode=search_filter_mode, search_exclude_mode=search_exclude_mode)
        logger.info("[shareurl_autoupdate] search keyword=%r -> %d items, msg=%s", keyword, len(items) if isinstance(items, list) else 0, _msg)
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
        title = str(item.get("taskname") or item.get("content") or "").strip()
        if not _title_matches_tmdb_names(title, names):
            stats["skip_tmdb_mismatch"] = int(stats.get("skip_tmdb_mismatch") or 0) + 1
            logger.info("[shareurl_autoupdate] skip_tmdb_mismatch: %s title=%s", shareurl, title[:80])
            continue
        seen_urls.add(shareurl)
        filtered.append(item)
        stats["kept"] = int(stats.get("kept") or 0) + 1
    return filtered, db_changed, stats


def resolve_drama_shareurl_update(db: Session, task: Any, *, respect_toggle: bool = True, tried_shareurls: set[str] | None = None) -> dict[str, Any]:
    task_id = int(getattr(task, "id", 0) or 0)
    task_uid = str(getattr(task, "task_uid", "") or "").strip()
    logger.info("[shareurl_autoupdate] >>> START task_id=%s task_uid=%s", task_id, task_uid)

    if not is_auto_update_task(db, task, respect_toggle=respect_toggle):
        logger.info("[shareurl_autoupdate] SKIP: not applicable")
        return {"checked": False, "updated": False, "reason": "not_applicable"}

    drive_type = _pick_drive_type(db, task) or "quark"
    logger.info("[shareurl_autoupdate] drive_type=%s", drive_type)

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
    dir_min_date = str(addition.get("dir_min_date") or "").strip()
    file_min_date = str(addition.get("file_min_date") or "").strip()
    file_filter_str = str(addition.get("file_filter") or "").strip()
    file_filter_words = [w.strip().lower() for w in file_filter_str.split("|") if w.strip()] if file_filter_str else []
    file_filter_is_any = str(addition.get("file_filter_mode") or "all").strip().lower() == "any"
    logger.info(
        "[shareurl_autoupdate] addition: search_filter=%r search_exclude=%r date_from=%r folder_filter=%r folder_exclude=%r dir_min_date=%r file_min_date=%r file_filter=%r preferred_only=%s filter_words=%r min_size=%r",
        search_filter, search_exclude, search_date_from, folder_filter, folder_exclude, dir_min_date, file_min_date, file_filter_str, addition.get("preferred_only"), addition.get("filter_words"), addition.get("min_size"),
    )

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
            logger.info("[shareurl_autoupdate] rename rule: pattern=%r replace=%r", task_pattern, task_replace)
        except Exception:
            return {"checked": False, "updated": False, "reason": "rename_rule_invalid"}
    else:
        logger.info("[shareurl_autoupdate] no rename rule configured")

    tmdb_context = _load_tmdb_context(db, task)
    if tmdb_context is None:
        return {"checked": False, "updated": False, "reason": "tmdb_context_missing"}

    old_shareurl = str(getattr(task, "shareurl", "") or "").strip()
    if not old_shareurl:
        return {"checked": False, "updated": False, "reason": "shareurl_empty"}

    current_season: int | None = None
    current_episode: int | None = None

    # 从快照获取当前已保存的实际进度
    from app.models.task_savepath_snapshot import TaskSavepathSnapshot
    from sqlalchemy import select as sa_select
    tv_seasons = tmdb_context.detail.get("seasons") if isinstance(tmdb_context.detail, dict) else None
    snapshot = db.execute(sa_select(TaskSavepathSnapshot).where(TaskSavepathSnapshot.task_uid == str(getattr(task, "task_uid", "") or "").strip())).scalars().first()
    if snapshot is not None:
        saved_season = getattr(snapshot, "saved_latest_season", None)
        saved_episode = getattr(snapshot, "saved_latest_episode", None)
        if saved_season is not None and saved_episode is not None:
            current_season = int(saved_season)
            current_episode = int(saved_episode)
            logger.info("[shareurl_autoupdate] snapshot: S%sE%s", current_season, current_episode)
        else:
            logger.info("[shareurl_autoupdate] snapshot: no saved_latest")
    else:
        logger.info("[shareurl_autoupdate] no snapshot found")

    logger.info("[shareurl_autoupdate] current progress: S%sE%s", current_season, current_episode)

    # 如果当前进度已到TMDB最新集数，不需要换链
    from app.services.drama_update_progress import resolve_tmdb_latest_aired_episode
    tmdb_detail = tmdb_context.detail if isinstance(tmdb_context.detail, dict) else {}
    tmdb_latest_season, tmdb_latest_episode, _ = resolve_tmdb_latest_aired_episode(tmdb_detail)
    if tmdb_latest_season is not None and tmdb_latest_episode is not None:
        logger.info("[shareurl_autoupdate] TMDB latest: S%sE%s", tmdb_latest_season, tmdb_latest_episode)
        if current_season is not None and current_episode is not None:
            if (current_season or 0, current_episode) >= (tmdb_latest_season or 1, tmdb_latest_episode):
                logger.info("[shareurl_autoupdate] SKIP: already at TMDB latest")
                return {
                    "checked": True,
                    "updated": False,
                    "reason": "already_latest",
                    "current_season": current_season,
                    "current_episode": current_episode,
                }

    suggestions, suggestions_changed, search_stats = _search_candidates(db, names=tmdb_context.names, drive_type=drive_type, search_filter=search_filter, search_exclude=search_exclude, search_date_from=search_date_from, search_filter_mode=search_filter_mode, search_exclude_mode=search_exclude_mode)
    logger.info("[shareurl_autoupdate] search returned %d suggestions", len(suggestions))
    for i, s in enumerate(suggestions[:10]):
        logger.info("[shareurl_autoupdate] suggestion[%d] author=%s url=%s datetime=%s", i, s.get("share_author_name"), s.get("shareurl"), s.get("datetime"))
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
            logger.info("[shareurl_autoupdate] validated %d links, %d valid, %d invalid", len(shareurls_to_validate), len(valid_urls), len(shareurls_to_validate) - len(valid_urls))
            before_count = len(suggestions)
            suggestions = [s for s in suggestions if str(s.get("shareurl") or "").strip() in valid_urls]
            removed = before_count - len(suggestions)
            if removed:
                search_stats["skip_invalid"] = removed
                logger.info("[shareurl_autoupdate] skip_invalid: %d", removed)
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
                        logger.info("[shareurl_autoupdate] skip_non_preferred: %d", removed)
            # 屏蔽分享者过滤
            from app.services.resource_search import filter_blocked_sharers
            before_count = len(suggestions)
            suggestions = filter_blocked_sharers(db, suggestions)
            removed = before_count - len(suggestions)
            if removed:
                search_stats["skip_blocked"] = removed
                logger.info("[shareurl_autoupdate] skip_blocked: %d", removed)
    logger.info("[shareurl_autoupdate] after filters: %d suggestions remaining", len(suggestions))
    for i, s in enumerate(suggestions[:10]):
        logger.info("[shareurl_autoupdate] filtered[%d] author=%s url=%s", i, s.get("share_author_name"), s.get("shareurl"))
    if not suggestions:
        logger.info(
            "[shareurl_autoupdate] no_candidates task_id=%s task_uid=%s stats=%s",
            int(getattr(task, "id", 0) or 0),
            str(getattr(task, "task_uid", "") or ""),
            json.dumps(search_stats, ensure_ascii=False),
        )
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
    logger.info("[shareurl_autoupdate] preview_suggestions: %d picked from %d total", len(preview_suggestions), len(suggestions))
    if not preview_suggestions:
        logger.info(
            "[shareurl_autoupdate] no_better_candidate_before_preview task_id=%s task_uid=%s current=S%sE%s stats=%s",
            int(getattr(task, "id", 0) or 0),
            str(getattr(task, "task_uid", "") or ""),
            str(current_season or ""),
            str(current_episode or ""),
            json.dumps(
                {
                    "search": search_stats,
                    "suggestions": len(suggestions),
                },
                ensure_ascii=False,
            ),
        )
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
    logger.info("[shareurl_autoupdate] filters: min_size=%d(%s) filter_words=%s file_filter=%s", min_size, min_size_str, filter_words, file_filter_words)

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

    valid_candidates: list[tuple[dict[str, Any], int, int, float]] = []
    for suggestion in preview_suggestions:
        shareurl = str(suggestion.get("shareurl") or "").strip()
        if not shareurl or shareurl == old_shareurl:
            continue
        if tried_shareurls and shareurl in tried_shareurls:
            continue
        title = str(suggestion.get("taskname") or suggestion.get("content") or "").strip()
        title_season, title_episode = _resolve_title_progress(title, tv_seasons=tv_seasons)
        author = str(suggestion.get("share_author_name") or "").strip()
        is_preferred = 1 if author in preferred_set else 0
        pub_ts = _parse_dt(str(suggestion.get("datetime") or ""))
        valid_candidates.append((suggestion, int(title_season or current_season or 0), int(title_episode or 0), is_preferred, pub_ts))

    # 排序：优选优先 > 发布时间从新到旧
    valid_candidates.sort(key=lambda x: (x[3], x[4]), reverse=True)
    logger.info("[shareurl_autoupdate] sorted %d candidates (preferred_set=%s, blocked_sharers=%s)", len(valid_candidates), preferred_set, None)
    for i, (sug, cs, ce, pref, pts) in enumerate(valid_candidates[:10]):
        logger.info("[shareurl_autoupdate] candidate[%d] preferred=%s pub_ts=%.0f author=%s url=%s", i, pref, pts, sug.get("share_author_name"), sug.get("shareurl"))

    # 依次尝试每个候选，获取文件列表检查连贯性
    from app.services.share_preview_batch import fetch_share_file_list_grouped
    from app.services.drama_share_consecutive import check_consecutive_episodes

    best_shareurl: str | None = None
    best_season: int | None = None
    best_episode: int | None = None
    best_pdir_fid: str | None = None
    best_taskname: str = ""

    # 备用候选池：连贯性检查失败但有缺口后面集数的链接
    fallback_candidates: list[dict[str, Any]] = []
    current_ep_int = int(current_episode) if current_episode is not None else 0

    for suggestion, candidate_season, candidate_episode, _, _ in valid_candidates:
        shareurl = str(suggestion.get("shareurl") or "").strip()
        if tried_shareurls is not None and shareurl in tried_shareurls:
            continue
        # 按子目录分组获取文件列表
        groups = fetch_share_file_list_grouped(db, shareurl, folder_filter=folder_filter, folder_exclude=folder_exclude, folder_filter_mode=folder_filter_mode, folder_exclude_mode=folder_exclude_mode)
        logger.info("[shareurl_autoupdate] candidate url=%s author=%s -> %d groups (folder_filter=%r folder_exclude=%r)", shareurl, suggestion.get("share_author_name"), len(groups), folder_filter, folder_exclude)
        if not groups:
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
        for file_list, fid, dir_updated_at in groups:
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
                        logger.info("[shareurl_autoupdate] skip_old_dir: fid=%s date=%s < %s", fid, dir_date, dir_min_date)
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
                tv_seasons=tv_seasons if isinstance(tv_seasons, list) else None,
                mr=mr,
            )
            logger.info("[shareurl_autoupdate]   group fid=%s files=%d consecutive=%s episodes=%s max_ep=%d dir_ts=%s", fid, len(file_list), is_consecutive, consecutive_episodes, max_ep, dir_updated_at)
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
                if ep > candidate_max_ep or (ep == candidate_max_ep and group_ts > candidate_best_ts):
                    candidate_max_ep = ep
                    candidate_best_ts = group_ts
                    candidate_best_fid = fid
                    logger.info("[shareurl_autoupdate] new best: ep=%d ts=%d fid=%s url=%s author=%s", ep, group_ts, fid, shareurl, suggestion.get("share_author_name"))
            elif max_ep > current_ep_int:
                # 连贯性失败但有缺口后面的集数，记录为备用
                if max_ep > candidate_later_max_ep or (max_ep == candidate_later_max_ep and group_ts > candidate_later_ts):
                    candidate_later_max_ep = max_ep
                    candidate_later_fid = fid
                    candidate_later_ts = group_ts
                    candidate_has_later = True

        if candidate_best_fid is not None:
            # 连贯性检查通过，标记已尝试，立即使用
            if tried_shareurls is not None:
                tried_shareurls.add(shareurl)
            best_shareurl = shareurl
            best_season = candidate_season
            best_episode = candidate_episode
            best_pdir_fid = candidate_best_fid
            best_taskname = str(suggestion.get("taskname") or suggestion.get("content") or "").strip()
            logger.info("[shareurl_autoupdate] consecutive check passed: shareurl=%s max_ep=%s fid=%s", shareurl, candidate_max_ep, candidate_best_fid)
            break
        elif candidate_has_later:
            # 备用候选池：不标记已尝试
            fallback_candidates.append({
                "suggestion": suggestion,
                "season": candidate_season,
                "episode": candidate_episode,
                "fid": candidate_later_fid,
                "max_ep": candidate_later_max_ep,
                "ts": candidate_later_ts,
            })
            logger.info("[shareurl_autoupdate] fallback candidate: url=%s max_ep=%d fid=%s", shareurl, candidate_later_max_ep, candidate_later_fid)
        else:
            # 没有用处的链接，标记已尝试
            if tried_shareurls is not None:
                tried_shareurls.add(shareurl)
            preview_stats["skip_not_consecutive"] = int(preview_stats.get("skip_not_consecutive") or 0) + 1
            logger.info("[shareurl_autoupdate] consecutive check FAILED: url=%s author=%s", shareurl, suggestion.get("share_author_name"))

    # 主候选池没有找到，尝试备用候选池（同样的连贯性检查逻辑）
    if best_shareurl is None and fallback_candidates:
        fallback_candidates.sort(key=lambda x: (x["max_ep"], x["ts"]), reverse=True)
        logger.info("[shareurl_autoupdate] trying %d fallback candidates", len(fallback_candidates))
        for fb in fallback_candidates:
            fb_url = str(fb["suggestion"].get("shareurl") or "").strip()
            if tried_shareurls is not None and fb_url in tried_shareurls:
                continue
            # 重新获取文件列表，走同样的连贯性检查
            fb_groups = fetch_share_file_list_grouped(db, fb_url, folder_filter=folder_filter, folder_exclude=folder_exclude, folder_filter_mode=folder_filter_mode, folder_exclude_mode=folder_exclude_mode)
            if not fb_groups:
                continue
            fb_best_fid: str | None = None
            fb_max_ep: int = 0
            fb_best_ts: int = 0
            for file_list, fid, dir_updated_at in fb_groups:
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
                    tv_seasons=tv_seasons if isinstance(tv_seasons, list) else None,
                    mr=mr,
                )
                logger.info("[shareurl_autoupdate]   fallback group fid=%s files=%d consecutive=%s episodes=%s max_ep=%d", fid, len(file_list), is_consecutive, consecutive_episodes, max_ep)
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
                # 备用候选连贯性检查通过，标记已尝试，使用
                if tried_shareurls is not None:
                    tried_shareurls.add(fb_url)
                best_shareurl = fb_url
                best_season = fb["season"]
                best_episode = fb["episode"]
                best_pdir_fid = fb_best_fid
                best_taskname = str(fb["suggestion"].get("taskname") or fb["suggestion"].get("content") or "").strip()
                candidate_max_ep = fb_max_ep
                logger.info("[shareurl_autoupdate] fallback passed: url=%s max_ep=%d fid=%s", fb_url, fb_max_ep, fb_best_fid)
                break
            else:
                # 备用候选也没通过，不标记已尝试，下次还能用
                logger.info("[shareurl_autoupdate] fallback not passed: url=%s", fb_url)

    if best_shareurl is None:
        logger.info(
            "[shareurl_autoupdate] no_better_candidate_after_preview task_id=%s task_uid=%s current=S%sE%s stats=%s",
            int(getattr(task, "id", 0) or 0),
            str(getattr(task, "task_uid", "") or ""),
            str(current_season or ""),
            str(current_episode or ""),
            json.dumps({"search": search_stats, "preview": preview_stats}, ensure_ascii=False),
        )
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
    logger.info("[shareurl_autoupdate] rewrite: best_shareurl=%s best_pdir_fid=%s new_shareurl=%s", best_shareurl, best_pdir_fid, new_shareurl)
    if not new_shareurl or new_shareurl == old_shareurl:
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

    logger.info(
        "[shareurl_autoupdate] task_id=%s old=%s new=%s current=S%sE%s next=S%sE%s",
        int(getattr(task, "id", 0) or 0),
        old_shareurl,
        new_shareurl,
        str(current_season or ""),
        str(current_episode or ""),
        str(best_season),
        str(best_episode),
    )
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
