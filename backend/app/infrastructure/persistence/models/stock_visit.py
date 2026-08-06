import enum
from uuid import uuid4

from sqlalchemy import (
    Column, Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy import Uuid as UUID

from app.infrastructure.persistence.base import DeclarativeBase, TimestampMixin


class StockVisitStatus(str, enum.Enum):
    DRAFT = "draft"           # rascunho, ainda em digitação
    SUBMITTED = "submitted"   # enviado pelo promotor
    EXPORTED = "exported"     # já baixado em planilha pelo administrador


class StockVisit(DeclarativeBase, TimestampMixin):
    """Contagem de estoque feita por um promotor em um cliente."""

    __tablename__ = "stock_visits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    promoter_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # String e não Enum nativo: mesmo padrão de `orders.order_status` no ERP,
    # que evita ALTER TYPE a cada novo status.
    status = Column(String(20), nullable=False, default=StockVisitStatus.DRAFT.value)

    visited_at = Column(DateTime(timezone=True), nullable=True)    # data real da contagem
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    exported_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    # UUID gerado no celular (crypto.randomUUID()). Torna o reenvio idempotente:
    # se o app enviar duas vezes por falha de rede, faz UPDATE em vez de duplicar.
    client_uuid = Column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "client_uuid", name="uq_stock_visits_client_uuid"),
        Index("idx_stock_visits_tenant_id", "tenant_id"),
        Index("idx_stock_visits_tenant_customer", "tenant_id", "customer_id"),
        Index("idx_stock_visits_tenant_promoter", "tenant_id", "promoter_id"),
        Index("idx_stock_visits_tenant_status", "tenant_id", "status"),
        Index("idx_stock_visits_submitted_at", "tenant_id", "submitted_at"),
    )


class StockVisitItem(DeclarativeBase, TimestampMixin):
    """Uma linha de contagem: produto + quantidade encontrada."""

    __tablename__ = "stock_visit_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    visit_id = Column(UUID(as_uuid=True), ForeignKey("stock_visits.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)

    # Numeric(15,3): mesmo tipo de products.stock e order_items.quantity no ERP
    quantity = Column(Numeric(15, 3), nullable=False, default=0)
    # Laticínio é perecível — validade é informação de negócio, não detalhe
    expires_at = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("visit_id", "product_id", name="uq_stock_visit_item"),
        Index("idx_stock_visit_items_visit_id", "visit_id"),
        Index("idx_stock_visit_items_tenant_product", "tenant_id", "product_id"),
    )
