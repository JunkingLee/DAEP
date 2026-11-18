"""RC17: stalled work-package tracking for manager-controlled reassignment."""
from alembic import op
import sqlalchemy as sa

revision = "0019_rc17_work_package_stall"
down_revision = "0018_rc15_task_work_packages"
branch_labels = None
depends_on = None

def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.add_column("task_work_packages", sa.Column("needs_attention", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("task_work_packages", sa.Column("stalled_at", sa.Text(), nullable=True))
    op.add_column("task_work_packages", sa.Column("stall_reason", sa.Text(), nullable=True))
    op.alter_column("task_work_packages", "needs_attention", server_default=None)

def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.drop_column("task_work_packages", "stall_reason")
    op.drop_column("task_work_packages", "stalled_at")
    op.drop_column("task_work_packages", "needs_attention")
