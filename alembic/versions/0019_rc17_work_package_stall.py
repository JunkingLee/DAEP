"""RC17: stalled work-package tracking for manager-controlled reassignment."""
from alembic import op

revision = "0019_rc17_work_package_stall"
down_revision = "0018_rc15_task_work_packages"
branch_labels = None
depends_on = None

def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    # The application bootstrap may have created these columns before Alembic runs.
    op.execute("ALTER TABLE task_work_packages ADD COLUMN IF NOT EXISTS needs_attention INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE task_work_packages ADD COLUMN IF NOT EXISTS stalled_at TEXT")
    op.execute("ALTER TABLE task_work_packages ADD COLUMN IF NOT EXISTS stall_reason TEXT")

def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE task_work_packages DROP COLUMN IF EXISTS stall_reason")
    op.execute("ALTER TABLE task_work_packages DROP COLUMN IF EXISTS stalled_at")
    op.execute("ALTER TABLE task_work_packages DROP COLUMN IF EXISTS needs_attention")
