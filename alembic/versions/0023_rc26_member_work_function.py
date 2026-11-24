"""RC26: project member work functions for role-aware workbenches."""
from alembic import op

revision = "0023_rc26_member_work_function"
down_revision = "0022_rc20_approvals"
branch_labels = None
depends_on = None

def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE project_members ADD COLUMN IF NOT EXISTS work_function TEXT NOT NULL DEFAULT 'other'")
    op.execute("UPDATE project_members SET work_function='other' WHERE work_function IS NULL OR work_function=''")
    op.execute("ALTER TABLE project_members ALTER COLUMN work_function SET DEFAULT 'other'")

def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE project_members DROP COLUMN IF EXISTS work_function")
