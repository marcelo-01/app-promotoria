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
    ("Quantidade", 14),
    ("Unidade", 12),
]

# Coluna de quantidade — usada para formatar os números depois de preencher
_QUANTITY_COLUMN = 6

_HEADER_FILL = PatternFill("solid", fgColor="1A237E")   # mesma cor primária do ERP
_HEADER_FONT = Font(color="FFFFFF", bold=True)

_VISIT_TYPE_LABEL = {"gondola": "Gôndola", "estoque": "Estoque"}
_UNIT_TYPE_LABEL = {"caixa": "Caixa", "unidade": "Unidade"}


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
            float(r.quantity) if r.quantity is not None else 0.0,
            _UNIT_TYPE_LABEL.get(r.unit_type, r.unit_type or ""),
        ])

    # Congela o cabeçalho e liga o autofiltro — o administrador vai filtrar muito
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(_HEADERS))}{ws.max_row}"

    for row in ws.iter_rows(
        min_row=2, min_col=_QUANTITY_COLUMN, max_col=_QUANTITY_COLUMN
    ):
        for cell in row:
            cell.number_format = "#,##0.###"

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
