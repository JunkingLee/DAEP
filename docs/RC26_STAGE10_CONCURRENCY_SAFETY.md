# RC26 Stage 10 — Concurrent Outbox Claim Safety

## Scope

Stage 10 adds a deterministic concurrency test for the outbox's exclusive-lease invariant. Two independent worker requests begin at a barrier and compete to claim the same newly created notification while each request may claim a batch.

## Invariants verified

- The target outbox row is returned to exactly one worker.
- No outbox row ID appears in both workers' claim results.
- The claimed target is in `IN_FLIGHT` state and has a worker owner and an unguessable lease token.
- The test exercises the production database-specific claim strategy: SQLite uses `BEGIN IMMEDIATE`; PostgreSQL uses `SELECT ... FOR UPDATE SKIP LOCKED`.

## Test limits

This is an automated API-level concurrency test against the CI database backends. It does not simulate a distributed broker, network partition, process kill at every instruction boundary, or production-scale worker load. It does not establish that arbitrary MCP Hosts can be awakened while asleep. DAEP remains a governance and durable-work coordination platform; member-local Agent Runtime processes remain outside DAEP's control.

Run the focused test with:

```bash
pytest -q tests/test_api.py -k stage10_concurrent_outbox_claims
```
