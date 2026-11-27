from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.workers.tasks import cancel_overdue_tasks_async
from tests.conftest import register_and_login


@pytest.mark.asyncio
async def test_overdue_worker_cancels_only_active_overdue_tasks(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, admin_h, _ = await register_and_login(client, "w_admin@example.com", "w_admin")
    tid = (await client.post("/api/v1/teams", json={"name": "Worker"}, headers=admin_h)).json()["id"]
    base = f"/api/v1/teams/{tid}/tasks"
    future = (datetime.now(UTC) + timedelta(days=2)).isoformat()

    t_overdue = (await client.post(base, json={"title": "Expire", "assignee_id": admin["id"], "deadline": future}, headers=admin_h)).json()
    t_future = (await client.post(base, json={"title": "Valid", "assignee_id": admin["id"], "deadline": future}, headers=admin_h)).json()
    t_done = (await client.post(base, json={"title": "Done", "assignee_id": admin["id"], "deadline": future}, headers=admin_h)).json()
    for st in ("in_progress", "review", "done"):
        await client.patch(f"{base}/{t_done['id']}/status", json={"status": st}, headers=admin_h)

    await db_session.execute(
        update(Task)
        .where(Task.id.in_([UUID(t_overdue["id"]), UUID(t_done["id"])]))
        .values(deadline=datetime.now(UTC) - timedelta(hours=1))
    )
    await db_session.commit()

    assert await cancel_overdue_tasks_async(db_session) == 1
    assert (await client.get(f"{base}/{t_overdue['id']}", headers=admin_h)).json()["status"] == "cancelled"
    assert (await client.get(f"{base}/{t_future['id']}", headers=admin_h)).json()["status"] == "backlog"
    assert (await client.get(f"{base}/{t_done['id']}", headers=admin_h)).json()["status"] == "done"
