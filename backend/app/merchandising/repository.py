from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.models.customer import Customer, CustomerStatus
from app.infrastructure.persistence.models.customer_product import CustomerProduct
from app.infrastructure.persistence.models.product import Product
from app.infrastructure.persistence.models.promoter_customer import PromoterCustomer
from app.infrastructure.persistence.models.stock_visit import (
    StockVisit, StockVisitItem, StockVisitStatus,
)
from app.infrastructure.persistence.models.user import User


class MerchandisingRepository:

    # ── Clientes do promotor ──────────────────────────────────────────────

    @staticmethod
    async def list_customers_for_promoter(
        session: AsyncSession,
        tenant_id: UUID,
        user_id: Optional[UUID],
        search: Optional[str] = None,
    ) -> Sequence[Customer]:
        """Clientes atendidos pelo promotor.
        `user_id=None` retorna todos os clientes do tenant (visão do admin)."""

        query = select(Customer).where(
            Customer.tenant_id == tenant_id,
            Customer.status == CustomerStatus.ACTIVE,
        )

        if user_id is not None:
            query = query.join(
                PromoterCustomer,
                and_(
                    PromoterCustomer.customer_id == Customer.id,
                    PromoterCustomer.tenant_id == tenant_id,
                    PromoterCustomer.user_id == user_id,
                    PromoterCustomer.is_active.is_(True),
                ),
            )

        if search:
            query = query.where(Customer.name.ilike(f"%{search.strip()}%"))

        query = query.order_by(Customer.name)
        return (await session.execute(query)).scalars().all()

    @staticmethod
    async def last_visit_by_customer_and_type(
        session: AsyncSession, tenant_id: UUID
    ) -> dict[tuple[UUID, str], datetime]:
        """{(customer_id, 'gondola'|'estoque'): última contagem enviada}.

        Uma query para a tela inteira em vez de duas subqueries correlacionadas
        por cliente — a lista do promotor é curta e isso a mantém legível.
        """
        query = (
            select(
                StockVisit.customer_id,
                StockVisit.visit_type,
                func.max(StockVisit.submitted_at),
            )
            .where(
                StockVisit.tenant_id == tenant_id,
                StockVisit.status != StockVisitStatus.DRAFT.value,
            )
            .group_by(StockVisit.customer_id, StockVisit.visit_type)
        )
        rows = (await session.execute(query)).all()
        return {(customer_id, visit_type): moment for customer_id, visit_type, moment in rows}

    @staticmethod
    async def is_customer_assigned(
        session: AsyncSession, tenant_id: UUID, user_id: UUID, customer_id: UUID
    ) -> bool:
        query = select(func.count()).select_from(PromoterCustomer).where(
            PromoterCustomer.tenant_id == tenant_id,
            PromoterCustomer.user_id == user_id,
            PromoterCustomer.customer_id == customer_id,
            PromoterCustomer.is_active.is_(True),
        )
        return bool((await session.execute(query)).scalar_one())

    # ── Produtos para contagem ────────────────────────────────────────────

    @staticmethod
    async def list_mix_products(
        session: AsyncSession, tenant_id: UUID, customer_id: UUID
    ) -> Sequence[tuple[Product, int]]:
        query = (
            select(Product, CustomerProduct.position)
            .join(
                CustomerProduct,
                and_(
                    CustomerProduct.product_id == Product.id,
                    CustomerProduct.tenant_id == tenant_id,
                    CustomerProduct.customer_id == customer_id,
                ),
            )
            .where(Product.tenant_id == tenant_id, Product.is_active.is_(True))
            .order_by(CustomerProduct.position, Product.name)
        )
        return (await session.execute(query)).all()

    @staticmethod
    async def list_mix_product_ids(
        session: AsyncSession, tenant_id: UUID, customer_id: UUID
    ) -> list[UUID]:
        query = (
            select(CustomerProduct.product_id)
            .where(
                CustomerProduct.tenant_id == tenant_id,
                CustomerProduct.customer_id == customer_id,
            )
            .order_by(CustomerProduct.position)
        )
        return list((await session.execute(query)).scalars().all())

    @staticmethod
    async def list_all_products(
        session: AsyncSession, tenant_id: UUID, search: Optional[str] = None
    ) -> Sequence[Product]:
        query = select(Product).where(
            Product.tenant_id == tenant_id, Product.is_active.is_(True)
        )
        if search:
            query = query.where(Product.name.ilike(f"%{search.strip()}%"))
        query = query.order_by(Product.name)
        return (await session.execute(query)).scalars().all()

    @staticmethod
    async def package_sizes(
        session: AsyncSession, tenant_id: UUID, product_ids: list[UUID]
    ) -> dict[UUID, Decimal]:
        """{product_id: unidades por caixa} — o fator que converte a contagem.

        `package_size` nulo ou zero vira 1: produto sem caixa cadastrada é
        contado como se a "caixa" fosse a própria unidade, nunca como zero.
        """
        if not product_ids:
            return {}

        query = select(Product.id, Product.package_size).where(
            Product.tenant_id == tenant_id, Product.id.in_(product_ids)
        )
        return {
            product_id: Decimal(size) if size else Decimal(1)
            for product_id, size in (await session.execute(query)).all()
        }

    @staticmethod
    async def last_quantities_for_customer(
        session: AsyncSession, tenant_id: UUID, customer_id: UUID, visit_type: str
    ) -> dict[UUID, tuple]:
        """Quantidades da última contagem DO MESMO TIPO nesse cliente.

        Separado por tipo de propósito: o que estava na gôndola não serve de
        referência para o que está no estoque, e vice-versa.
        """
        last_visit_id = (
            select(StockVisit.id)
            .where(
                StockVisit.tenant_id == tenant_id,
                StockVisit.customer_id == customer_id,
                StockVisit.visit_type == visit_type,
                StockVisit.status != StockVisitStatus.DRAFT.value,
            )
            .order_by(StockVisit.submitted_at.desc())
            .limit(1)
            .scalar_subquery()
        )
        query = select(
            StockVisitItem.product_id,
            StockVisitItem.boxes,
            StockVisitItem.units,
            StockVisitItem.quantity,
        ).where(
            StockVisitItem.tenant_id == tenant_id,
            StockVisitItem.visit_id == last_visit_id,
        )
        return {
            product_id: (boxes, units, quantity)
            for product_id, boxes, units, quantity in (await session.execute(query)).all()
        }

    # ── Visitas ───────────────────────────────────────────────────────────

    @staticmethod
    async def get_visit(
        session: AsyncSession, tenant_id: UUID, visit_id: UUID
    ) -> Optional[StockVisit]:
        query = select(StockVisit).where(
            StockVisit.tenant_id == tenant_id, StockVisit.id == visit_id
        )
        return (await session.execute(query)).scalars().first()

    @staticmethod
    async def get_visit_detail(
        session: AsyncSession, tenant_id: UUID, visit_id: UUID
    ) -> Optional[tuple[StockVisit, Optional[str], Optional[str]]]:
        """Visita + nome do cliente + nome do promotor, em UMA query."""
        query = (
            select(StockVisit, Customer.name, User.full_name)
            .join(Customer, Customer.id == StockVisit.customer_id, isouter=True)
            .join(User, User.id == StockVisit.promoter_id, isouter=True)
            .where(StockVisit.tenant_id == tenant_id, StockVisit.id == visit_id)
        )
        return (await session.execute(query)).first()

    @staticmethod
    async def get_visit_by_client_uuid(
        session: AsyncSession, tenant_id: UUID, client_uuid: str
    ) -> Optional[StockVisit]:
        query = select(StockVisit).where(
            StockVisit.tenant_id == tenant_id, StockVisit.client_uuid == client_uuid
        )
        return (await session.execute(query)).scalars().first()

    @staticmethod
    async def save_visit(session: AsyncSession, visit: StockVisit) -> StockVisit:
        session.add(visit)
        await session.commit()
        await session.refresh(visit)
        return visit

    @staticmethod
    async def replace_items(
        session: AsyncSession, visit_id: UUID, items: list[StockVisitItem]
    ) -> None:
        await session.execute(
            delete(StockVisitItem).where(StockVisitItem.visit_id == visit_id)
        )
        for item in items:
            session.add(item)
        await session.commit()

    @staticmethod
    async def list_items(
        session: AsyncSession, visit_id: UUID
    ) -> Sequence[tuple[StockVisitItem, Optional[Product]]]:
        """Itens da contagem, cada um com o seu produto.

        Devolve o produto inteiro e não só o nome porque a tela de correção
        remonta os mesmos painéis da contagem — precisa de foto e package_size.
        """
        query = (
            select(StockVisitItem, Product)
            .join(Product, Product.id == StockVisitItem.product_id, isouter=True)
            .where(StockVisitItem.visit_id == visit_id)
            .order_by(Product.name)
        )
        return (await session.execute(query)).all()

    @staticmethod
    async def list_visits(
        session: AsyncSession,
        tenant_id: UUID,
        promoter_id: Optional[UUID] = None,
        customer_id: Optional[UUID] = None,
        status: Optional[str] = None,
        visit_type: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[tuple[StockVisit, str, str, int]], int]:
        items_count = (
            select(func.count())
            .select_from(StockVisitItem)
            .where(StockVisitItem.visit_id == StockVisit.id)
            .correlate(StockVisit)
            .scalar_subquery()
        )

        base = (
            select(StockVisit, Customer.name, User.full_name, items_count)
            .join(Customer, Customer.id == StockVisit.customer_id, isouter=True)
            .join(User, User.id == StockVisit.promoter_id, isouter=True)
            .where(StockVisit.tenant_id == tenant_id)
        )

        if promoter_id:
            base = base.where(StockVisit.promoter_id == promoter_id)
        if customer_id:
            base = base.where(StockVisit.customer_id == customer_id)
        if status:
            base = base.where(StockVisit.status == status)
        if visit_type:
            base = base.where(StockVisit.visit_type == visit_type)
        if date_from:
            base = base.where(StockVisit.visited_at >= date_from)
        if date_to:
            base = base.where(StockVisit.visited_at <= date_to)

        total = (
            await session.execute(
                select(func.count()).select_from(base.subquery())
            )
        ).scalar_one()

        rows = (
            await session.execute(
                base.order_by(StockVisit.visited_at.desc().nullslast(),
                              StockVisit.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()

        return rows, total

    @staticmethod
    async def list_visits_for_pairing(
        session: AsyncSession,
        tenant_id: UUID,
        customer_ids: Optional[Sequence[UUID]] = None,
        promoter_ids: Optional[Sequence[UUID]] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> Sequence:
        """Contagens enviadas, sem os itens, com nome de cliente e promotor.

        Sem join com os itens de propósito: a contagem declarada "sem produtos"
        não tem item nenhum e precisa entrar no par do mesmo jeito — é ela que
        destrava a planilha do cliente que não tinha nada num dos dois lugares.
        Por isso a quantidade de itens vem de subconsulta correlacionada e não de
        join: contar sem multiplicar linhas, e devolver 0 em vez de sumir.
        """
        items_count = (
            select(func.count())
            .select_from(StockVisitItem)
            .where(StockVisitItem.visit_id == StockVisit.id)
            .correlate(StockVisit)
            .scalar_subquery()
        )

        query = (
            select(
                StockVisit.id,
                StockVisit.customer_id,
                StockVisit.promoter_id,
                StockVisit.visit_type,
                StockVisit.status,
                StockVisit.visited_at,
                StockVisit.submitted_at,
                StockVisit.exported_at,
                StockVisit.created_at,
                StockVisit.no_products,
                items_count.label("items_count"),
                Customer.name.label("customer_name"),
                User.full_name.label("promoter_name"),
            )
            .select_from(StockVisit)
            .join(Customer, Customer.id == StockVisit.customer_id, isouter=True)
            .join(User, User.id == StockVisit.promoter_id, isouter=True)
            .where(
                StockVisit.tenant_id == tenant_id,
                StockVisit.status != StockVisitStatus.DRAFT.value,
            )
        )

        if customer_ids is not None:
            query = query.where(StockVisit.customer_id.in_(customer_ids))
        if promoter_ids is not None:
            query = query.where(StockVisit.promoter_id.in_(promoter_ids))
        if date_from:
            query = query.where(StockVisit.visited_at >= date_from)
        if date_to:
            query = query.where(StockVisit.visited_at <= date_to)

        return (await session.execute(query)).all()

    @staticmethod
    async def list_export_items(
        session: AsyncSession, tenant_id: UUID, visit_ids: Sequence[UUID]
    ) -> Sequence:
        """Itens das contagens informadas, achatados para a planilha.

        Traz o `package_size` de hoje em vez do total gravado: a conversão é
        refeita na planilha, e o cadastro corrigido conserta contagens antigas.
        """
        if not visit_ids:
            return []

        query = (
            select(
                StockVisitItem.visit_id,
                StockVisitItem.product_id,
                Product.name.label("product_name"),
                Product.package_size,
                StockVisitItem.boxes,
                StockVisitItem.units,
            )
            .select_from(StockVisitItem)
            .join(Product, Product.id == StockVisitItem.product_id, isouter=True)
            .where(
                StockVisitItem.tenant_id == tenant_id,
                StockVisitItem.visit_id.in_(visit_ids),
            )
        )
        return (await session.execute(query)).all()

    @staticmethod
    async def mark_exported(
        session: AsyncSession, tenant_id: UUID, visit_ids: list[UUID], moment: datetime
    ) -> None:
        """Marca as visitas que acabaram de entrar numa planilha baixada.

        É isso que faz o promotor ver 'já processada' na tela de envios e o admin
        distinguir o que ainda não foi baixado. Só sai de `submitted`.
        """
        if not visit_ids:
            return
        await session.execute(
            update(StockVisit)
            .where(
                StockVisit.tenant_id == tenant_id,
                StockVisit.id.in_(visit_ids),
                StockVisit.status == StockVisitStatus.SUBMITTED.value,
            )
            .values(status=StockVisitStatus.EXPORTED.value, exported_at=moment)
        )
        await session.commit()

    # ── Vínculos e mix (admin) ────────────────────────────────────────────

    @staticmethod
    async def replace_assignments(
        session: AsyncSession, tenant_id: UUID, user_id: UUID, customer_ids: list[UUID]
    ) -> None:
        await session.execute(
            delete(PromoterCustomer).where(
                PromoterCustomer.tenant_id == tenant_id,
                PromoterCustomer.user_id == user_id,
            )
        )
        for customer_id in customer_ids:
            session.add(
                PromoterCustomer(
                    tenant_id=tenant_id, user_id=user_id,
                    customer_id=customer_id, is_active=True,
                )
            )
        await session.commit()

    @staticmethod
    async def replace_mix(
        session: AsyncSession, tenant_id: UUID, customer_id: UUID, product_ids: list[UUID]
    ) -> None:
        await session.execute(
            delete(CustomerProduct).where(
                CustomerProduct.tenant_id == tenant_id,
                CustomerProduct.customer_id == customer_id,
            )
        )
        for position, product_id in enumerate(product_ids):
            session.add(
                CustomerProduct(
                    tenant_id=tenant_id, customer_id=customer_id,
                    product_id=product_id, position=position,
                )
            )
        await session.commit()

    @staticmethod
    async def list_assigned_customer_ids(
        session: AsyncSession, tenant_id: UUID, user_id: UUID
    ) -> list[UUID]:
        query = select(PromoterCustomer.customer_id).where(
            PromoterCustomer.tenant_id == tenant_id,
            PromoterCustomer.user_id == user_id,
        )
        return list((await session.execute(query)).scalars().all())
