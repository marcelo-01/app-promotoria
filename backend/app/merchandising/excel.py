"""Geração das planilhas .xlsx entregues ao administrador."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Sequence

from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_HEADERS = [
    ("Data da visita", 18),
    ("Cliente", 36),
    ("Promotor", 24),
    ("Contagem", 12),
    ("Produto", 40),
    ("Caixas", 10),
    ("Unidades avulsas", 17),
    ("Un. por caixa", 14),
    ("Total (unidades)", 17),
]

# Colunas numéricas — formatadas depois de preencher. A última é o total.
_FIRST_NUMBER_COLUMN = 6
_TOTAL_COLUMN = len(_HEADERS)

_HEADER_FILL = PatternFill("solid", fgColor="1A237E")   # mesma cor primária do ERP
_HEADER_FONT = Font(color="FFFFFF", bold=True)
_TOTAL_FONT = Font(bold=True)

_VISIT_TYPE_LABEL = {"gondola": "Gôndola", "estoque": "Estoque"}


def _package_size(row) -> float:
    """Unidades por caixa do produto. Nulo ou zero vira 1 — produto sem caixa
    cadastrada é contado como se a caixa fosse a própria unidade."""
    return float(row.package_size) if row.package_size else 1.0


def _total_units(row) -> float:
    """A conversão que o administrador espera: 1 caixa de 10 + 10 avulsas = 20.

    Recalculada aqui, com o `package_size` de hoje, em vez de usar o total
    gravado na contagem: se o cadastro do produto for corrigido, a planilha
    seguinte já sai certa — inclusive para contagens antigas.
    """
    return float(row.boxes or 0) * _package_size(row) + float(row.units or 0)


def build_workbook(rows: Sequence, sheet_title: str = "Estoque") -> BytesIO:
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
            r.visited_at.strftime("%d/%m/%Y %H:%M") if r.visited_at else "",
            r.customer_name or "",
            r.promoter_name or "",
            _VISIT_TYPE_LABEL.get(r.visit_type, r.visit_type or ""),
            r.product_name or "",
            float(r.boxes or 0),
            float(r.units or 0),
            _package_size(r),
            _total_units(r),
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
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
