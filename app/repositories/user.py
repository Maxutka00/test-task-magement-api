from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def create(self, email: str, username: str, password_hash: str) -> User:
        user = User(email=email, username=username, password_hash=password_hash)
        self.session.add(user)
        await self.session.flush()
        return user

    async def list_users(
        self,
        search: str | None,
        page: int,
        size: int,
    ) -> tuple[list[User], int]:
        stmt = select(User)
        count_stmt = select(func.count(User.id))
        if search and search.strip():
            pattern = f"%{_escape_like(search.strip())}%"
            condition = or_(
                User.username.ilike(pattern, escape="\\"),
                User.email.ilike(pattern, escape="\\"),
            )
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one()

        stmt = stmt.order_by(User.created_at.desc()).offset((page - 1) * size).limit(size)
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all()), total
