"""RC35: project lifecycle status migration and PostgreSQL write boundary contract."""
from alembic import op

revision = "0025_rc35_project_lifecycle"
down_revision = "0024_rc26_workflow_gates"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'ACTIVE'")
    op.execute("UPDATE projects SET status='ACTIVE' WHERE status IS NULL OR status=''")
    op.execute("ALTER TABLE projects ALTER COLUMN status SET DEFAULT 'ACTIVE'")
    op.execute("ALTER TABLE projects ALTER COLUMN status SET NOT NULL")
    op.execute("ALTER TABLE projects DROP CONSTRAINT IF EXISTS projects_status_check")
    op.execute("ALTER TABLE projects ADD CONSTRAINT projects_status_check CHECK (status IN ('ACTIVE','CLOSED'))")
    op.execute("DROP POLICY IF EXISTS daep_projects_tenant ON projects")
    op.execute("""CREATE POLICY daep_projects_tenant ON projects
      USING (
        daep_tenant_visible(tenant_id)
        AND (
          status='ACTIVE'
          OR (
            status='CLOSED'
            AND EXISTS (
              SELECT 1 FROM project_members pm
              WHERE pm.project_id=projects.id
                AND pm.member_id=current_setting('app.member_id', true)
                AND pm.role='owner'
                AND current_setting('app.lifecycle_action', true)='REOPEN'
            )
          )
        )
      )
      WITH CHECK (
        daep_tenant_visible(tenant_id)
        AND (
          status='ACTIVE'
          OR (
            status='CLOSED'
            AND current_setting('app.lifecycle_action', true)='REOPEN'
          )
        )
      )""")

def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP POLICY IF EXISTS daep_projects_update ON projects")
    op.execute("DROP POLICY IF EXISTS daep_projects_insert ON projects")
    op.execute("DROP POLICY IF EXISTS daep_projects_select ON projects")
    op.execute("""CREATE POLICY daep_projects_tenant ON projects
      USING (daep_tenant_visible(tenant_id))
      WITH CHECK (daep_tenant_visible(tenant_id))""")
    op.execute("ALTER TABLE projects DROP CONSTRAINT IF EXISTS projects_status_check")
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS status")
