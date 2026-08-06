import enum
from uuid import uuid4

from sqlalchemy import Column, String, ForeignKey, Index, Enum as SQLEnum, Text
from sqlalchemy import Uuid as UUID

from app.infrastructure.persistence.base import DeclarativeBase, TimestampMixin
from app.infrastructure.persistence.types import FlexibleJSON


class CustomerStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Customer(DeclarativeBase, TimestampMixin):
    __tablename__ = "customers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)

    # ── Chave de casamento com o ERP (Âncora 4) ───────────────────────────
    # CNPJ/CPF somente dígitos. É por aqui que os cadastros serão unificados.
    document = Column(String(20), nullable=True)
    # Preenchido apenas no dia da integração, com o ID vindo do Firebird.
    external_id = Column(String(255), nullable=True)

    name = Column(String(255), nullable=False)            # nome fantasia
    corporate_name = Column(String(255), nullable=True)   # razão social
    state_registration = Column(String(50), nullable=True)

    phone = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)

    status = Column(
        SQLEnum(CustomerStatus, native_enum=True,
                values_callable=lambda x: [e.value for e in x]),
        default=CustomerStatus.ACTIVE,
        nullable=False,
    )

    # Mesmas chaves do ERP:
    # zip_code, street, number, complement, neighborhood, city, state
    address = Column(FlexibleJSON, nullable=True)

    # varejo | food_service | industria | atacado
    customer_type = Column(String(30), nullable=True)
    logistics_notes = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_customers_tenant_id", "tenant_id"),
        Index("idx_customers_tenant_document", "tenant_id", "document"),
        Index("idx_customers_tenant_external", "tenant_id", "external_id"),
    )
