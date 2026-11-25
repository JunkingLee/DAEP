"""RC48: close PostgreSQL RLS coverage gaps for workflow governance tables."""

from alembic import op

revision = "0038_rc48_workflow_governance_rls"
down_revision = "0037_rc47_notify_prefs"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return

    for table in ("project_workflows", "project_gates"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS daep_{table}_tenant ON {table}")
        op.execute(f"""
            CREATE POLICY daep_{table}_tenant ON {table}
            USING (daep_tenant_visible(tenant_id))
            WITH CHECK (daep_tenant_visible(tenant_id))
        """)


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return

    for table in ("project_gates", "project_workflows"):
        op.execute(f"DROP POLICY IF EXISTS daep_{table}_tenant ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
