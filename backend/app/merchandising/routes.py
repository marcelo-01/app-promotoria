from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_roles
from app.infrastructure.persistence.session import get_db_session
from app.merchandising import excel, imports
from app.merchandising.repository import MerchandisingRepository as Repo
from app.merchandising.schemas import (
    AssignmentUpdate, CountProductResponse, CustomerMixUpdate, ImportReport,
    PromoterCustomerResponse, StockVisitCreate, StockVisitListResponse, StockVisitResponse,
)
from app.merchandising.service import MerchandisingService

router = APIRouter(prefix="/merchandising", tags=["merchandising"])

_ADMIN = ("admin", "supervisor")
_FIELD = ("promoter", "admin", "supervisor")


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


@router.get("/customers/{customer_id}/products", response_model=list[CountProductResponse])
async def list_products_for_customer(
    customer_id: UUID,
    search: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_FIELD)),
):
    return await MerchandisingService.list_products_for_customer(
        session, context["tenant_id"], context["user"], customer_id, search
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

@router.get("/visits", response_model=StockVisitListResponse)
async def list_visits(
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
    items, total = await MerchandisingService.list_visits(
        session, context["tenant_id"],
        promoter_id=promoter_id, customer_id=customer_id, status=status_filter,
        date_from=date_from, date_to=date_to, limit=limit, offset=offset,
    )
    return StockVisitListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/visits/{visit_id}/export.xlsx")
async def export_visit(
    visit_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    rows = await Repo.export_rows(session, context["tenant_id"], visit_ids=[visit_id])
    if not rows:
        raise HTTPException(status_code=404, detail="Contagem sem itens ou inexistente")
    buf = excel.build_workbook(rows)
    await Repo.mark_exported(
        session, context["tenant_id"], [visit_id], datetime.now(timezone.utc)
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
    rows = await Repo.export_rows(
        session, context["tenant_id"],
        promoter_id=promoter_id, customer_id=customer_id,
        date_from=date_from, date_to=date_to,
    )
    buf = excel.build_workbook(rows, sheet_title="Consolidado")
    await Repo.mark_exported(
        session,
        context["tenant_id"],
        list({row.visit_id for row in rows}),
        datetime.now(timezone.utc),
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


# ─── Administrador: importação de planilhas ───────────────────────────────────

@router.post("/imports/customers", response_model=ImportReport)
async def import_customers(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    return await imports.import_customers(session, context["tenant_id"], await file.read())


@router.post("/imports/products", response_model=ImportReport)
async def import_products(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    return await imports.import_products(session, context["tenant_id"], await file.read())


@router.get("/imports/{entity}/template.xlsx")
async def download_template(
    entity: str,
    context: dict = Depends(require_roles(*_ADMIN)),
):
    if entity not in ("customers", "products"):
        raise HTTPException(status_code=404, detail="Modelo não encontrado")
    buf = imports.build_template(entity)
    return excel.xlsx_response(buf, f"modelo_{entity}.xlsx")
