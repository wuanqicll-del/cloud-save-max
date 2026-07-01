from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, get_current_user, require_permissions
from app.core.permissions import TASK_READ, TASK_WRITE
from app.db.session import get_db
from app.schemas.resource_search import ResourceSearchSourceListOut, ResourceSearchSourceUpdateIn
from app.services import audit
from app.services.resource_search import get_quark_share_author, list_sources, update_source


router = APIRouter()


class ShareAuthorOut(BaseModel):
    author_name: str = ""


@router.get("/sources", response_model=ResourceSearchSourceListOut, dependencies=[Depends(require_permissions(TASK_READ))])
def get_resource_search_sources(db: Session = Depends(get_db)) -> ResourceSearchSourceListOut:
    return ResourceSearchSourceListOut(sources=list_sources(db))


@router.get("/share-author", response_model=ShareAuthorOut, dependencies=[Depends(require_permissions(TASK_READ))])
def get_share_author(shareurl: str = Query("", description="分享链接")) -> ShareAuthorOut:
    """获取夸克分享链接的分享者昵称"""
    author = get_quark_share_author(shareurl) or ""
    return ShareAuthorOut(author_name=author)


@router.patch("/sources/{key}", response_model=ResourceSearchSourceListOut, dependencies=[Depends(require_permissions(TASK_WRITE))])
def patch_resource_search_source(
    request: Request,
    key: str,
    payload: ResourceSearchSourceUpdateIn,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResourceSearchSourceListOut:
    row = update_source(db, key=key, payload=payload.model_dump(exclude_unset=True))
    audit.write_audit_log(
        db,
        actor_user_id=current.user.id,
        action="resource_search.source.update",
        target_type="resource_search_source",
        target_id=str(row.key),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        success=True,
    )
    db.commit()
    return ResourceSearchSourceListOut(sources=list_sources(db))

