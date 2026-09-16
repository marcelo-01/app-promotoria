from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.infrastructure.persistence.models.stock_visit import UnitType, VisitType

# ─── Clientes do promotor ─────────────────────────────────────────────────────


class PromoterCustomerResponse(BaseModel):
    id: UUID
    name: str
    # Uma data por tipo: o promotor decide onde precisa passar olhando o card
    last_gondola_at: Optional[datetime] = None
    last_estoque_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─── Produtos para contagem ───────────────────────────────────────────────────


class CountProductResponse(BaseModel):
    id: UUID
    name: str
    image_url: Optional[str] = None
    position: int = 0
    # Unidades por caixa: a tela mostra "caixa com N un" ao lado do campo
    package_size: Decimal = Decimal(1)
    # Contagem anterior NO MESMO TIPO — âncora mental para o promotor
    last_boxes: Optional[Decimal] = None
    last_units: Optional[Decimal] = None
    last_quantity: Optional[Decimal] = None

    # O que já está gravado neste produto. Só vem preenchido na folha de
    # correção de um envio; na contagem nova não há nada digitado ainda.
    boxes: Optional[Decimal] = None
    units: Optional[Decimal] = None

    # ── Vencimento ────────────────────────────────────────────────────────
    # O servidor decide QUEM precisa de coleta (é ele que tem o histórico e as
    # planilhas); o aparelho decide QUANDO barrar, com o total que acabou de ser
    # contado. A conta não pode depender de rede: o promotor fecha a contagem sem
    # sinal.
    collect_expiry: bool = False
    # 'nao_escoa' (no ritmo do ciclo, o estoque não sai antes de vencer) ou
    # 'parado' (não vendeu nada no ciclo — estoque parado não sai sozinho)
    expiry_reason: Optional[str] = None

    # A conta aberta, para a tela poder EXPLICAR por que este produto apareceu.
    # Nulo em `days_to_clear` quer dizer "não escoa nunca", que é diferente de
    # zero e não pode virar zero na serialização.
    expiry_days_to_clear: Optional[Decimal] = None
    expiry_shelf_life: Optional[int] = None
    expiry_cycle_days: Optional[int] = None
    expiry_sold: Optional[Decimal] = None

    model_config = {"from_attributes": True}


class CountSheetResponse(BaseModel):
    """Tudo que a tela de contagem precisa, numa requisição só — é a única
    chamada que o promotor faz ao entrar na loja, muitas vezes com sinal ruim.

    A folha de correção de um envio usa esta mesma resposta (com `visit_id`
    preenchido), porque a tela é a mesma: só muda de onde vêm os produtos.
    """

    customer_id: UUID
    customer_name: str
    visit_type: str
    visit_id: Optional[UUID] = None
    status: Optional[str] = None
    # Quadrado "não tem produtos aqui" — só vem marcado na folha de correção de
    # um envio que foi feito assim
    no_products: bool = False
    products: List[CountProductResponse] = []


# ─── Planilha de faturamento ──────────────────────────────────────────────────


class UnknownKeyResponse(BaseModel):
    """Um código da planilha que não existe no cadastro deste app.

    É a lista de trabalho da tela: cada linha aqui é mercadoria que entrou num
    cliente e o sistema não conseguiu contabilizar. Vem com quanto ficou de fora
    justamente para o administrador saber o que ignorar e o que vincular.
    """

    code: str
    name: str
    document: Optional[str] = None     # só nos clientes
    lines: int
    quantity: Decimal


class InvoiceImportResponse(BaseModel):
    """O relato de uma planilha lida — igual na prévia e na importação."""

    # Só preenchido quando o arquivo não tem as colunas esperadas. Nesse caso
    # nada mais vem: não dá para relatar sobre um arquivo que não foi entendido.
    missing_columns: List[str] = []

    # 'venda' (faturamento) ou 'brinde'
    kind: str = "venda"

    total_lines: int = 0
    # Linhas de entrada de mercadoria em cliente, já limpas
    usable_lines: int = 0
    # O que o CFOP deixou de fora. No faturamento, devolução e outras entradas —
    # a devolução só é lançada no ERP quando a mercadoria volta ao estoque, dias
    # depois, e para esta conta chega tarde demais. No brinde, tudo que não é
    # remessa ao cliente: transferência entre filiais, retorno, consumo interno,
    # baixa por perda.
    ignored_cfop: int = 0
    ignored_incomplete: int = 0
    # Linhas cuja quantidade é PESO, não contagem de peças (só na de brindes,
    # que não traz coluna de peças). Descartadas em vez de chutadas.
    ignored_weight: int = 0

    first_day: Optional[date] = None
    last_day: Optional[date] = None

    # Linhas que casaram com cliente E produto do cadastro
    matched_lines: int = 0
    matched_quantity: Decimal = Decimal(0)
    # true = gravado; false = foi só prévia
    saved: bool = False

    unknown_customers: List[UnknownKeyResponse] = []
    unknown_products: List[UnknownKeyResponse] = []
    # A quebra por motivo do que ENTROU (só na planilha de brindes). É por aqui
    # que se confere se o filtro de CFOP pegou o que devia.
    by_reason: List[UnknownKeyResponse] = []


