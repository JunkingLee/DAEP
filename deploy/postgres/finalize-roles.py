"""Grant application roles and transfer schema ownership after Alembic."""
import os
import psycopg
from psycopg import sql

with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
    connection.execute("GRANT daep_privileged TO daep_privileged_login")
    connection.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
        "TO daep_runtime, daep_privileged_login"
    )
    connection.execute(
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public "
        "TO daep_runtime, daep_privileged_login"
    )
    tables = connection.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = %s", ("public",)
    ).fetchall()
    for (name,) in tables:
        connection.execute(
            sql.SQL("ALTER TABLE public.{} OWNER TO daep_privileged_login").format(
                sql.Identifier(name)
            )
        )
    sequences = connection.execute(
        "SELECT sequencename FROM pg_sequences WHERE schemaname = %s", ("public",)
    ).fetchall()
    for (name,) in sequences:
        connection.execute(
            sql.SQL("ALTER SEQUENCE public.{} OWNER TO daep_privileged_login").format(
                sql.Identifier(name)
            )
        )
