# Code Quality Audit — RC9

Date: 2026-11-25

## Executive Summary

The current RC9 application is functionally mature, but the source tree still has a significant structural quality issue centered on `app/main.py`.

The file is approximately 12,356 lines and contains repeated top-level function definitions and repeated FastAPI route registrations. This is not treated as a cosmetic issue: Python resolves later function definitions while FastAPI keeps route registrations in declaration order, so the source-level function symbol and the effective HTTP route implementation can diverge.

## Current Findings

### P0 — No confirmed immediate production break from this scan

This scan did not by itself establish an exploitable authorization bypass or data-loss defect.

### P1 — Duplicate top-level functions

Static scan of `app/main.py` found 105 function names defined more than once.

The following core helpers are defined six times:

- `require_worker`
- `require_project_access`
- `task_project`
- `require_task_access`
- `event`
- `dashboard`
- OIDC helpers and handlers
- `create_project`
- `projects`
- multiple health/member/task handlers

Some repeated helpers are byte-for-byte/semantically equivalent, while some business handlers are different historical variants.

### P1 — Duplicate FastAPI routes

The scan found approximately 117 distinct method/path combinations, with 87 registered more than once.

Examples include:

- `GET /`
- `GET /health`
- `GET /readyz`
- `GET /api/v1/me`
- `POST /api/v1/projects`
- `GET /api/v1/projects`
- OIDC endpoints
- member endpoints
- requirement/task endpoints

Many are registered six times.

### P1 — Known example of semantic drift

`create_project` has six definitions. The first route implementation contains the intended RC9 behavior allowing a normal human Member to create a Project and become Owner.

Other historical definitions include versions that:

- do not enforce the same tenant rules; or
- require platform administration.

FastAPI will match the first registered route, while the Python module name `create_project` refers to the last definition after module import. Therefore these duplicate definitions are not equivalent source representations even when the HTTP route currently behaves correctly.

This is a strong reason not to remove duplicates using a simple “keep the last definition” rule.

### P1 — Existing helper deduplication is incomplete

The earlier helper-deduplication work was reverted after CI regression. The current branch therefore still contains the duplicated helpers.

## Recommended Remediation Strategy

Do **not** perform another blind whole-file deduplication.

Use a staged migration:

1. Freeze new feature additions to `app/main.py` except security/bug fixes.
2. Add a static duplicate-definition/duplicate-route detector as a non-blocking quality report first.
3. Establish characterization tests for the effective HTTP routes.
4. Extract shared infrastructure helpers first:
   - authentication/context
   - tenant access
   - project/task access
   - audit/event
   - worker/service access
5. Migrate one business domain at a time into routers/modules.
6. After each domain migration, run unit tests, PostgreSQL/RLS tests and Browser E2E.
7. Only after route parity is demonstrated should obsolete historical definitions be removed.
8. Finally make duplicate-route detection a blocking CI quality gate.

## Safe vs. Unsafe Changes

### Safe to automate

- Detect duplicate function names.
- Detect duplicate method/path registrations.
- Detect exact duplicate function bodies.
- Report file/line locations.
- Report route-order collisions.

### Requires behavior verification

- Removing duplicate route blocks.
- Choosing between different historical implementations.
- Moving routes between modules.
- Replacing authorization helpers.
- Changing route registration order.

## Current Decision

No production behavior was changed by this audit.

The codebase should now enter a dedicated **Code Quality / Modularization** phase before additional large feature work. The objective is to reduce structural risk without changing the established DAEP domain model or authorization semantics.
