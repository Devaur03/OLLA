from logging.config import fileConfig
from sqlalchemy import pool, create_engine
from alembic import context

# Import all models so Alembic can detect them
from app.models.db.base import Base
from app.models.db.query import StoredQuery     # noqa: F401
from app.models.db.result import StoredResult   # noqa: F401
from app.models.db.chunk import StoredChunk     # noqa: F401
from app.config import settings

config = context.config

# Convert async driver URL to sync psycopg for Alembic
# postgresql+psycopg://... -> postgresql+psycopg://... (psycopg3 works sync too)
# Just strip any asyncpg reference if present
db_url = settings.database_url.replace("postgresql+asyncpg", "postgresql+psycopg")
config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url")
    connectable = create_engine(url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
