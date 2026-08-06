from __future__ import annotations

from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.models.product import Product


class ProductsRepository:
    """Todas as queries filtram por tenant_id (Âncora 2), sem exceção."""

    @staticmethod
    async def list(
        session: AsyncSession,
        tenant_id: UUID,
        search: Optional[str] = None,
        active_only: bool = False,
        limit: int = 500,
        offset: int = 0,
    ) -> tuple[Sequence[Product], int]:
        base = select(Product).where(Product.tenant_id == tenant_id)

        if active_only:
            base = base.where(Product.is_active.is_(True))

        if search:
            base = base.where(Product.name.ilike(f"%{search.strip()}%"))

        total = (
            await session.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()

        rows = (
            await session.execute(base.order_by(Product.name).limit(limit).offset(offset))
        ).scalars().all()

        return rows, total

    @staticmethod
    async def get(
        session: AsyncSession, tenant_id: UUID, product_id: UUID
    ) -> Optional[Product]:
        query = select(Product).where(
            Product.tenant_id == tenant_id, Product.id == product_id
        )
        return (await session.execute(query)).scalars().first()

    @staticmethod
    async def save(session: AsyncSession, product: Product) -> Product:
        session.add(product)
        await session.commit()
        await session.refresh(product)
        return product
