"""
影巢任务 API 路由
"""
from __future__ import annotations

import logging
import traceback
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.schemas.task import HiveResourceOut, HiveResourceListOut
from app.services.hive_client import get_hive_client

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/status", response_model=dict)
def hive_status():
    """获取HDHive服务状态"""
    try:
        client = get_hive_client()
        result = client.get_status()
        logger.info(f"HDHive状态: {result}")
        return result
    except Exception as e:
        logger.error(f"获取HDHive状态失败: {e}")
        return {"success": False, "message": str(e)}


@router.get("/resources", response_model=HiveResourceListOut)
def hive_resources():
    """获取HDHive片单资源列表"""
    try:
        client = get_hive_client()
        
        # 先检查服务是否可用
        status = client.get_status()
        logger.info(f"HDHive服务状态: {status}")
        
        if not status.get("success"):
            return HiveResourceListOut(
                success=False,
                data=[],
                message=f"HDHive服务不可用: {status.get('message', '未知错误')}"
            )
        
        resources = client.get_resources()
        logger.info(f"获取到 {len(resources)} 个HDHive资源")
        
        # 转换为输出格式
        result_data = []
        for r in resources:
            try:
                item = HiveResourceOut(
                    item_id=r.get("item_id", 0),
                    resource_id=r.get("resource_id"),
                    title=r.get("title"),
                    media_type=r.get("media_type"),
                    tmdb_id=str(r.get("tmdb_id", "")) if r.get("tmdb_id") else None,
                    full_url=r.get("full_url") or r.get("share_url"),
                    access_code=r.get("access_code"),
                    validate_status=r.get("validate_status"),
                    uploader_name=r.get("uploader_name"),
                )
                result_data.append(item)
            except Exception as e:
                logger.warning(f"转换资源数据失败: {r} - {e}")
        
        return HiveResourceListOut(
            success=True,
            data=result_data
        )
    except Exception as e:
        logger.error(f"获取HDHive资源失败: {traceback.format_exc()}")
        return HiveResourceListOut(
            success=False,
            data=[],
            message=str(e)
        )


@router.post("/update", response_model=dict)
def hive_update():
    """触发HDHive更新资源"""
    try:
        client = get_hive_client()
        return client.update_resources()
    except Exception as e:
        logger.error(f"触发HDHive更新失败: {e}")
        return {"success": False, "message": str(e)}


@router.get("/resource/{item_id}", response_model=HiveResourceOut | None)
def hive_resource_detail(item_id: int):
    """获取单个HDHive资源详情"""
    try:
        client = get_hive_client()
        resource = client.get_resource_by_item_id(item_id)
        if resource:
            return HiveResourceOut(
                item_id=resource.get("item_id", 0),
                resource_id=resource.get("resource_id"),
                title=resource.get("title"),
                media_type=resource.get("media_type"),
                tmdb_id=str(resource.get("tmdb_id", "")) if resource.get("tmdb_id") else None,
                full_url=resource.get("full_url") or resource.get("share_url"),
                access_code=resource.get("access_code"),
                validate_status=resource.get("validate_status"),
                uploader_name=resource.get("uploader_name"),
            )
        raise HTTPException(status_code=404, detail="资源不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取HDHive资源详情失败: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
