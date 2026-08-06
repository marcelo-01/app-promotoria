from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# ─── Clientes do promotor ─────────────────────────────────────────────────────


class PromoterCustomerResponse(BaseModel):
    id: UUID
    name: str
    corporate_name: Optional[str] = None
    document: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[dict] = None
    customer_type: Optional[str] = None
    # Para o promotor saber onde já passou
    last_visited_at: Optional[datetime] = None
    has_draft: bool = False

    model_config = {"from_attributes": True}


# ─── Produtos para contagem ───────────────────────────────────────────────────


class CountProductResponse(BaseModel):
    id: UUID
    sku: str
    barcode: Optional[str] = None
    name: str
    unit: str
    package_size: Optional[Decimal] = None
    image_url: Optional[str] = None
    position: int = 0
    # Contagem da visita anterior nesse cliente — âncora mental para o promotor
    last_quantity: Optional[Decimal] = None

    model_config = {"from_attributes": True}


# ─── Visita / contagem ────────────────────────────────────────────────────────


class StockVisitItemInput(BaseModel):
    product_id: UUID
    quantity: Decimal = Field(ge=0)
    expires_at: Optional[date] = None
    notes: Optional[str] = None


class StockVisitCreate(BaseModel):
    customer_id: UUID
    # UUID gerado no aparelho — chave de idempotência do reenvio offline
    client_uuid: Optional[str] = Field(default=None, max_length=64)
    visited_at: Optional[datetime] = None
    notes: Optional[str] = None
    items: List[StockVisitItemInput] = []
    # true = já envia fechada; false = salva rascunho no servidor
    submit: bool = False


class StockVisitItemResponse(BaseModel):
    id: UUID
    product_id: UUID
    product_sku: Optional[str] = None
    product_name: Optional[str] = None
    product_unit: Optional[str] = None
    quantity: Decimal
    expires_at: Optional[date] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class StockVisitResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    customer_name: Optional[str] = None
    customer_document: Optional[str] = None
    promoter_id: UUID
    promoter_name: Optional[str] = None
    status: str
    visited_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    exported_at: Optional[datetime] = None
    notes: Optional[str] = None
    client_uuid: Optional[str] = None
    items: List[StockVisitItemResponse] = []
    items_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class StockVisitListResponse(BaseModel):
    items: List[StockVisitResponse]
    total: int
    limit: int
    offset: int


# ─── Administração ────────────────────────────────────────────────────────────


class AssignmentUpdate(BaseModel):
    """Define o conjunto completo de clientes de um promotor (substitui o anterior)."""
    customer_ids: List[UUID]


class CustomerMixUpdate(BaseModel):
    """Define o mix de produtos contados em um cliente, na ordem informada."""
    product_ids: List[UUID]


# ─── Importação de planilhas ──────────────────────────────────────────────────


class ImportRowError(BaseModel):
    row: int
    reason: str


class ImportReport(BaseModel):
    total_rows: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[ImportRowError] = []
