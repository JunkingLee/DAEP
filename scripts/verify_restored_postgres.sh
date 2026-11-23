#!/bin/sh
set -eu

compose=${DAEP_COMPOSE_FILE:-compose.production.yaml}
target=${DAEP_RESTORE_DATABASE:-daep_restore}
: "${DAEP_RESTORE_DATABASE:?Set DAEP_RESTORE_DATABASE to the isolated restored database}"

command -v docker >/dev/null 2>&1 || { echo "docker is required" >&2; exit 2; }
command -v alembic >/dev/null 2>&1 || { echo "alembic is required; install project requirements first" >&2; exit 2; }

expected_head=$(alembic heads | awk 'NR == 1 { print $1 }')
[ -n "$expected_head" ] || { echo "Unable to determine Alembic head" >&2; exit 2; }

actual_head=$(docker compose -f "$compose" exec -T postgres \
  psql -U daep_bootstrap -d "$target" -v ON_ERROR_STOP=1 -Atqc \
  "SELECT version_num FROM alembic_version")
[ "$actual_head" = "$expected_head" ] || {
  echo "Alembic revision mismatch: expected $expected_head, got $actual_head" >&2
  exit 1
}

result=$(docker compose -f "$compose" exec -T postgres \
  psql -U daep_bootstrap -d "$target" -v ON_ERROR_STOP=1 -Atqc "
    SELECT
      (SELECT count(*) = 15 AND bool_and(c.relrowsecurity AND c.relforcerowsecurity)
       FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
       WHERE n.nspname='public' AND c.relname IN (
         'members','projects','events','artifacts','outbox','messages',
         'project_agents','task_delegations','task_work_packages','project_approvals',
         'requirements','tasks','project_members','assignments','dependencies'))
      AND
      (SELECT count(*) = 15 FROM pg_policies
       WHERE schemaname='public' AND policyname IN (
         'daep_members_tenant','daep_projects_tenant','daep_events_tenant',
         'daep_artifacts_tenant','daep_outbox_tenant','daep_messages_tenant',
         'daep_project_agents_tenant','daep_task_delegations_tenant',
         'daep_task_work_packages_tenant','daep_project_approvals_tenant',
         'daep_requirements_tenant','daep_tasks_tenant',
         'daep_project_members_tenant','daep_assignments_tenant','daep_dependencies_tenant'))
      AND (SELECT count(*) = 1 FROM pg_proc WHERE proname='daep_authenticate_member' AND prosecdef)
      AND (SELECT count(*) = 1 FROM pg_roles WHERE rolname='daep_runtime' AND rolcanlogin AND NOT rolbypassrls)
      AND (SELECT count(*) = 1 FROM pg_roles WHERE rolname='daep_privileged' AND NOT rolcanlogin AND NOT rolbypassrls)
      AND (SELECT count(*) = 1 FROM pg_roles WHERE rolname='daep_privileged_login' AND rolcanlogin AND NOT rolbypassrls)
      AND (SELECT count(*) = 1 FROM pg_roles WHERE rolname='daep_authenticator' AND NOT rolcanlogin AND rolbypassrls)
      AND pg_has_role('daep_privileged_login','daep_privileged','MEMBER');
  ")
[ "$result" = "t" ] || {
  echo "Restored database failed schema, RLS, auth-function, or role validation" >&2
  exit 1
}

echo "PASS: restored database revision=$actual_head; required tables, forced RLS policies, auth function, and role boundaries verified."
