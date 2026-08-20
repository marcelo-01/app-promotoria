"""Contagem declarada sem produtos.

Até aqui, uma contagem sem nenhum item era indistinguível de uma contagem que
nunca foi feita — e como a planilha do administrador passou a exigir os dois
lados (gôndola E estoque) para sair, o cliente que simplesmente não tem produto
num dos dois travaria o download para sempre.

`no_products` é o promotor dizendo "estive aqui e não há nada": a contagem conta
como enviada, fecha o par e aparece na planilha como "sem produtos" naquele
lado, em vez de zero — que seria uma contagem de verdade que deu zero.

Revision ID: 004_no_products
Revises: 003_boxes_units
Create Date: 2026-08-20
"""
from alembic import op
import sqlalchemy as sa

revision = "004_no_products"
down_revision = "003_boxes_units"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Contagens que já existiam foram feitas com produtos digitados — nenhuma
    # delas é uma declaração de ausência.
    op.add_column(
        "stock_visits",
        sa.Column(
            "no_products", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    op.drop_column("stock_visits", "no_products")
