import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.database import get_db
from app.main import app
from app.models import Base

settings = get_settings()
if not settings.test_database_url:
    raise RuntimeError("TEST_DATABASE_URL must be set to run tests")

test_database_url = settings.test_database_url
parsed_test_url = make_url(test_database_url)
parsed_main_url = make_url(settings.database_url)
if (
    (parsed_test_url.host, parsed_test_url.port, parsed_test_url.database)
    == (parsed_main_url.host, parsed_main_url.port, parsed_main_url.database)
    or not parsed_test_url.database
    or "test" not in parsed_test_url.database.lower()
):
    raise RuntimeError("Refusing to run destructive test setup against a non-test database")

test_engine = create_async_engine(test_database_url, poolclass=NullPool)
test_session_factory = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


def _alembic_config() -> Config:
    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", test_database_url)
    return cfg


@pytest_asyncio.fixture(scope="session", autouse=True)
async def prepare_database() -> AsyncGenerator[None, None]:
    async with test_engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))

    def run_upgrade() -> None:
        command.upgrade(_alembic_config(), "head")

    await asyncio.to_thread(run_upgrade)
    yield
    await test_engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_tables() -> AsyncGenerator[None, None]:
    yield
    table_names = ", ".join(table.name for table in reversed(Base.metadata.sorted_tables))
    async with test_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def register_and_login(
    client: AsyncClient,
    email: str,
    username: str,
    password: str = "StrongPass123!",
) -> tuple[dict, dict[str, str], dict]:
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": username, "password": password},
    )
    assert reg_resp.status_code == 201, reg_resp.text
    user = reg_resp.json()

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 200, login_resp.text
    tokens = login_resp.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    return user, headers, tokens


async def invite_and_join(
    client: AsyncClient,
    inviter_headers: dict[str, str],
    team_id: str,
    join_code: str,
    invitee_email: str,
    invitee_headers: dict[str, str],
) -> dict:
    inv_resp = await client.post(
        f"/api/v1/teams/{team_id}/invitations",
        json={"email": invitee_email},
        headers=inviter_headers,
    )
    assert inv_resp.status_code == 201, inv_resp.text

    join_resp = await client.post(
        "/api/v1/teams/join",
        json={"code": join_code},
        headers=invitee_headers,
    )
    assert join_resp.status_code == 201, join_resp.text
    return join_resp.json()
