from __future__ import annotations

import re
from datetime import date
from typing import Any


_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_COMPACT_DATE = re.compile(r"(?<!\d)((?:19|20)\d{2})(\d{2})(\d{2})(?!\d)")
_MEDIA_NUMBER = re.compile(
    r"(?i)(?<![a-z0-9])(?:s\d{1,3}e|ep(?:isode)?|e)\s*\d{1,4}(?!\d)"
    r"|第\s*\d{1,4}\s*[集话話期]"
    r"|(?<!\d)\d{3,4}\s*[x×]\s*\d{3,4}(?!\d)"
    r"|(?<!\d)\d{3,4}[pi](?![a-z0-9])"
)


def normalize_year(value: Any) -> str | None:
    text = str(value or "").strip()
    return text if re.fullmatch(r"(?:19|20)\d{2}", text) else None


def year_filter_enabled(addition: dict[str, Any]) -> bool:
    enabled = addition.get("year_filter_enabled", True)
    return enabled is not False and str(enabled).strip().lower() not in {"0", "false", "off", ""}


def active_filter_year(addition: dict[str, Any]) -> str | None:
    return normalize_year(addition.get("filter_year")) if year_filter_enabled(addition) else None


def name_years(name: str) -> set[str]:
    text = _MEDIA_NUMBER.sub("", str(name or ""))
    years = set(_YEAR.findall(text))
    for match in _COMPACT_DATE.finditer(text):
        try:
            date(*(int(part) for part in match.groups()))
        except ValueError:
            continue
        years.add(match.group(1))
    return years


def year_allowed(name: str, filter_year: str | None) -> bool:
    if not filter_year:
        return True
    years = name_years(name)
    return not years or years == {filter_year}


def share_path_year_reason(data: dict[str, Any], pdir_fid: str, filter_year: str | None) -> str | None:
    if not filter_year:
        return None
    current_fid = str(data.get("resolved_pdir_fid") or pdir_fid or "")
    path = data.get("full_path")
    names = []
    if isinstance(path, list):
        for item in path:
            if isinstance(item, dict):
                name = str(item.get("file_name") or item.get("name") or "").strip()
                if name and name != "/":
                    names.append(name)
    # Path-style IDs are actual directory paths, not share-title hints.
    if current_fid.startswith("/"):
        names.extend(part for part in current_fid.split("/") if part)
    for name in names:
        if not year_allowed(name, filter_year):
            return f"文件夹年份不符：{name}（目标 {filter_year}）"
    if current_fid not in {"", "0", "/", "root"} and not names:
        return "无法获取当前文件夹名称，年份过滤已阻止转存；请重新选择目录或关闭年份过滤"
    return None



def latest_tmdb_year(detail: dict[str, Any], *, today: date | None = None) -> str | None:
    """Resolve the latest aired regular-season episode, never the series premiere."""
    today = today or date.today()
    aired: list[tuple[int, int, date]] = []

    def add_episode(ep: dict[str, Any], season_number: Any = None) -> None:
        try:
            season = int((season_number if season_number is not None else ep.get("season_number")) or 0)
            number = int(ep.get("episode_number") or 0)
            aired_on = date.fromisoformat(str(ep.get("air_date") or ""))
        except (ValueError, TypeError):
            return
        if season > 0 and number > 0 and aired_on <= today:
            aired.append((season, number, aired_on))

    for season in detail.get("seasons_full") or []:
        if not isinstance(season, dict):
            continue
        for ep in season.get("episodes") or []:
            if isinstance(ep, dict):
                add_episode(ep, season.get("season_number"))
    last_episode = detail.get("last_episode_to_air")
    if isinstance(last_episode, dict):
        add_episode(last_episode)
    if aired:
        return normalize_year(max(aired)[2].year)
    seasons: list[tuple[int, date]] = []
    for season in detail.get("seasons") or []:
        if not isinstance(season, dict):
            continue
        try:
            number = int(season.get("season_number") or 0)
            aired_on = date.fromisoformat(str(season.get("air_date") or ""))
        except (ValueError, TypeError):
            continue
        if number > 0 and aired_on <= today:
            seasons.append((number, aired_on))
    return normalize_year(max(seasons)[1].year) if seasons else None
