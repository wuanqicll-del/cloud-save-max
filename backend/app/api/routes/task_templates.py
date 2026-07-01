from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.task_template import TaskTemplate

router = APIRouter()


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    config: dict[str, Any] = Field(default_factory=dict)


class TemplateUpdateIn(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    config: dict[str, Any] | None = None


class TemplateOut(BaseModel):
    id: int
    name: str
    config: dict[str, Any]
    created_at: str | None = None
    updated_at: str | None = None


def _to_out(row: TaskTemplate) -> TemplateOut:
    config = {}
    try:
        config = json.loads(row.config_json) if row.config_json else {}
    except Exception:
        pass
    return TemplateOut(
        id=row.id,
        name=row.name,
        config=config,
        created_at=str(row.created_at) if row.created_at else None,
        updated_at=str(row.updated_at) if row.updated_at else None,
    )


@router.get("", response_model=list[TemplateOut])
def list_templates(db: Session = Depends(get_db)):
    rows = db.execute(select(TaskTemplate).order_by(TaskTemplate.id.desc())).scalars().all()
    return [_to_out(r) for r in rows]


@router.post("", response_model=TemplateOut)
def create_template(payload: TemplateIn, db: Session = Depends(get_db)):
    row = TaskTemplate(
        name=payload.name,
        config_json=json.dumps(payload.config, ensure_ascii=False),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.patch("/{template_id:int}", response_model=TemplateOut)
def update_template(template_id: int, payload: TemplateUpdateIn, db: Session = Depends(get_db)):
    row = db.execute(select(TaskTemplate).where(TaskTemplate.id == template_id)).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    if payload.name is not None:
        row.name = payload.name
    if payload.config is not None:
        row.config_json = json.dumps(payload.config, ensure_ascii=False)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.delete("/{template_id:int}")
def delete_template(template_id: int, db: Session = Depends(get_db)):
    row = db.execute(select(TaskTemplate).where(TaskTemplate.id == template_id)).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    db.delete(row)
    db.commit()
    return {"success": True}
