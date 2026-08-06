"""Importação de clientes e produtos a partir de planilhas .xlsx (ou .csv).

Regra central: **upsert pela chave natural** (Âncora 4) — `document` para cliente,
`sku` para produto. Rodar a mesma planilha duas vezes não duplica nada.
"""
from __future__ import annotations

import csv
import io
import re
from io import BytesIO
from typing import Any, Optional
from uuid import uuid4

from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.models.customer import Customer
from app.infrastructure.persistence.models.product import Product
from app.merchandising.schemas import ImportReport, ImportRowError

# Colunas esperadas em cada modelo. A primeira de cada tupla é a obrigatória.
CUSTOMER_COLUMNS = [
    "documento", "nome", "razao_social", "telefone", "email",
    "cep", "logradouro", "numero", "complemento", "bairro", "cidade", "uf", "tipo",
]
PRODUCT_COLUMNS = [
    "sku", "nome", "codigo_barras", "descricao", "categoria",
    "unidade", "preco", "unidades_por_caixa", "validade_dias",
]

# Assinatura de arquivo .xlsx (é um zip)
_XLSX_MAGIC = b"PK\x03\x04"


def _only_digits(value: Any) -> Optional[str]:
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    return digits or None


def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_decimal(value: Any, default=0):
    if value is None or str(value).strip() == "":
        return default
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return default


def _normalize_header(raw_header) -> list[str]:
    return [
        re.sub(r"[^a-z0-9]+", "_", str(h or "").strip().lower()).strip("_")
        for h in raw_header
    ]


def _read_csv_rows(content: bytes) -> tuple[list[str], list[tuple[int, tuple]]]:
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        return [], []

    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";" if sample.count(";") > sample.count(",") else ","

    reader = csv.reader(io.StringIO(text), dialect)
    all_rows = list(reader)
    if not all_rows:
        return [], []

    header = _normalize_header(all_rows[0])
    data = [(idx, tuple(values)) for idx, values in enumerate(all_rows[1:], start=2)]
    return header, data


def _read_rows(content: bytes) -> tuple[list[str], list[tuple[int, tuple]]]:
    """Retorna (cabeçalho normalizado, [(numero_da_linha, valores)])."""
    if not content.startswith(_XLSX_MAGIC):
        # Não é .xlsx — tenta interpretar como .csv
        return _read_csv_rows(content)

    wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
    ws = wb.active

    rows = ws.iter_rows(values_only=True)
    raw_header = next(rows, None)
    if not raw_header:
        return [], []

    header = _normalize_header(raw_header)
    data = [(idx, values) for idx, values in enumerate(rows, start=2)]
    return header, data


def _column_getter(header: list[str]):
    col = {name: idx for idx, name in enumerate(header)}

    def get(values, name):
        idx = col.get(name)
        return values[idx] if idx is not None and idx < len(values) else None

    return get


