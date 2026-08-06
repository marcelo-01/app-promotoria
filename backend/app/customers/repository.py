from __future__ import annotations

from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.models.customer import Customer


class CustomersRepository:
    """Todas as queries filtram por tenant_id (Âncora 2), sem exceção."""

    @staticmethod
    async def list(
        session: AsyncSession,
        tenant_id: UUID,
        search: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> tuple[Sequence[Customer], int]:
        base = select(Customer).where(Customer.tenant_id == tenant_id)

        if search:
            base = base.where(Customer.name.ilike(f"%{search.strip()}%"))

        total = (
            await session.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()

        rows = (
            await session.execute(base.order_by(Customer.name).limit(limit).offset(offset))
        ).scalars().all()

        return rows, total

    @staticmethod
    async def get(
        session: AsyncSession, tenant_id: UUID, customer_id: UUID
    ) -> Optional[Customer]:
        query = select(Customer).where(
            Customer.tenant_id == tenant_id, Customer.id == customer_id
        )
        return (await session.execute(query)).scalars().first()

    @staticmethod
    async def save(session: AsyncSession, customer: Customer) -> Customer:
        session.add(customer)
        await session.commit()
        await session.refresh(customer)
        return customer
