from __future__ import annotations

from typing import Optional
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.models.product import Product
from app.products.repository import ProductsRepository as Repo
from app.products.schemas import ProductCreate, ProductUpdate


class ProductsService:

    @staticmethod
    async def list(
        session: AsyncSession,
        tenant_id: UUID,
        search: Optional[str] = None,
        active_only: bool = False,
        limit: int = 500,
        offset: int = 0,
    ):
        return await Repo.list(session, tenant_id, search, active_only, limit, offset)

    @staticmethod
    async def get(session: AsyncSession, tenant_id: UUID, product_id: UUID) -> Product:
        product = await Repo.get(session, tenant_id, product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Produto não encontrado")
        return product

    @staticmethod
    async def create(
        session: AsyncSession, tenant_id: UUID, payload: ProductCreate
    ) -> Product:
        existing = await Repo.get_by_sku(session, tenant_id, payload.sku)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Já existe um produto com o SKU {payload.sku}",
            )
        product = Product(id=uuid4(), tenant_id=tenant_id, **payload.model_dump())
        return await Repo.save(session, product)

    @staticmethod
    async def update(
        session: AsyncSession, tenant_id: UUID, product_id: UUID, payload: ProductUpdate
    ) -> Product:
        product = await ProductsService.get(session, tenant_id, product_id)

        data = payload.model_dump(exclude_unset=True)

        sku = data.get("sku")
        if sku and sku != product.sku:
            existing = await Repo.get_by_sku(session, tenant_id, sku)
            if existing and existing.id != product.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Já existe um produto com o SKU {sku}",
                )

        for key, value in data.items():
            setattr(product, key, value)

        return await Repo.save(session, product)
