"""Produto é nome + foto.

Como em `customers/`, as colunas do ERP (sku, código de barras, preço, unidade…)
continuam na tabela para o dia da fusão, mas não são digitadas neste app. A foto
é o que o promotor realmente usa para reconhecer o produto na gôndola.
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _strip(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value else value


class ProductResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    # Caminho relativo servido pela própria API: /uploads/products/<arquivo>
    image_url: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ProductListResponse(BaseModel):
    items: List[ProductResponse]
    total: int
