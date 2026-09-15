"""O fator de giro do vendedor, cliente a cliente.

A sugestão de pedido é `venda × fator − estoque atual`. A venda o sistema
calcula; o fator é o vendedor quem diz, porque só ele sabe se aquela loja está
prestes a fazer uma promoção ou se o gerente pediu para não encher o depósito.

Mora em `promoter_customers` — a tabela "pessoa de campo ↔ cliente" — porque o
fator é do PAR: o mesmo cliente pode girar 1,5 para um vendedor e 2 para outro
que assuma a rota depois. Nasce em 1 ("repõe o que vendeu"), que é o que a
tela mostra até o vendedor mexer. Nas linhas de promotor a coluna fica em 1 e
não significa nada.

Revision ID: 008_turnover_factor
Revises: 007_delivery_kind
Create Date: 2026-09-15
"""
from alembic import op
import sqlalchemy as sa

revision = "008_turnover_factor"
down_revision = "007_delivery_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "promoter_customers",
        sa.Column("turnover_factor", sa.Numeric(2, 1), nullable=False, server_default="1.0"),
    )


def downgrade() -> None:
    op.drop_column("promoter_customers", "turnover_factor")
