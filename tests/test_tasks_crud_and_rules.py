from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from tests.conftest import invite_and_join, register_and_login


@pytest.mark.asyncio
async def test_task_lifecycle_and_strict_rules_even_for_admin(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, admin_h, _ = await register_and_login(client, "t_admin@example.com", "t_admin")
    dev, dev_h, _ = await register_and_login(client, "t_dev@example.com", "t_dev")

    team = (await client.post("/api/v1/teams", json={"name": "Rules"}, headers=admin_h)).json()
    tid = team["id"]
    await invite_and_join(client, admin_h, tid, team["join_code"], dev["email"], dev_h)

    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    future = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    base = f"/api/v1/teams/{tid}/tasks"

    assert (await client.post(base, json={"title": "Past", "deadline": past}, headers=admin_h)).status_code == 400

    t1 = (await client.post(base, json={"title": "Auth", "priority": "high", "assignee_id": None, "deadline": future}, headers=admin_h)).json()
    u1 = f"{base}/{t1['id']}"
    assert t1["status"] == "backlog" and t1["assignee_id"] is None

    assert (await client.patch(u1, json={"status": "in_progress"}, headers=admin_h)).status_code == 422
    assert (await client.patch(f"{u1}/status", json={"status": "done"}, headers=admin_h)).status_code == 409
    assert (await client.patch(f"{u1}/status", json={"status": "in_progress"}, headers=admin_h)).status_code == 200
    assert (await client.patch(f"{u1}/status", json={"status": "backlog"}, headers=admin_h)).status_code == 409
    assert (await client.delete(u1, headers=admin_h)).status_code == 409
    assert (await client.patch(f"{u1}/status", json={"status": "review"}, headers=admin_h)).status_code == 400

    assert (await client.patch(u1, json={"assignee_id": dev["id"]}, headers=admin_h)).status_code == 200
    assert (await client.patch(f"{u1}/status", json={"status": "review"}, headers=admin_h)).status_code == 200
    assert (await client.delete(u1, headers=admin_h)).status_code == 409
    assert (await client.patch(u1, json={"assignee_id": admin["id"]}, headers=admin_h)).status_code == 409
    assert (await client.patch(f"{u1}/status", json={"status": "in_progress"}, headers=admin_h)).status_code == 409
    assert (await client.patch(f"{u1}/status", json={"status": "cancelled"}, headers=admin_h)).status_code == 200
    assert (await client.patch(u1, json={"title": "Edit"}, headers=admin_h)).status_code == 409
    assert (await client.delete(u1, headers=admin_h)).status_code == 204

    t2 = (await client.post(base, json={"title": "Expired", "assignee_id": dev["id"], "deadline": future}, headers=admin_h)).json()
    u2 = f"{base}/{t2['id']}"
    await client.patch(f"{u2}/status", json={"status": "in_progress"}, headers=admin_h)
    await client.patch(f"{u2}/status", json={"status": "review"}, headers=admin_h)
    await db_session.execute(update(Task).where(Task.id == UUID(t2["id"])).values(deadline=datetime.now(UTC) - timedelta(minutes=5)))
    await db_session.commit()
    assert (await client.patch(f"{u2}/status", json={"status": "done"}, headers=admin_h)).status_code == 400

    t3 = (await client.post(base, json={"title": "Departure", "assignee_id": dev["id"], "deadline": future}, headers=admin_h)).json()
    u3 = f"{base}/{t3['id']}"
    await client.patch(f"{u3}/status", json={"status": "in_progress"}, headers=admin_h)
    await client.patch(f"{u3}/status", json={"status": "review"}, headers=admin_h)
    assert (await client.delete(f"/api/v1/teams/{tid}/members/{dev['id']}", headers=dev_h)).status_code == 204
    reopened = (await client.get(u3, headers=admin_h)).json()
    assert reopened["status"] == "in_progress" and reopened["assignee_id"] is None

    assert (await client.patch(u3, json={"assignee_id": admin["id"]}, headers=admin_h)).status_code == 200
    assert (await client.patch(f"{u3}/status", json={"status": "review"}, headers=admin_h)).status_code == 200
    assert (await client.patch(f"{u3}/status", json={"status": "done"}, headers=admin_h)).status_code == 200
    assert (await client.patch(u3, json={"title": "Nope"}, headers=admin_h)).status_code == 409
    assert (await client.delete(u3, headers=admin_h)).status_code == 204


@pytest.mark.asyncio
async def test_max_ten_active_tasks_per_team(client: AsyncClient) -> None:
    admin, admin_h, _ = await register_and_login(client, "lim_adm@example.com", "lim_adm")
    team1 = (await client.post("/api/v1/teams", json={"name": "T1"}, headers=admin_h)).json()
    team2 = (await client.post("/api/v1/teams", json={"name": "T2"}, headers=admin_h)).json()

    ids = []
    for i in range(10):
        resp = await client.post(f"/api/v1/teams/{team1['id']}/tasks", json={"title": f"Task {i}", "assignee_id": admin["id"]}, headers=admin_h)
        assert resp.status_code == 201
        ids.append(resp.json()["id"])

    assert (await client.post(f"/api/v1/teams/{team1['id']}/tasks", json={"title": "Task 11", "assignee_id": admin["id"]}, headers=admin_h)).status_code == 409
    assert (await client.post(f"/api/v1/teams/{team2['id']}/tasks", json={"title": "Other", "assignee_id": admin["id"]}, headers=admin_h)).status_code == 201
    assert (await client.patch(f"/api/v1/teams/{team1['id']}/tasks/{ids[0]}/status", json={"status": "cancelled"}, headers=admin_h)).status_code == 200
    assert (await client.post(f"/api/v1/teams/{team1['id']}/tasks", json={"title": "Task 11 ok", "assignee_id": admin["id"]}, headers=admin_h)).status_code == 201
