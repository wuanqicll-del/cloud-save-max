from __future__ import annotations

"""TMDB 重命名：用 TMDB 最新一季的集表，把「第几期 + 上/中/下」对照成集号。

约束：
- 只处理调用方传入的文件名；调用方负责先应用用户自己的过滤规则。
- 只按「期数 + 分段」匹配，不做集号、日期等猜测；对不上就跳过并写明原因。
- 附加内容（纯享/加更/花絮等）保持原名继续转存，不参与对照。
"""

import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from app.extensions.runtime.magic_rename import MagicRename


TMDB_MODE = "tmdb_rename"
RULE_MODE = "rule"

_MEDIA_EXTS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v",
    ".ts", ".m2ts", ".mpg", ".mpeg", ".3gp", ".cas", ".zip",
}

_NON_FEATURE_TOKENS = (
    "纯享", "加更", "花絮", "彩蛋", "预告", "幕后", "特辑", "番外",
    "未播", "精编版", "先导", "合集", "特别篇", "看点", "速看",
)

_SLOT_SINGLE = "整"
DEFAULT_TEMPLATE = "{TASKNAME}-{SXX}E{E0}.{EXT}"
_SLOT_ORDER = ("上", "中", "下")

_RE_SEASON_EPISODE = re.compile(r"\b[Ss](\d{1,2})[Ee]\d{1,4}\b")
_RE_EPISODE = re.compile(r"第\s*(\d{1,4}|[零一二三四五六七八九十百两]{1,5})\s*[期週周]")
_RE_EPISODE_BARE = re.compile(r"(?<![\d一二三四五六七八九十百两])(\d{1,3})\s*[期週周](?![\d])")
_RE_PART_LABEL_PAREN = re.compile(r"[（(\[【]\s*([上中下])\s*[）)\]】]")
_RE_PART_LABEL_AFTER = re.compile(r"[期週周][\s:：·、_\-—]?\s*[（(\[【]?\s*([上中下])\s*[）)\]】]?\s*(?:半部分|部分|段|篇|集)?")
_RE_PART_INDEX = re.compile(r"(?:[Pp][Aa][Rr][Tt]|[Pp])[\s_\-.]*([123])(?!\d)|([①②③])")
_RE_CN_PART = re.compile(r"[（(\[【]\s*([一二三])\s*[）)\]】]")
_RE_INDEX_TO_SLOT = {"1": "上", "2": "中", "3": "下"}
_RE_SYMBOL_TO_INDEX = {"①": "1", "②": "2", "③": "3"}
_RE_CN_INDEX = {"一": "上", "二": "中", "三": "下"}
_RE_NOISE = re.compile(
    r"(?i)\b(?:4k|8k|2160p|1080p|720p|480p|bluray|bdrip|web-?dl|webrip|hdtv|x264|x265|h\.?264|h\.?265|hevc|aac|dts|uhd|sd|hd|fhd)\b"
)
_RE_CN_DIGIT = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


class TmdbRenameError(RuntimeError):
    """TMDB 数据不可用（未配置、未绑定、没有可用集）。"""


def get_rename_mode(addition: Any) -> str:
    if not isinstance(addition, dict):
        return RULE_MODE
    return TMDB_MODE if str(addition.get("rename_mode") or "").strip().lower() == TMDB_MODE else RULE_MODE


def is_tmdb_task(task_data: Any) -> bool:
    if not isinstance(task_data, dict):
        return False
    return get_rename_mode(task_data.get("addition")) == TMDB_MODE


def normalize_source_name(name: str) -> str:
    """归一化文件名，作为对照结果的键（抗清晰度、站点噪声后缀）。"""
    text = os.path.splitext(str(name or ""))[0].lower()
    text = _RE_NOISE.sub(" ", text)
    return re.sub(r"[\s\-_·.。:：|丨/\\]+", "", text)


def _cn_number(text: str) -> int | None:
    if not text:
        return None
    total = 0
    current = 0
    for ch in text:
        if ch in _RE_CN_DIGIT:
            current = _RE_CN_DIGIT[ch]
        elif ch == "十":
            current = (current or 1) * 10
            total += current
            current = 0
        elif ch == "百":
            current = (current or 1) * 100
            total += current
            current = 0
        elif ch == "两":
            current = 2
        elif ch == "零":
            continue
        else:
            return None
    return total + current


