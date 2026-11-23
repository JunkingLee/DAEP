"""RC39: enforce project lifecycle ownership in a SECURITY DEFINER trigger.

RLS remains responsible for tenant visibility and write isolation. The trigger
owns the domain-specific ACTIVE/CLOSED transition authorization so PostgreSQL
does not have to evaluate an ownership lookup against the UPDATE's new tuple
inside a row-policy WITH CHECK expression.
"""
from alembic import op

revision = "0029_rc39_lifecycle_guard"
down_revision = "0028_rc38_lifecycle_rls_fix"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return

    # The trigger runs with the migration-owned function privileges and checks
    # the authenticated member context against the project's real owner row.
    op.execute("""CREATE OR REPLACE FUNCTION daep_enforce_project_lifecycle_owner()
      RETURNS trigger
      LANGUAGE plpgsql
      SECURITY DEFINER
      SET search_path = public
      SET row_security = off
      AS $func$
      BEGIN
        IF NEW.status IS DISTINCT FROM OLD.status THEN
          IF NEW.status = 'CLOSED' THEN
            IF NOT daep_project_owner(OLD.id) THEN
              RAISE EXCEPTION 'Project owner approval required to close project'
                USING ERRCODE = '42501';
            END IF;
          ELSIF OLD.status = 'CLOSED' AND NEW.status = 'ACTIVE' THEN
            IF current_setting('app.lifecycle_action', true) IS DISTINCT FROM 'REOPEN'
               OR NOT daep_project_owner(OLD.id) THEN
              RAISE EXCEPTION 'Project owner approval required to reopen project'
                USING ERRCODE = '42501';
            END IF;
          END IF;
        END IF;
        RETURN NEW;
      END
      $func$""")

    op.execute("DROP TRIGGER IF EXISTS daep_projects_lifecycle_owner_guard ON projects")
    op.execute("""CREATE TRIGGER daep_projects_lifecycle_owner_guard
      BEFORE UPDATE OF status ON projects
      FOR EACH ROW
      EXECUTE FUNCTION daep_enforce_project_lifecycle_owner()""")

    # Tenant RLS is kept strict. Lifecycle authorization is enforced by the
    # trigger above, while the CHECK expression validates tenant ownership.
    op.execute("""DROP POLICY IF EXISTS daep_projects_tenant ON projects""")
    op.execute("""CREATE POLICY daep_projects_tenant ON projects
      USING (
        daep_tenant_visible(tenant_id)
        AND (
          status = 'ACTIVE'
          OR (
            status = 'CLOSED'
            AND current_setting('app.lifecycle_action', true) = 'REOPEN'
            AND daep_project_owner(id)
          )
        )
      )
      WITH CHECK (daep_tenant_visible(tenant_id))""")


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("DROP TRIGGER IF EXISTS daep_projects_lifecycle_owner_guard ON projects")
    op.execute("DROP FUNCTION IF EXISTS daep_enforce_project_lifecycle_owner()")
    op.execute("DROP POLICY IF EXISTS daep_projects_tenant ON projects")
    op.execute("""CREATE POLICY daep_projects_tenant ON projects
      USING (
        daep_tenant_visible(tenant_id)
        AND (
          status = 'ACTIVE'
          OR (
            status = 'CLOSED'
            AND current_setting('app.lifecycle_action', true) = 'REOPEN'
            AND daep_project_owner(id)
          )
        )
      )
      WITH CHECK (
        daep_tenant_visible(tenant_id)
        AND (
          status = 'ACTIVE'
          OR (status = 'CLOSED' AND daep_project_owner(id))
        )
      )""")
