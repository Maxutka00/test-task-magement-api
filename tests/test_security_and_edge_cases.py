from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from tests.conftest import invite_and_join, register_and_login


@pytest.mark.asyncio
async def test_idor_jwt_confusion_and_extreme_inputs(client: AsyncClient) -> None:
    u1, h1, t1 = await register_and_login(client, "sec1@example.com", "sec1")
    u2, h2, _ = await register_and_login(client, "sec2@example.com", "sec2")

    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {t1['refresh_token']}"})).status_code == 401
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": t1["access_token"]})).status_code == 401

    team1 = (await client.post("/api/v1/teams", json={"name": "A"}, headers=h1)).json()
    team2 = (await client.post("/api/v1/teams", json={"name": "B"}, headers=h2)).json()
    base1 = f"/api/v1/teams/{team1['id']}/tasks"
    task1 = (await client.post(base1, json={"title": "Secret", "assignee_id": u1["id"]}, headers=h1)).json()

    assert (await client.get(f"/api/v1/teams/{team1['id']}", headers=h2)).status_code == 403
    assert (await client.get(f"{base1}/{task1['id']}", headers=h2)).status_code == 403
    assert (await client.post(base1, json={"title": "Bad", "assignee_id": u2["id"]}, headers=h1)).status_code == 400

    assert (await client.get(f"{base1}?page=1000000000000000000", headers=h1)).status_code == 422
    assert (await client.post(base1, json={"title": "bad\x00title"}, headers=h1)).status_code == 422
    assert (await client.get(f"{base1}?search=bad%00q", headers=h1)).status_code == 400
    assert (await client.post(base1, json={"title": "Max", "deadline": "9999-12-31T23:59:59-05:00"}, headers=h1)).status_code == 422
    assert (await client.get(f"{base1}?deadline_from=9999-12-31T23:59:59-05:00", headers=h1)).status_code == 400
    assert (await client.get(f"{base1}?sort_order=asc", headers=h1)).status_code == 400
    assert (await client.get(f"{base1}?deadline_from=2030-02-01T00:00:00Z&deadline_to=2030-01-01T00:00:00Z", headers=h1)).status_code == 400

    roles_team2 = (await client.get(f"/api/v1/teams/{team2['id']}/roles", headers=h2)).json()
    await invite_and_join(client, h1, team1["id"], team1["join_code"], u2["email"], h2)
    assert (await client.patch(f"/api/v1/teams/{team1['id']}/members/{u2['id']}/role", json={"role_id": roles_team2[0]["id"]}, headers=h1)).status_code == 404


@pytest.mark.asyncio
async def test_roles_members_patch_guards_and_nested_delete(client: AsyncClient) -> None:
    admin, admin_h, _ = await register_and_login(client, "rk_adm@example.com", "rk_adm")
    user, user_h, _ = await register_and_login(client, "rk_usr@example.com", "rk_usr")
    user2, user2_h, _ = await register_and_login(client, "rk_usr2@example.com", "rk_usr2")

    team = (await client.post("/api/v1/teams", json={"name": "Ops"}, headers=admin_h)).json()
    tid = team["id"]
    await invite_and_join(client, admin_h, tid, team["join_code"], user["email"], user_h)
    await invite_and_join(client, admin_h, tid, team["join_code"], user2["email"], user2_h)

    role = (await client.post(f"/api/v1/teams/{tid}/roles", json={"name": "QA", "level": 30, "permissions": ["task:read", "comment:create"]}, headers=admin_h)).json()
    assert (await client.patch(f"/api/v1/teams/{tid}/roles/{role['id']}", json={"name": None}, headers=admin_h)).status_code == 422
    assert (await client.patch(f"/api/v1/teams/{tid}/roles/{role['id']}", json={"permissions": ["comment:create"]}, headers=admin_h)).status_code == 400

    await client.patch(f"/api/v1/teams/{tid}/members/{user['id']}/role", json={"role_id": role["id"]}, headers=admin_h)
    assert (await client.delete(f"/api/v1/teams/{tid}/roles/{role['id']}", headers=admin_h)).status_code == 409

    t1 = (await client.post(f"/api/v1/teams/{tid}/tasks", json={"title": "100% wildcard_test", "assignee_id": user2["id"]}, headers=user2_h)).json()
    t1_url = f"/api/v1/teams/{tid}/tasks/{t1['id']}"
    await client.patch(t1_url, json={"assignee_id": user["id"]}, headers=admin_h)

    assert (await client.patch(t1_url, json={"assignee_id": user2["id"]}, headers=user2_h)).status_code == 403
    assert (await client.patch(t1_url, json={"assignee_id": None}, headers=user2_h)).status_code == 403
    assert (await client.patch(t1_url, json={"title": None}, headers=admin_h)).status_code == 422
    assert (await client.patch(t1_url, json={"deadline": (datetime.now(UTC) - timedelta(minutes=10)).isoformat()}, headers=admin_h)).status_code == 400

    assert (await client.get(f"/api/v1/teams/{tid}/tasks?search=100%25", headers=admin_h)).json()["total"] == 1
    assert (await client.get(f"/api/v1/teams/{tid}/tasks?search=999%25", headers=admin_h)).json()["total"] == 0

    assert (await client.delete(f"/api/v1/teams/{tid}/members/{admin['id']}", headers=admin_h)).status_code == 400
    assert (await client.delete(f"/api/v1/teams/{tid}/members/{user['id']}", headers=admin_h)).status_code == 204
    assert (await client.get(t1_url, headers=admin_h)).json()["assignee_id"] is None
    assert (await client.delete(f"/api/v1/teams/{tid}/roles/{role['id']}", headers=admin_h)).status_code == 204
    assert (await client.delete(f"/api/v1/teams/{tid}/members/{user2['id']}", headers=user2_h)).status_code == 204

    parent_id = None
    for depth in range(11):
        resp = await client.post(f"{t1_url}/comments", json={"content": f"L{depth}", "parent_id": parent_id}, headers=admin_h)
        assert resp.status_code == 201
        parent_id = resp.json()["id"]
    assert (await client.post(f"{t1_url}/comments", json={"content": "Deep", "parent_id": parent_id}, headers=admin_h)).status_code == 400
    assert (await client.delete(t1_url, headers=admin_h)).status_code == 204
