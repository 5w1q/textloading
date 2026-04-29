import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.factory import get_douyin_adapter
from app.config import get_settings
from app.douyin_pool import douyin_fetch_slot, init_douyin_permit_pool
from app.models import SyncTask, TaskStatus, UniqueIdMapping, UserVideo

logger = logging.getLogger(__name__)


async def _with_fetch_slot(redis, pool: int, fn):
    if redis is None or pool <= 0:
        return await fn()
    await init_douyin_permit_pool(redis, pool)
    async with douyin_fetch_slot(redis):
        return await fn()


async def process_sync_task(ctx: dict, task_id: str) -> None:
    settings = get_settings()
    adapter = get_douyin_adapter(settings)
    session_factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    redis = ctx.get("redis_cli")
    pool = settings.douyin_fetch_max_concurrent

    tid = UUID(task_id)
    async with session_factory() as session:
        task = await session.get(SyncTask, tid)
        if task is None:
            logger.error("sync task not found: %s", task_id)
            return

        task.status = TaskStatus.running
        task.error_message = None
        await session.commit()

        try:
            unique_id = task.unique_id.strip()
            result = await session.execute(select(UniqueIdMapping).where(UniqueIdMapping.unique_id == unique_id))
            mapping = result.scalar_one_or_none()
            if mapping:
                sec_uid = mapping.sec_uid
            else:

                async def _resolve():
                    return await adapter.resolve_sec_uid(unique_id)

                sec_uid = await _with_fetch_slot(redis, pool, _resolve)
                session.add(UniqueIdMapping(unique_id=unique_id, sec_uid=sec_uid))
                await session.flush()

            task.sec_uid = sec_uid
            await session.commit()

            cursor = task.cursor
            new_total = 0
            max_new = settings.max_new_links_per_task

            while new_total < max_new:

                async def _page():
                    return await adapter.fetch_user_post_page(sec_uid, cursor)

                page = await _with_fetch_slot(redis, pool, _page)
                if not page.items:
                    break

                for item in page.items:
                    stmt = (
                        insert(UserVideo)
                        .values(
                            user_id=task.user_id,
                            unique_id=unique_id,
                            sec_uid=sec_uid,
                            aweme_id=item.aweme_id,
                            share_url=item.share_url,
                            source_task_id=task.id,
                        )
                        .on_conflict_do_nothing(constraint="uq_user_video_aweme")
                        .returning(UserVideo.id)
                    )
                    res = await session.execute(stmt)
                    if res.scalar_one_or_none() is not None:
                        new_total += 1
                        if new_total >= max_new:
                            break

                cursor = page.next_cursor
                task.cursor = cursor
                task.new_links_count = new_total
                await session.commit()

                if new_total >= max_new:
                    break
                if not page.has_more:
                    break
                if cursor is None:
                    break

            task.status = TaskStatus.completed
            task.new_links_count = new_total
            await session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.exception("sync task failed: %s", task_id)
            async with session_factory() as session2:
                t2 = await session2.get(SyncTask, tid)
                if t2:
                    # 已提交过若干页时 new_links_count>0：标为 partial，避免与「完全失败」混淆
                    if (t2.new_links_count or 0) > 0:
                        t2.status = TaskStatus.partial
                    else:
                        t2.status = TaskStatus.failed
                    t2.error_message = str(exc)[:4000]
                    await session2.commit()
