import asyncio
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.repositories.task import TaskRepository
from app.workers.celery_app import celery_app


async def cancel_overdue_tasks_async(session: AsyncSession | None = None) -> int:
    now = datetime.now(UTC)
    if session is not None:
        count = await TaskRepository(session).cancel_overdue_tasks(now)
        await session.commit()
        return count

    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as db_session:
            count = await TaskRepository(db_session).cancel_overdue_tasks(now)
            await db_session.commit()
            return count
    finally:
        await engine.dispose()


@celery_app.task(
    name="app.workers.tasks.cancel_overdue_tasks",
    ignore_result=True,
    soft_time_limit=30,
    time_limit=60,
)
def cancel_overdue_tasks() -> int:
    return asyncio.run(cancel_overdue_tasks_async())
