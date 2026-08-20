from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_roles
from app.infrastructure.persistence.models.stock_visit import VisitType
from app.infrastructure.persistence.session import get_db_session
from app.merchandising import excel
from app.merchandising.repository import MerchandisingRepository as Repo
from app.merchandising.schemas import (
    AssignmentUpdate, CountSheetResponse, CustomerMixUpdate, PromoterCustomerResponse,
    StockVisitCreate, StockVisitListResponse, StockVisitResponse, StockVisitUpdate,
    VisitPairListResponse,
)
from app.merchandising.service import MerchandisingService

router = APIRouter(prefix="/merchandising", tags=["merchandising"])

_ADMIN = ("admin", "supervisor")
_FIELD = ("promoter", "admin", "supervisor")


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
    context: dict = Depends(require_roles(*_FIELD)),
):
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
