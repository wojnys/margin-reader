"""Runtime migrations; explicit URLs/connections never load private configuration."""

from alembic import context
from sqlalchemy import Connection, create_engine

from backend.app.db import models  # noqa: F401
from backend.app.db.base import Base


def run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    # The transfer owns one transaction covering schema, data and verification.
    run(connection)
else:
    url = context.config.get_main_option("sqlalchemy.url")
    if not url:
        from backend.app.core.config import settings

        url = settings().database_url
    if context.is_offline_mode():
        context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = create_engine(url)
        with engine.connect() as connection:
            run(connection)
        engine.dispose()