class InvoiceImportRecordResponse(BaseModel):
    """Uma planilha que já entrou — o que a tela lista embaixo do campo de
    anexar para responder "essa eu já mandei?"."""

    id: UUID
    kind: str
    file_name: str
    imported_at: Optional[datetime] = None
    # Nome (ou e-mail) de quem anexou; nulo se o usuário foi apagado.
    imported_by: Optional[str] = None
    first_day: Optional[date] = None
    last_day: Optional[date] = None
    total_lines: int = 0
    matched_lines: int = 0
    matched_quantity: Decimal = Decimal(0)


# ─── Vencido retirado da loja ─────────────────────────────────────────────────


class ProductRemovalInput(BaseModel):
    """Uma retirada: produto, a data lida na embalagem, e quanto saiu."""

    product_id: UUID
    expires_at: date
    boxes: Decimal = Field(default=Decimal(0), ge=0)
    units: Decimal = Field(default=Decimal(0), ge=0)


class ProductRemovalCreate(BaseModel):
    customer_id: UUID
    # UUID gerado no aparelho, um por retirada — reenvio offline substitui
    client_uuid: Optional[str] = Field(default=None, max_length=64)
    removed_at: Optional[datetime] = None
    items: List[ProductRemovalInput] = []


class ProductRemovalResponse(BaseModel):
    id: UUID
    customer_id: UUID
    product_id: UUID
    product_name: Optional[str] = None
    removed_day: date
    expires_at: date
    boxes: Decimal = Decimal(0)
    units: Decimal = Decimal(0)
    quantity: Decimal = Decimal(0)

    model_config = {"from_attributes": True}


# ─── Visita / contagem ────────────────────────────────────────────────────────


class StockVisitItemInput(BaseModel):
    """Um produto contado: caixas fechadas e unidades avulsas, separadas.

    `quantity`/`unit_type` são o formato antigo (um número + a unidade). Ainda
    são aceitos porque a fila offline de um aparelho que não recarregou o app
    pode subir uma contagem nesse formato dias depois.
    """

    product_id: UUID
    boxes: Decimal = Field(default=Decimal(0), ge=0)
    units: Decimal = Field(default=Decimal(0), ge=0)

    quantity: Optional[Decimal] = Field(default=None, ge=0, exclude=True)
    unit_type: Optional[str] = Field(default=None, exclude=True)

    @field_validator("unit_type")
    @classmethod
    def _valid_unit_type(cls, value: Optional[str]) -> Optional[str]:
        return UnitType(value).value if value else value

    @model_validator(mode="after")
    def _convert_legacy(self) -> "StockVisitItemInput":
        if self.quantity is not None and not self.boxes and not self.units:
            if self.unit_type == UnitType.CAIXA.value:
                self.boxes = self.quantity
            else:
                self.units = self.quantity
        return self


class ProductExpiryInput(BaseModel):
    """Uma data encontrada num produto, com quanto vence nela.

    Datas no passado são aceitas de propósito: mercadoria vencida na prateleira é
    exatamente o que esta coleta existe para achar, e recusá-la deixaria o
    promotor sem como registrar o que ele está vendo.
    """

    product_id: UUID
    expires_at: date
    boxes: Decimal = Field(default=Decimal(0), ge=0)
    units: Decimal = Field(default=Decimal(0), ge=0)


class StockVisitCreate(BaseModel):
    customer_id: UUID
    visit_type: str = VisitType.ESTOQUE.value
    # UUID gerado no aparelho — chave de idempotência do reenvio offline
    client_uuid: Optional[str] = Field(default=None, max_length=64)
    visited_at: Optional[datetime] = None
    items: List[StockVisitItemInput] = []
    # O promotor marcou "não tem produtos aqui": a contagem vale como feita e
    # fecha o par gôndola + estoque, sem nenhum item. Os itens que porventura
    # venham junto são ignorados — foi isso que ele declarou.
    no_products: bool = False
    # As datas de vencimento coletadas junto com esta contagem.
    #
    # Sobem no MESMO envio, e não numa chamada à parte, porque a tela do promotor
    # trata as duas como uma coisa só: sem as datas ele não consegue enviar a
    # contagem. Separá-las abriria a porta para a contagem subir e a coleta ficar
    # para trás numa fila offline — que é justamente o que o bloqueio evita.
    expiries: List[ProductExpiryInput] = []
    # true = já envia fechada; false = salva rascunho no servidor
    submit: bool = False

    @field_validator("visit_type")
    @classmethod
    def _valid_visit_type(cls, value: str) -> str:
        return VisitType(value).value


