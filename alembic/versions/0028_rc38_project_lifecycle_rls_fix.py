"""RC38: make the project owner predicate independent of caller RLS visibility."""
from alembic import op

revision = "0028_rc38_lifecycle_rls_fix"
down_revision = "0027_rc37_agent_task_assignment"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    # The predicate is SECURITY DEFINER because project lifecycle policies must
    # verify ownership even when project_members has FORCE ROW LEVEL SECURITY.
    # row_security=off makes a misconfigured function owner fail closed rather
    # than silently evaluating against a caller-filtered membership set.
    op.execute("""CREATE OR REPLACE FUNCTION daep_project_owner(project_id text)
      RETURNS boolean
      LANGUAGE sql
      STABLE
      SECURITY DEFINER
      SET search_path = public
      SET row_security = off
      AS $func$
        SELECT EXISTS (
          SELECT 1
          FROM project_members pm
          WHERE pm.project_id = $1
            AND pm.member_id = NULLIF(current_setting('app.member_id', true), '')
            AND pm.role = 'owner'
        )
      $func$""")
    op.execute("REVOKE ALL ON FUNCTION daep_project_owner(text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION daep_project_owner(text) TO PUBLIC")


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    # Restore the prior function contract without changing the lifecycle policy.
    op.execute("""CREATE OR REPLACE FUNCTION daep_project_owner(project_id text)
      RETURNS boolean
      LANGUAGE sql
      STABLE
      SECURITY DEFINER
      SET search_path = public
      AS $func$
        SELECT EXISTS (
          SELECT 1 FROM project_members pm
          WHERE pm.project_id = $1
            AND pm.member_id = current_setting('app.member_id', true)
            AND pm.role = 'owner'
        )
      $func$""")
    op.execute("GRANT EXECUTE ON FUNCTION daep_project_owner(text) TO PUBLIC")
