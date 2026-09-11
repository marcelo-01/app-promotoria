import enum
from uuid import uuid4

from sqlalchemy import Column, Date, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy import Uuid as UUID

from app.infrastructure.persistence.base import DeclarativeBase, TimestampMixin


class DeliveryKind(str, enum.Enum):
    """De qual planilha a entrada veio.

    As duas entram na conta somadas — mercadoria é mercadoria, chegou é chegou —
    mas ficam separadas porque saem de relatórios diferentes do ERP, com chaves e
    colunas diferentes, e porque o administrador precisa enxergar o brinde à
    parte quando a conta não fecha.
    """

    VENDA = "venda"
    BRINDE = "brinde"


class ProductDelivery(DeclarativeBase, TimestampMixin):
    """O que a empresa mandou para um cliente — uma linha por item.

    Vem da planilha de faturamento do ERP, anexada pelo administrador. É a
    metade da história que a contagem do promotor nunca conseguiu ver: a
    diferença entre duas contagens é líquida, e sem saber o que ENTROU não há
    como distinguir "o cliente vendeu 20" de "o cliente vendeu 40 e recebeu 20".

    A DATA É A DA EMISSÃO, E ISSO É DE PROPÓSITO
    --------------------------------------------
    A planilha tem uma coluna de data de entrega, mas ela vem vazia na maior
    parte das linhas. A emissão vem em praticamente todas — e, para o que se faz
    aqui, ela basta: hoje o sistema só sabe que a mercadoria chegou "em algum
    momento entre duas visitas", uma janela de sete dias. Trocar isso por uma
    data com dois ou três dias de erro é ganho, não perda.
    """

    __tablename__ = "product_deliveries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)

    # 'venda' (planilha de faturamento) ou 'brinde' (planilha de brindes).
    # String e não Enum nativo, pelo mesmo motivo de `stock_visits.status`: evita
    # ALTER TYPE no dia em que aparecer uma terceira origem.
    kind = Column(String(10), nullable=False, default=DeliveryKind.VENDA.value)

    issued_on = Column(Date, nullable=False)

    # N. PEÇAS da planilha, e não QUANTIDADE: a coluna de quantidade mistura
    # unidades e quilos (queijo é faturado por peso), e somá-la daria quilos com
    # unidades no mesmo balde. Peças é o que o promotor conta na prateleira.
    quantity = Column(Numeric(15, 3), nullable=False, default=0)

    # ── A chave natural da linha ──────────────────────────────────────────
    # Nº VENDA + item, e não NOTA FISCAL + item: a venda do dia que ainda não
    # foi faturada vem sem número de nota, e essas linhas entrariam duplicadas
    # no upload do dia seguinte. A empresa entra junto porque são duas (matriz e
    # filial) e nada garante que a numeração siga compartilhada para sempre.
    #
    # No brinde a planilha não traz empresa; entra '—' e a chave se apoia no
    # número do brinde, que é único no relatório inteiro.
    company = Column(String(120), nullable=False)
    sale_number = Column(String(40), nullable=False)

    invoice = Column(String(40), nullable=True)
    cfop = Column(String(10), nullable=True)

    __table_args__ = (
        # `kind` entra na chave porque as duas planilhas numeram por conta
        # própria: nada impede que um nº de brinde coincida com um nº de venda.
        UniqueConstraint(
            "tenant_id", "kind", "company", "sale_number", "product_id",
            name="uq_product_deliveries_venda",
        ),
        Index("idx_product_deliveries_lookup", "tenant_id", "customer_id", "product_id"),
        Index("idx_product_deliveries_date", "tenant_id", "issued_on"),
    )


class ProductRemoval(DeclarativeBase, TimestampMixin):
    """Mercadoria vencida que o promotor retirou da loja.

    A devolução só entra no ERP quando a mercadoria volta fisicamente ao
    estoque, dias depois — tarde demais para esta conta. Quem vê primeiro é o
    promotor, que está lá tirando o produto da gôndola.

    POR QUE ISTO NÃO É DETALHE
    --------------------------
    Sem este registro, o que foi para o lixo é lido como venda: o estoque caiu e
    o sistema não tem como saber por quê. O efeito é perverso — a loja parece
    girar mais rápido, "dias para escoar" encolhe, e o alerta de "não vai dar
    tempo de vender" para de disparar justamente no produto que está vencendo.
    Quanto mais mercadoria vencia, menos o sistema avisava.

    A ordem de campo é retirar primeiro e contar depois: assim a contagem do dia
    já é o que sobrou, e a retirada não aparece duas vezes na conta.
    """

    __tablename__ = "product_removals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    promoter_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Dia LOCAL da retirada — a mesma chave de dia que forma o par na planilha.
    removed_day = Column(Date, nullable=False)
    # A data lida na embalagem do que foi retirado. Serve para descontar do lote
    # certo e, com o tempo, para medir o quanto a estimativa errou.
    expires_at = Column(Date, nullable=False)

    boxes = Column(Numeric(15, 3), nullable=False, default=0)
    units = Column(Numeric(15, 3), nullable=False, default=0)
    quantity = Column(Numeric(15, 3), nullable=False, default=0)

    # UUID gerado no aparelho, um por retirada (não por linha). O reenvio
    # offline substitui todas as linhas daquela retirada em vez de duplicar —
    # mesmo mecanismo das contagens.
    client_uuid = Column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "client_uuid", "product_id", "expires_at",
            name="uq_product_removals_linha",
        ),
        Index("idx_product_removals_lookup", "tenant_id", "customer_id", "product_id"),
        Index("idx_product_removals_day", "tenant_id", "removed_day"),
    )