class StockVisitUpdate(BaseModel):
    """Correção de uma contagem já enviada.

    Só as quantidades: o cliente e o tipo continuam os mesmos, e produto que não
    vier na lista sai da contagem (foi apagado na tela). Produto que nunca foi
    contado não entra por aqui — para isso o promotor faz uma contagem nova.
    """

    items: List[StockVisitItemInput] = []
    no_products: bool = False


class StockVisitItemResponse(BaseModel):
    id: UUID
    product_id: UUID
    product_name: Optional[str] = None
    boxes: Decimal = Decimal(0)
    units: Decimal = Decimal(0)
    # Total em unidades — boxes convertidas pelo package_size do produto + units
    quantity: Decimal
    unit_type: str = UnitType.UNIDADE.value
    expires_at: Optional[date] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class ProductExpiryResponse(BaseModel):
    id: UUID
    product_id: UUID
    product_name: Optional[str] = None
    expires_at: date
    boxes: Decimal = Decimal(0)
    units: Decimal = Decimal(0)
    quantity: Decimal = Decimal(0)

    model_config = {"from_attributes": True}


class StockVisitResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    customer_name: Optional[str] = None
    promoter_id: UUID
    promoter_name: Optional[str] = None
    visit_type: str
    status: str
    no_products: bool = False
    # Lado que falta para o par fechar ('gondola'/'estoque'), ou None quando as
    # duas contagens do dia já chegaram. Enquanto houver lado faltando, esta
    # contagem não entra em nenhuma planilha.
    missing_side: Optional[str] = None
    visited_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    exported_at: Optional[datetime] = None
    notes: Optional[str] = None
    client_uuid: Optional[str] = None
    items: List[StockVisitItemResponse] = []
    items_count: int = 0
    # As datas coletadas quando este envio foi fechado. A soma delas por produto
    # fecha com o total do PAR (gôndola + estoque), não com o desta contagem.
    expiries: List[ProductExpiryResponse] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class StockVisitListResponse(BaseModel):
    items: List[StockVisitResponse]
    total: int
    limit: int
    offset: int


# ─── O par gôndola + estoque, como o administrador vê ─────────────────────────


class VisitPairSideResponse(BaseModel):
    """Um dos dois lados do par: a contagem de gôndola ou a de estoque."""

    visit_id: UUID
    status: str
    no_products: bool = False
    items_count: int = 0
    visited_at: Optional[datetime] = None


class VisitPairResponse(BaseModel):
    """As duas contagens de um cliente num dia, na linha única da tela do
    administrador.

    O promotor conta os dois lugares separadamente — são duas visitas no banco.
    Quem administra não vê duas: vê a visita do dia, com os dois números lado a
    lado, exatamente como a planilha entrega. O lado que ainda não chegou vem
    como None, e é ele que `missing_side` nomeia.
    """

    # 'cliente|promotor|dia' — a mesma chave que forma o par, e o que identifica
    # a linha na tela. Não existe no banco: nasce do agrupamento.
    id: str
    customer_id: UUID
    customer_name: Optional[str] = None
    promoter_id: UUID
    promoter_name: Optional[str] = None
    day: str
    # A primeira das duas contagens — a hora em que o promotor chegou na loja.
    visited_at: Optional[datetime] = None
    gondola: Optional[VisitPairSideResponse] = None
    estoque: Optional[VisitPairSideResponse] = None
    missing_side: Optional[str] = None
    status: str


class VisitPairListResponse(BaseModel):
    items: List[VisitPairResponse]
    total: int
    limit: int
    offset: int


# ─── Administração ────────────────────────────────────────────────────────────


class AssignmentUpdate(BaseModel):
    """Define o conjunto completo de clientes de um promotor ou vendedor
    (substitui o anterior)."""
    customer_ids: List[UUID]


class CustomerMixUpdate(BaseModel):
    """Define o mix de produtos contados em um cliente, na ordem informada."""
    product_ids: List[UUID]


# ─── Vendedor: fator de giro e sugestão de pedido ─────────────────────────────


class TurnoverFactorUpdate(BaseModel):
    """De 1 a 3, uma casa decimal. 1 repõe o que vendeu; 3 triplica a cobertura."""
    turnover_factor: Decimal = Field(..., ge=1, le=3, decimal_places=1)


