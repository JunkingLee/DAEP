"""RC13: project-scoped local Agent capability registry with tenant RLS."""
from alembic import op
import sqlalchemy as sa

revision = "0016_rc13_project_agents"
down_revision = "0015_rc12_outbox_lease_token"
branch_labels = None
depends_on = None

def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
    CREATE TABLE IF NOT EXISTS project_agents (
      id TEXT PRIMARY KEY,
      project_id TEXT NOT NULL REFERENCES projects(id),
      member_id TEXT NOT NULL REFERENCES members(id),
      tenant_id TEXT NOT NULL,
      agent_name TEXT NOT NULL,
      capabilities TEXT NOT NULL,
      protocols TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'AVAILABLE',
      metadata TEXT NOT NULL DEFAULT '{}',
      last_seen TEXT NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      CONSTRAINT uq_project_agents_identity UNIQUE(project_id,member_id,agent_name)
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_project_agents_discovery ON project_agents(project_id,status,last_seen)")
    op.execute("ALTER TABLE project_agents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE project_agents FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS daep_project_agents_tenant ON project_agents")
    op.execute("""
    CREATE POLICY daep_project_agents_tenant ON project_agents
    USING (daep_tenant_visible(tenant_id))
    WITH CHECK (daep_tenant_visible(tenant_id))
    """)

def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP TABLE IF EXISTS project_agents")
