from alembic import context
from pathlib import Path
from sqlalchemy import engine_from_config, pool

from aeroroute_api.infrastructure.db.models import Base

config = context.config
target_metadata = Base.metadata

# FAT/exFAT volumes may expose macOS AppleDouble sidecars as Python files.
for sidecar in (Path(__file__).parent / "versions").glob("._*.py"):
    sidecar.unlink(missing_ok=True)


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
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
