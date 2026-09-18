from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.service import CustomersService
from app.infrastructure.persistence.models.delivery import (
    DeliveryKind, InvoiceImport, ProductDelivery, ProductRemoval,
)
from app.infrastructure.persistence.models.product_expiry import ProductExpiry
from app.infrastructure.persistence.models.stock_visit import (
    StockVisit, StockVisitItem, StockVisitStatus, UnitType, VisitType,
)
from app.infrastructure.persistence.models.user import User, UserRole
from app.merchandising import consolidation, evolution, expiry, invoices, orders
from app.merchandising.repository import MerchandisingRepository as Repo
from app.merchandising.schemas import (
    CountProductResponse, CountSheetResponse, InvoiceImportRecordResponse,
    InvoiceImportResponse,
    ExpiryLotResponse, MovedProductResponse, OrderSuggestionItemResponse,
    OrderSuggestionResponse,
    ProductExpiryInput, ProductExpiryResponse,
    ProductRemovalCreate, ProductRemovalResponse, PromoterCustomerResponse,
    ShelfGapResponse, StalledProductResponse, UnknownKeyResponse,
    StockCustomerResponse, StockHistoryResponse, StockInsightsResponse,
    StockPointResponse, StockVisitCreate, StockVisitItemInput, StockVisitItemResponse,
    StockVisitResponse, StockVisitUpdate, VisitPairResponse, VisitPairSideResponse,
)
from app.products.service import ProductsService

# Quanto passado a série precisa cobrir para que as duas últimas contagens
# completas apareçam. A conta usa só o último ciclo, mas um cliente que ficou um
# mês sem visita ainda tem de ter as duas pontas dentro da janela.
EXPIRY_WINDOW_DAYS = 120


@dataclass(frozen=True)
class _ExpiryInput:
    """O que o aparelho precisa saber, por produto, para fechar a conta do
    vencimento com a contagem de hoje em mãos.

    Tudo no intervalo que vai do último dia completo até hoje.
    """

    previous_stock: float    # o total do par naquele dia
    invoiced: float          # entrou pela planilha de faturamento
    gifted: float            # entrou pela planilha de brinde
    removed: float           # o promotor retirou por vencimento


def _quantia(valor: float) -> Decimal:
    """Float da série → Decimal da resposta, na mesma casa das quantidades."""
    return Decimal(str(round(valor, 3)))


def _is_admin(user: User) -> bool:
    return user.role in (UserRole.ADMIN, UserRole.SUPERVISOR)


def _side_response(visit) -> VisitPairSideResponse:
    return VisitPairSideResponse(
        visit_id=visit.id,
        status=visit.status,
        no_products=bool(visit.no_products),
        items_count=visit.items_count,
        visited_at=visit.visited_at,
    )


