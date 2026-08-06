from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.customers.utils import only_digits


class Address(BaseModel):
    """Mesmas chaves do `Customer.address` do ERP (Âncora 5)."""
    zip_code: Optional[str] = None
    street: Optional[str] = None
    number: Optional[str] = None
    complement: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = Field(default=None, max_length=2)


class CustomerBase(BaseModel):
    name: str = Field(..., max_length=255)
    document: Optional[str] = Field(default=None, max_length=20)
    corporate_name: Optional[str] = Field(default=None, max_length=255)
    state_registration: Optional[str] = Field(default=None, max_length=50)
    phone: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = Field(default=None, max_length=255)
    address: Optional[Address] = None
    customer_type: Optional[str] = Field(default=None, max_length=30)
    logistics_notes: Optional[str] = None

    @field_validator("document")
    @classmethod
    def _normalize_document(cls, value: Optional[str]) -> Optional[str]:
        """Âncora 4: documento sempre só dígitos, normalizado na entrada."""
        return only_digits(value)


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    document: Optional[str] = Field(default=None, max_length=20)
    corporate_name: Optional[str] = Field(default=None, max_length=255)
    state_registration: Optional[str] = Field(default=None, max_length=50)
    phone: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = Field(default=None, max_length=255)
    address: Optional[Address] = None
    customer_type: Optional[str] = Field(default=None, max_length=30)
    logistics_notes: Optional[str] = None
    status: Optional[str] = None

    @field_validator("document")
    @classmethod
    def _normalize_document(cls, value: Optional[str]) -> Optional[str]:
        return only_digits(value)


class CustomerResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    document: Optional[str] = None
    external_id: Optional[str] = None
    name: str
    corporate_name: Optional[str] = None
    state_registration: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    status: str
    address: Optional[dict] = None
    customer_type: Optional[str] = None
    logistics_notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @field_validator("status", mode="before")
    @classmethod
    def _status_value(cls, value):
        return getattr(value, "value", value)


class CustomerListResponse(BaseModel):
    items: List[CustomerResponse]
    total: int
