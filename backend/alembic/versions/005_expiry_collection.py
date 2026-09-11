"""Coleta de vencimento: a validade na chegada e as datas encontradas na loja.

Duas coisas, que só fazem sentido juntas.

`products.arrival_shelf_life_days` é com quantos dias para vencer a mercadoria
costuma chegar ao cliente. É o que transforma "este lote apareceu na contagem do
dia 3" em "este lote vence no dia 43" — e é o único jeito de estimar vencimento
sem conhecer nota fiscal nenhuma. Fica em branco por padrão: produto sem ele
simplesmente não entra na coleta, e a função liga produto a produto conforme o
cadastro for sendo preenchido.

`product_expiries` são as datas que o promotor achou no estoque. Uma linha por
data, porque a pilha tem mercadoria de datas diferentes, e a soma delas fecha com
o total contado no dia. A partir da primeira coleta, elas substituem a
estimativa: data lida na embalagem vale mais que data calculada.

Revision ID: 005_expiry_collection
Revises: 004_no_products
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa

revision = "005_expiry_collection"
down_revision = "004_no_products"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Sem server_default: em branco é "ninguém sabe ainda", que é diferente de
    # qualquer número que se chutasse aqui.
    op.add_column(
        "products", sa.Column("arrival_shelf_life_days", sa.Integer(), nullable=True)
    )

    op.create_table(
        "product_expiries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("promoter_id", sa.Uuid(), nullable=False),
        sa.Column("visit_id", sa.Uuid(), nullable=False),
        sa.Column("collected_day", sa.Date(), nullable=False),
        sa.Column("expires_at", sa.Date(), nullable=False),
        sa.Column("boxes", sa.Numeric(15, 3), nullable=False, server_default="0"),
        sa.Column("units", sa.Numeric(15, 3), nullable=False, server_default="0"),
        sa.Column("quantity", sa.Numeric(15, 3), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["promoter_id"], ["users.id"]),
        # A coleta não sobrevive à contagem que a exigiu: sem o total contado, as
        # datas não têm com o que fechar.
        sa.ForeignKeyConstraint(["visit_id"], ["stock_visits.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "visit_id", "product_id", "expires_at", name="uq_product_expiry"
        ),
    )
    op.create_index("idx_product_expiries_visit", "product_expiries", ["visit_id"])
    op.create_index(
        "idx_product_expiries_lookup",
        "product_expiries", ["tenant_id", "customer_id", "product_id"],
    )
    op.create_index(
        "idx_product_expiries_date", "product_expiries", ["tenant_id", "expires_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_product_expiries_date", table_name="product_expiries")
    op.drop_index("idx_product_expiries_lookup", table_name="product_expiries")
    op.drop_index("idx_product_expiries_visit", table_name="product_expiries")
    op.drop_table("product_expiries")
    op.drop_column("products", "arrival_shelf_life_days")