def parse_episode_slot(name: str) -> tuple[int | None, str | None]:
    """从文件名（或 TMDB 集名）里取出期数与非空分段标记。"""
    text = str(name or "")
    episode: int | None = None
    if match := _RE_EPISODE.search(text):
        raw = match.group(1)
        episode = int(raw) if raw.isdigit() else _cn_number(raw)
    if episode is None:
        if match := _RE_EPISODE_BARE.search(text):
            episode = int(match.group(1))
    if episode is None:
        return None, None

    slot: str | None = None
    if match := _RE_PART_LABEL_PAREN.search(text):
        slot = match.group(1)
    elif match := _RE_PART_LABEL_AFTER.search(text):
        slot = match.group(1)
    if slot is None:
        if match := _RE_PART_INDEX.search(text):
            index = match.group(1) or _RE_SYMBOL_TO_INDEX.get(match.group(2) or "", "")
            slot = _RE_INDEX_TO_SLOT.get(index)
    if slot is None:
        if match := _RE_CN_PART.search(text):
            slot = _RE_CN_INDEX.get(match.group(1))
    return episode, slot


def is_non_feature(name: str) -> bool:
    text = str(name or "")
    return any(token in text for token in _NON_FEATURE_TOKENS)


def build_episode_table(episodes: Iterable[dict[str, Any]]) -> dict[str, int]:
    """把 TMDB 集列表转成「期|分段 -> 集号」对照表；未命名的占位集不参与。"""
    table: dict[str, int] = {}
    for episode in episodes or []:
        if not isinstance(episode, dict):
            continue
        number = episode.get("episode_number")
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            continue
        episode_no, slot = parse_episode_slot(str(episode.get("name") or ""))
        if episode_no is None:
            continue
        table.setdefault(f"{episode_no}|{slot or _SLOT_SINGLE}", int(number))
    return table


@dataclass
class TmdbPlan:
    season: int = 1
    table: dict[str, int] = field(default_factory=dict)
    targets: dict[str, int] = field(default_factory=dict)
    passthrough: set[str] = field(default_factory=set)
    blocked: dict[str, str] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    fatal_reason: str | None = None


def build_plan(
    *,
    taskname: str,
    season: int,
    episodes: Iterable[dict[str, Any]],
    names: Iterable[str],
) -> TmdbPlan:
    plan = TmdbPlan(season=int(season or 1))
    plan.table = build_episode_table(episodes)
    if not plan.table:
        plan.fatal_reason = "TMDB 最新一季还没有可用的集信息（可能是新季未开播或集名未录入）"

    for raw in names:
        text = str(raw or "").strip()
        if not text:
            continue
        ext = os.path.splitext(text)[1].lower()
        if ext not in _MEDIA_EXTS:
            continue
        key = normalize_source_name(text)
        if is_non_feature(text):
            plan.passthrough.add(key)
            continue
        episode_no, slot = parse_episode_slot(text)
        if episode_no is None:
            plan.blocked[key] = "文件名里没有“第N期”，无法对照 TMDB"
            continue
        number = plan.table.get(f"{episode_no}|{slot or _SLOT_SINGLE}")
        if number is None:
            plan.blocked[key] = f"TMDB 最新一季（S{plan.season:02d}）没有对应的「第{episode_no}期{slot or ''}」"
            continue
        plan.targets[key] = int(number)

    if plan.blocked and plan.fatal_reason is None:
        plan.reasons.append(f"有 {len(plan.blocked)} 个文件在 TMDB 里找不到对应集，已跳过")
    return plan


