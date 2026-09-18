from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.models.customer import Customer, CustomerStatus
from app.infrastructure.persistence.models.customer_product import CustomerProduct
from app.infrastructure.persistence.models.delivery import (
    InvoiceImport, ProductDelivery, ProductRemoval,
)
from app.infrastructure.persistence.models.product import Product
from app.infrastructure.persistence.models.product_expiry import ProductExpiry
from app.infrastructure.persistence.models.promoter_customer import PromoterCustomer
from app.infrastructure.persistence.models.stock_visit import (
    StockVisit, StockVisitItem, StockVisitStatus,
)
from app.infrastructure.persistence.models.turnover_factor import TurnoverFactor
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
    async def replace_expiries(
        session: AsyncSession, visit_id: UUID, expiries: list[ProductExpiry]
    ) -> None:
        """Troca as datas coletadas deste envio. Mesmo espírito de `replace_items`:
        o reenvio offline da mesma contagem substitui, não duplica."""
        await session.execute(
            delete(ProductExpiry).where(ProductExpiry.visit_id == visit_id)
        )
        for expiry in expiries:
            session.add(expiry)
        await session.commit()

    @staticmethod
    async def products_by_sku(
        session: AsyncSession, tenant_id: UUID
    ) -> dict[str, UUID]:
        """Código do ERP → id do produto aqui. Produto sem código fica de fora."""
        query = select(Product.sku, Product.id).where(
            Product.tenant_id == tenant_id, Product.sku.isnot(None)
        )
        return {
            sku.strip(): product_id
            for sku, product_id in (await session.execute(query)).all()
            if sku and sku.strip()
        }

    @staticmethod
    async def customers_by_document(
        session: AsyncSession, tenant_id: UUID
    ) -> dict[str, UUID]:
        """CNPJ/CPF (só dígitos) → id do cliente aqui."""
        query = select(Customer.document, Customer.id).where(
            Customer.tenant_id == tenant_id, Customer.document.isnot(None)
        )
        return {
            documento.strip(): customer_id
            for documento, customer_id in (await session.execute(query)).all()
            if documento and documento.strip()
        }

    # Linhas por INSERT. Cada uma leva 13 parâmetros, e o protocolo do Postgres
    # aceita 32 767 por comando — 2 000 linhas ficam em 26 mil, com folga.
    _LOTE_ENTREGAS = 2000

    @staticmethod
    async def replace_deliveries(
        session: AsyncSession, tenant_id: UUID, deliveries: list[ProductDelivery]
    ) -> None:
        """Grava as entradas, substituindo as que já tinham a mesma chave.

        Anexar a planilha de ontem de novo não duplica nada: a chave é
        (origem, empresa, nº venda, produto), e uma linha corrigida no ERP
        sobrescreve a que estava aqui.

        É um upsert em lotes, e não DELETE + INSERT de tudo, por tamanho: dois
        meses de faturamento são 60 mil linhas, e um único `DELETE ... IN` com
        60 mil chaves estoura o Postgres ("stack depth limit exceeded") antes
        de apagar qualquer coisa. O `ON CONFLICT` faz a troca linha a linha,
        dentro do limite de parâmetros por comando, e numa transação só.
        """
        if not deliveries:
            return

        tabela = ProductDelivery.__table__
        for inicio in range(0, len(deliveries), MerchandisingRepository._LOTE_ENTREGAS):
            lote = deliveries[inicio:inicio + MerchandisingRepository._LOTE_ENTREGAS]
            comando = pg_insert(tabela).values([
                {
                    "id": d.id,
                    "tenant_id": tenant_id,
                    "kind": d.kind,
                    "customer_id": d.customer_id,
                    "product_id": d.product_id,
                    "issued_on": d.issued_on,
                    "quantity": d.quantity,
                    "company": d.company,
                    "sale_number": d.sale_number,
                    "invoice": d.invoice,
                    "cfop": d.cfop,
                }
                for d in lote
            ])
            comando = comando.on_conflict_do_update(
                constraint="uq_product_deliveries_venda",
                set_={
                    "customer_id": comando.excluded.customer_id,
                    "issued_on": comando.excluded.issued_on,
                    "quantity": comando.excluded.quantity,
                    "invoice": comando.excluded.invoice,
                    "cfop": comando.excluded.cfop,
                    "updated_at": func.now(),
                },
            )
            await session.execute(comando)
        await session.commit()

    @staticmethod
    async def add_invoice_import(session: AsyncSession, receipt: InvoiceImport) -> None:
        """Guarda o recibo de uma planilha que acabou de entrar."""
        session.add(receipt)
        await session.commit()

    @staticmethod
    async def list_invoice_imports(
        session: AsyncSession, tenant_id: UUID, kind: str, limit: int = 20,
    ) -> list[tuple[InvoiceImport, Optional[str]]]:
        """As últimas planilhas desta origem que entraram, da mais recente
        para a mais antiga, com o nome de quem anexou."""
        query = (
            select(InvoiceImport, func.coalesce(User.full_name, User.email))
            .outerjoin(User, User.id == InvoiceImport.user_id)
            .where(InvoiceImport.tenant_id == tenant_id, InvoiceImport.kind == kind)
            .order_by(InvoiceImport.created_at.desc())
            .limit(limit)
        )
        return [(recibo, nome) for recibo, nome in (await session.execute(query)).all()]

    @staticmethod
    async def sum_deliveries_in_cycle(
        session: AsyncSession, tenant_id: UUID, customer_id: UUID,
        after: date, until: date, kind: str,
    ) -> dict[UUID, float]:
        """O que entrou neste cliente DENTRO do ciclo, somado por produto.

        A janela é aberta no início e fechada no fim: a nota emitida no dia da
        contagem anterior já está refletida naquela contagem, e contá-la de novo
        inflaria a venda do ciclo seguinte.
        """
        query = (
            select(ProductDelivery.product_id, func.sum(ProductDelivery.quantity))
            .where(
                ProductDelivery.tenant_id == tenant_id,
                ProductDelivery.customer_id == customer_id,
                ProductDelivery.kind == kind,
                ProductDelivery.issued_on > after,
                ProductDelivery.issued_on <= until,
            )
            .group_by(ProductDelivery.product_id)
        )
        return {
            product_id: float(total or 0)
            for product_id, total in (await session.execute(query)).all()
        }

    @staticmethod
    async def sum_removals_in_cycle(
        session: AsyncSession, tenant_id: UUID, customer_id: UUID,
        after: date, until: date,
    ) -> dict[UUID, float]:
        """O vencido retirado dentro do ciclo, somado por produto."""
        query = (
            select(ProductRemoval.product_id, func.sum(ProductRemoval.quantity))
            .where(
                ProductRemoval.tenant_id == tenant_id,
                ProductRemoval.customer_id == customer_id,
                ProductRemoval.removed_day > after,
                ProductRemoval.removed_day <= until,
            )
            .group_by(ProductRemoval.product_id)
        )
        return {
            product_id: float(total or 0)
            for product_id, total in (await session.execute(query)).all()
        }

    @staticmethod
    async def replace_removals(
        session: AsyncSession, tenant_id: UUID, client_uuid: str,
        removals: list[ProductRemoval],
    ) -> None:
        """Troca as linhas de uma retirada. Reenvio offline substitui, não duplica."""
        await session.execute(
            delete(ProductRemoval).where(
                ProductRemoval.tenant_id == tenant_id,
                ProductRemoval.client_uuid == client_uuid,
            )
        )
        for linha in removals:
            session.add(linha)
        await session.commit()

    @staticmethod
    async def list_removals_by_day(
        session: AsyncSession, tenant_id: UUID, customer_id: UUID, day: date
    ) -> Sequence[tuple[ProductRemoval, Optional[str]]]:
        """As retiradas de um cliente num dia, com o nome do produto."""
        query = (
            select(ProductRemoval, Product.name)
            .join(Product, Product.id == ProductRemoval.product_id, isouter=True)
            .where(
                ProductRemoval.tenant_id == tenant_id,
                ProductRemoval.customer_id == customer_id,
                ProductRemoval.removed_day == day,
            )
            .order_by(ProductRemoval.expires_at)
        )
        return (await session.execute(query)).all()

    @staticmethod
    async def latest_expiries_for_customer(
        session: AsyncSession, tenant_id: UUID, customer_id: UUID, since: date
    ) -> dict[UUID, tuple[date, list[tuple[date, Decimal]]]]:
        """{product_id: (dia da coleta, [(vence em, quantidade), ...])} — a
        coleta de validade MAIS RECENTE de cada produto neste cliente.

        Só a mais recente, e de UM envio só: a coleta anterior descreve
        mercadoria que já foi em parte vendida, e um segundo envio do mesmo dia
        (reenvio com outro `client_uuid`) repetiria as mesmas linhas — somar
        qualquer um dos dois contaria o mesmo lote duas vezes. O dia da coleta
        vai junto para a tela dizer de quando é a informação.
        """
        query = (
            select(
                ProductExpiry.product_id, ProductExpiry.visit_id,
                ProductExpiry.collected_day, ProductExpiry.expires_at,
                ProductExpiry.quantity,
            )
            .where(
                ProductExpiry.tenant_id == tenant_id,
                ProductExpiry.customer_id == customer_id,
                ProductExpiry.collected_day >= since,
            )
            .order_by(
                ProductExpiry.product_id, ProductExpiry.collected_day.desc(),
                ProductExpiry.created_at.desc(), ProductExpiry.expires_at,
            )
        )
        saida: dict[UUID, tuple[date, list[tuple[date, Decimal]]]] = {}
        envio_que_vale: dict[UUID, UUID] = {}
        for product_id, visit_id, dia, vence, quantidade in (await session.execute(query)).all():
            if product_id not in envio_que_vale:
                envio_que_vale[product_id] = visit_id
                saida[product_id] = (dia, [])
            if visit_id == envio_que_vale[product_id]:
                saida[product_id][1].append((vence, quantidade))
        # Do que vence primeiro para o que vence depois — `created_at` desempata
        # o envio, mas não ordena as linhas dentro dele.
        for _, lotes in saida.values():
            lotes.sort()
        return saida

    @staticmethod
    async def list_expiries_for_visits(
        session: AsyncSession, visit_ids: Sequence[UUID]
    ) -> dict[UUID, list[tuple[ProductExpiry, Optional[str]]]]:
        """As datas coletadas em cada envio, com o nome do produto.

        O produto vem pelo JOIN e não dos itens da contagem: a coleta é do PAR, e
        a mercadoria pode ter sido contada só do outro lado — na gôndola, enquanto
        este envio é o do estoque.
        """
        if not visit_ids:
            return {}

        query = (
            select(ProductExpiry, Product.name)
            .join(Product, Product.id == ProductExpiry.product_id, isouter=True)
            .where(ProductExpiry.visit_id.in_(list(visit_ids)))
            .order_by(ProductExpiry.expires_at)
        )
        por_visita: dict[UUID, list[tuple[ProductExpiry, Optional[str]]]] = {}
        for linha, nome in (await session.execute(query)).all():
            por_visita.setdefault(linha.visit_id, []).append((linha, nome))
        return por_visita

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

    # ── Fator de giro (vendedor) ──────────────────────────────────────────

    @staticmethod
    async def turnover_factors_for_customer(
        session: AsyncSession, tenant_id: UUID, customer_id: UUID
    ) -> dict[UUID, Decimal]:
        """{product_id: fator} do que o vendedor já definiu nesta loja. Produto
        fora do mapa vale o `DEFAULT_FACTOR` de `orders.py` — quem lê decide,
        não o banco."""
        query = select(TurnoverFactor.product_id, TurnoverFactor.turnover_factor).where(
            TurnoverFactor.tenant_id == tenant_id,
            TurnoverFactor.customer_id == customer_id,
        )
        return dict((await session.execute(query)).all())

    @staticmethod
    async def set_turnover_factor(
        session: AsyncSession, tenant_id: UUID, customer_id: UUID, product_id: UUID,
        factor: Decimal,
    ) -> None:
        """Grava o fator do produto nesta loja — cria a linha na primeira vez."""
        linha = (await session.execute(
            select(TurnoverFactor).where(
                TurnoverFactor.tenant_id == tenant_id,
                TurnoverFactor.customer_id == customer_id,
                TurnoverFactor.product_id == product_id,
            )
        )).scalars().first()
        if linha is None:
            linha = TurnoverFactor(
                tenant_id=tenant_id, customer_id=customer_id, product_id=product_id,
            )
        linha.turnover_factor = factor
        session.add(linha)
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
