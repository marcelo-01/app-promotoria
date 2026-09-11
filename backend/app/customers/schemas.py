"""Cliente é só um nome.

As demais colunas continuam na tabela (documento, endereço, telefone…) porque é
por elas que o cadastro casa com o Firebird na fusão — mas ninguém as digita
neste app, então elas não entram nem na entrada nem na saída da API.
"""
import re
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# CNPJ/CPF guardado só com dígitos — é assim que a planilha de faturamento é
# comparada com o cadastro, e '13.781.008/0001-84' e '13781008000184' não podem
# ser dois clientes diferentes.
def _so_digitos(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    limpo = re.sub(r"\D", "", value)
    return limpo or None


class CustomerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    document: Optional[str] = Field(default=None, max_length=20)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @field_validator("document")
    @classmethod
    def _digits(cls, value: Optional[str]) -> Optional[str]:
        return _so_digitos(value)


class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    # active | inactive — cliente inativo some da lista do promotor
    status: Optional[str] = None
    document: Optional[str] = Field(default=None, max_length=20)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value else value

    @field_validator("document")
    @classmethod
    def _digits(cls, value: Optional[str]) -> Optional[str]:
        return _so_digitos(value)


class CustomerResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    document: Optional[str] = None
    status: str
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
