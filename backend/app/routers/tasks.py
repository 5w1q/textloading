import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.deps import get_current_user
from app.models import SyncTask, TaskStatus, User
from app.rate_limit import check_user_sync_rate_limit
from app.schemas import SyncTaskCreate, SyncTaskPublic, TaskCountPublic

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[SyncTaskPublic])
async def list_tasks(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
) -> list[SyncTask]:
    result = await session.execute(
        select(SyncTask)
        .where(SyncTask.user_id == user.id)
        .order_by(SyncTask.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


@router.get("/count", response_model=TaskCountPublic)
async def count_my_tasks(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> TaskCountPublic:
    q = select(func.count(SyncTask.id)).where(SyncTask.user_id == user.id)
    n = await session.scalar(q)
    return TaskCountPublic(total=int(n or 0))


@router.post("/sync", response_model=SyncTaskPublic, status_code=status.HTTP_201_CREATED)
async def enqueue_sync(
    body: SyncTaskCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> SyncTask:
    settings = get_settings()
    unique_id = body.unique_id.strip()

    await check_user_sync_rate_limit(
        request.app.state.redis_cli,
        user.id,
        settings.rate_limit_sync_per_user_per_minute,
    )

    active = await session.execute(
        select(SyncTask.id).where(
            SyncTask.user_id == user.id,
            SyncTask.unique_id == unique_id,
            SyncTask.status.in_((TaskStatus.pending, TaskStatus.running)),
        ).limit(1)
    )
    if active.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该博主已有进行中的同步任务，请等待结束后再试",
        )

    task = SyncTask(user_id=user.id, unique_id=unique_id, status=TaskStatus.pending)
    session.add(task)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该博主已有进行中的同步任务，请等待结束后再试",
        ) from None
    await session.refresh(task)

    redis = request.app.state.redis_pool
    await redis.enqueue_job("process_sync_task", str(task.id), _job_id=str(uuid.uuid4()))
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_task(
    task_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    task = await session.get(SyncTask, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.status in (TaskStatus.pending, TaskStatus.running):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="进行中的任务不可删除，请等待结束后再试",
        )
    await session.delete(task)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{task_id}", response_model=SyncTaskPublic)
async def get_task(
    task_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> SyncTask:
    task = await session.get(SyncTask, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task
