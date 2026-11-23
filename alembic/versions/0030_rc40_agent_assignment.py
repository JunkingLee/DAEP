"""RC40: serialize and uniquely constrain active Agent task grants."""
from alembic import op

revision = "0030_rc40_agent_assignment"
down_revision = "0029_rc39_lifecycle_guard"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("""
        DELETE FROM agent_task_assignments a
        USING agent_task_assignments b
        WHERE a.task_id=b.task_id
          AND a.agent_id=b.agent_id
          AND a.status IN ('ASSIGNED','ACCEPTED')
          AND b.status IN ('ASSIGNED','ACCEPTED')
          AND a.created_at < b.created_at
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_task_assignments_active
        ON agent_task_assignments(task_id, agent_id)
        WHERE status IN ('ASSIGNED','ACCEPTED')
    """)

def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS uq_agent_task_assignments_active")
