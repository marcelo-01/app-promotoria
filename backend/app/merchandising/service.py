from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.service import CustomersService
from app.infrastructure.persistence.models.stock_visit import (
    StockVisit, StockVisitItem, StockVisitStatus, UnitType, VisitType,
)
from app.infrastructure.persistence.models.user import User, UserRole
from app.merchandising.repository import MerchandisingRepository as Repo
from app.merchandising.schemas import (
    CountProductResponse, CountSheetResponse, PromoterCustomerResponse,
    StockVisitCreate, StockVisitItemResponse, StockVisitResponse,
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
        customers = await Repo.list_customers_for_promoter(
            session, tenant_id, scope_user_id, search
        )
        last_visits = await Repo.last_visit_by_customer_and_type(session, tenant_id)

        return [
            PromoterCustomerResponse(
                id=customer.id,
                name=customer.name,
                last_gondola_at=last_visits.get((customer.id, VisitType.GONDOLA.value)),
                last_estoque_at=last_visits.get((customer.id, VisitType.ESTOQUE.value)),
            )
            for customer in customers
        ]

    # ── Promotor: folha de contagem ───────────────────────────────────────

    @staticmethod
    async def count_sheet(
        session: AsyncSession, tenant_id: UUID, user: User, customer_id: UUID,
        visit_type: str,
    ) -> CountSheetResponse:
        """Cliente + produtos + contagem anterior: tudo numa resposta só."""
        await MerchandisingService._assert_can_access_customer(
            session, tenant_id, user, customer_id
        )

        customer = await CustomersService.get(session, tenant_id, customer_id)
        last = await Repo.last_quantities_for_customer(
            session, tenant_id, customer_id, visit_type
        )

        mix = await Repo.list_mix_products(session, tenant_id, customer_id)
        if mix:
            products = [(p, position) for p, position in mix]
        else:
            # Sem mix cadastrado: cai no catálogo completo
            products = [(p, 0) for p in await Repo.list_all_products(session, tenant_id)]

        vazio = (None, None, None)
        return CountSheetResponse(
            customer_id=customer.id,
            customer_name=customer.name,
            visit_type=visit_type,
            products=[
                CountProductResponse(
                    id=p.id,
                    name=p.name,
                    image_url=p.image_url,
                    position=position,
                    package_size=p.package_size or Decimal(1),
                    last_boxes=last.get(p.id, vazio)[0],
                    last_units=last.get(p.id, vazio)[1],
                    last_quantity=last.get(p.id, vazio)[2],
                )
                for p, position in products
            ],
        )

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
                visit_type=payload.visit_type,
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
            visit.visit_type = payload.visit_type
            visit.visited_at = payload.visited_at or visit.visited_at or now

        if payload.submit:
            visit.status = StockVisitStatus.SUBMITTED.value
            visit.submitted_at = now

        visit = await Repo.save_visit(session, visit)

        # A conversão para unidades é feita aqui, na hora de gravar, e não na
        # planilha: assim o total já vale para o detalhe da visita e para a
        # "contagem anterior" da próxima visita, sem repetir a regra em cada
        # leitura.
        sizes = await Repo.package_sizes(
            session, tenant_id, [item.product_id for item in payload.items]
        )

        items = [
            StockVisitItem(
                id=uuid4(),
                tenant_id=tenant_id,
                visit_id=visit.id,
                product_id=item.product_id,
                boxes=item.boxes,
                units=item.units,
                quantity=item.boxes * sizes.get(item.product_id, Decimal(1)) + item.units,
                unit_type=UnitType.UNIDADE.value,
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

        visit, customer_name, promoter_name = row

        item_rows = await Repo.list_items(session, visit.id)
        items = [
            StockVisitItemResponse(
                id=item.id, product_id=item.product_id, product_name=name,
                boxes=item.boxes, units=item.units,
                quantity=item.quantity, unit_type=item.unit_type,
                expires_at=item.expires_at, notes=item.notes,
            )
            for item, name in item_rows
        ]

        return StockVisitResponse(
            id=visit.id, tenant_id=visit.tenant_id, customer_id=visit.customer_id,
            customer_name=customer_name,
            promoter_id=visit.promoter_id, promoter_name=promoter_name,
            visit_type=visit.visit_type, status=visit.status, visited_at=visit.visited_at,
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
                customer_name=c_name,
                promoter_id=v.promoter_id, promoter_name=p_name,
                visit_type=v.visit_type, status=v.status, visited_at=v.visited_at,
                submitted_at=v.submitted_at, exported_at=v.exported_at,
                notes=v.notes, client_uuid=v.client_uuid,
                items=[], items_count=count,
                created_at=v.created_at, updated_at=v.updated_at,
            )
            for v, c_name, p_name, count in rows
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
