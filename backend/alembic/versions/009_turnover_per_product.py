"""O fator de giro passa a ser por produto em cada cliente.

Na revisão anterior ele era um número por cliente, gravado no vínculo do
vendedor. Não serve: a mesma loja gira o leite condensado a 2 e o queijo a 1,
e o vendedor define isso olhando o produto, na tela do pedido sugerido.

Vai para uma tabela própria, chaveada por (cliente, produto) e sem vendedor:
o fator é uma característica daquele produto naquela loja — quem assumir a
rota depois herda o número, como herda a loja.

A coluna antiga cai sem migrar dado: a tela nunca foi para produção.

Revision ID: 009_turnover_per_product
Revises: 008_turnover_factor
Create Date: 2026-09-15
"""
from alembic import op
import sqlalchemy as sa

revision = "009_turnover_per_product"
down_revision = "008_turnover_factor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "turnover_factors",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "customer_id", sa.Uuid(),
            sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "product_id", sa.Uuid(),
            sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("turnover_factor", sa.Numeric(2, 1), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "customer_id", "product_id", name="uq_turnover_factors"),
    )
    op.create_index(
        "idx_turnover_factors_customer", "turnover_factors", ["tenant_id", "customer_id"]
    )
    op.drop_column("promoter_customers", "turnover_factor")


def downgrade() -> None:
    op.add_column(
        "promoter_customers",
        sa.Column("turnover_factor", sa.Numeric(2, 1), nullable=False, server_default="1.0"),
    )
    op.drop_index("idx_turnover_factors_customer", table_name="turnover_factors")
    op.drop_table("turnover_factors")
