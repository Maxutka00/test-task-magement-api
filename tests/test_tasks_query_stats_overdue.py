from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from tests.conftest import invite_and_join, register_and_login


@pytest.mark.asyncio
async def test_search_filter_sort_pagination_overdue_and_stats(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, admin_h, _ = await register_and_login(client, "q_admin@example.com", "q_admin")
    dev, dev_h, _ = await register_and_login(client, "q_dev@example.com", "q_dev")

    team = (await client.post("/api/v1/teams", json={"name": "Query"}, headers=admin_h)).json()
    tid = team["id"]
    await invite_and_join(client, admin_h, tid, team["join_code"], dev["email"], dev_h)

    now = datetime.now(UTC)
    d1, d2, d3 = [(now + timedelta(days=d)).isoformat() for d in (1, 3, 5)]
    base = f"/api/v1/teams/{tid}/tasks"

    t_low = (await client.post(base, json={"title": "Low", "description": "docs", "priority": "low", "deadline": d1, "assignee_id": admin["id"]}, headers=admin_h)).json()
    t_high_late = (await client.post(base, json={"title": "High late", "description": "billing", "priority": "high", "deadline": d3, "assignee_id": dev["id"]}, headers=admin_h)).json()
    t_high_soon = (await client.post(base, json={"title": "High soon", "description": "urgent payment", "priority": "high", "deadline": d2, "assignee_id": dev["id"]}, headers=admin_h)).json()
    t_med = (await client.post(base, json={"title": "Med", "description": "payment retry", "priority": "medium", "deadline": d2, "assignee_id": admin["id"]}, headers=admin_h)).json()

    default_items = (await client.get(base, headers=dev_h)).json()["items"]
    assert [i["id"] for i in default_items] == [t_high_soon["id"], t_high_late["id"], t_med["id"], t_low["id"]]
    assert (await client.get(f"{base}?search=payment", headers=dev_h)).json()["total"] == 2
    assert (await client.get(f"{base}?priority=high&assignee_id={dev['id']}", headers=dev_h)).json()["total"] == 2

    page2 = (await client.get(f"{base}?page=2&size=2", headers=dev_h)).json()
    assert page2["pages"] == 2 and [i["id"] for i in page2["items"]] == [t_med["id"], t_low["id"]]

    by_dl = (await client.get(f"{base}?sort_by=deadline&sort_order=asc", headers=dev_h)).json()["items"]
    assert by_dl[0]["id"] == t_low["id"] and by_dl[-1]["id"] == t_high_late["id"]

    await db_session.execute(update(Task).where(Task.id == UUID(t_low["id"])).values(deadline=now - timedelta(hours=2)))
    await db_session.commit()
    await client.patch(f"{base}/{t_med['id']}/status", json={"status": "cancelled"}, headers=admin_h)

    overdue = (await client.get(f"{base}/overdue", headers=dev_h)).json()
    assert overdue["total"] == 1 and overdue["items"][0]["id"] == t_low["id"]

    stats = (await client.get(f"{base}/stats", headers=dev_h)).json()
    assert (stats["total"], stats["active"], stats["overdue"]) == (4, 3, 1)
    assert stats["by_status"]["backlog"] == 3 and stats["by_status"]["cancelled"] == 1
    assert stats["by_priority"] == {"high": 2, "medium": 1, "low": 1}
