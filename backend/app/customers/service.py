from __future__ import annotations

from typing import Optional
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.repository import CustomersRepository as Repo
from app.customers.schemas import CustomerCreate, CustomerUpdate
from app.infrastructure.persistence.models.customer import Customer, CustomerStatus


class CustomersService:

    @staticmethod
    async def list(
        session: AsyncSession,
        tenant_id: UUID,
        search: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ):
        return await Repo.list(session, tenant_id, search, limit, offset)

    @staticmethod
    async def get(session: AsyncSession, tenant_id: UUID, customer_id: UUID) -> Customer:
        customer = await Repo.get(session, tenant_id, customer_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        return customer

    @staticmethod
    async def create(
        session: AsyncSession, tenant_id: UUID, payload: CustomerCreate
    ) -> Customer:
        customer = Customer(
            id=uuid4(),
            tenant_id=tenant_id,
            name=payload.name,
            status=CustomerStatus.ACTIVE,
        )
        return await Repo.save(session, customer)

    @staticmethod
    async def update(
        session: AsyncSession, tenant_id: UUID, customer_id: UUID, payload: CustomerUpdate
    ) -> Customer:
        customer = await CustomersService.get(session, tenant_id, customer_id)

        data = payload.model_dump(exclude_unset=True)

        if data.get("status") is not None:
            try:
                data["status"] = CustomerStatus(data["status"])
            except ValueError:
                raise HTTPException(status_code=422, detail="Status inválido")

        for key, value in data.items():
            if value is not None:
                setattr(customer, key, value)

        return await Repo.save(session, customer)
