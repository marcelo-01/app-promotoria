import enum
from uuid import uuid4

from sqlalchemy import Column, String, Enum as SQLEnum
from sqlalchemy import Uuid as UUID

from app.infrastructure.persistence.base import DeclarativeBase, TimestampMixin


class TenantStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Tenant(DeclarativeBase, TimestampMixin):
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), unique=True, nullable=False, index=True)
    status = Column(
        SQLEnum(TenantStatus, native_enum=True,
                values_callable=lambda x: [e.value for e in x]),
        default=TenantStatus.ACTIVE,
        nullable=False,
    )
    slug = Column(String(100), nullable=True, unique=True, index=True)
