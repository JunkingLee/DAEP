"""RC9 hardens PostgreSQL RLS context handling.

The API connection wrapper sets trusted transaction-scoped application context
before every query. Authentication lookup is a narrowly scoped SELECT policy
on members; internal bootstrap/worker operations use a separate service
context. Tenant data remains protected by the tenant policy.
"""
from alembic import op

revision = "0011_rc9_rls_context"
down_revision = "0010_rc8_postgres_rls"
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
          OR current_setting('app.internal_service', true) = 'true'
          OR (row_tenant IS NOT NULL AND row_tenant = current_setting('app.tenant_id', true))
    $$;
    """)

    op.execute("DROP POLICY IF EXISTS daep_members_auth_lookup ON members")
    op.execute("""
    CREATE POLICY daep_members_auth_lookup ON members
      FOR SELECT
      USING (current_setting('app.auth_lookup', true) = 'true')
    """)

    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS daep_{table}_tenant ON {table}")
        op.execute(
            f"CREATE POLICY daep_{table}_tenant ON {table} "
            f"USING (daep_tenant_visible(tenant_id)) "
            f"WITH CHECK (daep_tenant_visible(tenant_id))"
        )

def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("DROP POLICY IF EXISTS daep_members_auth_lookup ON members")
    op.execute("""
    CREATE OR REPLACE FUNCTION daep_tenant_visible(row_tenant text)
    RETURNS boolean LANGUAGE sql STABLE AS $$
      SELECT current_setting('app.platform_admin', true) = 'true'
          OR (row_tenant IS NOT NULL AND row_tenant = current_setting('app.tenant_id', true))
    $$;
    """)
