from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.append(str(Path(__file__).resolve().parents[1]))

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_sqlalchemy_url():
    user = os.getenv("DATABASE_USER", "estoque")
    password = os.getenv("DATABASE_PASSWORD", "estoque")
    host = os.getenv("DATABASE_HOST", "db")
    port = os.getenv("DATABASE_PORT", "5432")
    db = os.getenv("DATABASE_NAME", "estoque_db")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


config.set_main_option("sqlalchemy.url", get_sqlalchemy_url())

from app.infrastructure.persistence.base import DeclarativeBase
from app.infrastructure.persistence import models  # noqa: F401  (registra as tabelas)

target_metadata = DeclarativeBase.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_sqlalchemy_url()

    connectable = engine_from_config(
        configuration, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
