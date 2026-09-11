from uuid import uuid4

from sqlalchemy import Column, Date, ForeignKey, Index, Numeric, UniqueConstraint
from sqlalchemy import Uuid as UUID

from app.infrastructure.persistence.base import DeclarativeBase, TimestampMixin


class ProductExpiry(DeclarativeBase, TimestampMixin):
    """Uma data de vencimento encontrada num produto, num cliente, num dia.

    O promotor não coleta "a validade do produto": ele abre o estoque e acha
    mercadoria de datas diferentes na mesma pilha. Por isso a coleta é uma LISTA
    de linhas por produto — cada data com a sua quantidade — e a soma delas tem
    de fechar com o que ele acabou de contar.

    POR QUE ISTO NÃO PENDURA NO ITEM DA CONTAGEM
    --------------------------------------------
    O número que está sendo repartido é o do PAR (gôndola + estoque), não o de
    um lado só: a caixa que vence dia 20 pode estar metade na prateleira e
    metade no depósito, e obrigar o promotor a dizer onde cada data está seria
    pedir uma contagem que ele não fez. Então a linha é do cliente + produto +
    dia, e `visit_id` fica só como rastro de qual envio a trouxe — que é também
    por onde ela é substituída quando aquele envio sobe duas vezes.
    """

    __tablename__ = "product_expiries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    promoter_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # O envio que fechou o par e trouxe esta coleta. CASCADE porque a coleta não
    # sobrevive à contagem que a exigiu: sem o total, as linhas não significam
    # nada.
    visit_id = Column(
        UUID(as_uuid=True), ForeignKey("stock_visits.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Dia LOCAL da coleta (o mesmo dia que forma o par na planilha), e não o
    # instante UTC: é por ele que a série encontra a coleta no meio do histórico.
    collected_day = Column(Date, nullable=False)

    # Pode estar no passado, e isso não é erro: mercadoria vencida na prateleira
    # é exatamente o que esta coleta existe para achar.
    expires_at = Column(Date, nullable=False)

    # Os dois campos da tela, como na contagem — o promotor olha um palete e vê
    # caixas, não unidades.
    boxes = Column(Numeric(15, 3), nullable=False, default=0)
    units = Column(Numeric(15, 3), nullable=False, default=0)
    # boxes * products.package_size + units, convertido no envio: é nesta unidade
    # que a soma fecha com a contagem.
    quantity = Column(Numeric(15, 3), nullable=False, default=0)

    __table_args__ = (
        # Duas linhas com a mesma data no mesmo produto seriam uma só somada —
        # a tela junta antes de enviar.
        UniqueConstraint("visit_id", "product_id", "expires_at", name="uq_product_expiry"),
        Index("idx_product_expiries_visit", "visit_id"),
        Index("idx_product_expiries_lookup", "tenant_id", "customer_id", "product_id"),
        Index("idx_product_expiries_date", "tenant_id", "expires_at"),
    )
