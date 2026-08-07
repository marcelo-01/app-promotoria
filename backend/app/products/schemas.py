"""Produto é nome + foto + quantas unidades cabem numa caixa.

Como em `customers/`, as colunas do ERP (sku, código de barras, preço, unidade…)
continuam na tabela para o dia da fusão, mas não são digitadas neste app. A foto
é o que o promotor realmente usa para reconhecer o produto na gôndola, e
`package_size` é o que converte a contagem em unidades na planilha do admin.
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

# Quantas unidades vêm numa caixa. É `products.package_size` (o mesmo nome do
# ERP) e é o fator que converte a contagem do promotor em unidades na planilha.
_PACKAGE_SIZE = Field(default=1, gt=0, le=100000, description="Unidades por caixa")


class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    package_size: Decimal = _PACKAGE_SIZE

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    package_size: Optional[Decimal] = Field(default=None, gt=0, le=100000)
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _strip(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value else value


class ProductResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    package_size: Optional[Decimal] = None
    # Caminho relativo servido pela própria API: /uploads/products/<arquivo>
    image_url: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ProductListResponse(BaseModel):
    items: List[ProductResponse]
    total: int
