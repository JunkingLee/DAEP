# Code Quality Audit — RC9

Date: 2026-11-25  
Branch: `release/1.0.0-rc9`

## Executive Summary

RC9 has passed the blocking structural quality gate on the current branch. The historical duplicate-definition and duplicate-route findings below are retained as remediation history, not as current findings.

Current source snapshot:
- `app/main.py`: 4,347 lines.
- The blocking AST scanner reports zero duplicate top-level function names (within each scanned module) and zero duplicate direct `app.<method>()` route keys.
- CI job `quality-gate` enforces this scanner on every push and pull request.
- Latest recorded RC9 CI run `45567826933`: all 8 jobs succeeded, including quality-gate, Python 3.11/3.12/3.13, Chromium E2E, PostgreSQL migrations/RLS, container build and production Compose validation.

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
- This is a targeted fix, not a declaration that the full authorization matrix is complete. The remaining pass must still cover route-level negative tests for cross-tenant access, project roles, Agent grants, expired/revoked grants, and Worker identity.

## Next Quality Work

Prioritize in this order:

1. **Authorization matrix audit** — enumerate Member, Project Owner/Manager/Reviewer, Agent, Worker and System Admin operations; verify positive and negative cases, especially cross-Tenant and cross-Owner boundaries.
2. **Transaction and concurrency audit** — inspect commit/rollback behavior around state transitions, Grant expiry/revocation, Outbox claim/replay, idempotency and parent Work Package synchronization.
3. **Route inventory and API contract audit** — compare registered method/path/name/dependency sets with expected API contracts; include mounted routers and runtime-generated routes.
4. **Coverage quality** — report coverage by module and critical business path; do not optimize only for a global percentage.
5. **Incremental modularization** — extract one bounded domain at a time, preserving behavior with characterization tests and full CI after each step.

## Release Decision

Current code-level structural gate: **PASS**.

Current CI baseline: **PASS (8/8 jobs in run 45567826933)**.

This does not close the separate real-environment release gates. Real browser product acceptance, Production PostgreSQL backup/restore, and two-member/two-Agent interoperability remain NOT EXECUTED until evidence is collected in the target environment. See:
- `docs/RC9_RELEASE_READINESS.md`
- `docs/RC9_FINAL_EVIDENCE_PACKAGE.md`
- `docs/RC9_BROWSER_ACCEPTANCE_RUNBOOK.md`
- `docs/RC9_PRODUCTION_BACKUP_RESTORE_DRILL.md`
- `docs/RC9_AGENT_INTEROPERABILITY_DRILL.md`

No merge to `main` is implied by this audit.