class TmdbMagicRename(MagicRename):
    """兼容 MagicRename 接口的 TMDB 引擎：sub() 直接给出 SxxExx 目标名。"""

    # 已经是本方案目标名的文件不再二次改名
    _RE_OWN_TARGET = re.compile(r"^[^/\\]*-S[0-9]{2}E[0-9]{2,3}[.](mp4|mkv|zip|avi|mov|ts)$", re.IGNORECASE)

    def __init__(self, *, taskname: str, plan: TmdbPlan, template: str = "") -> None:
        super().__init__()
        self.taskname = str(taskname or "")
        self.plan = plan
        self.season = int(plan.season or 1)
        self.template = str(template or "").strip() or DEFAULT_TEMPLATE
        # 视频/压缩包全部交给引擎判定，便于在预览里给出“为什么没重命名”
        pattern = r".*\.(?:mp4|mkv|mov|m4v|avi|mpeg|ts|zip)$"
        self.pattern = pattern
        self.replace = self.template
        self._resolved_pattern = pattern
        self._resolved_replace = self.template
        self.magic_variable["{TASKNAME}"] = self.taskname

    def magic_regex_conv(self, pattern: str, replace: str) -> tuple[str, str]:
        return self._resolved_pattern, self._resolved_replace

    def render_target(self, file_name: str, episode: int) -> str:
        """按替换表达式出目标名：季集号取 TMDB，其余占位符按原文件名解析。"""
        text = str(file_name or "")
        ext = os.path.splitext(text)[1].lstrip(".").lower()
        rendered = self.template
        for key, value in (
            ("{TASKNAME}", self.taskname),
            ("{SXX}", f"S{self.season:02d}"),
            ("{S}", str(self.season)),
            ("{E0}", f"{int(episode):02d}"),
            ("{E}", str(int(episode))),
            ("{EXT}", ext),
        ):
            rendered = rendered.replace(key, value)
        # 剩余占位符（{DATE}/{YEAR}/{PART}/{VER}/{CHINESE} 等）沿用父类规则，从原文件名里取
        if any(key in rendered for key in self.magic_variable if key != "{I}"):
            rendered = self._sub_single(None, rendered, self._prepare_sub(rendered), text)
        rendered = re.sub(r'[\\/:*?"<>|]+', " ", rendered).strip()
        # 占位符取不到值时（例如文件名没有日期却用了 {DATE}）会留下多余分隔符，收敛一下
        rendered = re.sub(r"([-_\s])\1+", r"\1", rendered)
        base, dot, suffix = rendered.rpartition(".")
        if not dot:
            base, suffix = rendered, ""
        base = base.strip("-_ ")
        rendered = f"{base}.{suffix}" if suffix else base
        if not rendered:
            return ""
        if not os.path.splitext(rendered)[1] and ext:
            rendered = f"{rendered}.{ext}"
        return rendered

    def _lookup(self, text: str) -> int | None:
        key = normalize_source_name(text)
        number = self.plan.targets.get(key)
        if number is not None:
            return int(number)
        episode_no, slot = parse_episode_slot(text)
        if episode_no is None:
            return None
        found = self.plan.table.get(f"{episode_no}|{slot or _SLOT_SINGLE}")
        return int(found) if found is not None else None

    def sub(self, pattern: str, replace: str, file_name: str) -> str:  # type: ignore[override]
        """返回目标名；对照不上的正片返回空串（调用方跳过，不再转存）。"""
        text = str(file_name or "")
        if self._RE_OWN_TARGET.match(text):
            return text
        ext = os.path.splitext(text)[1].lower()
        number = self._lookup(text)
        if number is None:
            if ext not in _MEDIA_EXTS or normalize_source_name(text) in self.plan.passthrough:
                return text
            return ""
        rendered = self.render_target(text, int(number))
        if rendered:
            return rendered
        fallback_ext = ext.lstrip(".") or "mp4"
        return f"{self.taskname}-S{self.season:02d}E{int(number):02d}.{fallback_ext}"

    def blocked_reason(self, name: str) -> str | None:
        return self.plan.blocked.get(normalize_source_name(name))


def load_latest_season(db: Any, tmdb_id: int, *, log: Callable[[str], None] | None = None) -> tuple[int, list[dict[str, Any]]]:
    """取 TMDB 里集数最多的最新一季（跳过特辑季与空季）。"""
    from app.services.tmdb_cache import get_tmdb_detail_cached

    configured, detail, _update_weekdays, _episode_weekdays, _row = get_tmdb_detail_cached(
        db, media_type="tv", tmdb_id=int(tmdb_id)
    )
    if not configured:
        raise TmdbRenameError("TMDB 未配置，无法使用 TMDB 重命名")
    if not isinstance(detail, dict):
        raise TmdbRenameError("TMDB 详情获取失败")
    seasons = detail.get("seasons_full") if isinstance(detail.get("seasons_full"), list) else []
    best_season = 0
    best_episodes: list[dict[str, Any]] = []
    for season in seasons:
        if not isinstance(season, dict):
            continue
        try:
            number = int(season.get("season_number"))
        except (TypeError, ValueError):
            continue
        episodes = season.get("episodes") if isinstance(season.get("episodes"), list) else []
        if number < 1 or not episodes:
            continue
        if number > best_season:
            best_season = number
            best_episodes = [e for e in episodes if isinstance(e, dict)]
    if best_season <= 0 or not best_episodes:
        raise TmdbRenameError("TMDB 没有可用季/集数据")
    if log is not None:
        log(f"TMDB 重命名：使用第 {best_season} 季，共 {len(best_episodes)} 集")
    return best_season, best_episodes
