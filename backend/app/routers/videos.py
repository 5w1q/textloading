import json
import re
from datetime import datetime
from io import BytesIO
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import get_current_user
from app.models import SyncTask, TaskStatus, User, UserVideo
from app.schemas import UniqueIdRowPublic, UserVideoPublic, VideoCountPublic, VideosSummaryPublic

router = APIRouter(prefix="/videos", tags=["videos"])

_EXPORT_MAX_ROWS = 20_000


def _ascii_filename(name: str) -> str:
    safe = re.sub(r"[^\w.\-]", "_", name)[:120]
    return safe or "export"


def _export_base_name(unique_id: str | None, stamp: str) -> str:
    if not unique_id or not unique_id.strip():
        return f"douyin-links-all-{stamp}"
    u = unique_id.strip()
    slug = re.sub(r"[^\w.\-]", "_", u)[:48].strip("_") or "user"
    return f"douyin-links-{slug}-{stamp}"


def _videos_query(user_id: int, unique_id: str | None):
    q = select(UserVideo).where(UserVideo.user_id == user_id)
    if unique_id is not None and unique_id.strip() != "":
        q = q.where(UserVideo.unique_id == unique_id.strip())
    return q.order_by(UserVideo.created_at.desc()).limit(_EXPORT_MAX_ROWS)


@router.get("/identifiers", response_model=list[UniqueIdRowPublic])
async def list_video_unique_ids(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[UniqueIdRowPublic]:
    """当前账号下出现过的用户标识（按该标识下最新一条采集时间排序）。"""
    result = await session.execute(
        select(UserVideo.unique_id, func.count(UserVideo.id).label("cnt"))
        .where(UserVideo.user_id == user.id)
        .group_by(UserVideo.unique_id)
        .order_by(func.max(UserVideo.created_at).desc())
    )
    return [UniqueIdRowPublic(unique_id=row[0], video_count=int(row[1])) for row in result.all()]


@router.get("/count", response_model=VideoCountPublic)
async def count_my_videos(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    unique_id: str | None = Query(None, description="只统计该用户标识下的条数", max_length=128),
) -> VideoCountPublic:
    q = select(func.count(UserVideo.id)).where(UserVideo.user_id == user.id)
    if unique_id is not None and unique_id.strip() != "":
        q = q.where(UserVideo.unique_id == unique_id.strip())
    n = await session.scalar(q)
    return VideoCountPublic(total=int(n or 0))


@router.get("/summary", response_model=VideosSummaryPublic)
async def videos_sync_summary(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> VideosSummaryPublic:
    """最近一次 completed / partial 的同步任务（按更新时间）。"""
    result = await session.execute(
        select(SyncTask)
        .where(
            SyncTask.user_id == user.id,
            SyncTask.status.in_((TaskStatus.completed, TaskStatus.partial)),
        )
        .order_by(SyncTask.updated_at.desc())
        .limit(1)
    )
    t = result.scalar_one_or_none()
    if t is None:
        return VideosSummaryPublic()
    return VideosSummaryPublic(
        last_sync_unique_id=t.unique_id,
        last_sync_task_id=t.id,
        last_sync_at=t.updated_at,
        last_sync_status=t.status.value,
    )


@router.get("/export")
async def export_my_videos(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    export_format: Literal["txt", "json", "xlsx"] = Query("txt", alias="format"),
    unique_id: str | None = Query(
        None,
        description="仅导出该用户标识下的全部已采链接；不传则导出当前账号全部",
        max_length=128,
    ),
) -> Response:
    uid = unique_id.strip() if unique_id else None
    result = await session.execute(_videos_query(user.id, uid))
    rows: list[UserVideo] = list(result.scalars().all())
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    base = _export_base_name(uid, stamp)

    if export_format == "json":
        payload = [
            {
                "unique_id": v.unique_id,
                "aweme_id": v.aweme_id,
                "share_url": v.share_url,
                "sec_uid": v.sec_uid,
                "created_at": v.created_at.isoformat(),
                "source_task_id": str(v.source_task_id) if v.source_task_id else None,
            }
            for v in rows
        ]
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        return Response(
            content=body,
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{_ascii_filename(base + ".json")}"',
            },
        )

    if export_format == "txt":
        lines = ["unique_id\taweme_id\tshare_url\tcreated_at\tsource_task_id"]
        for v in rows:
            tid = str(v.source_task_id) if v.source_task_id else ""
            lines.append(
                f"{v.unique_id}\t{v.aweme_id}\t{v.share_url}\t{v.created_at.isoformat()}\t{tid}"
            )
        body = "\n".join(lines).encode("utf-8")
        return Response(
            content=body,
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{_ascii_filename(base + ".txt")}"',
            },
        )

    if export_format == "xlsx":
        wb = Workbook()
        ws = wb.active
        ws.title = "links"
        ws.append(["unique_id", "aweme_id", "share_url", "sec_uid", "created_at", "source_task_id"])
        for v in rows:
            ws.append(
                [
                    v.unique_id,
                    v.aweme_id,
                    v.share_url,
                    v.sec_uid,
                    v.created_at.isoformat(),
                    str(v.source_task_id) if v.source_task_id else "",
                ]
            )
        bio = BytesIO()
        wb.save(bio)
        body = bio.getvalue()
        return Response(
            content=body,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{_ascii_filename(base + ".xlsx")}"',
            },
        )

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="format 须为 txt、json 或 xlsx")


@router.get("", response_model=list[UserVideoPublic])
async def list_my_videos(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    unique_id: str | None = Query(None, description="只列出该用户标识下的链接", max_length=128),
) -> list[UserVideo]:
    q = select(UserVideo).where(UserVideo.user_id == user.id)
    if unique_id is not None and unique_id.strip() != "":
        q = q.where(UserVideo.unique_id == unique_id.strip())
    q = q.order_by(UserVideo.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(q)
    return list(result.scalars().all())
