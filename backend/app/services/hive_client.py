"""
HDHive API 客户端
用于从HDHive项目获取片单资源的最新分享链接
"""
from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

# 默认HDHive服务地址
DEFAULT_HIVE_BASE_URL = "http://192.168.50.41:8080"


def _get_hive_api_url() -> str:
    """从数据库获取HDHive服务地址"""
    try:
        from app.db.session import SessionLocal
        from app.models.system_setting import SystemSetting
        
        with SessionLocal() as db:
            row = db.query(SystemSetting).filter(SystemSetting.key == "hive_api_url").first()
            if row and row.value:
                return row.value.rstrip("/")
    except Exception as e:
        logger.warning(f"获取HDHive地址配置失败: {e}")
    
    return DEFAULT_HIVE_BASE_URL


class HiveClient:
    """HDHive API 客户端"""

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or _get_hive_api_url()
        logger.info(f"HDHive客户端: {self.base_url}")

    def _get(self, path: str, timeout: int = 30) -> dict[str, Any]:
        """发送GET请求"""
        url = f"{self.base_url}{path}"
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError as e:
            logger.error(f"HDHive连接失败: {url}")
            return {"success": False, "message": f"无法连接到HDHive服务"}
        except requests.exceptions.Timeout:
            logger.error(f"HDHive请求超时: {url}")
            return {"success": False, "message": "HDHive服务请求超时"}
        except requests.exceptions.RequestException as e:
            logger.error(f"HDHive API请求失败: {url} - {e}")
            return {"success": False, "message": str(e)}

    def _post(self, path: str, timeout: int = 60) -> dict[str, Any]:
        """发送POST请求"""
        url = f"{self.base_url}{path}"
        try:
            resp = requests.post(url, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError:
            logger.error(f"HDHive连接失败: {url}")
            return {"success": False, "message": f"无法连接到HDHive服务"}
        except requests.exceptions.Timeout:
            logger.error(f"HDHive请求超时: {url}")
            return {"success": False, "message": "HDHive服务请求超时"}
        except requests.exceptions.RequestException as e:
            logger.error(f"HDHive API请求失败: {url} - {e}")
            return {"success": False, "message": str(e)}

    def get_status(self) -> dict[str, Any]:
        """获取HDHive服务状态"""
        return self._get("/status")

    def get_resources(self) -> list[dict[str, Any]]:
        """获取片单资源列表"""
        result = self._get("/api/resources")
        if result.get("success"):
            return result.get("data", [])
        return []

    def get_resource_by_item_id(self, item_id: int) -> dict[str, Any] | None:
        """根据item_id获取单个资源"""
        resources = self.get_resources()
        for r in resources:
            if r.get("item_id") == item_id:
                return r
        return None

    def get_resource_latest_url(self, item_id: int) -> str | None:
        """获取资源的最新分享链接"""
        resource = self.get_resource_by_item_id(item_id)
        if resource:
            return resource.get("full_url") or resource.get("share_url")
        return None

    def update_resources(self) -> dict[str, Any]:
        """触发HDHive更新资源"""
        return self._post("/api/update")

    def is_available(self) -> bool:
        """检查HDHive服务是否可用"""
        try:
            result = self.get_status()
            return result.get("success", False)
        except Exception:
            return False


# 全局客户端实例
_hive_client: HiveClient | None = None


def get_hive_client(base_url: str | None = None) -> HiveClient:
    """获取HDHive客户端实例"""
    global _hive_client
    # 每次都重新创建，以便读取最新的配置
    _hive_client = HiveClient(base_url)
    return _hive_client
