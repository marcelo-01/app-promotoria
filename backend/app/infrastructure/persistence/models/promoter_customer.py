from uuid import uuid4

from sqlalchemy import Boolean, Column, ForeignKey, Index, Numeric, UniqueConstraint
from sqlalchemy import Uuid as UUID

from app.infrastructure.persistence.base import DeclarativeBase, TimestampMixin


class PromoterCustomer(DeclarativeBase, TimestampMixin):
    """Quais clientes cada pessoa de campo atende. Definido pelo administrador.

    O nome diz "promotor", mas a linha é de qualquer usuário de campo: o
    VENDEDOR também é vinculado por aqui, e a tela de vínculos é a mesma. Na
    fusão as duas viram `seller_customers`, cada uma com seu `link_type`.
    """

    __tablename__ = "promoter_customers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)

    # Só faz sentido na linha de um VENDEDOR: quantas vezes a venda do ciclo ele
    # quer ver no pedido sugerido (1 a 3, uma casa decimal). É do par — o mesmo
    # cliente pode girar diferente para quem assumir a rota depois. Nasce em 1,
    # "repõe o que vendeu". Na linha de promotor fica em 1 e não significa nada.
    turnover_factor = Column(Numeric(2, 1), nullable=False, default=1, server_default="1.0")

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "customer_id", name="uq_promoter_customers"),
        Index("idx_promoter_customers_user", "tenant_id", "user_id"),
        Index("idx_promoter_customers_customer", "tenant_id", "customer_id"),
    )
