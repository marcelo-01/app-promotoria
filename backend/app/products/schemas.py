"""Produto é nome + foto + quantas unidades cabem numa caixa + as duas validades.

Como em `customers/`, as colunas do ERP (sku, código de barras, preço, unidade…)
continuam na tabela para o dia da fusão, mas não são digitadas neste app. A foto
é o que o promotor realmente usa para reconhecer o produto na gôndola, e
`package_size` é o que converte a contagem em unidades na planilha do admin.
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

# Quantas unidades vêm numa caixa. É `products.package_size` (o mesmo nome do
# ERP) e é o fator que converte a contagem do promotor em unidades na planilha.
_PACKAGE_SIZE = Field(default=1, gt=0, le=100000, description="Unidades por caixa")

# Quantos dias o produto dura a partir da fabricação. É `products.shelf_life_days`
# (o mesmo nome do ERP) e continua em branco enquanto ninguém souber a validade —
# por isso é opcional, e não 0: 0 dia seria um produto que já nasce vencido.
_SHELF_LIFE_DAYS = Field(default=None, gt=0, le=3650, description="Dias de validade")

# Com quantos dias PARA VENCER a mercadoria costuma chegar ao cliente — o que
# sobra da validade depois do caminho entre a fábrica e a prateleira.
#
# Não é derivado de `shelf_life_days`: ninguém mede aqui o tempo desse caminho, e
# este é um número observado pelo comercial ("chega com uns 40 dias"). É ele, e
# não a validade total, que estima quando vence o que está na loja — e produto
# sem ele fica de fora da coleta de vencimento, o que permite ligar a função
# produto a produto.
_ARRIVAL_SHELF_LIFE_DAYS = Field(
    default=None, gt=0, le=3650, description="Dias de validade na chegada ao cliente"
)


def _check_arrival(payload):
    """A mercadoria não pode chegar ao cliente com mais vida do que ela tem.

    Erro de digitação comum (trocar os dois campos de lugar), e que estragaria a
    estimativa inteira: um produto que "chega com 45 de 40" nunca alertaria.
    """
    total, chegada = payload.shelf_life_days, payload.arrival_shelf_life_days
    if total and chegada and chegada > total:
        raise ValueError(
            "A validade na chegada não pode ser maior que os dias de validade do produto."
        )
    return payload


class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    package_size: Decimal = _PACKAGE_SIZE
    shelf_life_days: Optional[int] = _SHELF_LIFE_DAYS
    arrival_shelf_life_days: Optional[int] = _ARRIVAL_SHELF_LIFE_DAYS

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def _arrival_within_shelf_life(self) -> "ProductCreate":
        return _check_arrival(self)


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    package_size: Optional[Decimal] = Field(default=None, gt=0, le=100000)
    shelf_life_days: Optional[int] = Field(default=None, gt=0, le=3650)
    arrival_shelf_life_days: Optional[int] = Field(default=None, gt=0, le=3650)
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _strip(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value else value

    @model_validator(mode="after")
    def _arrival_within_shelf_life(self) -> "ProductUpdate":
        # Só compara quando os dois vieram no mesmo PUT: um update que mexe só na
        # chegada não tem a validade total em mãos para comparar, e recusá-lo por
        # isso travaria o botão de Ativo/Inativo da lista.
        return _check_arrival(self)


class ProductResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    package_size: Optional[Decimal] = None
    shelf_life_days: Optional[int] = None
    arrival_shelf_life_days: Optional[int] = None
    # Caminho relativo servido pela própria API: /uploads/products/<arquivo>
    image_url: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ProductListResponse(BaseModel):
    items: List[ProductResponse]
    total: int
