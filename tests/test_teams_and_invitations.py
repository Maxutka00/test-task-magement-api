from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invitation import TeamInvitation
from tests.conftest import register_and_login


@pytest.mark.asyncio
async def test_teams_invitations_and_join_by_code(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, admin_h, _ = await register_and_login(client, "admin@example.com", "admin_u")
    bob, bob_h, _ = await register_and_login(client, "bob@example.com", "bob_u")
    eve, eve_h, _ = await register_and_login(client, "eve@example.com", "eve_u")

    team = (await client.post("/api/v1/teams", json={"name": "Core Backend"}, headers=admin_h)).json()
    tid, code = team["id"], team["join_code"]
    assert len(code) == 6 and code.isdigit() and team["owner_id"] == admin["id"]

    no_inv = await client.post("/api/v1/teams/join", json={"code": code}, headers=bob_h)
    bad_code = await client.post("/api/v1/teams/join", json={"code": "000000" if code != "000000" else "999999"}, headers=bob_h)
    assert no_inv.status_code == 403 and bad_code.status_code == 403 and no_inv.json() == bad_code.json()

    inv = (await client.post(f"/api/v1/teams/{tid}/invitations", json={"email": bob["email"]}, headers=admin_h)).json()
    assert (await client.get("/api/v1/invitations/me", headers=bob_h)).json()[0]["id"] == inv["id"]

    joined = await client.post("/api/v1/teams/join", json={"code": code}, headers=bob_h)
    assert joined.status_code == 201 and joined.json()["role"]["name"] == "user"
    assert (await client.post(f"/api/v1/teams/{tid}/invitations", json={"email": eve["email"]}, headers=bob_h)).status_code == 403

    eve_inv = (await client.post(f"/api/v1/teams/{tid}/invitations", json={"user_id": eve["id"]}, headers=admin_h)).json()
    assert (await client.delete(f"/api/v1/teams/{tid}/invitations/{eve_inv['id']}", headers=admin_h)).status_code == 204
    assert (await client.post("/api/v1/teams/join", json={"code": code}, headers=eve_h)).status_code == 403

    eve_inv2 = (await client.post(f"/api/v1/teams/{tid}/invitations", json={"user_id": eve["id"]}, headers=admin_h)).json()
    await db_session.execute(
        update(TeamInvitation)
        .where(TeamInvitation.id == UUID(eve_inv2["id"]))
        .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db_session.commit()
    assert (await client.delete(f"/api/v1/teams/{tid}/invitations/{eve_inv2['id']}", headers=admin_h)).status_code == 409
    team_invs = {i["id"]: i["status"] for i in (await client.get(f"/api/v1/teams/{tid}/invitations", headers=admin_h)).json()}
    assert team_invs[eve_inv2["id"]] == "expired"
    assert (await client.post("/api/v1/teams/join", json={"code": code}, headers=eve_h)).status_code == 403

    assert (await client.patch(f"/api/v1/teams/{tid}", json={"name": "Nope"}, headers=bob_h)).status_code == 403
    assert (await client.delete(f"/api/v1/teams/{tid}", headers=bob_h)).status_code == 403
    assert (await client.patch(f"/api/v1/teams/{tid}", json={"name": "Platform"}, headers=admin_h)).json()["name"] == "Platform"
    assert (await client.delete(f"/api/v1/teams/{tid}", headers=admin_h)).status_code == 204
