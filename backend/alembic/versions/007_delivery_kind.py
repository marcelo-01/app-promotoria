"""De qual planilha a entrada veio: faturamento ou brinde.

O brinde entra no estoque do cliente exatamente como a venda — mercadoria é
mercadoria — e na conta as duas se somam. Mas saem de relatórios diferentes do
ERP, com colunas e numeração próprias, e o administrador precisa poder olhar o
brinde à parte quando a conta não fecha.

`kind` entra também na chave única: nada impede que um número de brinde coincida
com um número de venda, e sem ele a segunda planilha sobrescreveria linhas da
primeira em silêncio.

Revision ID: 007_delivery_kind
Revises: 006_deliveries_removals
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa

revision = "007_delivery_kind"
down_revision = "006_deliveries_removals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tudo que já está gravado veio da planilha de faturamento.
    op.add_column(
        "product_deliveries",
        sa.Column("kind", sa.String(10), nullable=False, server_default="venda"),
    )
    op.drop_constraint(
        "uq_product_deliveries_venda", "product_deliveries", type_="unique"
    )
    op.create_unique_constraint(
        "uq_product_deliveries_venda",
        "product_deliveries",
        ["tenant_id", "kind", "company", "sale_number", "product_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_product_deliveries_venda", "product_deliveries", type_="unique"
    )
    op.create_unique_constraint(
        "uq_product_deliveries_venda",
        "product_deliveries",
        ["tenant_id", "company", "sale_number", "product_id"],
    )
    op.drop_column("product_deliveries", "kind")
