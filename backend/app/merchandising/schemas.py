from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

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
    # Unidades por caixa: a tela mostra "caixa com N un" ao lado do campo
    package_size: Decimal = Decimal(1)
    # Contagem anterior NO MESMO TIPO — âncora mental para o promotor
    last_boxes: Optional[Decimal] = None
    last_units: Optional[Decimal] = None
    last_quantity: Optional[Decimal] = None

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
    """Um produto contado: caixas fechadas e unidades avulsas, separadas.

    `quantity`/`unit_type` são o formato antigo (um número + a unidade). Ainda
    são aceitos porque a fila offline de um aparelho que não recarregou o app
    pode subir uma contagem nesse formato dias depois.
    """

    product_id: UUID
    boxes: Decimal = Field(default=Decimal(0), ge=0)
    units: Decimal = Field(default=Decimal(0), ge=0)

    quantity: Optional[Decimal] = Field(default=None, ge=0, exclude=True)
    unit_type: Optional[str] = Field(default=None, exclude=True)

    @field_validator("unit_type")
    @classmethod
    def _valid_unit_type(cls, value: Optional[str]) -> Optional[str]:
        return UnitType(value).value if value else value

    @model_validator(mode="after")
    def _convert_legacy(self) -> "StockVisitItemInput":
        if self.quantity is not None and not self.boxes and not self.units:
            if self.unit_type == UnitType.CAIXA.value:
                self.boxes = self.quantity
            else:
                self.units = self.quantity
        return self


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
    boxes: Decimal = Decimal(0)
    units: Decimal = Decimal(0)
    # Total em unidades — boxes convertidas pelo package_size do produto + units
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
