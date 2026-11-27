import pytest
from httpx import AsyncClient

from tests.conftest import invite_and_join, register_and_login


@pytest.mark.asyncio
async def test_comments_and_nested_replies_on_done_task(client: AsyncClient) -> None:
    _, admin_h, _ = await register_and_login(client, "c_admin@example.com", "c_admin")
    dev, dev_h, _ = await register_and_login(client, "c_dev@example.com", "c_dev")

    team = (await client.post("/api/v1/teams", json={"name": "Comments"}, headers=admin_h)).json()
    tid = team["id"]
    await invite_and_join(client, admin_h, tid, team["join_code"], dev["email"], dev_h)

    t1 = (await client.post(f"/api/v1/teams/{tid}/tasks", json={"title": "T1", "assignee_id": dev["id"]}, headers=admin_h)).json()
    t2 = (await client.post(f"/api/v1/teams/{tid}/tasks", json={"title": "T2", "assignee_id": dev["id"]}, headers=admin_h)).json()
    for st in ("in_progress", "review", "done"):
        await client.patch(f"/api/v1/teams/{tid}/tasks/{t1['id']}/status", json={"status": st}, headers=admin_h)

    c_url = f"/api/v1/teams/{tid}/tasks/{t1['id']}/comments"
    root = (await client.post(c_url, json={"content": "Done!"}, headers=dev_h)).json()
    r1 = (await client.post(c_url, json={"content": "Thanks", "parent_id": root["id"]}, headers=admin_h)).json()
    r2 = (await client.post(c_url, json={"content": "Reply", "parent_id": r1["id"]}, headers=dev_h)).json()

    assert (await client.post(f"/api/v1/teams/{tid}/tasks/{t2['id']}/comments", json={"content": "Cross", "parent_id": root["id"]}, headers=dev_h)).status_code == 404

    listed = (await client.get(c_url, headers=dev_h)).json()
    assert listed["total"] == 1
    assert listed["items"][0]["replies"][0]["id"] == r1["id"]
    assert listed["items"][0]["replies"][0]["replies"][0]["id"] == r2["id"]
