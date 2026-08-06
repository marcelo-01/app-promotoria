"""Cadastro temporário de produtos.

Mesma premissa de `customers/`: morre na fusão, quando o catálogo passa a vir do
Firebird. A via de entrada preferida é `POST /merchandising/imports/products`.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_roles
from app.infrastructure.persistence.session import get_db_session
from app.products.schemas import (
    ProductCreate, ProductListResponse, ProductResponse, ProductUpdate,
)
from app.products.service import ProductsService

router = APIRouter(prefix="/products", tags=["products"])

_ADMIN = ("admin", "supervisor")
_FIELD = ("promoter", "admin", "supervisor")


@router.get("", response_model=ProductListResponse)
async def list_products(
    search: Optional[str] = None,
    active_only: bool = Query(False),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_FIELD)),
):
    items, total = await ProductsService.list(
        session, context["tenant_id"], search, active_only, limit, offset
    )
    return ProductListResponse(
        items=[ProductResponse.model_validate(p) for p in items], total=total
    )


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_FIELD)),
):
    return await ProductsService.get(session, context["tenant_id"], product_id)


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    return await ProductsService.create(session, context["tenant_id"], payload)


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    return await ProductsService.update(session, context["tenant_id"], product_id, payload)
