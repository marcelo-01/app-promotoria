"""Um usuário pode acumular promotor e vendedor.

Há funcionários que contam a loja e lançam o pedido. Com um só `role` por
usuário, o administrador tinha de escolher — o segundo cadastro com o mesmo
e-mail era recusado. `role` não muda de forma (é o que vai no token e o que o
ERP conhece); a coluna nova guarda o outro papel de campo, e é nula para quem
tem um só.

Revision ID: 010_secondary_role
Revises: 009_turnover_per_product
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "010_secondary_role"
down_revision = "009_turnover_per_product"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # O tipo `userrole` existe desde a 001 — só se reaproveita.
    op.add_column(
        "users",
        sa.Column(
            "secondary_role",
            postgresql.ENUM(name="userrole", create_type=False),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "secondary_role")
