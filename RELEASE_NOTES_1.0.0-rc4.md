# DAEP Enterprise 1.0.0-rc4

## Delivery reliability increment

- Collaboration message and outbox record are committed in the same SQLite transaction.
- Internal worker API supports bounded batch claims, leases, ownership-checked completion, retry scheduling with exponential backoff, and terminal `DEAD` status after eight failed attempts.
- Expired leases can be reclaimed by another worker.
- Durable member inbox remains the source of truth; WebSocket is only a best-effort wake-up channel.
- `/health` reports the number of pending/in-flight outbox records.

## Internal worker API

All endpoints require an administrator Bearer token:

- `POST /internal/v1/outbox/claim` with `{ "worker_id": "worker-1", "limit": 20, "lease_seconds": 60 }`
- `POST /internal/v1/outbox/{id}/complete` with `{ "worker_id": "worker-1" }`
- `POST /internal/v1/outbox/{id}/fail` with `{ "worker_id": "worker-1", "error": "..." }`

Workers must be idempotent: a worker may successfully deliver to an external broker and crash before marking the outbox row complete. In that case the lease expires and the record is delivered again. Use the outbox record ID as the downstream idempotency key. Never expose the admin token to developer workstations.

## Verification

- `pytest -q`: 10 passed.
- `python -m py_compile app/main.py daep_mcp/server.py`: passed.
- PostgreSQL, OIDC/SSO, a real broker worker, Docker build, MCP Host compatibility, load/security and disaster-recovery testing are not included in this release.

## Release status

Release Candidate only. Runtime database remains single-organization SQLite. The outbox provides durable handoff semantics, but actual external broker delivery requires a separately deployed worker and operational controls.
