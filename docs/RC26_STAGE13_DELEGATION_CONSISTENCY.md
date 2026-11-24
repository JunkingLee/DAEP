# RC26 Stage 13 — Delegation Decision Consistency

Stage 13 hardens cross-member task delegation state transitions at the collaboration boundary.

## Scope

A delegation offer is a durable governance object. Its terminal decision must be single-winner even when two requests arrive concurrently, and expiration must produce at most one audit event.

## Implementation

- `POST /api/v1/delegations/{delegation_id}/respond` now serializes the delegation row before evaluating and applying a decision.
- SQLite uses `BEGIN IMMEDIATE`; PostgreSQL uses `SELECT ... FOR UPDATE`.
- The terminal `PENDING -> ACCEPTED/REJECTED` update is conditional and its affected-row count is checked.
- Only the request that actually wins the state transition emits `task.delegation.accepted` or `task.delegation.rejected`.
- Concurrent decisions therefore converge to one successful response and one `409 Conflict`.
- Expiration paths in task/project delegation reads now emit `task.delegation.expired` only when the conditional transition actually changes the row.
- This preserves durable delegation state, assignment state, notification delivery, and audit evidence without allowing duplicate governance events.

## Verification

Added barrier-synchronized API tests covering:

1. concurrent `ACCEPT` versus `REJECT` on one delegation;
2. exactly one terminal delegation audit event;
3. concurrent expiration observation without duplicate `task.delegation.expired` events.

This is deterministic concurrency coverage, not a production-scale load test or broker partition drill. DAEP still does not create, host, control, or wake member-local Agent Runtime processes.