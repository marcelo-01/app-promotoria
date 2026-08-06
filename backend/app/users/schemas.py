from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=30)
    # Papéis aceitos neste app: promoter (padrão) ou admin
    role: str = "promoter"

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        """Âncora 4: e-mail é a chave natural do usuário — sempre minúsculo."""
        return value.lower().strip()


class SetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=6)


class UserResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    email: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: str
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @field_validator("role", mode="before")
    @classmethod
    def _role_value(cls, value):
        return getattr(value, "value", value)
