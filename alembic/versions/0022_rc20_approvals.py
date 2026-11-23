"""RC20: project approval workflow and tenant isolation."""
from alembic import op
revision = "0022_rc20_approvals"
down_revision = "0021_rc19_health"
branch_labels = None
depends_on = None
def upgrade():
    if op.get_bind().dialect.name != "postgresql": return
    op.execute("""CREATE TABLE IF NOT EXISTS project_approvals (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
        tenant_id TEXT NOT NULL, requester_member_id TEXT NOT NULL REFERENCES members(id),
        action TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING',
        decided_by TEXT, decision_reason TEXT, created_at TEXT NOT NULL, decided_at TEXT)""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_project_approvals_status ON project_approvals(project_id,status,created_at)")
    op.execute("ALTER TABLE project_approvals ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE project_approvals FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS daep_project_approvals_tenant ON project_approvals")
    op.execute("""CREATE POLICY daep_project_approvals_tenant ON project_approvals
        USING (daep_tenant_visible(tenant_id)) WITH CHECK (daep_tenant_visible(tenant_id))""")
def downgrade():
    if op.get_bind().dialect.name != "postgresql": return
    op.execute("DROP TABLE IF EXISTS project_approvals")
