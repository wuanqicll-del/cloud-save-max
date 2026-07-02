import logging
import os
import time
from datetime import datetime


logger = logging.getLogger(__name__)


class Trigger_scan:
    """转存新文件后写标记文件，用于触发外部扫描脚本"""

    default_config = {
        "tips_": "转存新文件后写标记文件到指定目录，用于触发外部扫描脚本（如飞牛影视库刷新）",
        "global_enable": False,
        "global_enable_label": "全局启用",
        "trigger_dir": "/app/data/sync",
        "trigger_dir_label": "标记文件目录",
        "trigger_filename": "trigger_scan",
        "trigger_filename_label": "标记文件名",
    }

    default_task_config = {
        "enable": False,
    }

    is_active = True

    def __init__(self, **kwargs):
        self.plugin_name = self.__class__.__name__.lower()
        for key, default in self.default_config.items():
            setattr(self, key, kwargs.get(key, default))

    def run(self, task, **kwargs):
        task_config = task.get("addition", {}).get(self.plugin_name, self.default_task_config)

        if not str(self.global_enable).lower() == "true":
            if not task_config.get("enable"):
                return task

        trigger_dir = str(self.trigger_dir or "").strip()
        trigger_filename = str(self.trigger_filename or "trigger_scan").strip()

        if not trigger_dir:
            logger.warning("🟨 [trigger_scan] trigger_dir 未配置")
            return task

        try:
            os.makedirs(trigger_dir, exist_ok=True)
            trigger_path = os.path.join(trigger_dir, trigger_filename)
            taskname = str(task.get("taskname") or "").strip()
            savepath = str(task.get("savepath") or "").strip()
            with open(trigger_path, "w", encoding="utf-8") as f:
                f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}|{taskname}|{savepath}\n")
        except Exception as e:
            logger.error("🟥 [trigger_scan] 写入标记文件失败: %s", str(e))

        return task

    def task_after(self, tasklist=None, account=None):
        """task_after 钩子，转存完成后执行"""
        if not tasklist:
            return {}
        for task in tasklist:
            if isinstance(task, dict):
                self.run(task, account=account)
        return {}
