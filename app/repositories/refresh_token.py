from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import RefreshToken


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        user_id: UUID,
        family_id: UUID,
        token_jti: str,
        expires_at: datetime,
    ) -> RefreshToken:
        record = RefreshToken(
            user_id=user_id,
            family_id=family_id,
            token_jti=token_jti,
            expires_at=expires_at,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_by_jti(
        self,
        token_jti: str,
        for_update: bool = False,
    ) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.token_jti == token_jti)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke(self, record: RefreshToken) -> None:
        record.revoked = True
        await self.session.flush()

    async def revoke_family(self, family_id: UUID) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked.is_(False))
            .values(revoked=True)
        )
        await self.session.flush()
