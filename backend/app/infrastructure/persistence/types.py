"""
Tipos customizados que adaptam entre dialetos.

FlexibleJSON → JSONB no PostgreSQL, JSON em outros (SQLite para testes).
Mantém os benefícios de indexação GIN em produção sem quebrar os testes.
"""
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB as _PG_JSONB

FlexibleJSON = JSON().with_variant(_PG_JSONB(), "postgresql")
