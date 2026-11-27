from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_password_async,
    verify_password_async,
)
from app.models.user import User
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, TokenPairResponse

DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-protection")


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_repo = UserRepository(session)
        self.token_repo = RefreshTokenRepository(session)

    async def register(self, data: RegisterRequest) -> User:
        if await self.user_repo.get_by_email(data.email):
            raise ConflictError("User with this email already exists")
        if await self.user_repo.get_by_username(data.username):
            raise ConflictError("User with this username already exists")

        password_hash = await hash_password_async(data.password)
        try:
            user = await self.user_repo.create(
                email=data.email,
                username=data.username,
                password_hash=password_hash,
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("User with this email or username already exists") from exc
        return user

    async def login(self, data: LoginRequest) -> TokenPairResponse:
        user = await self.user_repo.get_by_email(data.email)
        if user is None:
            await verify_password_async(data.password, DUMMY_PASSWORD_HASH)
            raise UnauthorizedError("Invalid email or password")

        if not await verify_password_async(data.password, user.password_hash):
            raise UnauthorizedError("Invalid email or password")

        return await self._issue_tokens(user.id, uuid4())

    async def refresh(self, refresh_token: str) -> TokenPairResponse:
        payload = decode_token(refresh_token, expected_type="refresh")
        token_jti = payload["jti"]
        try:
            user_id = UUID(payload["sub"])
        except ValueError as exc:
            raise UnauthorizedError("Invalid token subject") from exc

        record = await self.token_repo.get_by_jti(token_jti, for_update=True)
        if record is None or record.user_id != user_id:
            raise UnauthorizedError("Invalid refresh token")

        now = datetime.now(UTC)
        if record.revoked:
            await self.token_repo.revoke_family(record.family_id)
            await self.session.commit()
            raise UnauthorizedError("Refresh token has been revoked")

        if record.expires_at <= now:
            await self.token_repo.revoke(record)
            await self.session.commit()
            raise UnauthorizedError("Refresh token has expired")

        await self.token_repo.revoke(record)
        return await self._issue_tokens(user_id, record.family_id)

    async def logout(self, refresh_token: str, current_user_id: UUID) -> None:
        payload = decode_token(refresh_token, expected_type="refresh")
        token_jti = payload["jti"]
        record = await self.token_repo.get_by_jti(token_jti, for_update=True)
        if record is not None and record.user_id == current_user_id and not record.revoked:
            await self.token_repo.revoke(record)
            await self.session.commit()

    async def _issue_tokens(self, user_id: UUID, family_id: UUID) -> TokenPairResponse:
        access_token = create_access_token(user_id)
        refresh_token, jti, expires_at = create_refresh_token(user_id)
        await self.token_repo.create(
            user_id=user_id,
            family_id=family_id,
            token_jti=jti,
            expires_at=expires_at,
        )
        await self.session.commit()
        return TokenPairResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        )