def _pair_response(par: consolidation.Pair) -> VisitPairResponse:
    """Par → a linha única da tela do administrador."""
    gondola = par.side(consolidation.GONDOLA)
    estoque = par.side(consolidation.ESTOQUE)
    # Cliente e promotor são os mesmos nos dois lados (é o que define o par),
    # então qualquer lado presente serve para nomear a linha.
    qualquer = gondola or estoque
    customer_id, promoter_id, dia = par.key

    return VisitPairResponse(
        id=f"{customer_id}|{promoter_id}|{dia}",
        customer_id=customer_id,
        customer_name=qualquer.customer_name,
        promoter_id=promoter_id,
        promoter_name=qualquer.promoter_name,
        day=dia,
        visited_at=par.moment,
        gondola=_side_response(gondola) if gondola else None,
        estoque=_side_response(estoque) if estoque else None,
        missing_side=par.missing,
        status=par.status,
    )


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

        anterior, entradas = await MerchandisingService._expiry_inputs(
            session, tenant_id, customer_id, [p for p, _ in products]
        )

        vazio = (None, None, None)
        linhas = []
        for p, position in products:
            entrada = entradas.get(p.id)
            linhas.append(CountProductResponse(
                id=p.id,
                name=p.name,
                image_url=p.image_url,
                position=position,
                package_size=p.package_size or Decimal(1),
                last_boxes=last.get(p.id, vazio)[0],
                last_units=last.get(p.id, vazio)[1],
                last_quantity=last.get(p.id, vazio)[2],
                expiry_shelf_life=p.arrival_shelf_life_days,
                expiry_previous_stock=(
                    _quantia(entrada.previous_stock) if entrada else None
                ),
                expiry_invoiced=_quantia(entrada.invoiced) if entrada else Decimal(0),
                expiry_gifted=_quantia(entrada.gifted) if entrada else Decimal(0),
                expiry_removed=_quantia(entrada.removed) if entrada else Decimal(0),
            ))

        return CountSheetResponse(
            customer_id=customer.id,
            customer_name=customer.name,
            visit_type=visit_type,
            expiry_previous_day=anterior,
            products=linhas,
        )

    @staticmethod
    async def _expiry_inputs(
        session: AsyncSession, tenant_id: UUID, customer_id: UUID, products: list,
    ) -> tuple[Optional[date], dict[UUID, _ExpiryInput]]:
        """Os ingredientes da conta de vencimento — a conta em si é do aparelho.

        O ciclo que decide a coleta termina NA CONTAGEM DE HOJE, e não na última
        que está no banco: o que precisa caber dentro de uma validade é o estoque
        que está na loja neste momento, com o promotor na frente dele. A ponta de
        cima do ciclo, portanto, ainda não existe quando esta resposta é montada
        — ela está sendo digitada.

        Daí a divisão: o servidor manda daqui o que só ele sabe (o estoque do
        último dia completo, o que as planilhas do ERP registraram desde então, o
        vencido já retirado) e o veredito é fechado em `lib/vencimento.js`, no fim
        da contagem, sem depender de rede. A regra é a de `expiry.py`.

        O `removed` é o que o servidor conhecia ao montar a folha: retirada
        registrada depois disso não entra neste ciclo. Ela desconta no seguinte,
        e o efeito de ficar de fora é uma venda um pouco maior — ou seja, menos
        alarde, nunca mais.
        """
        # Sem nenhum produto com validade na chegada cadastrada não há o que
        # calcular — e nem por que ir ao banco buscar a história inteira.
        if not any(p.arrival_shelf_life_days for p in products):
            return None, {}

        series, _, hoje = await MerchandisingService._stock_series(
            session, tenant_id, EXPIRY_WINDOW_DAYS, customer_id
        )

        # O último dia completo ANTES de hoje. O corte não é detalhe: numa folha
        # reaberta depois de os dois lados já terem subido, hoje seria o "dia
        # anterior" de si mesmo, e o ciclo daria zero dia.
        dias = sorted({
            dia
            for serie in series
            for dia, _, _, _ in serie.complete_days()
            if dia < hoje
        })
        if not dias:
            return None, {}

        anterior = date.fromisoformat(dias[-1])
        atual = date.fromisoformat(hoje)

        estoques = {
            serie.product_id: total
            for serie in series
            for dia, _, _, total in serie.complete_days()
            if dia == dias[-1]
        }
        faturado = await Repo.sum_deliveries_in_cycle(
            session, tenant_id, customer_id, anterior, atual, DeliveryKind.VENDA.value
        )
        brindes = await Repo.sum_deliveries_in_cycle(
            session, tenant_id, customer_id, anterior, atual, DeliveryKind.BRINDE.value
        )
        retirados = await Repo.sum_removals_in_cycle(
            session, tenant_id, customer_id, anterior, atual
        )

        return anterior, {
            product_id: _ExpiryInput(
                previous_stock=estoque,
                invoiced=faturado.get(product_id, 0.0),
                gifted=brindes.get(product_id, 0.0),
                removed=retirados.get(product_id, 0.0),
            )
            for product_id, estoque in estoques.items()
        }

    @staticmethod
    async def _cycle_sales(
        session: AsyncSession, tenant_id: UUID, customer_id: UUID,
    ) -> tuple[dict[UUID, expiry.Cycle], Optional[tuple[date, date]]]:
        """A venda de cada produto deste cliente no último ciclo, e as pontas
        do ciclo (contagem anterior, contagem atual).

        É a leitura que a coleta de vencimento e a sugestão de pedido dividem:
        a série de contagens, o recorte do que entrou e do que foi retirado
        dentro do ciclo, e a conta de `expiry.cycle_sale`.
        """
        series, _, _ = await MerchandisingService._stock_series(
            session, tenant_id, EXPIRY_WINDOW_DAYS, customer_id
        )

        # O ciclo é o mesmo para todos os produtos do cliente: ele nasce dos dias
        # em que as DUAS contagens chegaram, e isso é propriedade da visita, não
        # do produto. Basta achar a primeira série que tenha um.
        janela = next(
            (b for b in (expiry.cycle_bounds(serie) for serie in series) if b), None
        )
        if not janela:
            return {}, None

        anterior, atual = janela
        faturado = await Repo.sum_deliveries_in_cycle(
            session, tenant_id, customer_id, anterior, atual, DeliveryKind.VENDA.value
        )
        brindes = await Repo.sum_deliveries_in_cycle(
            session, tenant_id, customer_id, anterior, atual, DeliveryKind.BRINDE.value
        )
        retirados = await Repo.sum_removals_in_cycle(
            session, tenant_id, customer_id, anterior, atual
        )

        porta = lambda mapa: {  # noqa: E731
            (customer_id, product_id): total for product_id, total in mapa.items()
        }
        ciclos = expiry.cycle_sales(
            series, porta(faturado), porta(brindes), porta(retirados)
        )
        return {product_id: ciclo for (_, product_id), ciclo in ciclos.items()}, janela

    # ── Vendedor: fator de giro e sugestão de pedido ──────────────────────

    @staticmethod
    async def set_turnover_factor(
        session: AsyncSession, tenant_id: UUID, user: User, customer_id: UUID,
        product_id: UUID, factor: Decimal,
    ) -> None:
        """Grava o fator de um produto numa loja do vendedor."""
        await MerchandisingService._assert_can_access_customer(
            session, tenant_id, user, customer_id
        )
        # Só para garantir que o produto é deste tenant — 404 se não for.
        await ProductsService.get(session, tenant_id, product_id)
        await Repo.set_turnover_factor(session, tenant_id, customer_id, product_id, factor)

    @staticmethod
    async def order_suggestion(
        session: AsyncSession, tenant_id: UUID, user: User, customer_id: UUID,
    ) -> OrderSuggestionResponse:
        """O pedido sugerido para um cliente: todo produto com ciclo, em ordem
        alfabética — os de zero também, para o vendedor ver o que a loja ainda
        cobre e decidir se sobe o fator. Com as datas de validade que o
        promotor leu, quando leu.
        """
        await MerchandisingService._assert_can_access_customer(
            session, tenant_id, user, customer_id
        )
        customer = await CustomersService.get(session, tenant_id, customer_id)

        ciclos, janela = await MerchandisingService._cycle_sales(session, tenant_id, customer_id)
        ultima = janela[1] if janela else None

        hoje = date.fromisoformat(consolidation.local_day(datetime.now(timezone.utc)))
        semana = orders.week_start(hoje)
        vale = bool(ultima) and orders.is_fresh(ultima, hoje)

        itens = []
        if vale:
            catalogo = {
                p.id: p for p in await Repo.list_all_products(session, tenant_id)
            }
            fatores = await Repo.turnover_factors_for_customer(session, tenant_id, customer_id)
            # A mesma janela da série: coleta mais velha que isso não tem
            # contagem para se apoiar.
            validades = await Repo.latest_expiries_for_customer(
                session, tenant_id, customer_id,
                since=hoje - timedelta(days=EXPIRY_WINDOW_DAYS),
            )
            sugestoes = [
                orders.suggest(c, float(fatores.get(c.product_id, orders.DEFAULT_FACTOR)))
                for c in ciclos.values()
                # Produto inativado depois de contado fica de fora: não se pede
                # o que saiu de linha.
                if c.product_id in catalogo
            ]
            # Alfabética, e não por tamanho do pedido: é a ordem em que o
            # vendedor lança — e a lista não pula de lugar a cada fator mexido.
            sugestoes.sort(key=lambda s: catalogo[s.product_id].name)
            for s in sugestoes:
                produto = catalogo[s.product_id]
                caixa = produto.package_size if produto.package_size else None
                dia_validade, lotes = validades.get(s.product_id, (None, []))
                itens.append(OrderSuggestionItemResponse(
                    product_id=s.product_id,
                    product_name=produto.name,
                    image_url=produto.image_url,
                    package_size=caixa or Decimal(1),
                    cycle_from=s.cycle_from,
                    cycle_to=s.cycle_to,
                    cycle_days=s.cycle_days,
                    sold=Decimal(str(round(s.sold, 3))),
                    current_stock=Decimal(str(round(s.current_stock, 3))),
                    turnover_factor=fatores.get(s.product_id, orders.DEFAULT_FACTOR),
                    suggested_units=s.suggested,
                    suggested_boxes=(
                        Decimal(str(round(s.suggested / float(caixa), 1)))
                        if caixa and caixa > 1 and s.suggested else None
                    ),
                    expiry_collected_day=dia_validade,
                    expiries=[
                        ExpiryLotResponse(expires_at=vence, quantity=quantidade)
                        for vence, quantidade in lotes
                    ],
                ))

        return OrderSuggestionResponse(
            customer_id=customer.id,
            customer_name=customer.name,
            last_collection_day=ultima,
            week_start=semana,
            stale=bool(ultima) and not vale,
            items=itens,
        )

    @staticmethod
    async def order_suggestion_for_pdf(
        session: AsyncSession, tenant_id: UUID, user: User, customer_id: UUID,
    ):
        """A mesma sugestão da tela, com o cadastro do cliente junto.

        A folha em PDF vai para a mão do comprador da loja e precisa de razão
        social e CNPJ, que a `OrderSuggestionResponse` não carrega — ela é a
        resposta de uma tela onde o vendedor já sabe em que cliente está.

        A conta não se refaz aqui: quem a faz é `order_suggestion`, e ela já
        checa o acesso deste usuário a este cliente.
        """
        sugestao = await MerchandisingService.order_suggestion(
            session, tenant_id, user, customer_id
        )
        customer = await CustomersService.get(session, tenant_id, customer_id)
        return sugestao, customer

    # ── Planilha de faturamento ───────────────────────────────────────────

    @staticmethod
    async def import_invoices(
        session: AsyncSession, tenant_id: UUID, content: bytes, save: bool,
        kind: str = DeliveryKind.VENDA.value,
        file_name: str = "", user: Optional[User] = None,
    ) -> InvoiceImportResponse:
        """Lê uma das planilhas do ERP e grava as entradas de mercadoria.

        `save=False` é a prévia: lê, casa com o cadastro e relata, sem tocar no
        banco. É o modo em que a tela abre — anexar um arquivo errado não pode
        sujar a base antes de alguém olhar.

        Quando grava, deixa também o recibo (`InvoiceImport`): as linhas não
        sabem de que arquivo vieram, e é o recibo que permite à tela dizer
        "esta planilha já entrou" no dia seguinte.

        LINHA QUE NÃO CASA NÃO É ERRO, É TAREFA
        ---------------------------------------
        Produto ou cliente que a planilha traz e o cadastro não conhece sai na
        resposta com quanto ficou de fora. O administrador vincula o código e
        anexa de novo — a importação é idempotente pela chave da venda, então
        reanexar o mesmo arquivo não duplica o que já entrou.
        """
        # Fora do event loop: são segundos de CPU num arquivo grande, e com um
        # processo só a API inteira (a contagem do promotor, o login) ficaria
        # parada esperando a leitura acabar.
        try:
            lido = await asyncio.to_thread(invoices.parse, content, kind)
        except invoices.UnreadableWorkbook as erro:
            raise HTTPException(status_code=422, detail=str(erro))
        if lido.missing_columns:
            return InvoiceImportResponse(
                kind=kind, missing_columns=lido.missing_columns
            )

        produtos = await Repo.products_by_sku(session, tenant_id)
        clientes = await Repo.customers_by_document(session, tenant_id)

        # Chave natural → entrada. A mesma venda pode trazer o mesmo item em
        # duas linhas (dois lotes, por exemplo): elas somam numa entrada só,
        # porque a chave é única no banco e o que importa é quanto chegou.
        entradas: dict[tuple, ProductDelivery] = {}
        casadas = 0
        # código → (nome, linhas, quantidade) do que ficou de fora
        sem_produto: dict[str, list] = {}
        sem_cliente: dict[str, list] = {}
        # motivo → o mesmo, do que ENTROU (a planilha de brindes traz motivo)
        motivos: dict[str, list] = {}

        for linha in lido.rows:
            product_id = produtos.get(linha.product_code)
            customer_id = clientes.get(linha.customer_document)

            if product_id is None:
                falta = sem_produto.setdefault(
                    linha.product_code, [linha.product_name, 0, 0.0, None]
                )
                falta[1] += 1
                falta[2] += linha.quantity
            if customer_id is None:
                falta = sem_cliente.setdefault(
                    linha.customer_code,
                    [linha.customer_name, 0, 0.0, linha.customer_document],
                )
                falta[1] += 1
                falta[2] += linha.quantity
            if product_id is None or customer_id is None:
                continue

            if linha.reason:
                conta = motivos.setdefault(linha.reason, [linha.reason, 0, 0.0, None])
                conta[1] += 1
                conta[2] += linha.quantity

            casadas += 1
            chave = (linha.company, linha.sale_number, product_id)
            repetida = entradas.get(chave)
            if repetida is not None:
                repetida.quantity += Decimal(str(linha.quantity))
                continue
            entradas[chave] = ProductDelivery(
                id=uuid4(),
                tenant_id=tenant_id,
                kind=kind,
                customer_id=customer_id,
                product_id=product_id,
                issued_on=linha.issued_on,
                quantity=Decimal(str(linha.quantity)),
                company=linha.company,
                sale_number=linha.sale_number,
                invoice=linha.invoice,
                cfop=linha.cfop,
            )

        quantidade = Decimal(
            str(round(sum(float(e.quantity) for e in entradas.values()), 3))
        )

        if save:
            await Repo.replace_deliveries(session, tenant_id, list(entradas.values()))
            await Repo.add_invoice_import(
                session,
                InvoiceImport(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    user_id=user.id if user else None,
                    kind=kind,
                    file_name=(file_name or "planilha.xlsx")[:255],
                    first_day=lido.first_day,
                    last_day=lido.last_day,
                    total_lines=lido.total,
                    matched_lines=casadas,
                    matched_quantity=quantidade,
                ),
            )

        desconhecidos = lambda faltas: sorted(  # noqa: E731
            (
                UnknownKeyResponse(
                    code=codigo, name=nome or "—", document=documento,
                    lines=linhas, quantity=Decimal(str(round(quanto, 3))),
                )
                for codigo, (nome, linhas, quanto, documento) in faltas.items()
            ),
            key=lambda u: -u.lines,
        )

        return InvoiceImportResponse(
            kind=kind,
            total_lines=lido.total,
            usable_lines=len(lido.rows),
            ignored_cfop=lido.ignored_cfop,
            ignored_incomplete=lido.ignored_incomplete,
            ignored_weight=lido.ignored_weight,
            first_day=lido.first_day,
            last_day=lido.last_day,
            matched_lines=casadas,
            matched_quantity=quantidade,
            saved=save,
            unknown_customers=desconhecidos(sem_cliente),
            unknown_products=desconhecidos(sem_produto),
            by_reason=desconhecidos(motivos),
        )

    @staticmethod
    async def list_invoice_imports(
        session: AsyncSession, tenant_id: UUID, kind: str,
    ) -> list[InvoiceImportRecordResponse]:
        """As planilhas desta origem que já entraram, da mais recente para a
        mais antiga."""
        return [
            InvoiceImportRecordResponse(
                id=recibo.id,
                kind=recibo.kind,
                file_name=recibo.file_name,
                imported_at=recibo.created_at,
                imported_by=nome,
                first_day=recibo.first_day,
                last_day=recibo.last_day,
                total_lines=recibo.total_lines,
                matched_lines=recibo.matched_lines,
                matched_quantity=recibo.matched_quantity,
            )
            for recibo, nome in await Repo.list_invoice_imports(session, tenant_id, kind)
        ]

    # ── Vencido retirado da loja ──────────────────────────────────────────

    @staticmethod
    async def register_removal(
        session: AsyncSession, tenant_id: UUID, user: User,
        payload: ProductRemovalCreate,
    ) -> list[ProductRemovalResponse]:
        """Grava o que o promotor retirou por vencimento neste cliente.

        Substitui pelo `client_uuid`, como as contagens: o reenvio da fila
        offline atualiza em vez de duplicar. Lista vazia apaga a retirada — é
        assim que o promotor desfaz um registro feito por engano.
        """
        await MerchandisingService._assert_can_access_customer(
            session, tenant_id, user, payload.customer_id
        )

        quando = payload.removed_at or datetime.now(timezone.utc)
        dia = date.fromisoformat(consolidation.local_day(quando))

        sizes = await Repo.package_sizes(
            session, tenant_id, [item.product_id for item in payload.items]
        )
        linhas = [
            ProductRemoval(
                id=uuid4(),
                tenant_id=tenant_id,
                customer_id=payload.customer_id,
                product_id=item.product_id,
                promoter_id=user.id,
                removed_day=dia,
                expires_at=item.expires_at,
                boxes=item.boxes,
                units=item.units,
                quantity=item.boxes * sizes.get(item.product_id, Decimal(1)) + item.units,
                client_uuid=payload.client_uuid,
            )
            for item in payload.items
        ]

        await Repo.replace_removals(
            session, tenant_id, payload.client_uuid or str(uuid4()), linhas
        )
        return await MerchandisingService.list_removals(
            session, tenant_id, user, payload.customer_id, dia
        )

    @staticmethod
    async def list_removals(
        session: AsyncSession, tenant_id: UUID, user: User, customer_id: UUID,
        day: date,
    ) -> list[ProductRemovalResponse]:
        await MerchandisingService._assert_can_access_customer(
            session, tenant_id, user, customer_id
        )
        return [
            ProductRemovalResponse(
                id=linha.id, customer_id=linha.customer_id,
                product_id=linha.product_id, product_name=nome,
                removed_day=linha.removed_day, expires_at=linha.expires_at,
                boxes=linha.boxes, units=linha.units, quantity=linha.quantity,
            )
            for linha, nome in await Repo.list_removals_by_day(
                session, tenant_id, customer_id, day
            )
        ]

    @staticmethod
    async def visit_sheet(
        session: AsyncSession, tenant_id: UUID, user: User, visit_id: UUID
    ) -> CountSheetResponse:
        """Folha de correção de um envio: os mesmos painéis da contagem, mas só
        com os produtos que o promotor de fato contou, já preenchidos com o que
        ele digitou. Quem errou um número volta para corrigir aquele número, não
        para refazer a contagem inteira.
        """
        visit, customer_name = await MerchandisingService._load_editable_visit(
            session, tenant_id, user, visit_id
        )

        # Mesma ordem da tela de contagem: o promotor reencontra os produtos na
        # sequência em que os contou.
        mix = await Repo.list_mix_product_ids(session, tenant_id, visit.customer_id)
        position_of = {product_id: index for index, product_id in enumerate(mix)}

        rows = sorted(
            # Produto apagado do catálogo não tem painel para desenhar
            ((item, p) for item, p in await Repo.list_items(session, visit.id) if p),
            key=lambda row: (position_of.get(row[1].id, len(mix)), row[1].name),
        )

        return CountSheetResponse(
            customer_id=visit.customer_id,
            customer_name=customer_name or "",
            visit_type=visit.visit_type,
            visit_id=visit.id,
            status=visit.status,
            no_products=visit.no_products,
            products=[
                CountProductResponse(
                    id=product.id,
                    name=product.name,
                    image_url=product.image_url,
                    position=position_of.get(product.id, 0),
                    package_size=product.package_size or Decimal(1),
                    boxes=item.boxes,
                    units=item.units,
                )
                for item, product in rows
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
        if payload.submit:
            MerchandisingService._assert_not_empty(payload.no_products, payload.items)

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
                no_products=payload.no_products,
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
            visit.no_products = payload.no_products
            visit.visited_at = payload.visited_at or visit.visited_at or now

        if payload.submit:
            visit.status = StockVisitStatus.SUBMITTED.value
            visit.submitted_at = now

        visit = await Repo.save_visit(session, visit)

        await Repo.replace_items(
            session, visit.id,
            await MerchandisingService._build_items(
                session, tenant_id, visit.id,
                # "Não tem produtos aqui" é a contagem inteira: o que estivesse
                # digitado antes de marcar o quadrado não vai junto.
                [] if payload.no_products else payload.items,
            ),
        )

        # As datas coletadas NÃO são apagadas pelo "não tem produtos aqui": elas
        # descrevem o par (gôndola + estoque), e o lado vazio é justamente o que
        # joga todo o estoque para o outro lado.
        await Repo.replace_expiries(
            session, visit.id,
            await MerchandisingService._build_expiries(
                session, tenant_id, visit, payload.expiries
            ),
        )

        return await MerchandisingService.get_visit(session, tenant_id, visit.id)

    @staticmethod
    async def update_visit(
        session: AsyncSession, tenant_id: UUID, user: User, visit_id: UUID,
        payload: StockVisitUpdate,
    ) -> StockVisitResponse:
        """Correção de uma contagem já enviada: troca as quantidades dos itens.

        Não mexe no status — a contagem continua enviada, só com outros números.
        """
        visit, _ = await MerchandisingService._load_editable_visit(
            session, tenant_id, user, visit_id
        )
        MerchandisingService._assert_not_empty(payload.no_products, payload.items)
        visit.no_products = payload.no_products

        await Repo.replace_items(
            session, visit.id,
            await MerchandisingService._build_items(
                session, tenant_id, visit.id,
                [] if payload.no_products else payload.items,
            ),
        )

        # `updated_at` só muda sozinho quando a própria linha da visita muda, e
        # aqui quem mudou foram os itens. Marcar na mão é o que registra que
        # esta contagem foi corrigida depois de enviada.
        visit.updated_at = datetime.now(timezone.utc)
        await Repo.save_visit(session, visit)

        return await MerchandisingService.get_visit(session, tenant_id, visit.id)

    @staticmethod
    async def _build_items(
        session: AsyncSession, tenant_id: UUID, visit_id: UUID,
        inputs: list[StockVisitItemInput],
    ) -> list[StockVisitItem]:
        """Converte o que o promotor digitou (caixas + unidades) em linhas.

        A conversão para unidades é feita aqui, na hora de gravar, e não na
        planilha: assim o total já vale para o detalhe da visita e para a
        "contagem anterior" da próxima visita, sem repetir a regra em cada
        leitura.
        """
        sizes = await Repo.package_sizes(
            session, tenant_id, [item.product_id for item in inputs]
        )
        return [
            StockVisitItem(
                id=uuid4(),
                tenant_id=tenant_id,
                visit_id=visit_id,
                product_id=item.product_id,
                boxes=item.boxes,
                units=item.units,
                quantity=item.boxes * sizes.get(item.product_id, Decimal(1)) + item.units,
                unit_type=UnitType.UNIDADE.value,
            )
            for item in inputs
        ]

    @staticmethod
    async def _build_expiries(
        session: AsyncSession, tenant_id: UUID, visit: StockVisit,
        inputs: list[ProductExpiryInput],
    ) -> list[ProductExpiry]:
        """As datas digitadas pelo promotor → linhas da coleta.

        Mesma conversão da contagem (caixas viram unidades pelo `package_size` de
        hoje), pelo mesmo motivo: é na unidade convertida que a soma das datas
        fecha com o total contado.

        `collected_day` é o dia LOCAL da visita, e não o instante UTC: é por ele
        que a coleta se encaixa no meio da história do produto, no mesmo dia em
        que o par se formou.
        """
        if not inputs:
            return []

        sizes = await Repo.package_sizes(
            session, tenant_id, [linha.product_id for linha in inputs]
        )
        dia = consolidation.local_day(visit.visited_at or visit.submitted_at)

        return [
            ProductExpiry(
                id=uuid4(),
                tenant_id=tenant_id,
                customer_id=visit.customer_id,
                product_id=linha.product_id,
                promoter_id=visit.promoter_id,
                visit_id=visit.id,
                collected_day=date.fromisoformat(dia),
                expires_at=linha.expires_at,
                boxes=linha.boxes,
                units=linha.units,
                quantity=(
                    linha.boxes * sizes.get(linha.product_id, Decimal(1)) + linha.units
                ),
            )
            for linha in inputs
        ]

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
                id=item.id, product_id=item.product_id,
                product_name=product.name if product else None,
                boxes=item.boxes, units=item.units,
                quantity=item.quantity, unit_type=item.unit_type,
                expires_at=item.expires_at, notes=item.notes,
            )
            for item, product in item_rows
        ]

        coletadas = (await Repo.list_expiries_for_visits(session, [visit.id])).get(
            visit.id, []
        )
        expiries = [
            ProductExpiryResponse(
                id=linha.id, product_id=linha.product_id, product_name=nome,
                expires_at=linha.expires_at, boxes=linha.boxes,
                units=linha.units, quantity=linha.quantity,
            )
            for linha, nome in coletadas
        ]

        par = await MerchandisingService._pair_of(session, tenant_id, visit)

        return StockVisitResponse(
            id=visit.id, tenant_id=visit.tenant_id, customer_id=visit.customer_id,
            customer_name=customer_name,
            promoter_id=visit.promoter_id, promoter_name=promoter_name,
            visit_type=visit.visit_type, status=visit.status,
            no_products=visit.no_products,
            missing_side=par.missing if par else None,
            visited_at=visit.visited_at,
            submitted_at=visit.submitted_at, exported_at=visit.exported_at,
            notes=visit.notes, client_uuid=visit.client_uuid,
            items=items, items_count=len(items), expiries=expiries,
            created_at=visit.created_at, updated_at=visit.updated_at,
        )

    @staticmethod
    async def list_visits(
        session: AsyncSession, tenant_id: UUID, **filters
    ) -> tuple[list[StockVisitResponse], int]:
        rows, total = await Repo.list_visits(session, tenant_id, **filters)
        faltando = await MerchandisingService._missing_sides(
            session, tenant_id, [v for v, _, _, _ in rows]
        )
        visits = [
            StockVisitResponse(
                id=v.id, tenant_id=v.tenant_id, customer_id=v.customer_id,
                customer_name=c_name,
                promoter_id=v.promoter_id, promoter_name=p_name,
                visit_type=v.visit_type, status=v.status,
                no_products=v.no_products,
                missing_side=faltando.get(v.id),
                visited_at=v.visited_at,
                submitted_at=v.submitted_at, exported_at=v.exported_at,
                notes=v.notes, client_uuid=v.client_uuid,
                items=[], items_count=count,
                created_at=v.created_at, updated_at=v.updated_at,
            )
            for v, c_name, p_name, count in rows
        ]
        return visits, total

    @staticmethod
    async def list_visit_pairs(
        session: AsyncSession, tenant_id: UUID,
        promoter_id: Optional[UUID] = None, customer_id: Optional[UUID] = None,
        status: Optional[str] = None,
        date_from: Optional[datetime] = None, date_to: Optional[datetime] = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[VisitPairResponse], int]:
        """A lista do administrador: uma linha por cliente/promotor/dia.

        O promotor conta gôndola e estoque separadamente — são duas visitas no
        banco, e continuam sendo. Mas quem administra recebe uma planilha só, com
        os dois lugares lado a lado, e via duas linhas na tela para a mesma ida à
        loja. Agora a tela conta a mesma história que a planilha.

        A paginação é feita aqui, sobre os pares, e não no SQL sobre as visitas.
        Não é preguiça: o par se forma pelo DIA LOCAL, que só existe em Python
        (`consolidation.local_day`), e um LIMIT aplicado às visitas partiria pares
        ao meio — a gôndola no fim de uma página, o estoque no começo da outra,
        as duas metades marcadas como incompletas.

        Como na planilha, a janela consultada é um dia maior de cada lado e o
        recorte final é por dia local: é isso que faz "até 19/08" incluir a
        contagem das 21h do dia 19, que em UTC já é dia 20.
        """
        visitas = await Repo.list_visits_for_pairing(
            session, tenant_id,
            customer_ids=[customer_id] if customer_id else None,
            promoter_ids=[promoter_id] if promoter_id else None,
            date_from=date_from - timedelta(days=1) if date_from else None,
            date_to=date_to + timedelta(days=1) if date_to else None,
        )

        primeiro, ultimo = consolidation.day_bounds(date_from, date_to)
        pares = [
            par for par in consolidation.group_visits(visitas).values()
            if consolidation.within_days(par, primeiro, ultimo)
            and (not status or par.status == status)
        ]

        pagina = consolidation.sort_recent_first(pares)[offset : offset + limit]
        return [_pair_response(par) for par in pagina], len(pares)

    # ── Evolução do estoque do cliente ────────────────────────────────────

    @staticmethod
    async def _stock_series(
        session: AsyncSession, tenant_id: UUID, days: int,
        customer_id: Optional[UUID] = None,
    ) -> tuple[list[evolution.Series], str, str]:
        """As contagens da janela, já viradas em história por produto.

        Duas leituras e nenhum SQL novo: as visitas saem da mesma consulta que
        forma o par da planilha, e os itens da mesma que a alimenta — inclusive
        o `package_size` de hoje, que é o que mantém a série inteira na mesma
        unidade mesmo se o cadastro do produto tiver sido corrigido no meio.
        """
        hoje = consolidation.local_day(datetime.now(timezone.utc))
        primeiro = (date.fromisoformat(hoje) - timedelta(days=days - 1)).isoformat()

        desde, _ = consolidation.day_window(primeiro)
        _, ate = consolidation.day_window(hoje)

        visitas = await Repo.list_visits_for_pairing(
            session, tenant_id,
            customer_ids=[customer_id] if customer_id else None,
            date_from=desde, date_to=ate,
        )
        itens = await Repo.list_export_items(
            session, tenant_id, [v.id for v in visitas]
        )
        return evolution.build_series(visitas, itens), primeiro, hoje

    @staticmethod
    async def stock_insights(
        session: AsyncSession, tenant_id: UUID, days: int = 90, limit: int = 20,
    ) -> StockInsightsResponse:
        """O que mudou no estoque dos clientes na janela pedida."""
        series, primeiro, hoje = await MerchandisingService._stock_series(
            session, tenant_id, days
        )

        parados = evolution.stalled(series)
        sumiram, voltaram = evolution.moved(series)
        faltas = evolution.shelf_gap(series)

        return StockInsightsResponse(
            window_days=days,
            from_day=primeiro,
            to_day=hoje,
            customers=[
                StockCustomerResponse(**asdict(c)) for c in evolution.customers(series)
            ],
            stalled=[StalledProductResponse(**asdict(p)) for p in parados[:limit]],
            gone=[MovedProductResponse(**asdict(m)) for m in sumiram[:limit]],
            returned=[MovedProductResponse(**asdict(m)) for m in voltaram[:limit]],
            shelf_gap=[ShelfGapResponse(**asdict(f)) for f in faltas[:limit]],
            stalled_total=len(parados),
            gone_total=len(sumiram),
            returned_total=len(voltaram),
            shelf_gap_total=len(faltas),
        )

    @staticmethod
    async def stock_history(
        session: AsyncSession, tenant_id: UUID, customer_id: UUID,
        product_id: Optional[UUID] = None, days: int = 90,
    ) -> StockHistoryResponse:
        """A linha do tempo de um cliente — de um produto, ou da loja inteira."""
        series, _, _ = await MerchandisingService._stock_series(
            session, tenant_id, days, customer_id=customer_id
        )
        pontos = evolution.history(series, customer_id, product_id)

        # Nome do produto só existe se ele foi contado ali dentro da janela.
        do_produto = next(
            (s for s in series if product_id and s.product_id == product_id), None
        )
        return StockHistoryResponse(
            customer_id=customer_id,
            customer_name=next((s.customer_name for s in series), None),
            product_id=product_id,
            product_name=do_produto.product_name if do_produto else None,
            window_days=days,
            points=[StockPointResponse(**asdict(p)) for p in pontos],
        )

    # ── O par gôndola + estoque ───────────────────────────────────────────

    @staticmethod
    async def _pair_of(
        session: AsyncSession, tenant_id: UUID, visit
    ) -> Optional[consolidation.Pair]:
        """O par a que esta contagem pertence — ela e a do outro lugar, no mesmo
        cliente, mesmo promotor, mesmo dia.

        Devolve None para rascunho: contagem que o promotor ainda não fechou não
        entra em par nenhum, e dizer que "falta o estoque" seria mentira.
        """
        if visit.status == StockVisitStatus.DRAFT.value:
            return None

        dia = consolidation.local_day(visit.visited_at)
        inicio, fim = consolidation.day_window(dia) if dia else (None, None)

        candidatas = await Repo.list_visits_for_pairing(
            session, tenant_id,
            customer_ids=[visit.customer_id], promoter_ids=[visit.promoter_id],
            date_from=inicio, date_to=fim,
        )
        return consolidation.group_visits(candidatas).get(consolidation.group_key(visit))

    @staticmethod
    async def _missing_sides(
        session: AsyncSession, tenant_id: UUID, visits: list
    ) -> dict[UUID, Optional[str]]:
        """{visit_id: lado que falta} para uma página inteira da lista.

        Uma consulta só, limitada aos clientes e promotores que aparecem na
        página e à janela de dias que ela cobre — e não uma por linha.
        """
        if not visits:
            return {}

        momentos = [v.visited_at for v in visits if v.visited_at]
        inicio = min(momentos) - timedelta(days=1) if momentos else None
        fim = max(momentos) + timedelta(days=1) if momentos else None

        candidatas = await Repo.list_visits_for_pairing(
            session, tenant_id,
            customer_ids=list({v.customer_id for v in visits}),
            promoter_ids=list({v.promoter_id for v in visits}),
            date_from=inicio, date_to=fim,
        )
        return consolidation.missing_side_by_visit(candidatas)

    # ── Planilha consolidada ──────────────────────────────────────────────

    @staticmethod
    async def consolidated_export(
        session: AsyncSession, tenant_id: UUID,
        promoter_id: Optional[UUID] = None, customer_id: Optional[UUID] = None,
        date_from: Optional[datetime] = None, date_to: Optional[datetime] = None,
    ) -> tuple[list, list[UUID]]:
        """Linhas da planilha do período + as contagens que entraram nela.

        A janela consultada é um dia maior de cada lado do filtro, e o recorte
        final é feito por DIA LOCAL: sem isso, "de 19 a 19/08" traria a contagem
        das 21h do dia 18 (que em UTC já é dia 19) e perderia a das 21h do dia
        19 — e, pior, poderia cortar um par no meio.
        """
        visitas = await Repo.list_visits_for_pairing(
            session, tenant_id,
            customer_ids=[customer_id] if customer_id else None,
            promoter_ids=[promoter_id] if promoter_id else None,
            date_from=date_from - timedelta(days=1) if date_from else None,
            date_to=date_to + timedelta(days=1) if date_to else None,
        )

        primeiro, ultimo = consolidation.day_bounds(date_from, date_to)
        pares = [
            par for par in consolidation.group_visits(visitas).values()
            if par.complete and consolidation.within_days(par, primeiro, ultimo)
        ]

        itens = await Repo.list_export_items(
            session, tenant_id, [vid for par in pares for vid in par.visit_ids]
        )
        return consolidation.build_rows(pares, itens)

    @staticmethod
    async def consolidated_export_for_visit(
        session: AsyncSession, tenant_id: UUID, visit_id: UUID
    ) -> tuple[list, list[UUID]]:
        """A planilha de uma contagem é a planilha do par dela — nunca de um
        lado só. Sem o par, o administrador recebe o motivo em vez do arquivo."""
        row = await Repo.get_visit_detail(session, tenant_id, visit_id)
        if not row:
            raise HTTPException(status_code=404, detail="Contagem não encontrada")

        visit = row[0]
        par = await MerchandisingService._pair_of(session, tenant_id, visit)

        if par is None or not par.complete:
            faltando = par.missing if par else visit.visit_type
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "A contagem de "
                    f"{consolidation.SIDE_LABEL.get(faltando, faltando)} deste "
                    "cliente ainda não chegou. A planilha só sai com as duas."
                ),
            )

        itens = await Repo.list_export_items(session, tenant_id, par.visit_ids)
        return consolidation.build_rows([par], itens)

    # ── Guarda de acesso ──────────────────────────────────────────────────

    @staticmethod
    def _assert_not_empty(no_products: bool, items: list) -> None:
        """Contagem fechada tem que dizer alguma coisa: ou os produtos que o
        promotor encontrou, ou o quadrado de que ali não há produto nenhum.

        Uma contagem vazia sem esse quadrado fecharia o par e sairia na planilha
        como se o cliente não tivesse mix — indistinguível de um engano.
        """
        if not no_products and not items:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Contagem vazia: preencha ao menos um produto ou marque "
                    "que não há produtos neste lugar."
                ),
            )


    @staticmethod
    async def _load_editable_visit(
        session: AsyncSession, tenant_id: UUID, user: User, visit_id: UUID
    ) -> tuple[StockVisit, Optional[str]]:
        """Visita que este usuário ainda pode alterar — ou o erro que diz por quê.

        Depois de exportada a contagem já virou planilha na mão do administrador:
        mudar o número aqui faria o app discordar do que ele baixou.
        """
        row = await Repo.get_visit_detail(session, tenant_id, visit_id)
        if not row:
            raise HTTPException(status_code=404, detail="Contagem não encontrada")

        visit, customer_name, _ = row
        if visit.promoter_id != user.id and not _is_admin(user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Esta contagem pertence a outro promotor.",
            )
        if visit.status == StockVisitStatus.EXPORTED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Esta contagem já foi processada pelo administrador e não pode mais ser alterada.",
            )
        return visit, customer_name

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
