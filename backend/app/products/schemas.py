from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.customers.utils import only_digits


class ProductBase(BaseModel):
    sku: str = Field(..., max_length=50)
    name: str = Field(..., max_length=255)
    barcode: Optional[str] = Field(default=None, max_length=30)   # EAN-13
    description: Optional[str] = Field(default=None, max_length=500)
    category: Optional[str] = Field(default=None, max_length=50)
    unit: str = Field(default="UN", max_length=10)
    price: Decimal = Field(default=Decimal("0"), ge=0)
    package_size: Optional[Decimal] = Field(default=Decimal("1"), ge=0)
    is_perishable: bool = True
    shelf_life_days: Optional[int] = Field(default=None, ge=0)
    image_url: Optional[str] = Field(default=None, max_length=512)
    is_active: bool = True

    @field_validator("barcode")
    @classmethod
    def _normalize_barcode(cls, value: Optional[str]) -> Optional[str]:
        return only_digits(value)

    @field_validator("unit")
    @classmethod
    def _normalize_unit(cls, value: str) -> str:
        return (value or "UN").strip().upper()[:10]


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    sku: Optional[str] = Field(default=None, max_length=50)
    name: Optional[str] = Field(default=None, max_length=255)
    barcode: Optional[str] = Field(default=None, max_length=30)
    description: Optional[str] = Field(default=None, max_length=500)
    category: Optional[str] = Field(default=None, max_length=50)
    unit: Optional[str] = Field(default=None, max_length=10)
    price: Optional[Decimal] = Field(default=None, ge=0)
    package_size: Optional[Decimal] = Field(default=None, ge=0)
    is_perishable: Optional[bool] = None
    shelf_life_days: Optional[int] = Field(default=None, ge=0)
    image_url: Optional[str] = Field(default=None, max_length=512)
    is_active: Optional[bool] = None

    @field_validator("barcode")
    @classmethod
    def _normalize_barcode(cls, value: Optional[str]) -> Optional[str]:
        return only_digits(value)

    @field_validator("unit")
    @classmethod
    def _normalize_unit(cls, value: Optional[str]) -> Optional[str]:
        return value.strip().upper()[:10] if value else value


class ProductResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    sku: str
    barcode: Optional[str] = None
    external_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    unit: str
    price: Decimal
    package_size: Optional[Decimal] = None
    is_perishable: bool
    shelf_life_days: Optional[int] = None
    image_url: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ProductListResponse(BaseModel):
    items: List[ProductResponse]
    total: int
