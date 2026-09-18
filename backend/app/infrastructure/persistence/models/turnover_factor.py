from uuid import uuid4

from sqlalchemy import Column, ForeignKey, Index, Numeric, UniqueConstraint
from sqlalchemy import Uuid as UUID

from app.infrastructure.persistence.base import DeclarativeBase, TimestampMixin


class TurnoverFactor(DeclarativeBase, TimestampMixin):
    """Quantas vezes a venda do ciclo o vendedor quer ver no pedido sugerido
    de um produto numa loja — de 1 a 3, uma casa decimal.

    É do PAR (cliente, produto), e não do vendedor: a mesma loja gira o leite
    condensado a 2 e o queijo a 1, e isso é característica da loja, que quem
    assumir a rota depois herda junto com ela. Produto sem linha aqui vale o
    `DEFAULT_FACTOR` de `orders.py` — hoje 2 —, e é o que a tela mostra até o
    vendedor mexer. Quem decide isso é quem lê, não o banco: o `server_default`
    abaixo nunca chega a ser usado, porque a gravação sempre manda o número.
    """

    __tablename__ = "turnover_factors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    turnover_factor = Column(Numeric(2, 1), nullable=False, default=2, server_default="2.0")

    __table_args__ = (
        UniqueConstraint("tenant_id", "customer_id", "product_id", name="uq_turnover_factors"),
        Index("idx_turnover_factors_customer", "tenant_id", "customer_id"),
    )
