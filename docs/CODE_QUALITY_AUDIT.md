# Code Quality Audit — RC9

Date: 2026-11-25  
Branch: `release/1.0.0-rc9`

## Executive Summary

RC9 has passed the blocking structural quality gate on the current branch. The historical duplicate-definition and duplicate-route findings below are retained as remediation history, not as current findings.

Current source snapshot:
- `app/main.py`: 4396 lines.
- The blocking AST scanner reports zero duplicate top-level function names (within each scanned module) and zero duplicate direct `app.<method>()` route keys.
- CI job `quality-gate` enforces this scanner on every push and pull request.
- Latest recorded RC9 CI run `45576103698`: all 8 jobs succeeded, including quality-gate, Python 3.11/3.12/3.13, Chromium E2E, PostgreSQL migrations/RLS, container build and production Compose validation.

A green structural gate is meaningful, but it is not a complete security audit, code-duplication audit, route-parity proof, or production acceptance.

## Historical Findings — Remediated at Structural Level

An earlier scan of `app/main.py` found:
- 105 duplicate top-level function names.
- 87 duplicate FastAPI method/path route keys.
- Approximately 12,356 lines in the file.

The duplicates were not removed with a blind “keep last definition” transformation. That approach was attempted, caused CI regressions, and was rolled back. Subsequent changes converged route/helper implementations in stages, with regression tests and CI checks.

The current scanner result supersedes those historical counts for its defined scope. The historical numbers are kept here to explain why the quality gate exists.

## Current Structural Findings

### PASS — Duplicate definitions and direct route registrations

The current scanner:
- Parses Python files under `app`, `daep_mcp`, `daep_agent_bridge`, and `daep_worker`.
- Detects duplicate top-level function names per module.
- Detects duplicate direct FastAPI route decorators of the form `@app.get/post/put/patch/delete/options/head/websocket("...")`.
- Exits non-zero if either category is detected.
- Runs as the blocking CI job `quality-gate`.

Latest observed result: zero duplicate function names and zero duplicate direct route keys.

### REMAINING — Main application module is still large

`app/main.py` remains approximately 4.3k lines. Although the duplicate-symbol/route issue is structurally controlled, the application is still relatively centralized.

Recommended future modularization domains:
1. Authentication and identity.
2. Tenant / project / task authorization.
3. Project and requirement workflows.
4. Task execution, Work Packages and Agent grants.
5. Collaboration sessions, messages and proposals.
6. Notifications, Inbox / Outbox and Worker operations.
7. Integrations, health and operational endpoints.

This should be a separate, incremental refactoring stream. Do not combine broad module extraction with release-blocking security fixes.

## Scanner Scope and Limitations

A zero result does **not** prove that:
- Two routers included under different prefixes cannot expose equivalent effective paths.
- Dynamically assembled paths or decorators are collision-free.
- Business logic is not duplicated under different function names.
- Two different functions do not implement subtly divergent versions of the same rule.
- Authorization is correct for every route and every actor type.
- Transaction boundaries, concurrency behavior or database isolation are correct.

The scanner intentionally checks a narrow, deterministic subset of structural hazards. It complements, but does not replace, route inventory tests, authorization tests, PostgreSQL/RLS tests, code review and runtime verification.

## Authorization Audit Update — 2026-11-25

The first focused authorization pass found inconsistent platform-admin checks in project workflow and gate administration:
- Workflow and project Gate configuration compared the account role directly to `admin`, bypassing the shared platform-admin predicate.
- Workflow-exit and project-gate enforcement treated any `members.role='admin'` row as platform admin without checking the platform tenant.

Corrected on `release/1.0.0-rc9`:
- All four checks now require the platform role **and** `tenant_id='tenant-default'`, consistent with `is_admin()`.
- Added a regression test for platform-admin identity scoping.
- Proposal withdrawal now validates the originating accepted Collaboration Grant, OPEN Session and active Task, so revoked/expired Agents cannot mutate pending proposals.
- Browser E2E now covers the revoked-grant withdrawal denial.
- This is a targeted fix, not a declaration that the full authorization matrix is complete. The remaining pass must still cover broader route-level negative tests for cross-tenant access, every project role, Agent grants, expired/revoked grants, and Worker identity.

### Second authorization finding — Agent identity management

The Agent token resolves to its human owner's Member ID for task attribution. Agent management routes previously relied on that ID alone in `_agent_owner()`, and the list/create/unbind routes did not consistently enforce a human actor type. An Agent token could therefore attempt to manage Agent identities through its owner's identity context.

Corrected on `release/1.0.0-rc9`:
- Added a shared `MEMBER` actor guard to Agent management operations.
- `_agent_owner()` now rejects Agent actors before owner-ID checks.
- Agent list/create/unbind routes explicitly require human Member authentication; detail/update/token/bind routes inherit the guard through `_agent_owner()`.
- Added regression coverage asserting Agent tokens receive 403 for list/create/detail/update/token rotate/token revoke/project bind/project unbind, with database state unchanged.
- CI run `45572688339` passed all 8 jobs, including Python 3.11/3.12/3.13 and Browser E2E.

This closes the identified Agent-to-Member management impersonation path; the broader authorization matrix remains in progress.

### Further project authorization findings — 2026-11-25

