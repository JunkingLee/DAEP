# RC26 Stage 11 — Idempotency and State Transition Race Governance

## Goal

Stage 11 hardens two stateful API paths against concurrent requests:

1. work-result submission with the same idempotency key;
2. task review/approval transitions.

The goal is deterministic server-side behavior across the SQLite development/test path and PostgreSQL production path.

## Work-result idempotency

POST /api/v1/tasks/{task_id}/work-result now enters a serialized write transaction on SQLite and locks the work-package row on PostgreSQL.

Event creation with an idempotency key uses a database-level ON CONFLICT(idempotency_key) DO NOTHING insert followed by a read of the canonical event. This makes the unique idempotency constraint part of the normal request path rather than relying on a post-insert exception.

Consequences:

- concurrent requests with the same key and equivalent payload return the same event_id;
- only one task.work_package.reported event is persisted;
- reuse of the same key with a different payload returns HTTP 409;
- the losing concurrent request does not create a second governance event.

## Task review transition

POST /api/v1/tasks/{task_id}/review now serializes the state transition:

- SQLite starts the write transaction with BEGIN IMMEDIATE;
- PostgreSQL locks the task row with FOR UPDATE;
- the final update is conditional on status='REVIEW' and must affect exactly one row.

Therefore two concurrent approvals cannot both emit task.reviewed. One request completes the transition; the other receives HTTP 409 because the task is no longer awaiting review.

## Automated coverage

The Stage 11 tests cover:

- barrier-synchronized duplicate work-result submissions;
- canonical event identity and exactly-one governance event;
- same-key/different-payload conflict behavior;
- barrier-synchronized duplicate task approvals;
- exactly-one task.reviewed event.

These tests run in the existing Python matrix and PostgreSQL/Compose CI jobs.

## Scope and limitations

This is transactional concurrency governance inside DAEP's API/database boundary. It does not claim production-scale load testing, broker partition testing, or interoperability with arbitrary sleeping MCP Hosts.

DAEP remains a task/project/requirement/collaboration/governance platform. It does not create, host, control, or wake member-local Agent Runtime processes.
