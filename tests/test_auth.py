import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login


@pytest.mark.asyncio
async def test_auth_lifecycle_session_families_and_no_password_leak(client: AsyncClient) -> None:
    short_pw = await client.post("/api/v1/auth/register", json={"email": "leak@example.com", "username": "leak_u", "password": "123"})
    assert short_pw.status_code == 422 and "123" not in short_pw.text
    missing_email = await client.post("/api/v1/auth/login", json={"password": "SuperSecretPassword!"})
    assert missing_email.status_code == 422 and "SuperSecretPassword!" not in missing_email.text

    user, headers, session1 = await register_and_login(client, "alice@example.com", "alice")
    await register_and_login(client, "charlie@example.com", "charlie_qa")

    assert (await client.post("/api/v1/auth/register", json={"email": "alice@example.com", "username": "alice2", "password": "StrongPass123!"})).status_code == 409
    assert (await client.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": "WrongPassword!"})).status_code == 401
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers=headers)).json()["id"] == user["id"]

    session2 = (await client.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": "StrongPass123!"})).json()

    rotated = (await client.post("/api/v1/auth/refresh", json={"refresh_token": session1["refresh_token"]})).json()
    assert rotated["refresh_token"] != session1["refresh_token"]
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": session1["refresh_token"]})).status_code == 401
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]})).status_code == 401

    session2_refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": session2["refresh_token"]})
    assert session2_refreshed.status_code == 200
    s2 = session2_refreshed.json()
    s2_headers = {"Authorization": f"Bearer {s2['access_token']}"}
    assert (await client.post("/api/v1/auth/logout", json={"refresh_token": s2["refresh_token"]}, headers=s2_headers)).status_code == 204
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": s2["refresh_token"]})).status_code == 401

    users = (await client.get("/api/v1/users?search=charlie", headers=s2_headers)).json()
    assert users["total"] == 1 and users["items"][0]["username"] == "charlie_qa"
