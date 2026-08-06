"""Tipo de contagem (gôndola/estoque), unidade por item e SKU opcional.

O promotor passou a contar dois lugares separados no mesmo cliente — a gôndola e
o estoque — e a escolher, produto a produto, se contou em caixas ou unidades.
O cadastro de produto passou a pedir só o nome, por isso o SKU vira opcional.

Revision ID: 002_visit_unit_type
Revises: 001_initial
Create Date: 2026-08-06
"""
from alembic import op
import sqlalchemy as sa

revision = "002_visit_unit_type"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Contagens que já existiam eram do estoque — não havia gôndola até aqui.
    op.add_column(
        "stock_visits",
        sa.Column("visit_type", sa.String(20), nullable=False, server_default="estoque"),
    )
    op.create_index(
        "idx_stock_visits_tenant_customer_type",
        "stock_visits",
        ["tenant_id", "customer_id", "visit_type"],
    )

    # Itens antigos foram digitados sem escolha de unidade: eram unidades.
    op.add_column(
        "stock_visit_items",
        sa.Column("unit_type", sa.String(10), nullable=False, server_default="unidade"),
    )

    op.alter_column("products", "sku", existing_type=sa.String(50), nullable=True)


def downgrade() -> None:
    op.alter_column("products", "sku", existing_type=sa.String(50), nullable=False)
    op.drop_column("stock_visit_items", "unit_type")
    op.drop_index("idx_stock_visits_tenant_customer_type", table_name="stock_visits")
    op.drop_column("stock_visits", "visit_type")
