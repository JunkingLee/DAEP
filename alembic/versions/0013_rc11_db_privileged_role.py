"""RC11: privilege bypass requires a dedicated PostgreSQL role.

Custom GUCs are caller-settable and must never be treated as proof of
platform-admin or internal-service identity. Privileged bypass is now bound
to membership in the database role daep_privileged.
"""
from alembic import op

revision = "0013_rc11_db_privileged_role"
down_revision = "0012_rc10_graph_rls"
branch_labels = None
depends_on = None

def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='daep_privileged') THEN
        CREATE ROLE daep_privileged NOLOGIN NOINHERIT NOBYPASSRLS;
      END IF;
    END
    $$;
    """)
    op.execute("""
    CREATE OR REPLACE FUNCTION daep_tenant_visible(row_tenant text)
    RETURNS boolean LANGUAGE sql STABLE AS $$
      SELECT pg_has_role(session_user, 'daep_privileged', 'member')
          OR (row_tenant IS NOT NULL AND row_tenant = current_setting('app.tenant_id', true))
    $$;
    """)

def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    # Fail closed: restore tenant-only visibility; do not drop a role that
    # deployments may already have assigned to dedicated privileged logins.
    op.execute("""
    CREATE OR REPLACE FUNCTION daep_tenant_visible(row_tenant text)
    RETURNS boolean LANGUAGE sql STABLE AS $$
      SELECT current_setting('app.platform_admin', true) = 'true'
          OR current_setting('app.internal_service', true) = 'true'
          OR (row_tenant IS NOT NULL AND row_tenant = current_setting('app.tenant_id', true))
    $$
    """)
