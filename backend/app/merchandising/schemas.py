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
    """Define o conjunto completo de clientes de um promotor (substitui o anterior)."""
    customer_ids: List[UUID]


class CustomerMixUpdate(BaseModel):
    """Define o mix de produtos contados em um cliente, na ordem informada."""
    product_ids: List[UUID]


# ─── Painel do administrador ──────────────────────────────────────────────────


class CoverageResponse(BaseModel):
    """Quantas lojas de uma carteira fecharam o dia.

    `closed` é a loja com as duas contagens — a única que vira planilha. Somar
    `partial` a ela mostraria um dia melhor do que o que o administrador
    consegue exportar.
    """

    customers_total: int = 0
    closed: int = 0
    partial: int = 0
    missing: int = 0


class PromoterCoverageResponse(CoverageResponse):
    promoter_id: UUID
    promoter_name: Optional[str] = None


class DashboardCoverageResponse(CoverageResponse):
    # Cada promotor contra a própria carteira. A soma das linhas pode passar do
    # total: loja atendida por dois promotores conta nas duas carteiras, e uma
    # vez só no total.
    by_promoter: List[PromoterCoverageResponse] = []


class StuckPairResponse(BaseModel):
    """Uma visita pela metade: chegou um lado, o outro não."""

    customer_id: UUID
    customer_name: Optional[str] = None
    promoter_id: UUID
    promoter_name: Optional[str] = None
    day: str
    # Dias entre o dia da contagem e hoje. Zero é meia visita de hoje, que ainda
    # pode ser o promotor dentro da loja.
    days_waiting: int = 0
    missing_side: str
    # A contagem que chegou — é ela que a tela abre ao clicar na linha.
    visit_id: UUID


class DashboardStuckResponse(BaseModel):
    window_days: int
    total: int
    # Quantas passaram do próprio dia: as que não se fecham mais sozinhas.
    overdue: int = 0
    items: List[StuckPairResponse] = []


class DashboardResponse(BaseModel):
    """Os dois painéis da tela inicial do administrador, numa chamada só."""

    day: str
    coverage: DashboardCoverageResponse
    stuck: DashboardStuckResponse
