# RC35 · Project Lifecycle / PostgreSQL Boundary

## Scope

RC35 closes the database-lifecycle consistency gap introduced by project closure:

- projects.status is ACTIVE by default and can only be ACTIVE or CLOSED.
- SQLite legacy databases receive the column additively during init().
- PostgreSQL-managed databases receive the same contract through Alembic 0025_rc35_project_lifecycle.
- Closed projects remain readable.
- Normal project/task writes are rejected by the application once a project is CLOSED.
- Platform-admin task mutations are also frozen; admin status no longer bypasses the task-level closed-project check.
- PostgreSQL project RLS separates read visibility from lifecycle write eligibility.
- Owner reopen requires an explicit app.lifecycle_action=REOPEN context and the caller must be the project owner; platform-admin/service connections use the privileged DB role.

## Closure invariants

A project cannot close while it has:

1. unaccepted requirements;
2. non-DONE tasks;
3. ACTIVE work packages;
4. ACTIVE work packages marked needs_attention;
5. pending task delegations;
6. pending project approvals.

On successful closure an audit event project.closed is recorded.

## Reopen invariants

- Only a project Owner or platform administrator can reopen.
- Project Managers cannot self-reopen.
- Reopen requires a reason of at least 10 characters.
- Successful reopen records project.reopened.
- Reopen restores normal write access.

## PostgreSQL migration

Alembic revision: 0025_rc35_project_lifecycle
Down revision: 0024_rc26_workflow_gates

The migration adds the lifecycle status constraint and replaces the broad projects RLS policy with explicit SELECT / INSERT / UPDATE policies. Closed rows are not writable through normal project updates; an owner reopen must carry the explicit lifecycle action.

## Verification

- RC35 API tests cover SQLite upgrade, default ACTIVE, admin task freeze, real pending-delegation closure blocking, and migration contract.
- tests/postgres_rls_smoke.sql verifies tenant isolation plus the closed-project write freeze and explicit owner reopen path.

## Operational note

The privileged PostgreSQL connection remains required for platform-admin and internal-service operations. RLS is a defense-in-depth boundary; application authorization remains the source of the project workflow and role semantics.
