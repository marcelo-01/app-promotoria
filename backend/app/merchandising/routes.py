import asyncio
import time
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import (
    APIRouter, Depends, HTTPException, Query, Request, status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import require_roles
from app.infrastructure.persistence.models.delivery import DeliveryKind
from app.infrastructure.persistence.models.stock_visit import VisitType
from app.infrastructure.persistence.session import get_db_session
from app.merchandising import erp_sync, excel, pdf
from app.merchandising.repository import MerchandisingRepository as Repo
from app.merchandising.schemas import (
    AssignmentUpdate, CountSheetResponse, CustomerMixUpdate, ErpSyncResponse,
    InvoiceImportRecordResponse,
    OrderSuggestionResponse, ProductRemovalCreate, ProductRemovalResponse,
    PromoterCustomerResponse, StockHistoryResponse, StockInsightsResponse,
    StockVisitCreate, StockVisitListResponse, StockVisitResponse, StockVisitUpdate,
    TurnoverFactorUpdate, VisitPairListResponse,
)
from app.merchandising.service import MerchandisingService

router = APIRouter(prefix="/merchandising", tags=["merchandising"])

_ADMIN = ("admin", "supervisor")
_FIELD = ("promoter", "admin", "supervisor")
# O vendedor lê o que o promotor contou, mas não conta: as rotas de contagem
# continuam só em `_FIELD`.
_SELLER = ("seller", "admin", "supervisor")


def _validate_visit_type(value: str) -> str:
    try:
        return VisitType(value).value
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Tipo de contagem inválido. Use gondola ou estoque."
        )


# ─── Promotor ─────────────────────────────────────────────────────────────────

@router.get("/my-customers", response_model=list[PromoterCustomerResponse])
async def list_my_customers(
    search: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_FIELD, "seller")),
):
    """Os clientes de quem chamou — promotor ou vendedor, o vínculo é o mesmo."""
    return await MerchandisingService.list_my_customers(
        session, context["tenant_id"], context["user"], search
    )


@router.get(
    "/customers/{customer_id}/count-sheet/{visit_type}",
    response_model=CountSheetResponse,
)
async def get_count_sheet(
    customer_id: UUID,
    visit_type: str,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_FIELD)),
):
    """Folha de contagem de um cliente: gôndola ou estoque."""
    return await MerchandisingService.count_sheet(
        session, context["tenant_id"], context["user"],
        customer_id, _validate_visit_type(visit_type),
    )


@router.post("/visits", response_model=StockVisitResponse, status_code=status.HTTP_201_CREATED)
async def upsert_visit(
    payload: StockVisitCreate,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_FIELD)),
):
    """Cria ou atualiza uma contagem. Idempotente via `client_uuid`."""
    return await MerchandisingService.upsert_visit(
        session, context["tenant_id"], context["user"], payload
    )


@router.get("/visits/{visit_id}/count-sheet", response_model=CountSheetResponse)
async def get_visit_sheet(
    visit_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_FIELD)),
):
    """Folha de correção: só os produtos contados naquele envio, preenchidos."""
    return await MerchandisingService.visit_sheet(
        session, context["tenant_id"], context["user"], visit_id
    )


@router.put("/visits/{visit_id}", response_model=StockVisitResponse)
async def update_visit(
    visit_id: UUID,
    payload: StockVisitUpdate,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_FIELD)),
):
    """Corrige as quantidades de uma contagem já enviada."""
    return await MerchandisingService.update_visit(
        session, context["tenant_id"], context["user"], visit_id, payload
    )


@router.post("/visits/{visit_id}/submit", response_model=StockVisitResponse)
async def submit_visit(
    visit_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_FIELD)),
):
    return await MerchandisingService.submit_visit(
        session, context["tenant_id"], context["user"], visit_id
    )


# IMPORTANTE: declarada antes de `/visits/{visit_id}`, senão "mine" seria
# interpretado como UUID e a rota devolveria 422.
@router.get("/visits/mine", response_model=StockVisitListResponse)
async def list_my_visits(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_FIELD)),
):
    items, total = await MerchandisingService.list_visits(
        session, context["tenant_id"],
        promoter_id=context["user"].id, status=status_filter,
        limit=limit, offset=offset,
    )
    return StockVisitListResponse(items=items, total=total, limit=limit, offset=offset)


# ─── Administrador: evolução do estoque ───────────────────────────────────────


