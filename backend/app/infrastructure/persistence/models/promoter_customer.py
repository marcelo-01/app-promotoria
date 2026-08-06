from uuid import uuid4

from sqlalchemy import Boolean, Column, ForeignKey, Index, UniqueConstraint
from sqlalchemy import Uuid as UUID

from app.infrastructure.persistence.base import DeclarativeBase, TimestampMixin


class PromoterCustomer(DeclarativeBase, TimestampMixin):
    """Quais clientes cada promotor atende. Definido pelo administrador."""

    __tablename__ = "promoter_customers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "customer_id", name="uq_promoter_customers"),
        Index("idx_promoter_customers_user", "tenant_id", "user_id"),
        Index("idx_promoter_customers_customer", "tenant_id", "customer_id"),
    )
