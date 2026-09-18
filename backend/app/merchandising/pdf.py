"""A folha do pedido sugerido, em PDF, para o vendedor entregar ao comprador.

Este é o único documento do app que sai da empresa: a planilha de `excel.py` é
para o administrador, e a tela do pedido é para o vendedor, mas esta folha vai
para a mão de quem compra na loja.

É por isso que ela NÃO traz a conta aberta que a tela mostra embaixo de cada
número — venda do ciclo, estoque contado, fator de giro. Aquilo é conversa
interna: o fator é a aposta do vendedor sobre a loja, e imprimi-lo convida a
uma discussão que não é sobre o pedido. O comprador precisa saber o que vai
chegar e conferir, então a linha tem produto, unidades e caixas, e mais nada.

Também não há preço. `Product.price` existe no modelo, mas ninguém preenche —
o cadastro deste app pede só o nome. Uma folha com a coluna de valor zerada
seria pior do que uma folha sem ela.

Só entram os produtos com sugestão maior que zero. Os de zero existem na tela
para o vendedor decidir se sobe o fator; num pedido, uma linha pedindo zero
unidades não quer dizer nada.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from io import BytesIO
from typing import Optional
from unicodedata import normalize

from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from app.core.config import settings
from app.merchandising.consolidation import local_zone

PDF_MIME = "application/pdf"

# O mesmo azul do cabeçalho da planilha (`_HEADER_FILL` em `excel.py`) e da cor
# primária do ERP — os dois documentos saem da mesma casa.
_AZUL = colors.HexColor("#1A237E")
_CINZA_TEXTO = colors.HexColor("#5F6B7A")
_CINZA_LINHA = colors.HexColor("#CFD6DF")
_ZEBRA = colors.HexColor("#F4F6F9")

_MARGEM = 16 * mm
# Rodapé de página: o texto é desenhado dentro desta faixa, por baixo do conteúdo.
_MARGEM_RODAPE = 18 * mm

# Produto que não vem em caixa: melhor um travessão do que um zero, que se leria
# como "zero caixas" de um produto que tem caixa.
_SEM_CAIXA = "—"


def _estilos() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["Normal"]
    return {
        "titulo": ParagraphStyle(
            "titulo", parent=base, fontName="Helvetica-Bold", fontSize=16,
            leading=19, textColor=_AZUL, spaceAfter=2,
        ),
        "fornecedor": ParagraphStyle(
            "fornecedor", parent=base, fontName="Helvetica", fontSize=9,
            leading=12, textColor=_CINZA_TEXTO,
        ),
        "cliente": ParagraphStyle(
            "cliente", parent=base, fontName="Helvetica-Bold", fontSize=12,
            leading=15, spaceBefore=6,
        ),
        "dado": ParagraphStyle(
            "dado", parent=base, fontName="Helvetica", fontSize=9, leading=12,
            textColor=_CINZA_TEXTO,
        ),
        "produto": ParagraphStyle(
            "produto", parent=base, fontName="Helvetica", fontSize=9.5, leading=12,
        ),
        "produto_cab": ParagraphStyle(
            "produto_cab", parent=base, fontName="Helvetica-Bold", fontSize=9,
            leading=11, textColor=colors.white,
        ),
        "num_cab": ParagraphStyle(
            "num_cab", parent=base, fontName="Helvetica-Bold", fontSize=9,
            leading=11, textColor=colors.white, alignment=TA_RIGHT,
        ),
        "assinatura": ParagraphStyle(
            "assinatura", parent=base, fontName="Helvetica", fontSize=8.5,
            leading=11, textColor=_CINZA_TEXTO,
        ),
    }


def _data_br(dia: Optional[date]) -> str:
    return dia.strftime("%d/%m/%Y") if dia else ""


def _hoje_local() -> date:
    """Hoje no fuso de quem lê, e não no do contêiner (que roda em UTC).

    Sem isto, uma folha emitida às 22h sai datada de amanhã — bem no campo que
    o comprador usa para saber se o pedido é o de hoje.
    """
    return datetime.now(timezone.utc).astimezone(local_zone()).date()


def _documento(digitos: Optional[str]) -> str:
    """CNPJ/CPF gravado só com dígitos → pontuado. O que não for nenhum dos dois
    volta como está: um cadastro pela metade não pode derrubar a folha."""
    if not digitos:
        return ""
    limpo = "".join(c for c in digitos if c.isdigit())
    if len(limpo) == 14:
        return (f"{limpo[:2]}.{limpo[2:5]}.{limpo[5:8]}"
                f"/{limpo[8:12]}-{limpo[12:]}")
    if len(limpo) == 11:
        return f"{limpo[:3]}.{limpo[3:6]}.{limpo[6:9]}-{limpo[9:]}"
    return digitos


def _numero(valor) -> str:
    """Decimal → pt-BR, sem casas quando o número é inteiro (1,5 cx mas 2 cx)."""
    n = float(valor)
    texto = f"{n:,.1f}" if n % 1 else f"{n:,.0f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


class _CanvasNumerado(Canvas):
    """Canvas que só sabe o total de páginas no fim — por isso desenha o rodapé
    no `save`, quando já contou todas. É o jeito de ter "Página 1 de 3" sem
    montar o documento duas vezes."""

    def __init__(self, *args, rodape: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self._paginas = []
        self._rodape = rodape

    def showPage(self):
        self._paginas.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._paginas)
        for estado in self._paginas:
            self.__dict__.update(estado)
            self._desenhar_rodape(total)
            super().showPage()
        super().save()

    def _desenhar_rodape(self, total: int):
        largura, _ = self._pagesize
        y = _MARGEM_RODAPE
        self.setStrokeColor(_CINZA_LINHA)
        self.setLineWidth(0.5)
        self.line(_MARGEM, y + 10, largura - _MARGEM, y + 10)
        self.setFont("Helvetica", 7.5)
        self.setFillColor(_CINZA_TEXTO)
        self.drawString(_MARGEM, y, self._rodape)
        self.drawRightString(
            largura - _MARGEM, y, f"Página {self._pageNumber} de {total}"
        )


def _cabecalho(sugestao, cliente, vendedor: Optional[str], estilos) -> list:
    """O bloco de cima: quem manda, para quem, de quando."""
    blocos = [Paragraph("PEDIDO SUGERIDO", estilos["titulo"])]

    if settings.company_name:
        blocos.append(Paragraph(settings.company_name, estilos["fornecedor"]))

    blocos.append(Paragraph(cliente.name, estilos["cliente"]))

    identificacao = [
        texto for texto in (
            cliente.corporate_name if cliente.corporate_name != cliente.name else None,
            f"CNPJ {_documento(cliente.document)}" if cliente.document else None,
        ) if texto
    ]
    if identificacao:
        blocos.append(Paragraph(" · ".join(identificacao), estilos["dado"]))

    rodape_dados = [f"Emitido em {_data_br(_hoje_local())}"]
    if sugestao.last_collection_day:
        rodape_dados.append(
            f"Contagem da loja em {_data_br(sugestao.last_collection_day)}"
        )
    if vendedor:
        rodape_dados.append(f"Vendedor: {vendedor}")
    blocos.append(Spacer(1, 4))
    blocos.append(Paragraph(" · ".join(rodape_dados), estilos["dado"]))

    blocos.append(Spacer(1, 10))
    return blocos


def _tabela(itens, largura: float, estilos) -> Table:
    """Produto, unidades, caixas — e a linha de total no fim.

    O nome do produto vai como `Paragraph` para quebrar em duas linhas em vez
    de ser cortado: nome de laticínio é comprido ("Queijo Mussarela Fatiado
    Fracionado 150g") e o comprador confere pelo nome.
    """
    col_num = 22 * mm
    larguras = [largura - 2 * col_num, col_num, col_num]

    linhas = [[
        Paragraph("PRODUTO", estilos["produto_cab"]),
        Paragraph("UN", estilos["num_cab"]),
        Paragraph("CX", estilos["num_cab"]),
    ]]
    for item in itens:
        linhas.append([
            Paragraph(item.product_name or "Produto", estilos["produto"]),
            _numero(item.suggested_units),
            _numero(item.suggested_boxes) if item.suggested_boxes else _SEM_CAIXA,
        ])

    total_unidades = sum(item.suggested_units for item in itens)
    linhas.append([
        f"{len(itens)} {'item' if len(itens) == 1 else 'itens'}",
        _numero(total_unidades),
        "",
    ])

    ultima = len(linhas) - 1
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), _AZUL),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (1, 1), (-1, -2), "Helvetica"),
        ("FONTSIZE", (1, 1), (-1, -2), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, _CINZA_LINHA),
        # Linha de total: destacada e separada do corpo por um traço mais forte
        ("FONTNAME", (0, ultima), (-1, ultima), "Helvetica-Bold"),
        ("FONTSIZE", (0, ultima), (-1, ultima), 10),
        ("LINEABOVE", (0, ultima), (-1, ultima), 1, _AZUL),
        ("TOPPADDING", (0, ultima), (-1, ultima), 7),
    ]
    # Zebrado só no corpo — o cabeçalho é azul e o total, destacado
    for i in range(1, ultima):
        if i % 2 == 0:
            estilo.append(("BACKGROUND", (0, i), (-1, i), _ZEBRA))

    tabela = Table(linhas, colWidths=larguras, repeatRows=1)
    tabela.setStyle(TableStyle(estilo))
    return tabela


def _assinatura(largura: float, estilos) -> list:
    """Observações e assinatura, num bloco que não se parte entre páginas.

    O comprador risca a quantidade de que discorda e assina o resto: é assim que
    o pedido volta do balcão.
    """
    campos = Table(
        [
            [Paragraph("Observações", estilos["assinatura"])],
            [""],          # duas pautas para o comprador escrever
            [""],
            [""],          # respiro antes da linha da assinatura
            [""],          # a linha em que ele assina
            [Paragraph("Assinatura do comprador", estilos["assinatura"])],
        ],
        colWidths=[largura],
        rowHeights=[12, 18, 18, 14, 26, 12],
    )
    # O rótulo de cada campo fica do lado em que se lê: "Observações" em cima
    # das pautas, "Assinatura" embaixo da linha — é onde se assina.
    campos.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("LINEBELOW", (0, 1), (0, 2), 0.5, _CINZA_LINHA),
        ("LINEBELOW", (0, 4), (0, 4), 0.5, _CINZA_LINHA),
    ]))
    # `KeepTogether`: o bloco inteiro desce para a página seguinte se não couber
    # aqui — assinatura órfã numa página sozinha não é folha, é sobra.
    return [Spacer(1, 16), KeepTogether([campos])]


def build_order(sugestao, cliente, vendedor: Optional[str] = None) -> BytesIO:
    """Monta a folha de um pedido. `sugestao` é a `OrderSuggestionResponse` que
    a tela recebe; `cliente`, o cadastro (razão social e CNPJ vêm dele).

    Quem decide se há pedido é a rota: aqui, lista vazia sairia como uma folha
    com zero itens.
    """
    itens = [i for i in sugestao.items if i.suggested_units > 0]
    estilos = _estilos()

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=_MARGEM, rightMargin=_MARGEM,
        topMargin=_MARGEM, bottomMargin=_MARGEM_RODAPE + 10,
        title=f"Pedido sugerido — {cliente.name}",
        author=settings.company_name or "Pedido sugerido",
    )

    rodape = "Sugestão calculada sobre a contagem de estoque da loja"
    if sugestao.last_collection_day:
        rodape += f" em {_data_br(sugestao.last_collection_day)}"
    rodape += " — quantidades sujeitas a conferência."

    doc.build(
        [
            *_cabecalho(sugestao, cliente, vendedor, estilos),
            _tabela(itens, doc.width, estilos),
            *_assinatura(doc.width, estilos),
        ],
        canvasmaker=lambda *a, **kw: _CanvasNumerado(*a, rodape=rodape, **kw),
    )
    buf.seek(0)
    return buf


def pdf_response(buf: BytesIO, filename: str) -> StreamingResponse:
    return StreamingResponse(
        buf,
        media_type=PDF_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def order_filename(customer_name: str) -> str:
    """`pedido_supermercado_silva_20260918.pdf`.

    O nome do cliente entra no arquivo porque o vendedor baixa vários no mesmo
    dia, e "pedido (3).pdf" na pasta de downloads não diz de que loja é. Sem
    acento e sem espaço: o arquivo passa por celular, WhatsApp e Windows.
    """
    ascii_nome = (
        normalize("NFKD", customer_name).encode("ascii", "ignore").decode("ascii")
    )
    limpo = "".join(c if c.isalnum() else "_" for c in ascii_nome.lower())
    limpo = "_".join(p for p in limpo.split("_") if p)[:40] or "cliente"
    return f"pedido_{limpo}_{_hoje_local():%Y%m%d}.pdf"