@router.get("/stock-insights", response_model=StockInsightsResponse)
async def get_stock_insights(
    days: int = Query(90, ge=7, le=730),
    limit: int = Query(20, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    """O que mudou no estoque dos clientes: parados, sumidos, voltados, e
    gôndola vazia com saldo no depósito.

    Tudo é variação ENTRE CONTAGENS, nunca venda — o app não conhece entregas.
    As comparações usam só os dias com gôndola e estoque contados, pela mesma
    razão da planilha: meia contagem faria todo produto guardado no depósito
    parecer que sumiu.
    """
    return await MerchandisingService.stock_insights(
        session, context["tenant_id"], days=days, limit=limit
    )


@router.get("/stock-history", response_model=StockHistoryResponse)
async def get_stock_history(
    customer_id: UUID,
    product_id: Optional[UUID] = None,
    days: int = Query(90, ge=7, le=730),
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    """A linha do tempo de um cliente — da loja inteira, ou de um produto.

    Um ponto por contagem, na data em que ela foi feita. Dia sem contagem não
    vira ponto: o espaçamento irregular entre eles é a informação.
    """
    return await MerchandisingService.stock_history(
        session, context["tenant_id"], customer_id, product_id=product_id, days=days
    )


# ─── Administrador: visitas e planilhas ───────────────────────────────────────

@router.get("/visit-pairs", response_model=VisitPairListResponse)
async def list_visit_pairs(
    promoter_id: Optional[UUID] = None,
    customer_id: Optional[UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    """A ida do promotor à loja, numa linha só: gôndola e estoque lado a lado.

    Sem filtro por tipo de contagem, pelo mesmo motivo da planilha — a linha é
    sempre dos dois lugares. Filtrar por um lado só devolveria meias visitas,
    que é justamente o que esta tela deixou de mostrar.
    """
    items, total = await MerchandisingService.list_visit_pairs(
        session, context["tenant_id"],
        promoter_id=promoter_id, customer_id=customer_id, status=status_filter,
        date_from=date_from, date_to=date_to,
        limit=limit, offset=offset,
    )
    return VisitPairListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/visits/{visit_id}/export.xlsx")
async def export_visit(
    visit_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    """Planilha de uma contagem — ou seja, do par dela: a gôndola e o estoque
    daquele cliente naquele dia, juntos. Sem o par, devolve 409 com o motivo."""
    rows, visit_ids = await MerchandisingService.consolidated_export_for_visit(
        session, context["tenant_id"], visit_id
    )
    buf = excel.build_workbook(rows)
    await Repo.mark_exported(
        session, context["tenant_id"], visit_ids, datetime.now(timezone.utc)
    )
    return excel.xlsx_response(buf, excel.default_filename("contagem"))


@router.get("/visits/{visit_id}", response_model=StockVisitResponse)
async def get_visit(
    visit_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_FIELD)),
):
    return await MerchandisingService.get_visit(session, context["tenant_id"], visit_id)


@router.get("/exports.xlsx")
async def export_consolidated(
    promoter_id: Optional[UUID] = None,
    customer_id: Optional[UUID] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    """Planilha do período: uma linha por produto, gôndola e estoque lado a lado.

    Sem filtro por tipo de contagem — a planilha é sempre dos dois. Só entram os
    clientes cujas duas contagens do dia chegaram.
    """
    rows, visit_ids = await MerchandisingService.consolidated_export(
        session, context["tenant_id"],
        promoter_id=promoter_id, customer_id=customer_id,
        date_from=date_from, date_to=date_to,
    )
    if not rows:
        # Planilha vazia não diz o que houve; esta mensagem diz.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Nenhuma contagem completa neste período. A planilha só inclui "
                "clientes com as duas contagens do dia — gôndola e estoque."
            ),
        )

    buf = excel.build_workbook(rows, sheet_title="Consolidado")
    await Repo.mark_exported(
        session, context["tenant_id"], visit_ids, datetime.now(timezone.utc)
    )
    return excel.xlsx_response(buf, excel.default_filename("estoque_consolidado"))


# ─── Administrador: vínculos e mix ────────────────────────────────────────────

@router.get("/assignments/{promoter_id}", response_model=list[UUID])
async def get_assignments(
    promoter_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    return await Repo.list_assigned_customer_ids(session, context["tenant_id"], promoter_id)


@router.put("/assignments/{promoter_id}", status_code=204)
async def set_assignments(
    promoter_id: UUID,
    payload: AssignmentUpdate,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    await Repo.replace_assignments(
        session, context["tenant_id"], promoter_id, payload.customer_ids
    )


@router.get("/customers/{customer_id}/mix", response_model=list[UUID])
async def get_customer_mix(
    customer_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    """Simétrico ao GET de assignments — a tela de mix precisa ler o estado atual."""
    return await Repo.list_mix_product_ids(session, context["tenant_id"], customer_id)


@router.put("/customers/{customer_id}/mix", status_code=204)
async def set_customer_mix(
    customer_id: UUID,
    payload: CustomerMixUpdate,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    await Repo.replace_mix(session, context["tenant_id"], customer_id, payload.product_ids)


# ─── Vencido retirado da loja (promotor) ──────────────────────────────────────

@router.post("/removals", response_model=list[ProductRemovalResponse])
async def register_removal(
    payload: ProductRemovalCreate,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_FIELD)),
):
    """Registra o vencido que o promotor tirou da gôndola.

    Idempotente pelo `client_uuid`, como as contagens: a fila offline pode
    reenviar a mesma retirada quantas vezes for preciso.
    """
    return await MerchandisingService.register_removal(
        session, context["tenant_id"], context["user"], payload
    )


@router.get("/customers/{customer_id}/removals", response_model=list[ProductRemovalResponse])
async def list_removals(
    customer_id: UUID,
    day: Optional[date] = Query(default=None, description="Dia local; padrão, hoje"),
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_FIELD)),
):
    from app.merchandising import consolidation

    quando = day or date.fromisoformat(
        consolidation.local_day(datetime.now(timezone.utc))
    )
    return await MerchandisingService.list_removals(
        session, context["tenant_id"], context["user"], customer_id, quando
    )


# ─── Vendedor: fator de giro e sugestão de pedido ─────────────────────────────

@router.get(
    "/customers/{customer_id}/order-suggestion", response_model=OrderSuggestionResponse
)
async def get_order_suggestion(
    customer_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_SELLER)),
):
    """O pedido sugerido para o cliente: `venda × fator − estoque atual` de cada
    produto com ciclo, do maior pedido para o menor (os de zero no fim), e a
    data da coleta de onde a conta saiu.

    Coleta anterior ao domingo mais recente devolve a lista vazia com `stale`
    ligado — a sugestão da semana passada não vale mais (ver `orders.py`).
    """
    return await MerchandisingService.order_suggestion(
        session, context["tenant_id"], context["user"], customer_id
    )


@router.get("/customers/{customer_id}/order-suggestion.pdf")
async def export_order_suggestion(
    customer_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_SELLER)),
):
    """A folha do pedido em PDF, para o vendedor entregar ao comprador da loja.

    Só os produtos com sugestão maior que zero: é o pedido, não a lista de
    conferência (ver `pdf.py`).

    Quando não há pedido, recusa com 409 e o motivo — o mesmo texto que a tela
    já mostra no banner, para o vendedor não ler duas explicações diferentes do
    mesmo fato. Na prática é rede de segurança: o botão nem aparece nesses
    estados.
    """
    sugestao, cliente = await MerchandisingService.order_suggestion_for_pdf(
        session, context["tenant_id"], context["user"], customer_id
    )

    if sugestao.stale:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"A última coleta foi em {sugestao.last_collection_day:%d/%m/%Y}, "
                "semana passada. O pedido volta a aparecer quando o promotor "
                "contar a loja de novo."
            ),
        )
    if not sugestao.last_collection_day:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Este cliente ainda não tem duas coletas completas (gôndola e "
                "estoque). Sem duas, não há venda para calcular."
            ),
        )
    if not any(item.suggested_units > 0 for item in sugestao.items):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Nada a pedir: o estoque da loja cobre a venda de todos os "
                "produtos."
            ),
        )

    buf = pdf.build_order(sugestao, cliente, vendedor=context["user"].full_name)
    return pdf.pdf_response(buf, pdf.order_filename(cliente.name))


