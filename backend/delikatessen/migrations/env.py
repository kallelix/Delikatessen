from alembic import context
from sqlalchemy import create_engine

from delikatessen import models  # noqa: F401  (Modelle registrieren)
from delikatessen.db import Base
from delikatessen.migrations_filter import include_name

config = context.config
target_metadata = Base.metadata


def run() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = create_engine(config.get_main_option("sqlalchemy.url"))
    with engine.connect() as conn:
        _run(conn)


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


run()
