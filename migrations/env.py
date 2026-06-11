from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection
from sqlmodel import SQLModel

from em_radar_api.db import create_db_engine
import em_radar_api.tables  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def configure_context(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=True,
    )


def run_migrations_offline() -> None:
    engine = create_db_engine()
    context.configure(
        url=engine.url,
        target_metadata=target_metadata,
        compare_type=True,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_db_engine()
    with engine.connect() as connection:
        configure_context(connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
