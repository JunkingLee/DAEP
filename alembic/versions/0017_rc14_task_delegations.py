"""RC14: persistent, tenant-isolated task delegation workflow."""
from alembic import op

revision = "0017_rc14_task_delegations"
down_revision = "0016_rc13_project_agents"
branch_labels = None
depends_on = None

def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
    CREATE TABLE IF NOT EXISTS task_delegations (
      id TEXT PRIMARY KEY,
      task_id TEXT NOT NULL REFERENCES tasks(id),
      project_id TEXT NOT NULL REFERENCES projects(id),
      tenant_id TEXT NOT NULL,
      requester_member_id TEXT NOT NULL REFERENCES members(id),
      recipient_member_id TEXT NOT NULL REFERENCES members(id),
      agent_name TEXT NOT NULL,
      reason TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'PENDING',
      message_id TEXT,
      expires_at TEXT NOT NULL,
      responded_at TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_delegations_recipient ON task_delegations(recipient_member_id,status,expires_at)")
    op.execute("ALTER TABLE task_delegations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE task_delegations FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS daep_task_delegations_tenant ON task_delegations")
    op.execute("""
    CREATE POLICY daep_task_delegations_tenant ON task_delegations
    USING (daep_tenant_visible(tenant_id))
    WITH CHECK (daep_tenant_visible(tenant_id))
    """)

def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TABLE IF EXISTS task_delegations")
