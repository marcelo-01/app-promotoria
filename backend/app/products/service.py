from __future__ import annotations

from typing import Optional
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.models.product import Product
from app.products import images
from app.products.repository import ProductsRepository as Repo
from app.products.schemas import ProductCreate, ProductUpdate


# Campos que podem voltar a ficar em branco: mandar `null` neles apaga o valor,
# em vez de ser lido como "não mexi neste campo".
_APAGAVEIS = {"shelf_life_days", "arrival_shelf_life_days"}


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
        product = Product(
            id=uuid4(),
            tenant_id=tenant_id,
            name=payload.name,
            package_size=payload.package_size,
            shelf_life_days=payload.shelf_life_days,
            arrival_shelf_life_days=payload.arrival_shelf_life_days,
        )
        return await Repo.save(session, product)

    @staticmethod
    async def update(
        session: AsyncSession, tenant_id: UUID, product_id: UUID, payload: ProductUpdate
    ) -> Product:
        product = await ProductsService.get(session, tenant_id, product_id)

        for key, value in payload.model_dump(exclude_unset=True).items():
            if value is not None or key in _APAGAVEIS:
                setattr(product, key, value)

        return await Repo.save(session, product)

    # ── Foto ──────────────────────────────────────────────────────────────

    @staticmethod
    async def set_image(
        session: AsyncSession,
        tenant_id: UUID,
        product_id: UUID,
        raw: bytes,
        content_type: Optional[str],
    ) -> Product:
        product = await ProductsService.get(session, tenant_id, product_id)
        anterior = product.image_url

        product.image_url = images.save_product_image(product_id, raw, content_type)
        product = await Repo.save(session, product)

        # Só depois de gravar o novo caminho: se o banco falhar, a foto antiga
        # continua valendo.
        images.delete_product_image(anterior)
        return product

    @staticmethod
    async def remove_image(
        session: AsyncSession, tenant_id: UUID, product_id: UUID
    ) -> Product:
        product = await ProductsService.get(session, tenant_id, product_id)
        anterior = product.image_url

        product.image_url = None
        product = await Repo.save(session, product)

        images.delete_product_image(anterior)
        return product
