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
# Os papéis de campo — os únicos que uma pessoa pode acumular. Administrador
# já entra em tudo, então não há o que acumular.
_FIELD_ROLES = {UserRole.PROMOTER.value, UserRole.SELLER.value}

_ROTULO = {UserRole.PROMOTER.value: "promotor", UserRole.SELLER.value: "vendedor"}


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
            # Quem acumula papéis aparece nos dois filtros
            query = query.where(
                or_(User.role == UserRole(role), User.secondary_role == UserRole(role))
            )
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

        if payload.secondary_role:
            _validate_field_roles({payload.role, payload.secondary_role})
            if payload.secondary_role == payload.role:
                raise HTTPException(
                    status_code=422, detail="O segundo papel tem de ser diferente do primeiro"
                )

        existing = (
            await session.execute(select(User).where(User.email == payload.email))
        ).scalars().first()
        if existing:
            outro = _ROTULO.get(payload.role, payload.role)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Já existe um usuário com o e-mail {payload.email}. "
                    f"Para essa pessoa também ser {outro}, ligue \"{outro}\" no cadastro dela."
                ),
            )

        user = User(
            id=uuid4(),
            tenant_id=tenant_id,
            email=payload.email,
            password_hash=AuthService.hash_password(payload.password),
            full_name=payload.full_name,
            role=UserRole(payload.role),
            secondary_role=(
                UserRole(payload.secondary_role) if payload.secondary_role else None
            ),
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    @staticmethod
    async def set_roles(
        session: AsyncSession, tenant_id: UUID, user_id: UUID, roles: Sequence[str]
    ) -> None:
        """Define o conjunto de papéis de campo da pessoa: promotor, vendedor ou
        os dois. O papel principal (`role`) só muda se sair do conjunto — aí o
        que sobrou assume, e a pessoa passa a cair no outro app ao entrar.
        """
        wanted = set(roles)
        _validate_field_roles(wanted)

        user = await UsersService.get(session, tenant_id, user_id)
        if user.role.value not in _FIELD_ROLES:
            raise HTTPException(
                status_code=422, detail="Administrador já tem acesso a tudo"
            )

        if user.role.value not in wanted:
            user.role = UserRole(wanted.pop())
        wanted.discard(user.role.value)
        user.secondary_role = UserRole(wanted.pop()) if wanted else None

        session.add(user)
        await session.commit()

    @staticmethod
    async def set_password(
        session: AsyncSession, tenant_id: UUID, user_id: UUID, new_password: str
    ) -> None:
        """Redefinição pelo administrador — no MVP não há 'esqueci minha senha'."""
        user = await UsersService.get(session, tenant_id, user_id)
        user.password_hash = AuthService.hash_password(new_password)
        session.add(user)
        await session.commit()


def _validate_field_roles(roles: set[str]) -> None:
    invalid = roles - _FIELD_ROLES
    if invalid or not roles:
        raise HTTPException(
            status_code=422,
            detail="Só promotor e vendedor podem ser acumulados. "
                   f"Use um destes: {', '.join(sorted(_FIELD_ROLES))}",
        )
