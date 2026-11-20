"""RC15: tenant-scoped task work packages and parent-child coordination."""
from alembic import op

revision = "0018_rc15_task_work_packages"
down_revision = "0017_rc14_task_delegations"
branch_labels = None
depends_on = None

def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
    CREATE TABLE IF NOT EXISTS task_work_packages (
      id TEXT PRIMARY KEY,
      parent_task_id TEXT NOT NULL REFERENCES tasks(id),
      child_task_id TEXT NOT NULL UNIQUE REFERENCES tasks(id),
      project_id TEXT NOT NULL REFERENCES projects(id),
      tenant_id TEXT NOT NULL,
      assignee_member_id TEXT NOT NULL REFERENCES members(id),
      agent_name TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'ACTIVE',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_work_packages_parent ON task_work_packages(parent_task_id,status)")
    op.execute("ALTER TABLE task_work_packages ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE task_work_packages FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS daep_task_work_packages_tenant ON task_work_packages")
    op.execute("CREATE POLICY daep_task_work_packages_tenant ON task_work_packages USING (daep_tenant_visible(tenant_id)) WITH CHECK (daep_tenant_visible(tenant_id))")

def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TABLE IF EXISTS task_work_packages")
