"""Schema inicial do app de coleta de estoque.

Revision ID: 001_initial
Revises:
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── tenants ────────────────────────────────────────────────────────────
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("status", sa.Enum("active", "inactive", name="tenantstatus"),
                  nullable=False, server_default="active"),
        sa.Column("slug", sa.String(100), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tenants_name", "tenants", ["name"])

    # ── users ──────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),
        # enum nasce completo — inclui os papéis do ERP + promoter
        sa.Column("role",
                  sa.Enum("admin", "supervisor", "seller", "promoter", name="userrole"),
                  nullable=False, server_default="promoter"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_users_tenant_email", "users", ["tenant_id", "email"])
    op.execute("CREATE INDEX idx_users_email_lower ON users (lower(email))")

    # ── customers ──────────────────────────────────────────────────────────
    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("document", sa.String(20), nullable=True),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("corporate_name", sa.String(255), nullable=True),
        sa.Column("state_registration", sa.String(50), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("status", sa.Enum("active", "inactive", name="customerstatus"),
                  nullable=False, server_default="active"),
        sa.Column("address", sa.JSON(), nullable=True),
        sa.Column("customer_type", sa.String(30), nullable=True),
        sa.Column("logistics_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_customers_tenant_id", "customers", ["tenant_id"])
    op.create_index("idx_customers_tenant_document", "customers", ["tenant_id", "document"])
    op.create_index("idx_customers_tenant_external", "customers", ["tenant_id", "external_id"])

    # ── products ───────────────────────────────────────────────────────────
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("sku", sa.String(50), nullable=False),
        sa.Column("barcode", sa.String(30), nullable=True),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("unit", sa.String(10), nullable=False, server_default="UN"),
        sa.Column("price", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("package_size", sa.Numeric(10, 3), nullable=True, server_default="1"),
        sa.Column("is_perishable", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("shelf_life_days", sa.Integer(), nullable=True),
        sa.Column("image_url", sa.String(512), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_products_tenant_id", "products", ["tenant_id"])
    op.create_index("idx_products_tenant_sku", "products", ["tenant_id", "sku"])
    op.create_index("idx_products_tenant_barcode", "products", ["tenant_id", "barcode"])

    # ── promoter_customers ─────────────────────────────────────────────────
    op.create_table(
        "promoter_customers",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", sa.Uuid(as_uuid=True), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "user_id", "customer_id", name="uq_promoter_customers"),
    )
    op.create_index("idx_promoter_customers_user", "promoter_customers", ["tenant_id", "user_id"])
    op.create_index("idx_promoter_customers_customer", "promoter_customers", ["tenant_id", "customer_id"])

    # ── customer_products ──────────────────────────────────────────────────
    op.create_table(
        "customer_products",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("customer_id", sa.Uuid(as_uuid=True), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "customer_id", "product_id", name="uq_customer_products"),
    )
    op.create_index("idx_customer_products_customer", "customer_products", ["tenant_id", "customer_id"])

    # ── stock_visits ───────────────────────────────────────────────────────
    op.create_table(
        "stock_visits",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("customer_id", sa.Uuid(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("promoter_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("visited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("client_uuid", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "client_uuid", name="uq_stock_visits_client_uuid"),
    )
    op.create_index("idx_stock_visits_tenant_id", "stock_visits", ["tenant_id"])
    op.create_index("idx_stock_visits_tenant_customer", "stock_visits", ["tenant_id", "customer_id"])
    op.create_index("idx_stock_visits_tenant_promoter", "stock_visits", ["tenant_id", "promoter_id"])
    op.create_index("idx_stock_visits_tenant_status", "stock_visits", ["tenant_id", "status"])
    op.create_index("idx_stock_visits_submitted_at", "stock_visits", ["tenant_id", "submitted_at"])

    # ── stock_visit_items ──────────────────────────────────────────────────
    op.create_table(
        "stock_visit_items",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("visit_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stock_visits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(15, 3), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("visit_id", "product_id", name="uq_stock_visit_item"),
    )
    op.create_index("idx_stock_visit_items_visit_id", "stock_visit_items", ["visit_id"])
    op.create_index("idx_stock_visit_items_tenant_product", "stock_visit_items", ["tenant_id", "product_id"])


def downgrade() -> None:
    op.drop_table("stock_visit_items")
    op.drop_table("stock_visits")
    op.drop_table("customer_products")
    op.drop_table("promoter_customers")
    op.drop_table("products")
    op.drop_table("customers")
    op.drop_table("users")
    op.drop_table("tenants")
    op.execute("DROP TYPE IF EXISTS userrole")
    op.execute("DROP TYPE IF EXISTS customerstatus")
    op.execute("DROP TYPE IF EXISTS tenantstatus")
