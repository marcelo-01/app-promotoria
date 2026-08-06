import enum
from uuid import uuid4

from sqlalchemy import Column, String, Text, Boolean, Enum as SQLEnum, ForeignKey, Index, func, text
from sqlalchemy import Uuid as UUID

from app.infrastructure.persistence.base import DeclarativeBase, TimestampMixin


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    SUPERVISOR = "supervisor"   # não usado no MVP; mantido por compatibilidade com o ERP
    SELLER = "seller"           # não usado no MVP; mantido por compatibilidade com o ERP
    PROMOTER = "promoter"       # NOVO — o papel deste app


class User(DeclarativeBase, TimestampMixin):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    email = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    phone = Column(String(30), nullable=True)
    role = Column(
        SQLEnum(UserRole, native_enum=True,
                values_callable=lambda x: [e.value for e in x]),
        default=UserRole.PROMOTER,
        nullable=False,
    )
    is_active = Column(Boolean, default=True, nullable=False)
    avatar_url = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_users_tenant_email", "tenant_id", "email"),
        Index("idx_users_email_lower", func.lower(text("email"))),
    )
