"""Geração das planilhas .xlsx entregues ao administrador.

Uma linha por produto, com os dois lugares lado a lado. A contagem da gôndola e
a do estoque chegam separadas (são duas visitas), mas o administrador nunca vê
isso: quem junta as duas é `consolidation`, e aqui só se desenha o resultado.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Optional, Sequence

from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.merchandising.consolidation import ConsolidatedRow, local_zone

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_HEADERS = [
    ("Data da visita", 18),
    ("Cliente", 36),
    ("Promotor", 24),
    ("Produto", 40),
    ("Gôndola (un)", 15),
    ("Estoque (un)", 15),
    ("Total (un)", 14),
]

# Colunas numéricas — formatadas depois de preencher. A última é o total.
_FIRST_NUMBER_COLUMN = 5
_TOTAL_COLUMN = len(_HEADERS)

_HEADER_FILL = PatternFill("solid", fgColor="1A237E")   # mesma cor primária do ERP
_HEADER_FONT = Font(color="FFFFFF", bold=True)
_TOTAL_FONT = Font(bold=True)

# O promotor marcou "não tem produtos aqui". Texto e não zero: zero seria uma
# contagem que deu zero, e é outra coisa.
_SEM_PRODUTOS = "sem produtos"


def _format_local(moment: Optional[datetime]) -> str:
    """Instante gravado (UTC) → data e hora no fuso de quem lê a planilha.

    As datas são gravadas com `datetime.now(timezone.utc)`, então formatá-las
    cruas adianta a contagem em 3 horas — e a feita depois das 21h aparece com
    a data do dia seguinte, bem na coluna que o administrador usa para filtrar.
    """
    if not moment:
        return ""
    # Linha vinda do SQLite (testes) volta ingênua; assume-se UTC, que é como foi gravada.
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(local_zone()).strftime("%d/%m/%Y %H:%M")


def _cell(quantidade: Optional[float], lado_vazio: bool):
    """O que vai na célula de um dos lados.

    Três estados, e a diferença importa para quem lê: o número contado, o lado
    inteiro declarado sem produtos, e o produto que não foi contado naquele
    lugar (célula em branco).
    """
    if lado_vazio:
        return _SEM_PRODUTOS
    return "" if quantidade is None else quantidade


def build_workbook(
    rows: Sequence[ConsolidatedRow], sheet_title: str = "Consolidado"
) -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title

    ws.append([h for h, _ in _HEADERS])
    for idx, (_, width) in enumerate(_HEADERS, start=1):
        cell = ws.cell(row=1, column=idx)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[get_column_letter(idx)].width = width

    for r in rows:
        ws.append([
            _format_local(r.visited_at),
            r.customer_name,
            r.promoter_name,
            r.product_name,
            _cell(r.gondola, r.gondola_vazia),
            _cell(r.estoque, r.estoque_vazio),
            r.total,
        ])

    # Congela o cabeçalho e liga o autofiltro — o administrador vai filtrar muito
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(_HEADERS))}{ws.max_row}"

    for row in ws.iter_rows(
        min_row=2, min_col=_FIRST_NUMBER_COLUMN, max_col=_TOTAL_COLUMN
    ):
        for cell in row:
            cell.number_format = "#,##0.###"
        row[-1].font = _TOTAL_FONT

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def xlsx_response(buf: BytesIO, filename: str) -> StreamingResponse:
    return StreamingResponse(
        buf,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def default_filename(prefix: str = "estoque") -> str:
    # Mesmo fuso do conteúdo: baixar a planilha às 22h e receber um arquivo com
    # a data de amanhã no nome confunde na hora de achar o download.
    stamp = datetime.now(timezone.utc).astimezone(local_zone()).strftime("%Y%m%d_%H%M")
    return f"{prefix}_{stamp}.xlsx"
