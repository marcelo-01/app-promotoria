"""As duas metades que faltavam da conta: o que entrou e o que foi para o lixo.

`product_deliveries` é o faturamento do ERP, anexado em planilha pelo
administrador. Com ele a contagem do promotor deixa de ser a FONTE dos lotes e
passa a ser a CONFERÊNCIA deles: o sistema sabe o que entrou e quando, e a
contagem só diz quanto sobrou.

`product_removals` é a mercadoria vencida que o promotor retira da loja. A
devolução do ERP não serve aqui — ela só é lançada quando a mercadoria volta
fisicamente ao estoque, dias depois. E sem esse registro o que foi para o lixo é
lido como venda, o que faz a loja parecer girar mais rápido e CALA justamente o
alerta do produto que está vencendo.

Nenhuma das duas é obrigatória: sem linha nenhuma, o razão de lotes se comporta
exatamente como antes desta migração.

Revision ID: 006_deliveries_removals
Revises: 005_expiry_collection
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa

revision = "006_deliveries_removals"
down_revision = "005_expiry_collection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("issued_on", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Numeric(15, 3), nullable=False, server_default="0"),
        sa.Column("company", sa.String(120), nullable=False),
        sa.Column("sale_number", sa.String(40), nullable=False),
        sa.Column("invoice", sa.String(40), nullable=True),
        sa.Column("cfop", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        # Nº VENDA + item: a venda ainda não faturada vem sem nota, e duplicaria
        # no upload do dia seguinte se a nota fosse a chave.
        sa.UniqueConstraint(
            "tenant_id", "company", "sale_number", "product_id",
            name="uq_product_deliveries_venda",
        ),
    )
    op.create_index(
        "idx_product_deliveries_lookup",
        "product_deliveries", ["tenant_id", "customer_id", "product_id"],
    )
    op.create_index(
        "idx_product_deliveries_date", "product_deliveries", ["tenant_id", "issued_on"]
    )

    op.create_table(
        "product_removals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("promoter_id", sa.Uuid(), nullable=False),
        sa.Column("removed_day", sa.Date(), nullable=False),
        sa.Column("expires_at", sa.Date(), nullable=False),
        sa.Column("boxes", sa.Numeric(15, 3), nullable=False, server_default="0"),
        sa.Column("units", sa.Numeric(15, 3), nullable=False, server_default="0"),
        sa.Column("quantity", sa.Numeric(15, 3), nullable=False, server_default="0"),
        sa.Column("client_uuid", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["promoter_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "client_uuid", "product_id", "expires_at",
            name="uq_product_removals_linha",
        ),
    )
    op.create_index(
        "idx_product_removals_lookup",
        "product_removals", ["tenant_id", "customer_id", "product_id"],
    )
    op.create_index(
        "idx_product_removals_day", "product_removals", ["tenant_id", "removed_day"]
    )


def downgrade() -> None:
    op.drop_index("idx_product_removals_day", table_name="product_removals")
    op.drop_index("idx_product_removals_lookup", table_name="product_removals")
    op.drop_table("product_removals")
    op.drop_index("idx_product_deliveries_date", table_name="product_deliveries")
    op.drop_index("idx_product_deliveries_lookup", table_name="product_deliveries")
    op.drop_table("product_deliveries")
