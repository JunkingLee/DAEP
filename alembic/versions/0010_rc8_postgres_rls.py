"""RC8 PostgreSQL row-level tenancy policies.

Policies are deliberately PostgreSQL-only. SQLite keeps application-level
isolation for local development. The API sets transaction-local app.tenant_id
and app.platform_admin before queries; FORCE ROW LEVEL SECURITY also prevents
table owners from silently bypassing the policies.
"""
from alembic import op

revision = "0010_rc8_postgres_rls"
down_revision = "0009_rc8_message_tenant"
branch_labels = None
depends_on = None

TABLES = ["members", "projects", "events", "artifacts", "outbox", "messages"]

def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("""
    CREATE OR REPLACE FUNCTION daep_tenant_visible(row_tenant text)
    RETURNS boolean LANGUAGE sql STABLE AS $$
      SELECT current_setting('app.platform_admin', true) = 'true'
          OR (row_tenant IS NOT NULL AND row_tenant = current_setting('app.tenant_id', true))
    $$;
    """)
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS daep_{table}_tenant ON {table}")
        op.execute(f"CREATE POLICY daep_{table}_tenant ON {table} USING (daep_tenant_visible(tenant_id)) WITH CHECK (daep_tenant_visible(tenant_id))")

def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS daep_{table}_tenant ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP FUNCTION IF EXISTS daep_tenant_visible(text)")
