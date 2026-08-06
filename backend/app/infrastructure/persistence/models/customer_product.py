from uuid import uuid4

from sqlalchemy import Column, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy import Uuid as UUID

from app.infrastructure.persistence.base import DeclarativeBase, TimestampMixin


class CustomerProduct(DeclarativeBase, TimestampMixin):
    """Mix de produtos contados em um cliente ('planograma' simplificado)."""

    __tablename__ = "customer_products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    # ordem de contagem na gôndola — o promotor conta de cima para baixo
    position = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("tenant_id", "customer_id", "product_id", name="uq_customer_products"),
        Index("idx_customer_products_customer", "tenant_id", "customer_id"),
    )
