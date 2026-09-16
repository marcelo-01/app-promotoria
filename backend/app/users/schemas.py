from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    """Promotor ou vendedor é nome, e-mail e senha — nada mais."""

    email: EmailStr
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = Field(default=None, max_length=255)
    # Papéis aceitos neste app: promoter (padrão), seller ou admin
    role: str = "promoter"
    # O outro papel de campo, para quem acumula promotor e vendedor
    secondary_role: Optional[str] = None

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        """Âncora 4: e-mail é a chave natural do usuário — sempre minúsculo."""
        return value.lower().strip()


class SetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=6)


class UserRolesUpdate(BaseModel):
    """O conjunto completo de papéis de campo da pessoa: um ou os dois."""

    roles: list[str] = Field(..., min_length=1, max_length=2)


class UserResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    email: str
    full_name: Optional[str] = None
    role: str
    # `role` mais o secundário, se houver — o que a tela usa para saber quem
    # acumula os dois papéis.
    roles: list[str]
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @field_validator("role", mode="before")
    @classmethod
    def _role_value(cls, value):
        return getattr(value, "value", value)

    @field_validator("roles", mode="before")
    @classmethod
    def _roles_list(cls, value):
        return sorted(value)
