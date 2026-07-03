"""检查链接文件列表的连贯性，返回从next_episode开始的连贯集数列表"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


_RE_SEASON_EPISODE = re.compile(r"\bS(\d{1,3})E(\d{1,4})\b", re.IGNORECASE)
_RE_EPISODE_ONLY = re.compile(r"\b(?:E(?:P(?:ISODE)?)?|第)\s*0*(\d{1,4})\s*(?:集)?\b", re.IGNORECASE)
_RE_NOISE_TOKEN = re.compile(
    r"\b(?:4k|8k|2160p|1080p|720p|bluray|bdrip|web-?dl|webrip|hdtv|x264|x265|h\.?264|h\.?265|hevc|aac|dts|uhd)\b",
    re.IGNORECASE,
)
_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts", ".m2ts", ".mpg", ".mpeg", ".3gp", ".cas"}
_ARCHIVE_EXTS = {".zip"}
_MEDIA_EXTS = _VIDEO_EXTS | _ARCHIVE_EXTS


def _parse_size(size_str: str) -> int:
    """解析文件大小字符串，返回字节数"""
    size_str = str(size_str or "").strip().upper()
    if not size_str:
        return 0
    match = re.match(r"([\d.]+)\s*(B|KB|MB|GB|TB)", size_str)
    if not match:
        return 0
    num = float(match.group(1))
    unit = match.group(2)
    multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    return int(num * multipliers.get(unit, 1))


def _extract_episode(file_name: str, *, mr: Any = None) -> tuple[int | None, int | None]:
    """从文件名提取季数和集数（必须使用重命名规则）"""
    text = str(file_name or "").strip()
    if not text:
        return None, None
    # 没有重命名规则，直接返回
    if mr is None:
        return None, None
    resolved_pattern = str(getattr(mr, "_resolved_pattern", "") or "").strip()
    resolved_replace = str(getattr(mr, "_resolved_replace", "") or "").strip()
    if not resolved_pattern and not resolved_replace:
        return None, None
    # 用规则替换后提取集数
    renamed = mr.sub(resolved_pattern, resolved_replace, text)
    if match := _RE_SEASON_EPISODE.search(renamed):
        return int(match.group(1)), int(match.group(2))
    if match := _RE_EPISODE_ONLY.search(renamed):
        return None, int(match.group(1))
    return None, None


def _is_video_file(file_name: str) -> bool:
    """判断是否是视频或压缩包文件"""
    name = str(file_name or "").strip().lower()
    if not name:
        return False
    for ext in _MEDIA_EXTS:
        if name.endswith(ext):
            return True
    return False


def check_consecutive_episodes(
    file_list: list[dict[str, Any]],
    *,
    current_episode: int,
    min_size: int = 0,
    filter_words: list[str] | None = None,
    file_filter_words: list[str] | None = None,
    file_filter_is_any: bool = False,
    file_min_date: str = "",
    mr: Any = None,
) -> tuple[bool, list[int]]:
    """
    检查文件列表中从 next_episode 开始的连贯集数。
    
    返回: (is_consecutive, episode_list)
    - is_consecutive: 是否连贯（从next_episode开始无间断）
    - episode_list: 连贯的集数列表
    """
    next_episode = current_episode + 1
    filter_words_lower = [w.strip().lower() for w in (filter_words or []) if w.strip()]
    file_filter_lower = [w.strip().lower() for w in (file_filter_words or []) if w.strip()]
    
    # 收集所有有效视频文件的集数
    valid_episodes: set[int] = set()
    
    for item in file_list:
        if not isinstance(item, dict):
            continue

        file_name = str(item.get("file_name") or item.get("name") or "").strip()
        is_dir = bool(item.get("dir") or item.get("is_dir"))

        # 跳过目录
        if is_dir:
            continue

        # 跳过非视频文件
        if not _is_video_file(file_name):
            continue

        # 检查文件大小过滤
        if min_size > 0:
            size = int(item.get("size") or 0)
            if size < min_size:
                continue

        # 检查关键词过滤
        if filter_words_lower:
            name_lower = file_name.lower()
            if any(w in name_lower for w in filter_words_lower):
                continue

        # 检查文件筛选
        if file_filter_lower:
            name_lower = file_name.lower()
            if file_filter_is_any:
                if not any(w in name_lower for w in file_filter_lower):
                    continue
            else:
                if not all(w in name_lower for w in file_filter_lower):
                    continue

        # 检查文件时间过滤
        if file_min_date:
            file_ts = item.get("updated_at")
            if file_ts is not None:
                try:
                    if isinstance(file_ts, (int, float)) and file_ts > 0:
                        file_date = datetime.fromtimestamp(file_ts / 1000 if file_ts > 1e12 else file_ts).strftime("%Y-%m-%d")
                    else:
                        file_date = str(file_ts)[:10]
                    if file_date < file_min_date:
                        continue
                except Exception:
                    pass

        # 提取集数
        season, episode = _extract_episode(file_name, mr=mr)
        if episode is not None and episode >= next_episode:
            valid_episodes.add(episode)

    if not valid_episodes:
        return False, [], 0
    
    # 从 next_episode 开始收集连贯集数，遇到缺口就停
    max_episode = max(valid_episodes)
    consecutive: list[int] = []
    for ep in range(next_episode, max_episode + 1):
        if ep not in valid_episodes:
            break
        consecutive.append(ep)
    
    if not consecutive:
        # 没有从next_episode开始的连贯集数，但可能有缺口后面的集数
        has_later = max_episode >= next_episode
        return False, [], max_episode if has_later else 0
    
    return True, consecutive, max_episode
