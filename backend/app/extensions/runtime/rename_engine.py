from __future__ import annotations

"""重命名引擎工厂：按任务模式返回普通规则引擎或 TMDB 对照引擎。

统一入口，避免同一批文件在预览、转存、连贯性检查、换链、进度快照里算出不同集号。
"""

from typing import Any, Callable, Iterable

from sqlalchemy.orm import Session

from app.extensions.runtime.magic_rename import MagicRename
from app.services.tmdb_rename import (
    TMDB_MODE,
    TmdbMagicRename,
    TmdbPlan,
    TmdbRenameError,
    build_plan,
    get_rename_mode,
    load_latest_season,
    normalize_source_name,
)


def _rule_engine(db: Session | None, task_data: dict[str, Any], *, rule_requires_pattern: bool) -> MagicRename | None:
    from app.services.magic_regex import get_enabled_magic_regex_map

    magic_regex = task_data.get("magic_regex") if isinstance(task_data.get("magic_regex"), dict) else None
    if magic_regex is None and db is not None:
        try:
            magic_regex = get_enabled_magic_regex_map(db)
        except Exception:
            magic_regex = None
    mr = MagicRename(magic_regex=magic_regex)
    mr.set_taskname(str(task_data.get("taskname") or ""))
    pattern = str(task_data.get("pattern") or "")
    replace = str(task_data.get("replace") or "")
    pattern, replace = mr.magic_regex_conv(pattern, replace)
    if rule_requires_pattern and not (pattern and replace):
        return None
    mr._resolved_pattern = pattern
    mr._resolved_replace = replace
    return mr


def build_rename_engine(
    db: Session | None,
    *,
    task_data: dict[str, Any],
    names: Iterable[str] | None = None,
    rule_requires_pattern: bool = False,
    log: Callable[[str], None] | None = None,
) -> MagicRename | None:
    """返回重命名引擎；TMDB 模式在数据不可用时把原因写在 plan.fatal_reason 上。"""
    name_list = [str(raw or "").strip() for raw in (names or []) if str(raw or "").strip()]
    if get_rename_mode(task_data.get("addition")) != TMDB_MODE:
        return _rule_engine(db, task_data, rule_requires_pattern=rule_requires_pattern)

    taskname = str(task_data.get("taskname") or "")
    try:
        tmdb_id = int(task_data.get("tmdb_id") or 0)
    except (TypeError, ValueError):
        tmdb_id = 0
    media_type = str(task_data.get("tmdb_media_type") or "").strip().lower()

    plan: TmdbPlan
    if tmdb_id <= 0 or media_type != "tv":
        plan = TmdbPlan()
        plan.fatal_reason = "该任务未绑定 TMDB 综艺/剧集，无法使用 TMDB 重命名"
    else:
        try:
            season, episodes = load_latest_season(db, tmdb_id, log=log)
            plan = build_plan(taskname=taskname, season=season, episodes=episodes, names=name_list)
        except TmdbRenameError as exc:
            plan = TmdbPlan()
            plan.fatal_reason = str(exc)

    if plan.fatal_reason:
        for name in name_list:
            plan.blocked.setdefault(normalize_source_name(name), str(plan.fatal_reason))
        if log is not None:
            log(f"TMDB 重命名不可用：{plan.fatal_reason}")
    for reason in plan.reasons:
        if log is not None:
            log(f"TMDB 重命名：{reason}")

    return TmdbMagicRename(taskname=taskname, plan=plan, template=str(task_data.get("replace") or ""))
