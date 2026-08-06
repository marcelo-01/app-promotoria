from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.infrastructure.persistence.models.stock_visit import UnitType, VisitType

# ─── Clientes do promotor ─────────────────────────────────────────────────────


class PromoterCustomerResponse(BaseModel):
    id: UUID
    name: str
    # Uma data por tipo: o promotor decide onde precisa passar olhando o card
    last_gondola_at: Optional[datetime] = None
    last_estoque_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─── Produtos para contagem ───────────────────────────────────────────────────


class CountProductResponse(BaseModel):
    id: UUID
    name: str
    image_url: Optional[str] = None
    position: int = 0
    # Contagem anterior NO MESMO TIPO — âncora mental para o promotor
    last_quantity: Optional[Decimal] = None
    last_unit_type: Optional[str] = None

    model_config = {"from_attributes": True}


class CountSheetResponse(BaseModel):
    """Tudo que a tela de contagem precisa, numa requisição só — é a única
    chamada que o promotor faz ao entrar na loja, muitas vezes com sinal ruim."""

    customer_id: UUID
    customer_name: str
    visit_type: str
    products: List[CountProductResponse] = []


# ─── Visita / contagem ────────────────────────────────────────────────────────


class StockVisitItemInput(BaseModel):
    product_id: UUID
    quantity: Decimal = Field(ge=0)
    unit_type: str = UnitType.UNIDADE.value

    @field_validator("unit_type")
    @classmethod
    def _valid_unit_type(cls, value: str) -> str:
        return UnitType(value).value


class StockVisitCreate(BaseModel):
    customer_id: UUID
    visit_type: str = VisitType.ESTOQUE.value
    # UUID gerado no aparelho — chave de idempotência do reenvio offline
    client_uuid: Optional[str] = Field(default=None, max_length=64)
    visited_at: Optional[datetime] = None
    items: List[StockVisitItemInput] = []
    # true = já envia fechada; false = salva rascunho no servidor
    submit: bool = False

    @field_validator("visit_type")
    @classmethod
    def _valid_visit_type(cls, value: str) -> str:
        return VisitType(value).value


class StockVisitItemResponse(BaseModel):
    id: UUID
    product_id: UUID
    product_name: Optional[str] = None
    quantity: Decimal
    unit_type: str = UnitType.UNIDADE.value
    expires_at: Optional[date] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class StockVisitResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    customer_name: Optional[str] = None
    promoter_id: UUID
    promoter_name: Optional[str] = None
    visit_type: str
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
