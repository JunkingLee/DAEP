"""RC26: configurable project workflow and governance gates."""
from alembic import op
revision="0024_rc26_workflow_gates"
down_revision="0023_rc26_member_work_function"
branch_labels=None
depends_on=None
def upgrade():
    if op.get_bind().dialect.name != "postgresql": return
    op.execute("""CREATE TABLE IF NOT EXISTS project_workflows(project_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,config TEXT NOT NULL,updated_by TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(project_id) REFERENCES projects(id))""")
    op.execute("""CREATE TABLE IF NOT EXISTS project_gates(project_id TEXT NOT NULL,gate_key TEXT NOT NULL,tenant_id TEXT NOT NULL,config TEXT NOT NULL,updated_by TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(project_id,gate_key),FOREIGN KEY(project_id) REFERENCES projects(id))""")
def downgrade():
    if op.get_bind().dialect.name != "postgresql": return
    op.execute("DROP TABLE IF EXISTS project_gates")
    op.execute("DROP TABLE IF EXISTS project_workflows")
