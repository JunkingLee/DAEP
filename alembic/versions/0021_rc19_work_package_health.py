"""RC19: work-package SLA and governance health state."""
from alembic import op
revision = "0021_rc19_health"
down_revision = "0020_rc18_corr"
branch_labels = None
depends_on = None
def upgrade():
    if op.get_bind().dialect.name != "postgresql": return
    op.execute("ALTER TABLE task_work_packages ADD COLUMN IF NOT EXISTS sla_due_at TEXT")
    op.execute("ALTER TABLE task_work_packages ADD COLUMN IF NOT EXISTS risk_state TEXT NOT NULL DEFAULT 'ON_TRACK'")
def downgrade():
    if op.get_bind().dialect.name != "postgresql": return
    op.execute("ALTER TABLE task_work_packages DROP COLUMN IF EXISTS risk_state")
    op.execute("ALTER TABLE task_work_packages DROP COLUMN IF EXISTS sla_due_at")
