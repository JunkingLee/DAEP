from logging.config import fileConfig
import os
from alembic import context
from sqlalchemy import engine_from_config, pool, create_engine

config=context.config
if config.config_file_name: fileConfig(config.config_file_name)
url=os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
if url.startswith("postgresql://"):
    url="postgresql+psycopg://"+url[len("postgresql://"):]
elif url.startswith("postgres://"):
    url="postgresql+psycopg://"+url[len("postgres://"): ]
if not url:
    raise RuntimeError("DATABASE_URL or sqlalchemy.url is required for Alembic")
config.set_main_option("sqlalchemy.url", url.replace("%","%%"))
target_metadata=None

def run_migrations_offline():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle":"named"})
    with context.begin_transaction(): context.run_migrations()

def run_migrations_online():
    connectable = create_engine(config.get_main_option("sqlalchemy.url"), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction(): context.run_migrations()

if context.is_offline_mode(): run_migrations_offline()
else: run_migrations_online()
