from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, verify_token,
)
from app.core.config import settings
from app.infrastructure.persistence.models.user import User

logger = logging.getLogger(__name__)


class AuthService:
    @staticmethod
    async def authenticate_user(session: AsyncSession, email: str, password: str) -> User | None:
        # Atalho de desenvolvimento — mesmo comportamento do ERP
        if settings.api_env == "development" and email.lower() == "admin" and password == "admin":
            result = await session.execute(select(User).where(User.email == "admin"))
            user = result.scalars().first()
            if user and user.is_active:
                return user

        result = await session.execute(select(User).where(User.email == email.lower().strip()))
        user = result.scalars().first()

        if not user or not verify_password(password, user.password_hash):
            return None
        if not user.is_active:
            return None
        return user

    @staticmethod
    def _token_data(user: User) -> dict:
        """FORMATO SAGRADO: idêntico ao do ERP (app/auth/service.py:44).
        Não altere sem alterar o ERP junto."""
        return {
            "sub": str(user.id),
            "tenant_id": str(user.tenant_id),
            "role": user.role.value,
            "profile": None,
            "email": user.email,
        }

    @staticmethod
    def create_tokens_for_user(user: User) -> tuple[str, str]:
        data = AuthService._token_data(user)
        return create_access_token(data), create_refresh_token(data)

    @staticmethod
    async def refresh_access_token(session: AsyncSession, refresh_token: str) -> str | None:
        payload = verify_token(refresh_token, token_type="refresh")
        if payload is None:
            return None
        user_id = payload.get("sub")
        if not user_id:
            return None
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if not user or not user.is_active:
            return None
        return create_access_token(AuthService._token_data(user))

    @staticmethod
    def hash_password(password: str) -> str:
        return hash_password(password)
