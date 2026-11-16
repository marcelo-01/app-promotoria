"""As notas do ERP passam a chegar pela sincronização, e não mais por planilha.

O computador da empresa lê a cópia do banco do ERP e manda as notas de venda e
de brinde dos últimos 120 dias (`sync/sincronizar.py`). Cada envio troca as
entradas daquele período inteiro e deixa um recibo por origem nesta tabela, a
mesma das planilhas: a tela lista os dois do mesmo jeito, e o histórico das
planilhas anexadas à mão continua lá.

O que o recibo da sincronização precisa a mais:

* `source` — de onde veio: `planilha` (todas as linhas de antes) ou `erp`.
* `sent_at` — a hora do envio, a mesma que vai assinada no cabeçalho. Pacote
  com hora igual ou anterior à do último aceito é recusado: sem isso, um pacote
  capturado no caminho poderia ser reenviado dentro da tolerância do relógio.
* `copy_at` — a data da cópia do banco que o computador leu, para a tela dizer
  de quando são os números.
* `report` — o relato do envio (o que entrou, o que ficou de fora e por quê),
  que a tela mostra. Na planilha ele aparecia na hora, para quem anexou; a
  sincronização roda no computador da empresa, e quem abre a tela depois
  precisa encontrá-lo guardado.

Revision ID: 013_erp_sync
Revises: 012_turnover_default_2
Create Date: 2026-11-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "013_erp_sync"
down_revision = "012_turnover_default_2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invoice_imports",
        sa.Column("source", sa.String(10), nullable=False, server_default="planilha"),
    )
    op.add_column(
        "invoice_imports", sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "invoice_imports", sa.Column("copy_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "invoice_imports", sa.Column("report", postgresql.JSONB(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("invoice_imports", "report")
    op.drop_column("invoice_imports", "copy_at")
    op.drop_column("invoice_imports", "sent_at")
    op.drop_column("invoice_imports", "source")
