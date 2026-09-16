"""O recibo de cada planilha importada.

As entradas de mercadoria são gravadas linha a linha, sem dizer de que arquivo
vieram — e reanexar substitui a linha, apagando o rastro. O administrador que
anexa a planilha e volta à tela no dia seguinte não tem como saber se ela já
entrou, a não ser anexando de novo e comparando números.

Esta tabela guarda um registro por importação concluída: o nome do arquivo,
quem anexou, quando, o período coberto e quanto dele entrou. É o que a tela
lista embaixo do campo de anexar.

Revision ID: 011_invoice_imports
Revises: 010_secondary_role
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa

revision = "011_invoice_imports"
down_revision = "010_secondary_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invoice_imports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "user_id", sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("kind", sa.String(10), nullable=False, server_default="venda"),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("first_day", sa.Date(), nullable=True),
        sa.Column("last_day", sa.Date(), nullable=True),
        sa.Column("total_lines", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched_lines", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched_quantity", sa.Numeric(15, 3), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_invoice_imports_list", "invoice_imports", ["tenant_id", "kind", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_invoice_imports_list", table_name="invoice_imports")
    op.drop_table("invoice_imports")
