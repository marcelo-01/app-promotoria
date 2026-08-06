from uuid import uuid4

from sqlalchemy import Column, String, Boolean, Integer, ForeignKey, Index, Numeric
from sqlalchemy import Uuid as UUID

from app.infrastructure.persistence.base import DeclarativeBase, TimestampMixin


class Product(DeclarativeBase, TimestampMixin):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)

    # ── Chaves de casamento com o ERP (Âncora 4) ──────────────────────────
    sku = Column(String(50), nullable=False)
    barcode = Column(String(30), nullable=True)           # EAN-13
    external_id = Column(String(255), nullable=True)

    name = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    category = Column(String(50), nullable=True)

    unit = Column(String(10), default="UN", nullable=False)
    price = Column(Numeric(15, 2), nullable=False, default=0)
    # quantas unidades por caixa/fardo — o promotor às vezes conta em caixas
    package_size = Column(Numeric(10, 3), nullable=True, default=1)

    is_perishable = Column(Boolean, default=True, nullable=False)
    shelf_life_days = Column(Integer, nullable=True)

    image_url = Column(String(512), nullable=True)

    # DIVERGÊNCIA DELIBERADA: o ERP não tem esta coluna (ver seção 22 do plano).
    is_active = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("idx_products_tenant_id", "tenant_id"),
        Index("idx_products_tenant_sku", "tenant_id", "sku"),
        Index("idx_products_tenant_barcode", "tenant_id", "barcode"),
    )
