from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.models.stock_visit import (
    StockVisit, StockVisitItem, StockVisitStatus,
)
from app.infrastructure.persistence.models.user import User, UserRole
from app.merchandising.repository import MerchandisingRepository as Repo
from app.merchandising.schemas import (
    CountProductResponse, PromoterCustomerResponse, StockVisitCreate,
    StockVisitItemResponse, StockVisitResponse,
)


def _is_admin(user: User) -> bool:
    return user.role in (UserRole.ADMIN, UserRole.SUPERVISOR)


class MerchandisingService:

    # ── Promotor: clientes ────────────────────────────────────────────────

    @staticmethod
    async def list_my_customers(
        session: AsyncSession, tenant_id: UUID, user: User, search: Optional[str] = None
    ) -> list[PromoterCustomerResponse]:
        # Admin enxerga todos; promotor só os seus
        scope_user_id = None if _is_admin(user) else user.id
        rows = await Repo.list_customers_for_promoter(session, tenant_id, scope_user_id, search)

        return [
            PromoterCustomerResponse(
                id=customer.id,
                name=customer.name,
                corporate_name=customer.corporate_name,
                document=customer.document,
                phone=customer.phone,
                address=customer.address,
                customer_type=customer.customer_type,
                last_visited_at=last_visited_at,
                has_draft=bool(draft_count),
            )
            for customer, last_visited_at, draft_count in rows
        ]

    # ── Promotor: produtos para contar ────────────────────────────────────

    @staticmethod
    async def list_products_for_customer(
        session: AsyncSession, tenant_id: UUID, user: User, customer_id: UUID,
        search: Optional[str] = None,
    ) -> list[CountProductResponse]:
        await MerchandisingService._assert_can_access_customer(session, tenant_id, user, customer_id)

        last_qty = await Repo.last_quantities_for_customer(session, tenant_id, customer_id)

        mix = await Repo.list_mix_products(session, tenant_id, customer_id)
        if mix:
            products = [(p, position) for p, position in mix]
        else:
            # Sem mix cadastrado: cai no catálogo completo
            products = [(p, 0) for p in await Repo.list_all_products(session, tenant_id, search)]

        if search and mix:
            term = search.strip().lower()
            products = [
                (p, pos) for p, pos in products
                if term in p.name.lower()
                or term in (p.sku or "").lower()
                or term in (p.barcode or "").lower()
            ]

        return [
            CountProductResponse(
                id=p.id, sku=p.sku, barcode=p.barcode, name=p.name, unit=p.unit,
                package_size=p.package_size, image_url=p.image_url,
                position=position, last_quantity=last_qty.get(p.id),
            )
            for p, position in products
        ]

    # ── Promotor: gravar contagem ─────────────────────────────────────────

    @staticmethod
    async def upsert_visit(
        session: AsyncSession, tenant_id: UUID, user: User, payload: StockVisitCreate
    ) -> StockVisitResponse:
        await MerchandisingService._assert_can_access_customer(
            session, tenant_id, user, payload.customer_id
        )

        visit = None
        if payload.client_uuid:
            # Idempotência: reenvio da mesma contagem atualiza em vez de duplicar
            visit = await Repo.get_visit_by_client_uuid(session, tenant_id, payload.client_uuid)

        now = datetime.now(timezone.utc)

        if visit is None:
            visit = StockVisit(
                id=uuid4(),
                tenant_id=tenant_id,
                customer_id=payload.customer_id,
                promoter_id=user.id,
                client_uuid=payload.client_uuid,
                status=StockVisitStatus.DRAFT.value,
                visited_at=payload.visited_at or now,
            )
        else:
            if visit.status == StockVisitStatus.EXPORTED.value:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Esta contagem já foi exportada e não pode mais ser alterada.",
                )
            if visit.promoter_id != user.id and not _is_admin(user):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Esta contagem pertence a outro promotor.",
                )
            visit.visited_at = payload.visited_at or visit.visited_at or now

        visit.notes = payload.notes

        if payload.submit:
            visit.status = StockVisitStatus.SUBMITTED.value
            visit.submitted_at = now

        visit = await Repo.save_visit(session, visit)

        items = [
            StockVisitItem(
                id=uuid4(),
                tenant_id=tenant_id,
                visit_id=visit.id,
                product_id=item.product_id,
                quantity=item.quantity,
                expires_at=item.expires_at,
                notes=item.notes,
            )
            for item in payload.items
        ]
        await Repo.replace_items(session, visit.id, items)

        return await MerchandisingService.get_visit(session, tenant_id, visit.id)

    @staticmethod
    async def submit_visit(
        session: AsyncSession, tenant_id: UUID, user: User, visit_id: UUID
    ) -> StockVisitResponse:
        visit = await Repo.get_visit(session, tenant_id, visit_id)
        if not visit:
            raise HTTPException(status_code=404, detail="Contagem não encontrada")
        if visit.promoter_id != user.id and not _is_admin(user):
            raise HTTPException(status_code=403, detail="Contagem de outro promotor")

        visit.status = StockVisitStatus.SUBMITTED.value
        visit.submitted_at = datetime.now(timezone.utc)
        await Repo.save_visit(session, visit)
        return await MerchandisingService.get_visit(session, tenant_id, visit_id)

    # ── Leitura ───────────────────────────────────────────────────────────

    @staticmethod
    async def get_visit(
        session: AsyncSession, tenant_id: UUID, visit_id: UUID
    ) -> StockVisitResponse:
        row = await Repo.get_visit_detail(session, tenant_id, visit_id)
        if not row:
            raise HTTPException(status_code=404, detail="Contagem não encontrada")

        visit, customer_name, customer_document, promoter_name = row

        item_rows = await Repo.list_items(session, visit.id)
        items = [
            StockVisitItemResponse(
                id=item.id, product_id=item.product_id, product_sku=sku,
                product_name=name, product_unit=unit, quantity=item.quantity,
                expires_at=item.expires_at, notes=item.notes,
            )
            for item, sku, name, unit in item_rows
        ]

        return StockVisitResponse(
            id=visit.id, tenant_id=visit.tenant_id, customer_id=visit.customer_id,
            customer_name=customer_name, customer_document=customer_document,
            promoter_id=visit.promoter_id, promoter_name=promoter_name,
            status=visit.status, visited_at=visit.visited_at,
            submitted_at=visit.submitted_at, exported_at=visit.exported_at,
            notes=visit.notes, client_uuid=visit.client_uuid,
            items=items, items_count=len(items),
            created_at=visit.created_at, updated_at=visit.updated_at,
        )

    @staticmethod
    async def list_visits(
        session: AsyncSession, tenant_id: UUID, **filters
    ) -> tuple[list[StockVisitResponse], int]:
        rows, total = await Repo.list_visits(session, tenant_id, **filters)
        visits = [
            StockVisitResponse(
                id=v.id, tenant_id=v.tenant_id, customer_id=v.customer_id,
                customer_name=c_name, customer_document=c_document,
                promoter_id=v.promoter_id, promoter_name=p_name,
                status=v.status, visited_at=v.visited_at, submitted_at=v.submitted_at,
                exported_at=v.exported_at, notes=v.notes, client_uuid=v.client_uuid,
                items=[], items_count=count,
                created_at=v.created_at, updated_at=v.updated_at,
            )
            for v, c_name, c_document, p_name, count in rows
        ]
        return visits, total

    # ── Guarda de acesso ──────────────────────────────────────────────────

    @staticmethod
    async def _assert_can_access_customer(
        session: AsyncSession, tenant_id: UUID, user: User, customer_id: UUID
    ) -> None:
        if _is_admin(user):
            return
        if not await Repo.is_customer_assigned(session, tenant_id, user.id, customer_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Este cliente não está atribuído a você.",
            )
