import enum
from uuid import uuid4

from sqlalchemy import (
    Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, String,
    UniqueConstraint,
)
from sqlalchemy import Uuid as UUID

from app.infrastructure.persistence.base import DeclarativeBase, TimestampMixin
from app.infrastructure.persistence.types import FlexibleJSON


class DeliveryKind(str, enum.Enum):
    """De qual planilha a entrada veio.

    As duas entram na conta somadas — mercadoria é mercadoria, chegou é chegou —
    mas ficam separadas porque saem de relatórios diferentes do ERP, com chaves e
    colunas diferentes, e porque o administrador precisa enxergar o brinde à
    parte quando a conta não fecha.
    """

    VENDA = "venda"
    BRINDE = "brinde"


class ImportSource(str, enum.Enum):
    """Por onde as notas chegaram.

    Até nov/2026 eram planilhas exportadas do ERP e anexadas à mão. Desde
    então é a sincronização com o banco do ERP, que o computador da empresa
    roda (`sync/sincronizar.py`). Os recibos das planilhas continuam na mesma
    tabela, como histórico.
    """

    PLANILHA = "planilha"
    ERP = "erp"


class ProductDelivery(DeclarativeBase, TimestampMixin):
    """O que a empresa mandou para um cliente — uma linha por item.

    Vem das notas do ERP: a sincronização que o computador da empresa roda
    (antes, a planilha anexada pelo administrador). É a
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

    # 'venda' (faturamento: VENDAS) ou 'brinde' (BRINDES), no ERP.
    # String e não Enum nativo, pelo mesmo motivo de `stock_visits.status`: evita
    # ALTER TYPE no dia em que aparecer uma terceira origem.
    kind = Column(String(10), nullable=False, default=DeliveryKind.VENDA.value)

    issued_on = Column(Date, nullable=False)

    # As peças do item (LISTAVENDA/LISTABRINDE.NUM_PECAS, a coluna N. PEÇAS da
    # planilha), e não QUANTIDADE: a quantidade mistura unidades e quilos
    # (queijo é faturado por peso), e somá-la daria quilos com unidades no mesmo
    # balde. Peças é o que o promotor conta na prateleira.
    quantity = Column(Numeric(15, 3), nullable=False, default=0)

    # ── A chave natural da linha ──────────────────────────────────────────
    # Nº VENDA + item, e não NOTA FISCAL + item: a venda do dia que ainda não
    # foi faturada vem sem número de nota, e essas linhas entrariam duplicadas
    # no upload do dia seguinte. A empresa entra junto porque são duas (matriz e
    # filial) e nada garante que a numeração siga compartilhada para sempre.
    #
    # Na sincronização, `sale_number` é o VENDAS.ID_VENDA (ou BRINDES.ID_BRINDE)
    # e `company` é o nome da empresa no ERP (CADASTROEMPRESA). Nas linhas que
    # vieram da planilha, `company` tem lixo: o cabeçalho da exportação tinha
    # uma coluna a menos que os dados, e a coluna EMPRESA lia a comissão do
    # supervisor ("0", "0.096"). Por isso a sincronização não tenta casar a
    # chave com a das planilhas: ela troca o período inteiro.
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


class InvoiceImport(DeclarativeBase, TimestampMixin):
    """O recibo de cada leva de notas que entrou: de onde, quando e quanto.

    Uma por origem (venda ou brinde) em cada sincronização com o ERP — e, antes
    dela, uma por planilha anexada (`source = 'planilha'`, com o nome do
    arquivo e quem anexou).

    As linhas de `product_deliveries` não sabem de que envio vieram — e o envio
    seguinte as troca, apagando o rastro. Sem este registro, quem abre a tela
    não tem como responder "os números de ontem já chegaram?".

    É só recibo: apagar um não desfaz a importação. As entradas continuam
    gravadas por conta própria.
    """

    __tablename__ = "invoice_imports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    # Quem anexou. Nulo se o usuário for apagado — o recibo continua valendo.
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # 'venda' ou 'brinde' — a mesma origem das entradas que este recibo cobre.
    kind = Column(String(10), nullable=False, default=DeliveryKind.VENDA.value)
    # 'planilha' ou 'erp' (ver `ImportSource`).
    source = Column(
        String(10), nullable=False, default=ImportSource.ERP.value,
        server_default=ImportSource.PLANILHA.value,
    )
    # O nome do arquivo anexado. Na sincronização, só um rótulo.
    file_name = Column(String(255), nullable=False)

    # O período coberto. Na planilha, a menor e a maior EMISSÃO das linhas
    # úteis; na sincronização, o período que o envio trocou inteiro.
    first_day = Column(Date, nullable=True)
    last_day = Column(Date, nullable=True)

    total_lines = Column(Integer, nullable=False, default=0)
    # Linhas que casaram com cliente E produto — as que de fato entraram.
    matched_lines = Column(Integer, nullable=False, default=0)
    matched_quantity = Column(Numeric(15, 3), nullable=False, default=0)

    # ── Só na sincronização ───────────────────────────────────────────────
    # A hora do envio, assinada no cabeçalho. Pacote com hora igual ou
    # anterior à do último aceito é recusado (reenvio de pacote capturado).
    sent_at = Column(DateTime(timezone=True), nullable=True)
    # A data da cópia do banco do ERP que o computador leu.
    copy_at = Column(DateTime(timezone=True), nullable=True)
    # O relato do envio (`InvoiceImportResponse`), que a tela mostra. Só o
    # recibo mais recente de cada origem o guarda: o envio seguinte apaga o do
    # anterior, que já não descreve o que está gravado.
    report = Column(FlexibleJSON, nullable=True)

    __table_args__ = (
        Index("idx_invoice_imports_list", "tenant_id", "kind", "created_at"),
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