@router.put(
    "/customers/{customer_id}/products/{product_id}/turnover-factor", status_code=204
)
async def set_turnover_factor(
    customer_id: UUID,
    product_id: UUID,
    payload: TurnoverFactorUpdate,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_SELLER)),
):
    """Grava o fator de giro de um produto nesta loja (1 a 3)."""
    await MerchandisingService.set_turnover_factor(
        session, context["tenant_id"], context["user"],
        customer_id, product_id, payload.turnover_factor,
    )


# ─── Faturamento e brindes do ERP ─────────────────────────────────────────────

@router.post("/erp/sync", response_model=ErpSyncResponse)
async def receive_erp_sync(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    """Recebe as notas de venda e de brinde do ERP, do computador da empresa.

    Não usa login: o pacote vem assinado com HMAC-SHA256 da hora do envio e do
    hash do corpo, com a ERP_SYNC_KEY que só o servidor e o `sync/config.ini`
    conhecem (`sync/sincronizar.py`, o mesmo esquema do BI Mais Vida e do EFFEX
    Trade). Recusa vem com `detail = {code, message}`, que o script mostra.
    """
    chave = settings.erp_sync_key.strip()
    try:
        if not chave:
            raise erp_sync.Recusado(
                503, "SINCRONIZACAO_DESLIGADA",
                "Sincronização desligada: falta a ERP_SYNC_KEY no .env do servidor.",
            )
        if len(chave) < erp_sync.MIN_CHAVE:
            raise erp_sync.Recusado(
                503, "CHAVE_FRACA",
                f"A ERP_SYNC_KEY do servidor tem menos de {erp_sync.MIN_CHAVE} "
                "caracteres. Gere outra com: "
                'python -c "import secrets; print(secrets.token_urlsafe(32))"',
            )
        corpo = await _ler_corpo(request, erp_sync.LIMITE_PACOTE)
        enviado_em = erp_sync.conferir_assinatura(
            chave,
            request.headers.get(erp_sync.CABECALHO_DATA),
            request.headers.get(erp_sync.CABECALHO_ASSINATURA),
            corpo,
            time.time(),
        )
        # Descompactar, ler e validar 100 mil itens é CPU: fora do event loop
        pacote = await asyncio.to_thread(erp_sync.ler_pacote, corpo)
        return await MerchandisingService.receive_erp_sync(session, pacote, enviado_em)
    except erp_sync.Recusado as recusa:
        raise HTTPException(
            status_code=recusa.status,
            detail={"code": recusa.codigo, "message": recusa.mensagem},
        )


async def _ler_corpo(request: Request, limite: int) -> bytes:
    """O corpo inteiro, sem passar de `limite`. Lido até o fim antes de
    qualquer recusa por assinatura: a resposta precisa chegar a quem enviou."""
    declarado = request.headers.get("content-length", "")
    if declarado.isdigit() and int(declarado) > limite:
        raise erp_sync.Recusado(
            413, "PACOTE_GRANDE",
            f"O pacote passa de {limite // (1024 * 1024)} MB.",
        )
    partes, total = [], 0
    async for parte in request.stream():
        total += len(parte)
        if total > limite:
            raise erp_sync.Recusado(
                413, "PACOTE_GRANDE",
                f"O pacote passa de {limite // (1024 * 1024)} MB.",
            )
        partes.append(parte)
    if not total:
        raise erp_sync.Recusado(400, "PACOTE_VAZIO", "O pedido chegou sem o pacote.")
    return b"".join(partes)


@router.get("/invoices/imports", response_model=list[InvoiceImportRecordResponse])
async def list_invoice_imports(
    kind: str = Query(default="venda", description="venda (faturamento) ou brinde"),
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    """Os recibos desta origem — sincronizações e, antes delas, as planilhas
    anexadas à mão —, do mais recente para o mais antigo."""
    return await MerchandisingService.list_invoice_imports(
        session, context["tenant_id"], _validate_kind(kind)
    )


@router.get(
    "/invoices/imports/latest", response_model=Optional[InvoiceImportRecordResponse]
)
async def latest_erp_import(
    kind: str = Query(default="venda", description="venda (faturamento) ou brinde"),
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    """A última sincronização desta origem, com o relato: o que entrou, o que
    ficou de fora e por quê. Nulo se nenhuma chegou ainda."""
    return await MerchandisingService.latest_erp_import(
        session, context["tenant_id"], _validate_kind(kind)
    )


def _validate_kind(value: str) -> str:
    try:
        return DeliveryKind(value).value
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Origem inválida. Use venda ou brinde."
        )