class ExpiryLotResponse(BaseModel):
    """Uma data lida na embalagem e quanto havia dela."""
    expires_at: date
    quantity: Decimal


class OrderSuggestionItemResponse(BaseModel):
    product_id: UUID
    product_name: Optional[str] = None
    image_url: Optional[str] = None
    package_size: Decimal

    # A conta aberta, para o vendedor conferir antes de lançar: o ciclo (as
    # duas coletas e os dias entre elas), a venda nele, o estoque de agora e o
    # fator que ele mesmo definiu para este produto nesta loja.
    cycle_from: date
    cycle_to: date
    cycle_days: int
    sold: Decimal
    current_stock: Decimal
    turnover_factor: Decimal

    # 0 = o estoque cobre a venda. O produto vem mesmo assim, porque é olhando
    # para ele que o vendedor decide subir o fator.
    suggested_units: int
    # suggested_units ÷ package_size, só quando o produto vem em caixa
    suggested_boxes: Optional[Decimal] = None

    # As datas de validade que o promotor leu na loja, na coleta mais recente
    # em que este produto entrou. Vazio quando nunca entrou. O dia da coleta
    # vai junto: pode ser anterior à contagem de onde os números saíram.
    expiry_collected_day: Optional[date] = None
    expiries: List[ExpiryLotResponse] = []


class OrderSuggestionResponse(BaseModel):
    customer_id: UUID
    customer_name: str

    # A coleta completa (gôndola + estoque) de onde os números saíram. None
    # quando o cliente ainda não tem duas — sem ciclo, sem venda, sem sugestão.
    last_collection_day: Optional[date] = None

    # O domingo mais recente. Coleta anterior a ele é da semana passada:
    # `stale` liga e `items` vem vazia, de propósito (ver `orders.py`).
    week_start: date
    stale: bool

    # Em ordem alfabética — a ordem em que o vendedor lança o pedido.
    items: List[OrderSuggestionItemResponse]



# ─── Evolução do estoque do cliente ───────────────────────────────────────────
#
# Tudo aqui é variação ENTRE CONTAGENS, nunca venda: este app não conhece
# entregas nem pedidos, então o que subiu quer dizer "houve entrega de pelo
# menos isso" e o que caiu, "saiu pelo menos isso". Ver `evolution.py`.


class StockCustomerResponse(BaseModel):
    """Um cliente com contagem na janela, e quanta história ele tem."""

    customer_id: UUID
    customer_name: Optional[str] = None
    # Contagens com os dois lados no mesmo dia — as únicas que comparam.
    complete_counts: int = 0
    first_day: str = ""
    last_day: str = ""


class StalledProductResponse(BaseModel):
    """Produto encalhado: mesma quantidade em contagens seguidas."""

    customer_id: UUID
    customer_name: Optional[str] = None
    product_id: UUID
    product_name: Optional[str] = None
    quantity: float = 0
    counts: int = 0
    days: int = 0
    since: str = ""


class MovedProductResponse(BaseModel):
    """Produto que zerou entre duas contagens, ou que voltou depois de zerado."""

    customer_id: UUID
    customer_name: Optional[str] = None
    product_id: UUID
    product_name: Optional[str] = None
    day: str
    previous_day: str
    previous: float = 0
    current: float = 0
    days: int = 0


class ShelfGapResponse(BaseModel):
    """Gôndola zerada com saldo no estoque — reposição, não falta de produto."""

    customer_id: UUID
    customer_name: Optional[str] = None
    product_id: UUID
    product_name: Optional[str] = None
    day: str
    estoque: float = 0
    repeated: bool = False


class StockInsightsResponse(BaseModel):
    window_days: int
    from_day: str
    to_day: str
    customers: List[StockCustomerResponse] = []
    stalled: List[StalledProductResponse] = []
    gone: List[MovedProductResponse] = []
    returned: List[MovedProductResponse] = []
    shelf_gap: List[ShelfGapResponse] = []
    # Totais antes do corte por `limit`, para a tela dizer "20 de 63".
    stalled_total: int = 0
    gone_total: int = 0
    returned_total: int = 0
    shelf_gap_total: int = 0


class StockPointResponse(BaseModel):
    """Um dia contado. Lado não contado vem como None: fica sem ponto no
    gráfico, em vez de virar um zero que não foi medido."""

    day: str
    gondola: Optional[float] = None
    estoque: Optional[float] = None


class StockHistoryResponse(BaseModel):
    customer_id: UUID
    customer_name: Optional[str] = None
    product_id: Optional[UUID] = None
    product_name: Optional[str] = None
    window_days: int
    points: List[StockPointResponse] = []
