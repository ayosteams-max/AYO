from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection

from BACKEND.persistence.tables import VERSION_TABLE, metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata


def run_migrations_offline() -> None:
    raise RuntimeError(
        "Offline migration generation is not approved. Use the reviewed migration runner."
    )


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if not isinstance(connection, Connection):
        raise RuntimeError(
            "Alembic requires an advisory-locked connection from MigrationRunner."
        )

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_server_default=True,
        compare_type=True,
        include_schemas=True,
        render_as_batch=False,
        transactional_ddl=True,
        version_table=VERSION_TABLE,
        version_table_schema=None,
    )

    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
