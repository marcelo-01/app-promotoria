"""Cadastro temporário de clientes.

Deliberadamente pobre — só o nome: morre no dia da fusão, quando os clientes
passam a vir do Firebird via ERP.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_roles
from app.customers.schemas import (
    CustomerCreate, CustomerListResponse, CustomerResponse, CustomerUpdate,
)
from app.customers.service import CustomersService
from app.infrastructure.persistence.session import get_db_session

router = APIRouter(prefix="/customers", tags=["customers"])

_ADMIN = ("admin", "supervisor")
_FIELD = ("promoter", "admin", "supervisor")


@router.get("", response_model=CustomerListResponse)
async def list_customers(
    search: Optional[str] = None,
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_FIELD)),
):
    items, total = await CustomersService.list(
        session, context["tenant_id"], search, limit, offset
    )
    return CustomerListResponse(
        items=[CustomerResponse.model_validate(c) for c in items], total=total
    )


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_FIELD)),
):
    return await CustomersService.get(session, context["tenant_id"], customer_id)


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    payload: CustomerCreate,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    return await CustomersService.create(session, context["tenant_id"], payload)


@router.put("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: UUID,
    payload: CustomerUpdate,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    return await CustomersService.update(session, context["tenant_id"], customer_id, payload)
