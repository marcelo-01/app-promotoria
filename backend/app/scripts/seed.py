import asyncio
from uuid import uuid4

from sqlalchemy import select

from app.auth.service import AuthService
from app.infrastructure.persistence.models.tenant import Tenant, TenantStatus
from app.infrastructure.persistence.models.user import User, UserRole
from app.infrastructure.persistence.session import AsyncSessionLocal

TENANT_NAME = "fv-laticinios"


async def seed():
    async with AsyncSessionLocal() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.name == TENANT_NAME))
        ).scalars().first()

        if not tenant:
            tenant = Tenant(
                id=uuid4(), name=TENANT_NAME, slug=TENANT_NAME, status=TenantStatus.ACTIVE
            )
            session.add(tenant)
            await session.flush()
            print(f"Tenant criado: {tenant.id}")

        seeds = [
            ("admin", "admin", "Administrador", UserRole.ADMIN),
            ("promotor", "promotor", "Promotor de Teste", UserRole.PROMOTER),
            ("vendedor", "vendedor", "Vendedor de Teste", UserRole.SELLER),
        ]

        for email, password, full_name, role in seeds:
            existing = (
                await session.execute(
                    select(User).where(User.tenant_id == tenant.id, User.email == email)
                )
            ).scalars().first()
            if existing:
                continue
            session.add(
                User(
                    id=uuid4(),
                    tenant_id=tenant.id,
                    email=email,
                    password_hash=AuthService.hash_password(password),
                    full_name=full_name,
                    role=role,
                    is_active=True,
                )
            )
            print(f"Usuário criado: {email} / {password}")

        await session.commit()
        print("Seed concluído.")


if __name__ == "__main__":
    asyncio.run(seed())