Two additional project-governance gaps were found and corrected:
- `POST /api/v1/projects/{pid}/members` previously allowed a project Owner or Manager to directly add another project Owner. The route now rejects direct Owner-role grants from project members; the platform administrator remains the explicit administrative exception. A regression test covers both project Owner and Manager attempts.
- Project-member removal revoked task grants, Agent bindings and Agent assignments, but left the departing Member's active Collaboration Grants intact. Removal now locks all affected grant tasks, revokes those Collaboration Grants, records audit events and queues a durable Member notification. The regression test exercises a real accepted Collaboration Grant and verifies it becomes REVOKED.

The current authorization tests also cover Agent-token attempts to list/create/detail/update Agents, rotate/revoke Agent tokens and bind/unbind project Agents. These operations now require a human Member actor rather than trusting the Owner Member ID carried by Agent identity context.

Latest full CI evidence for this batch: run `45573815527`, all 8 jobs successful.

### Third authorization finding — Agent-to-Member impersonation across business APIs

A broader route-level review found that Agent authentication intentionally carries the owning Member ID for attribution, but several Member-only routes did not independently check the actor type. A project-bound Agent could otherwise attempt to act through its Owner identity on profile/session, project and task-governance operations.

Corrected on `release/1.0.0-rc9`:
- Added a shared `require_member_actor()` guard.
- Protected Member profile read/update, password change and logout; protected the Member project-list endpoint.
- Protected project reopen and project approval decisions against Agent actors using an Owner Member ID.
- Restricted formal task workflow transitions, work-result reporting, human-to-human delegation create/respond/list, and generic Member message creation to human Members.
- Changed generic task authorization so Agent reads require a live accepted Task Execution Grant with `task.read`; project binding and legacy Agent assignment are not enough.
- Added regression coverage for Owner-profile integrity, token/logout integrity, project listing, approval state, project reopen, workflow transition, delegation, generic messaging and work-result denial.
- Added a grant lifecycle assertion: generic Agent task-event reads work with an accepted `task.read` grant and fail immediately after revocation.
- Static route review confirmed every `/internal/v1/*` endpoint invokes `require_worker()`; all four internal routes are Worker-only.

CI run `45575412495` passed all 8 jobs. Each Python version reported 263 passed and 2 skipped; Chromium Browser E2E, PostgreSQL migrations/RLS, Container Build, Production Compose and Quality Gate all succeeded.

### README architecture SVG rendering defect

The root English README and Chinese README referenced the correct relative path, but `docs/images/daep-architecture.svg` contained an extra closing `</g>` tag, making the SVG invalid XML. The malformed group closure was corrected. `tests/test_static_assets.py` now parses every `docs/images/*.svg` asset with Python's XML parser and verifies the SVG namespace, preventing malformed diagrams from silently reaching README again. The SVG validation test passed in CI run `45574650566`; the full current run `45575412495` also passed.

### Fourth authorization finding — Worker credential class separation

The dedicated Worker token was already checked for minimum length, constant-time comparison and inequality with the platform admin token. The review identified one remaining configuration hazard: an operator could accidentally reuse a Member or Agent token as `DAEP_WORKER_TOKEN`, collapsing the credential boundary.

Corrected on `release/1.0.0-rc9`:
- After validating the supplied Worker bearer, the API performs a privileged, read-only digest comparison against stored Member token digests and Agent token hashes.
- A collision is rejected with HTTP 503 and an explicit configuration error; no Worker operation runs.
- The service-context override is scoped and reset around the collision check.
- Regression tests cover both Member-token and Agent-token collisions and verify the Member request context remains usable afterward.

CI run `45576103698` passed all 8 jobs; each Python version reported 264 passed and 2 skipped. Worker credential separation is now enforced at runtime, while production secret injection and rotation remain deployment acceptance tasks.

## Next Quality Work

Prioritize in this order:

1. **Authorization matrix completion** — continue covering every mounted route, Project Owner/Manager/Reviewer distinctions, Agent collaboration-vs-execution grants, expiry races and cross-Tenant/cross-Owner boundaries. The highest-risk identity-impersonation paths above now have regression tests.
2. **Transaction and concurrency audit** — inspect commit/rollback behavior around state transitions, Grant expiry/revocation, Outbox claim/replay, idempotency and parent Work Package synchronization.
3. **Route inventory and API contract audit** — compare registered method/path/name/dependency sets with expected API contracts; include mounted routers and runtime-generated routes.
4. **Coverage quality** — report coverage by module and critical business path; do not optimize only for a global percentage.
5. **Incremental modularization** — extract one bounded domain at a time, preserving behavior with characterization tests and full CI after each step.

## Release Decision

Current code-level structural gate: **PASS**.

Current CI baseline: **PASS (8/8 jobs in run 45575412495)**.

This does not close the separate real-environment release gates. Real browser product acceptance, Production PostgreSQL backup/restore, and two-member/two-Agent interoperability remain NOT EXECUTED until evidence is collected in the target environment. See:
- `docs/RC9_RELEASE_READINESS.md`
- `docs/RC9_FINAL_EVIDENCE_PACKAGE.md`
- `docs/RC9_BROWSER_ACCEPTANCE_RUNBOOK.md`
- `docs/RC9_PRODUCTION_BACKUP_RESTORE_DRILL.md`
- `docs/RC9_AGENT_INTEROPERABILITY_DRILL.md`

No merge to `main` is implied by this audit.
