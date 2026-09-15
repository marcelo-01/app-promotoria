from __future__ import annotations

from typing import Optional, Sequence
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import AuthService
from app.infrastructure.persistence.models.user import User, UserRole
from app.users.schemas import UserCreate

# Papéis que este app sabe criar. `supervisor` existe no enum apenas por
# compatibilidade com o ERP (Âncora 5) e não é usado aqui.
_ALLOWED_ROLES = {UserRole.PROMOTER.value, UserRole.SELLER.value, UserRole.ADMIN.value}


class UsersService:

    @staticmethod
    async def list(
        session: AsyncSession,
        tenant_id: UUID,
        role: Optional[str] = None,
        search: Optional[str] = None,
        active_only: bool = False,
    ) -> Sequence[User]:
        query = select(User).where(User.tenant_id == tenant_id)

        if role:
            query = query.where(User.role == UserRole(role))
        if active_only:
            query = query.where(User.is_active.is_(True))
        if search:
            like = f"%{search.strip()}%"
            query = query.where(or_(User.full_name.ilike(like), User.email.ilike(like)))

        query = query.order_by(User.full_name, User.email)
        return (await session.execute(query)).scalars().all()

    @staticmethod
    async def get(session: AsyncSession, tenant_id: UUID, user_id: UUID) -> User:
        query = select(User).where(User.tenant_id == tenant_id, User.id == user_id)
        user = (await session.execute(query)).scalars().first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        return user

    @staticmethod
    async def create(
        session: AsyncSession, tenant_id: UUID, payload: UserCreate
    ) -> User:
        if payload.role not in _ALLOWED_ROLES:
            raise HTTPException(
                status_code=422,
                detail=f"Papel inválido. Use um destes: {', '.join(sorted(_ALLOWED_ROLES))}",
            )

        existing = (
            await session.execute(select(User).where(User.email == payload.email))
        ).scalars().first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Já existe um usuário com o e-mail {payload.email}",
            )

        user = User(
            id=uuid4(),
            tenant_id=tenant_id,
            email=payload.email,
            password_hash=AuthService.hash_password(payload.password),
            full_name=payload.full_name,
            role=UserRole(payload.role),
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    @staticmethod
    async def set_password(
        session: AsyncSession, tenant_id: UUID, user_id: UUID, new_password: str
    ) -> None:
        """Redefinição pelo administrador — no MVP não há 'esqueci minha senha'."""
        user = await UsersService.get(session, tenant_id, user_id)
        user.password_hash = AuthService.hash_password(new_password)
        session.add(user)
        await session.commit()
