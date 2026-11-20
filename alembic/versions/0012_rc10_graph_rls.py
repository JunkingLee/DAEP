"""RC10 adds tenant isolation to project collaboration graph tables.

The graph tables do not duplicate tenant_id: ownership is derived through
their canonical parent project and member records. Policies use EXISTS joins
so orphaned or cross-tenant links are not visible to tenant-scoped sessions.
"""
from alembic import op

revision = "0012_rc10_graph_rls"
down_revision = "0011_rc9_rls_context"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # Requirements and tasks inherit ownership from their parent project.
    op.execute("ALTER TABLE requirements ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE requirements FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS daep_requirements_tenant ON requirements")
    op.execute("""
      CREATE POLICY daep_requirements_tenant ON requirements
      USING (EXISTS (
        SELECT 1 FROM projects p
        WHERE p.id = requirements.project_id AND daep_tenant_visible(p.tenant_id)
      ))
      WITH CHECK (EXISTS (
        SELECT 1 FROM projects p
        WHERE p.id = requirements.project_id AND daep_tenant_visible(p.tenant_id)
      ))
    """)

    op.execute("ALTER TABLE tasks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tasks FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS daep_tasks_tenant ON tasks")
    op.execute("""
      CREATE POLICY daep_tasks_tenant ON tasks
      USING (EXISTS (
        SELECT 1 FROM requirements r
        JOIN projects p ON p.id = r.project_id
        WHERE r.id = tasks.requirement_id AND daep_tenant_visible(p.tenant_id)
      ))
      WITH CHECK (EXISTS (
        SELECT 1 FROM requirements r
        JOIN projects p ON p.id = r.project_id
        WHERE r.id = tasks.requirement_id AND daep_tenant_visible(p.tenant_id)
      ))
    """)

    # Collaboration edges must connect resources and members in the same tenant.
    op.execute("ALTER TABLE project_members ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE project_members FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS daep_project_members_tenant ON project_members")
    op.execute("""
      CREATE POLICY daep_project_members_tenant ON project_members
      USING (
        EXISTS (SELECT 1 FROM projects p
                WHERE p.id = project_members.project_id AND daep_tenant_visible(p.tenant_id))
        AND EXISTS (SELECT 1 FROM members m
                    WHERE m.id = project_members.member_id AND daep_tenant_visible(m.tenant_id))
      )
      WITH CHECK (
        EXISTS (SELECT 1 FROM projects p
                WHERE p.id = project_members.project_id AND daep_tenant_visible(p.tenant_id))
        AND EXISTS (SELECT 1 FROM members m
                    WHERE m.id = project_members.member_id AND daep_tenant_visible(m.tenant_id))
      )
    """)

    op.execute("ALTER TABLE assignments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE assignments FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS daep_assignments_tenant ON assignments")
    op.execute("""
      CREATE POLICY daep_assignments_tenant ON assignments
      USING (
        EXISTS (SELECT 1 FROM tasks t
                JOIN requirements r ON r.id = t.requirement_id
                JOIN projects p ON p.id = r.project_id
                WHERE t.id = assignments.task_id AND daep_tenant_visible(p.tenant_id))
        AND EXISTS (SELECT 1 FROM members m
                    WHERE m.id = assignments.member_id AND daep_tenant_visible(m.tenant_id))
      )
      WITH CHECK (
        EXISTS (SELECT 1 FROM tasks t
                JOIN requirements r ON r.id = t.requirement_id
                JOIN projects p ON p.id = r.project_id
                WHERE t.id = assignments.task_id AND daep_tenant_visible(p.tenant_id))
        AND EXISTS (SELECT 1 FROM members m
                    WHERE m.id = assignments.member_id AND daep_tenant_visible(m.tenant_id))
      )
    """)

    op.execute("ALTER TABLE dependencies ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE dependencies FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS daep_dependencies_tenant ON dependencies")
    op.execute("""
      CREATE POLICY daep_dependencies_tenant ON dependencies
      USING (
        EXISTS (
          SELECT 1 FROM tasks a
          JOIN requirements ar ON ar.id = a.requirement_id
          JOIN projects ap ON ap.id = ar.project_id
          JOIN tasks b ON b.id = dependencies.depends_on_task_id
          JOIN requirements br ON br.id = b.requirement_id
          JOIN projects bp ON bp.id = br.project_id
          WHERE a.id = dependencies.task_id
            AND ap.tenant_id = bp.tenant_id
            AND daep_tenant_visible(ap.tenant_id)
        )
      )
      WITH CHECK (
        EXISTS (
          SELECT 1 FROM tasks a
          JOIN requirements ar ON ar.id = a.requirement_id
          JOIN projects ap ON ap.id = ar.project_id
          JOIN tasks b ON b.id = dependencies.depends_on_task_id
          JOIN requirements br ON br.id = b.requirement_id
          JOIN projects bp ON bp.id = br.project_id
          WHERE a.id = dependencies.task_id
            AND ap.tenant_id = bp.tenant_id
            AND daep_tenant_visible(ap.tenant_id)
        )
      )
    """)

def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table, policy in (
        ("dependencies", "daep_dependencies_tenant"),
        ("assignments", "daep_assignments_tenant"),
        ("project_members", "daep_project_members_tenant"),
        ("tasks", "daep_tasks_tenant"),
        ("requirements", "daep_requirements_tenant"),
    ):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
