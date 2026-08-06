from __future__ import annotations

from typing import Optional
from uuid import UUID, uuid4

from fastapi import HTTPException, status
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
        if payload.document:
            existing = await Repo.get_by_document(session, tenant_id, payload.document)
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Já existe um cliente com o documento {payload.document}",
                )

        customer = Customer(
            id=uuid4(),
            tenant_id=tenant_id,
            status=CustomerStatus.ACTIVE,
            **payload.model_dump(exclude={"address"}),
            address=payload.address.model_dump() if payload.address else None,
        )
        return await Repo.save(session, customer)

    @staticmethod
    async def update(
        session: AsyncSession, tenant_id: UUID, customer_id: UUID, payload: CustomerUpdate
    ) -> Customer:
        customer = await CustomersService.get(session, tenant_id, customer_id)

        data = payload.model_dump(exclude_unset=True)

        document = data.get("document")
        if document and document != customer.document:
            existing = await Repo.get_by_document(session, tenant_id, document)
            if existing and existing.id != customer.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Já existe um cliente com o documento {document}",
                )

        if "address" in data:
            data["address"] = payload.address.model_dump() if payload.address else None
        if "status" in data and data["status"] is not None:
            data["status"] = CustomerStatus(data["status"])

        for key, value in data.items():
            setattr(customer, key, value)

        return await Repo.save(session, customer)
