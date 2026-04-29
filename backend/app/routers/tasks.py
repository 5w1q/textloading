import uuid
import hashlib
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.ab_client import try_consume_sync_from_request
from app.deps import get_current_user
from app.models import SyncTask, TaskStatus, User
from app.rate_limit import check_user_sync_rate_limit
from app.schemas import SyncTaskCreate, SyncTaskPublic, TaskCountPublic

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _consume_error_message(reason: str | None) -> str:
    if reason == "need_membership":
        return "当前功能需会员可用，请先在 Ab 主站开通会员"
    if reason == "insufficient_credits":
        return "积分不足，请先在 Ab 主站充值后重试"
    return "本次任务计费失败，请稍后重试"


async def _settle_task_charge(
    task: SyncTask,
    request: Request,
    session: AsyncSession,
) -> None:
    # 仅在任务成功后结算，失败不扣费
    if task.status not in (TaskStatus.completed, TaskStatus.partial):
        return
    # 无新增结果不结算（避免“完成但没有新增链接”也扣费）
    if int(task.new_links_count or 0) <= 0:
        return
    if getattr(task, "charged_at", None) is not None:
        return

    # 同一用户标识（unique_id）只结算一次：按 user_id + unique_id 生成稳定幂等键
    uid_raw = (task.unique_id or "").strip()
    uid_sig = hashlib.sha1(f"{task.user_id}:{uid_raw}".encode("utf-8")).hexdigest()[:16]
    stable_key = f"textloading:uid:{uid_sig}"
    consume = await try_consume_sync_from_request(request, stable_key)
    allowed = bool(consume.get("allowed", False))
    if not allowed:
        reason = str(consume.get("reason") or "")
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=_consume_error_message(reason),
        )
    # 兼容滚动升级：若 ORM 仍是旧模型（无 charged_at 字段），跳过本地标记，
    # 仅依赖 Ab try-consume 的 idempotency_key 保证不重复扣费。
    if hasattr(task, "charged_at"):
        task.charged_at = datetime.now(timezone.utc)
    await session.commit()


@router.get("", response_model=list[SyncTaskPublic])
async def list_tasks(
    request: Request,
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
    tasks = list(result.scalars().all())

    # 兜底补结算：避免仅依赖 /tasks/{id} 轮询导致“已完成但未扣费”。
    for t in tasks:
        try:
            await _settle_task_charge(t, request, session)
        except HTTPException:
            # 列表查询不应因单条结算失败而整体失败（例如积分不足/未登录）。
            # 具体错误会在任务详情轮询接口暴露。
            pass

    # 结算后重新读取，确保 charged_at 等字段返回最新值
    result2 = await session.execute(
        select(SyncTask)
        .where(SyncTask.user_id == user.id)
        .order_by(SyncTask.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result2.scalars().all())


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


@router.get("/{task_id}", response_model=SyncTaskPublic)
async def get_task(
    task_id: uuid.UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> SyncTask:
    task = await session.get(SyncTask, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    await _settle_task_charge(task, request, session)
    await session.refresh(task)
    return task
