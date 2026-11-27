import pytest
from httpx import AsyncClient

from tests.conftest import invite_and_join, register_and_login


@pytest.mark.asyncio
async def test_rbac_hierarchy_and_task_read_prerequisite(client: AsyncClient) -> None:
    admin, admin_h, _ = await register_and_login(client, "adm@example.com", "adm_role")
    lead, lead_h, _ = await register_and_login(client, "lead@example.com", "lead_role")
    dev, dev_h, _ = await register_and_login(client, "dev@example.com", "dev_role")

    team = (await client.post("/api/v1/teams", json={"name": "RBAC Team"}, headers=admin_h)).json()
    tid = team["id"]
    await invite_and_join(client, admin_h, tid, team["join_code"], lead["email"], lead_h)
    await invite_and_join(client, admin_h, tid, team["join_code"], dev["email"], dev_h)

    assert (await client.post(f"/api/v1/teams/{tid}/roles", json={"name": "Bad", "level": 30, "permissions": ["task:create"]}, headers=admin_h)).status_code == 400

    lead_role = (await client.post(
        f"/api/v1/teams/{tid}/roles",
        json={"name": "Lead", "level": 60, "permissions": ["task:read", "task:create", "role:create", "role:edit", "role:assign"]},
        headers=admin_h,
    )).json()
    assert (await client.patch(f"/api/v1/teams/{tid}/members/{lead['id']}/role", json={"role_id": lead_role["id"]}, headers=admin_h)).status_code == 200

    assert (await client.post(f"/api/v1/teams/{tid}/roles", json={"name": "High", "level": 60, "permissions": ["task:read"]}, headers=lead_h)).status_code == 403
    assert (await client.post(f"/api/v1/teams/{tid}/roles", json={"name": "Esc", "level": 30, "permissions": ["task:read", "task:delete"]}, headers=lead_h)).status_code == 403

    junior = (await client.post(f"/api/v1/teams/{tid}/roles", json={"name": "Junior", "level": 20, "permissions": ["task:read", "task:create"]}, headers=lead_h)).json()
    assert (await client.patch(f"/api/v1/teams/{tid}/members/{dev['id']}/role", json={"role_id": junior["id"]}, headers=lead_h)).status_code == 200

    roles = {r["name"]: r for r in (await client.get(f"/api/v1/teams/{tid}/roles", headers=admin_h)).json()}
    assert (await client.patch(f"/api/v1/teams/{tid}/members/{dev['id']}/role", json={"role_id": roles["manager"]["id"]}, headers=lead_h)).status_code == 403
    assert (await client.patch(f"/api/v1/teams/{tid}/members/{admin['id']}/role", json={"role_id": junior["id"]}, headers=lead_h)).status_code == 403

    no_read = (await client.post(f"/api/v1/teams/{tid}/roles", json={"name": "NoRead", "level": 5, "permissions": ["team:invite"]}, headers=admin_h)).json()
    await client.patch(f"/api/v1/teams/{tid}/members/{dev['id']}/role", json={"role_id": no_read["id"]}, headers=admin_h)
    assert (await client.get(f"/api/v1/teams/{tid}/tasks", headers=dev_h)).status_code == 403
    assert (await client.get(f"/api/v1/teams/{tid}/tasks/stats", headers=dev_h)).status_code == 403
    assert (await client.get(f"/api/v1/teams/{tid}/tasks/overdue", headers=dev_h)).status_code == 403
    assert (await client.post(f"/api/v1/teams/{tid}/tasks", json={"title": "Blocked"}, headers=dev_h)).status_code == 403


@pytest.mark.asyncio
async def test_user_and_manager_task_permissions(client: AsyncClient) -> None:
    _, admin_h, _ = await register_and_login(client, "adm2@example.com", "adm2")
    mgr, mgr_h, _ = await register_and_login(client, "mgr2@example.com", "mgr2")
    u1, u1_h, _ = await register_and_login(client, "u1@example.com", "u1_user")
    u2, u2_h, _ = await register_and_login(client, "u2@example.com", "u2_user")

    team = (await client.post("/api/v1/teams", json={"name": "Dev Team"}, headers=admin_h)).json()
    tid = team["id"]
    for u, h in ((mgr, mgr_h), (u1, u1_h), (u2, u2_h)):
        await invite_and_join(client, admin_h, tid, team["join_code"], u["email"], h)

    mgr_role = next(r for r in (await client.get(f"/api/v1/teams/{tid}/roles", headers=admin_h)).json() if r["name"] == "manager")
    await client.patch(f"/api/v1/teams/{tid}/members/{mgr['id']}/role", json={"role_id": mgr_role["id"]}, headers=admin_h)

    assert (await client.post(f"/api/v1/teams/{tid}/tasks", json={"title": "Bad", "assignee_id": u2["id"]}, headers=u1_h)).status_code == 403
    task = (await client.post(f"/api/v1/teams/{tid}/tasks", json={"title": "Own"}, headers=u1_h)).json()
    assert task["assignee_id"] == u1["id"]

    t_url = f"/api/v1/teams/{tid}/tasks/{task['id']}"
    assert (await client.patch(t_url, json={"title": "Hijack"}, headers=u2_h)).status_code == 403
    assert (await client.patch(f"{t_url}/status", json={"status": "in_progress"}, headers=u2_h)).status_code == 403

    assert (await client.patch(t_url, json={"assignee_id": u2["id"]}, headers=mgr_h)).json()["assignee_id"] == u2["id"]
    assert (await client.patch(f"{t_url}/status", json={"status": "in_progress"}, headers=u2_h)).json()["status"] == "in_progress"
    assert (await client.delete(t_url, headers=u1_h)).status_code == 403
    assert (await client.delete(t_url, headers=mgr_h)).status_code == 409
