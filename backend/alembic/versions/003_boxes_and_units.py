"""Caixas e unidades no mesmo item, e o total convertido em `quantity`.

O cliente quase nunca tem só caixas ou só unidades — tem "1 caixa e 5 unidades"
do mesmo produto. Em vez de escolher a unidade (`unit_type`), o promotor agora
digita os dois números, e o item guarda os dois.

`quantity` deixa de ser "o número digitado na unidade escolhida" e passa a ser
sempre o TOTAL EM UNIDADES (`boxes * products.package_size + units`), que é o que
a planilha do administrador entrega. `unit_type` continua na tabela, sempre
"unidade", porque é assim que `quantity` está expressa daqui em diante.

Revision ID: 003_boxes_units
Revises: 002_visit_unit_type
Create Date: 2026-08-07
"""
from alembic import op
import sqlalchemy as sa

revision = "003_boxes_units"
down_revision = "002_visit_unit_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stock_visit_items",
        sa.Column("boxes", sa.Numeric(15, 3), nullable=False, server_default="0"),
    )
    op.add_column(
        "stock_visit_items",
        sa.Column("units", sa.Numeric(15, 3), nullable=False, server_default="0"),
    )

    # Contagens antigas tinham um número só, na unidade escolhida no item.
    op.execute(
        """
        UPDATE stock_visit_items
           SET boxes = CASE WHEN unit_type = 'caixa' THEN quantity ELSE 0 END,
               units = CASE WHEN unit_type = 'caixa' THEN 0 ELSE quantity END
        """
    )

    # E `quantity` passa a ser o total em unidades. Como ninguém pôde cadastrar
    # `package_size` até agora (o campo nasce nesta mesma entrega), na prática
    # todo produto tem 1 e os números não mudam — a conversão fica registrada
    # aqui para quando isso deixar de ser verdade.
    op.execute(
        """
        UPDATE stock_visit_items AS i
           SET quantity = i.boxes * COALESCE(NULLIF(p.package_size, 0), 1) + i.units,
               unit_type = 'unidade'
          FROM products AS p
         WHERE p.id = i.product_id
        """
    )


def downgrade() -> None:
    # Volta ao número único: caixas viram o item em caixas, o resto em unidades.
    op.execute(
        """
        UPDATE stock_visit_items
           SET quantity  = CASE WHEN boxes > 0 THEN boxes ELSE units END,
               unit_type = CASE WHEN boxes > 0 THEN 'caixa' ELSE 'unidade' END
        """
    )
    op.drop_column("stock_visit_items", "units")
    op.drop_column("stock_visit_items", "boxes")