async def import_customers(
    session: AsyncSession, tenant_id, content: bytes
) -> ImportReport:
    header, rows = _read_rows(content)
    report = ImportReport(total_rows=len(rows))
    get = _column_getter(header)

    for line, values in rows:
        if not any(v is not None and str(v).strip() for v in values):
            report.skipped += 1
            continue

        name = _clean(get(values, "nome"))
        document = _only_digits(get(values, "documento"))

        if not name:
            report.errors.append(ImportRowError(row=line, reason="Coluna 'nome' vazia"))
            continue
        if document and len(document) not in (11, 14):
            report.errors.append(
                ImportRowError(row=line, reason=f"CPF/CNPJ inválido: {document}")
            )
            continue

        if document:
            existing = (
                await session.execute(
                    select(Customer).where(
                        Customer.tenant_id == tenant_id,
                        Customer.document == document,
                    )
                )
            ).scalars().first()
        else:
            # Sem documento não há chave natural. Casa pelo nome exato para que
            # rodar a mesma planilha duas vezes continue não duplicando nada.
            existing = (
                await session.execute(
                    select(Customer).where(
                        Customer.tenant_id == tenant_id,
                        Customer.document.is_(None),
                        Customer.name == name,
                    )
                )
            ).scalars().first()

        address = {
            "zip_code": _only_digits(get(values, "cep")),
            "street": _clean(get(values, "logradouro")),
            "number": _clean(get(values, "numero")),
            "complement": _clean(get(values, "complemento")),
            "neighborhood": _clean(get(values, "bairro")),
            "city": _clean(get(values, "cidade")),
            "state": (_clean(get(values, "uf")) or "").upper()[:2] or None,
        }

        if existing:
            existing.name = name
            existing.corporate_name = _clean(get(values, "razao_social"))
            existing.phone = _clean(get(values, "telefone"))
            existing.email = _clean(get(values, "email"))
            existing.address = address
            existing.customer_type = _clean(get(values, "tipo"))
            session.add(existing)
            report.updated += 1
        else:
            session.add(
                Customer(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    document=document,
                    name=name,
                    corporate_name=_clean(get(values, "razao_social")),
                    phone=_clean(get(values, "telefone")),
                    email=_clean(get(values, "email")),
                    address=address,
                    customer_type=_clean(get(values, "tipo")),
                )
            )
            report.created += 1
        # Grava linha a linha: assim a próxima iteração enxerga o que acabou de
        # entrar e uma planilha com o mesmo documento repetido não duplica.
        await session.flush()

    await session.commit()
    return report


async def import_products(
    session: AsyncSession, tenant_id, content: bytes
) -> ImportReport:
    header, rows = _read_rows(content)
    report = ImportReport(total_rows=len(rows))
    get = _column_getter(header)

    for line, values in rows:
        if not any(v is not None and str(v).strip() for v in values):
            report.skipped += 1
            continue

        sku = _clean(get(values, "sku"))
        name = _clean(get(values, "nome"))

        if not sku or not name:
            report.errors.append(
                ImportRowError(row=line, reason="Colunas 'sku' e 'nome' são obrigatórias")
            )
            continue

        existing = (
            await session.execute(
                select(Product).where(Product.tenant_id == tenant_id, Product.sku == sku)
            )
        ).scalars().first()

        fields = dict(
            name=name,
            barcode=_only_digits(get(values, "codigo_barras")),
            description=_clean(get(values, "descricao")),
            category=_clean(get(values, "categoria")),
            unit=(_clean(get(values, "unidade")) or "UN").upper()[:10],
            price=_to_decimal(get(values, "preco")),
            package_size=_to_decimal(get(values, "unidades_por_caixa"), 1),
            shelf_life_days=int(_to_decimal(get(values, "validade_dias"))) or None,
        )

        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
            session.add(existing)
            report.updated += 1
        else:
            session.add(Product(id=uuid4(), tenant_id=tenant_id, sku=sku, **fields))
            report.created += 1
        await session.flush()

    await session.commit()
    return report


def build_template(entity: str) -> BytesIO:
    """Planilha-modelo com o cabeçalho correto e uma linha de exemplo."""
    columns = CUSTOMER_COLUMNS if entity == "customers" else PRODUCT_COLUMNS
    example = (
        ["12345678000190", "Mercado Central", "Mercado Central LTDA", "34999998888",
         "contato@mercado.com", "35500000", "Rua das Flores", "120", "", "Centro",
         "Divinópolis", "MG", "varejo"]
        if entity == "customers"
        else ["LAT-001", "Leite Integral UHT 1L", "7891234567890",
              "Leite longa vida", "laticinios", "UN", "6.00", "12", "120"]
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Modelo"
    ws.append(columns)
    ws.append(example)
    for idx in range(1, len(columns) + 1):
        ws.column_dimensions[get_column_letter(idx)].width = 22
    ws.freeze_panes = "A2"

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
