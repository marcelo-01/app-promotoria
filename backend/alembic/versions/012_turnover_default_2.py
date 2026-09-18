"""O fator de giro passa a valer 2 por padrão, e não 1.

Com 1, a sugestão só repõe o que a loja vendeu — o pedido mais conservador que
existe, e o que todo produto mostrava enquanto o vendedor não mexesse em nada.
Mas o vendedor vai à loja para vender mais do que ela vendeu, e é mais fácil
discordar de um número cheio do que lembrar de subir um tímido produto a
produto. O padrão passa a dobrar a cobertura; quem quiser só repor abaixa para
1 na própria linha.

Quem manda no padrão é `DEFAULT_FACTOR`, em `orders.py`: o número vale para o
produto que NÃO TEM linha nesta tabela. Esta migração mexe só no
`server_default` da coluna, para o banco não continuar dizendo 1 enquanto o app
diz 2 — na prática ele nunca é usado, porque a gravação sempre manda o número.

O que já foi gravado fica como está: fator 1 numa linha existente é escolha do
vendedor para aquele produto naquela loja, não falta de escolha.

Revision ID: 012_turnover_default_2
Revises: 011_invoice_imports
Create Date: 2026-09-18
"""
from alembic import op
import sqlalchemy as sa

revision = "012_turnover_default_2"
down_revision = "011_invoice_imports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "turnover_factors", "turnover_factor",
        existing_type=sa.Numeric(2, 1), existing_nullable=False,
        server_default="2.0",
    )


def downgrade() -> None:
    op.alter_column(
        "turnover_factors", "turnover_factor",
        existing_type=sa.Numeric(2, 1), existing_nullable=False,
        server_default="1.0",
    )
