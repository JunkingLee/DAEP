"""RC37: explicit Agent-to-task assignment lifecycle."""
from alembic import op

revision = "0027_rc37_agent_task_assignment"
down_revision = "0026_rc36_agent_identity"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("""CREATE TABLE IF NOT EXISTS agent_task_assignments(
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL REFERENCES tasks(id),
        project_id TEXT NOT NULL REFERENCES projects(id),
        agent_id TEXT NOT NULL REFERENCES agents(id),
        tenant_id TEXT NOT NULL,
        assigned_by_member_id TEXT NOT NULL REFERENCES members(id),
        status TEXT NOT NULL DEFAULT 'ASSIGNED'
          CHECK (status IN ('ASSIGNED','ACCEPTED','REVOKED','COMPLETED')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        accepted_at TEXT,
        completed_at TEXT,
        revoked_at TEXT
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_task_assignments_agent ON agent_task_assignments(agent_id,status,created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_task_assignments_task ON agent_task_assignments(task_id,status)")
    op.execute("ALTER TABLE agent_task_assignments ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS daep_agent_task_assignments_tenant ON agent_task_assignments")
    op.execute("""CREATE POLICY daep_agent_task_assignments_tenant ON agent_task_assignments
      USING (daep_tenant_visible(tenant_id))
      WITH CHECK (daep_tenant_visible(tenant_id))""")

def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP POLICY IF EXISTS daep_agent_task_assignments_tenant ON agent_task_assignments")
    op.execute("DROP TABLE IF EXISTS agent_task_assignments")
