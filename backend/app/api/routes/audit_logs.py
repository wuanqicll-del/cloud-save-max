from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import require_permissions
from app.core.permissions import AUDIT_READ, AUDIT_WRITE
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.audit_log_scheduler_setting import AuditLogSchedulerSetting
from app.schemas.audit_log import AuditLogItemOut, AuditLogListOut
from app.services.audit_logs import list_audit_logs


router = APIRouter()


class AuditLogSchedulerIn(BaseModel):
    enabled: bool | None = None
    crontab: str | None = None
    timezone: str | None = None
    retention_days: int | None = None


class AuditLogSchedulerOut(BaseModel):
    enabled: bool
    crontab: str
    timezone: str
    retention_days: int


def _get_or_create_scheduler(db: Session) -> AuditLogSchedulerSetting:
    setting = db.query(AuditLogSchedulerSetting).first()
    if not setting:
        setting = AuditLogSchedulerSetting()
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting


@router.get("", response_model=AuditLogListOut, dependencies=[Depends(require_permissions(AUDIT_READ))])
def get_audit_logs(
    page: int = 1,
    page_size: int = 20,
    q: str | None = None,
    action: str | None = None,
    success: bool | None = None,
    db: Session = Depends(get_db),
):
    rows, total = list_audit_logs(db, page=page, page_size=page_size, q=q, action=action, success=success)
    items = [
        AuditLogItemOut(
            id=row.id,
            actor_user_id=row.actor_user_id,
            actor_username=username,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            ip=row.ip,
            user_agent=row.user_agent,
            success=bool(row.success),
            detail=row.detail,
            created_at=row.created_at,
        )
        for row, username in rows
    ]
    return AuditLogListOut(page=page, page_size=page_size, total=total, items=items)


@router.delete("", dependencies=[Depends(require_permissions(AUDIT_WRITE))])
def delete_all_audit_logs(db: Session = Depends(get_db)):
    db.query(AuditLog).delete()
    db.commit()
    return {"ok": True}


@router.get("/scheduler", response_model=AuditLogSchedulerOut, dependencies=[Depends(require_permissions(AUDIT_READ))])
def get_audit_log_scheduler(db: Session = Depends(get_db)):
    setting = _get_or_create_scheduler(db)
    return AuditLogSchedulerOut(
        enabled=setting.enabled,
        crontab=setting.crontab,
        timezone=setting.timezone,
        retention_days=setting.retention_days,
    )


@router.patch("/scheduler", response_model=AuditLogSchedulerOut, dependencies=[Depends(require_permissions(AUDIT_WRITE))])
def update_audit_log_scheduler(payload: AuditLogSchedulerIn, db: Session = Depends(get_db)):
    setting = _get_or_create_scheduler(db)
    if payload.enabled is not None:
        setting.enabled = payload.enabled
    if payload.crontab is not None:
        setting.crontab = payload.crontab
    if payload.timezone is not None:
        setting.timezone = payload.timezone
    if payload.retention_days is not None:
        setting.retention_days = payload.retention_days
    db.commit()
    db.refresh(setting)
    return AuditLogSchedulerOut(
        enabled=setting.enabled,
        crontab=setting.crontab,
        timezone=setting.timezone,
        retention_days=setting.retention_days,
    )

