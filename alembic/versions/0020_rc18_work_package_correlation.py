"""RC18: stable work-package correlation identifiers."""
from alembic import op
revision = "0020_rc18_work_package_correlation"
down_revision = "0019_rc17_work_package_stall"
branch_labels = None
depends_on = None
def upgrade():
    if op.get_bind().dialect.name != "postgresql": return
    op.execute("ALTER TABLE task_work_packages ADD COLUMN IF NOT EXISTS correlation_id TEXT")
    op.execute("UPDATE task_work_packages SET correlation_id=id WHERE correlation_id IS NULL OR correlation_id=''")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_task_work_packages_correlation ON task_work_packages(correlation_id)")
def downgrade():
    if op.get_bind().dialect.name != "postgresql": return
    op.execute("DROP INDEX IF EXISTS uq_task_work_packages_correlation")
    op.execute("ALTER TABLE task_work_packages DROP COLUMN IF EXISTS correlation_id")
