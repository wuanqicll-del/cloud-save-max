import logging
import os
import re
import time


logger = logging.getLogger(__name__)


class Auto_unarchive:
    default_config = {
        "tips_": "自动云解压(zip|rar|7z)到保存目录，在任务插件选项中启用，该功能需SVIP支持",
        "global_enable": False,  # 是否全局开启自动解压
        "max_concurrent": 3,  # 限制同时解压的任务数
    }

    default_task_config = {
        "enable": False,  # 是否自动解压
        "auto_clean": True,  # 是否自动删除原始文件
        "auto_clean_zipdir": True,  # 是否删除占位目录，适用于一次性运行的任务，无须防止重复转存的占位目录
    }

    is_active = True  # 默认全局激活，由任务配置中开启

    def __init__(self, **kwargs):
        self.plugin_name = self.__class__.__name__.lower()
        if kwargs:
            for key, _ in self.default_config.items():
                if key in kwargs:
                    setattr(self, key, kwargs[key])

    def run(self, task, **kwargs):
        account = kwargs.get("account")
        tree = kwargs.get("tree")

        task_config = task.get("addition", {}).get(self.plugin_name, self.default_task_config)

        if not str(self.global_enable).lower() == "true":
            if not task_config.get("enable"):
                return task

        # 任务配置中是否自动删除原始文件
        self.auto_clean = task_config.get("auto_clean", True)
        self.auto_clean_zipdir = task_config.get("auto_clean_zipdir", False)

        try:
            savepath = re.sub(r"/{2,}", "/", f"/{task['savepath']}").rstrip("/")
            target_pdir_fid = account.savepath_fid.get(savepath) if hasattr(account, "savepath_fid") else None

            if not target_pdir_fid:
                logger.warning("🟨 [%s] 未找到保存目录 fid，跳过云解压：%s", task.get("taskname", ""), savepath)
                return task

            drive_type = getattr(account, "DRIVE_TYPE", "") or ("quark" if account.__class__.__name__ == "Quark" else "")
            if drive_type and drive_type not in {"quark", "uc"}:
                logger.warning("⚠️ [%s] %s 网盘未适配云解压，跳过插件执行", task["taskname"], drive_type)
                return task

            # 获取待解压节点列表
            all_zip_nodes = [
                node
                for node in tree.all_nodes()
                if node.data
                and not node.data.get("is_dir")
                and re.search(r"\.(zip|rar|7z)$", node.tag, re.I)
            ]
            if not all_zip_nodes:
                return task

            # 加载重命名规则
            from app.extensions.runtime.magic_rename import MagicRename
            task_pattern = str(task.get("pattern") or "").strip()
            task_replace = str(task.get("replace") or "").strip()
            mr = None
            if task_pattern or task_replace:
                try:
                    mr = MagicRename()
                    mr.taskname = str(task.get("taskname") or "").strip()
                    task_pattern, task_replace = mr.magic_regex_conv(task_pattern, task_replace)
                    mr._resolved_pattern = task_pattern
                    mr._resolved_replace = task_replace
                except Exception:
                    mr = None

            wait_list = all_zip_nodes.copy()  # 等待提交队列
            active_tasks = []  # 正在解压队列
            all_move_fids = []
            all_rename_ops = []  # (fid, new_name)
            all_cleanup_fids = []


            while wait_list or active_tasks:

                while len(active_tasks) < int(self.max_concurrent) and wait_list:
                    node = wait_list.pop(0)
                    zip_fid = node.data["fid"]
                    zip_name = node.data["file_name_re"]
                    main_name = os.path.splitext(zip_name)[0]

                    # 解压到根目录
                    res = account.unarchive(zip_fid, "0")
                    if res.get("code") == 0:
                        task_id = res["data"]["task_id"]
                        active_tasks.append(
                            {
                                "task_id": task_id,
                                "zip_fid": zip_fid,
                                "main_name": main_name,
                                "zip_name": zip_name,
                            }
                        )
                    else:
                        logger.warning("  ❌ 提交失败: %s (%s)", zip_name, res.get("message"))
                        if "concurrent" in res.get("message", ""):
                            wait_list.insert(0, node)
                            break
                    time.sleep(1)

                for p_task in active_tasks[:]:
                    q_res = account.query_task(p_task["task_id"])

                    q_status = q_res.get("status")
                    q_data = q_res.get("data") or {}
                    if q_status == 200 and q_data.get("status") == 2:
                        self._process_files(
                            account,
                            p_task,
                            q_res,
                            target_pdir_fid,
                            mr,
                            all_move_fids,
                            all_rename_ops,
                            all_cleanup_fids,
                        )
                        active_tasks.remove(p_task)
                    elif q_status == 200 and q_data.get("status") == 4:
                        err_msg = (q_data.get("unarchive_result") or {}).get("message") or q_data.get("message") or "解压失败"
                        logger.warning("  ❌ 解压失败: %s %s", p_task["zip_name"], err_msg)
                        active_tasks.remove(p_task)
                    elif q_status != 200:
                        logger.warning("  ⚠️ 查询失败: %s %s", p_task["zip_name"], q_res.get("message", ""))
                        active_tasks.remove(p_task)

                if active_tasks:
                    time.sleep(5)

            # 批量移动文件到保存目录
            if all_move_fids:
                if account.move_files(all_move_fids, target_pdir_fid).get("code") == 0:
                    # 移动后执行重命名
                    for fid, new_name in all_rename_ops:
                        try:
                            account.rename(fid, new_name)
                        except Exception as e:
                            logger.warning("  ❌ 重命名失败: %s (%s)", new_name, e)
                    # 清理
                    if all_cleanup_fids:
                        if account.delete(all_cleanup_fids):
                            pass
                else:
                    logger.warning("  ❌ 移动文件失败")

        except Exception as e:
            logger.exception("❌ 运行异常: %s", e)
        return task

    def _process_files(self, account, p_task, q_res, target_fid, mr, move_list, rename_ops, clean_list):
        """处理解压后的文件"""
        # 获取解压出来的目录
        un_list = q_res.get("data", {}).get("unarchive_result", {}).get("list", [])
        sub_dir_fid = next(
            (i["fid"] for i in un_list if p_task["main_name"] == i["file_name"]), None
        )
        if not sub_dir_fid:
            return

        if self.auto_clean:
            # 压缩包加入清理队列
            clean_list.append(p_task["zip_fid"])
            if self.auto_clean_zipdir:
                # 解压目录加入清理队列
                clean_list.append(sub_dir_fid)
            else:
                # 不自动清理时，解压目录重命名为压缩包名称占位
                account.rename(sub_dir_fid, p_task["zip_name"])
        else:
            # 不自动清理时，解压目录加入清理队列
            clean_list.append(sub_dir_fid)

        # 获取解压目录下的所有文件并应用重命名
        try:
            ls_res = account.ls_dir(sub_dir_fid)
            items = (((ls_res or {}).get("data") or {}).get("list")) or []
            for item in items:
                if item.get("dir"):
                    continue
                move_list.append(item["fid"])
                # 应用重命名规则
                if mr:
                    try:
                        file_name = str(item.get("file_name") or "").strip()
                        new_name = mr.sub(mr._resolved_pattern, mr._resolved_replace, file_name)
                        if new_name and new_name != file_name:
                            rename_ops.append((item["fid"], new_name))
                    except Exception:
                        pass
        except Exception as e:
            logger.warning("  ❌ 读取解压目录失败: %s", e)
