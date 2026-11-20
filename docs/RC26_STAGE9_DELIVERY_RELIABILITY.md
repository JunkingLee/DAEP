# RC26 Stage 9 — Delivery Reliability and Recovery

## Scope

Stage 9 adds a deterministic failure-injection test for transactional outbox lease recovery. It complements existing coverage for retry backoff, dead-letter replay, message ACK idempotency, stalled work-package detection, and manager-approved reassignment.

## Lease recovery scenario

1. Create a durable member notification and claim its outbox row with worker A.
2. Simulate worker A terminating before completion by expiring its lease in the test database.
3. Claim the expired row with worker B.
4. Verify the attempt counter increments and the lease token rotates.
5. Verify worker A's stale token cannot complete the recovered row.
6. Verify worker B can complete it exactly once and duplicate completion is rejected.
7. Verify the member inbox still contains exactly one notification.

## Reliability guarantees exercised

- Expired IN_FLIGHT work can be reclaimed by another worker.
- Lease ownership is fenced by both worker identity and a fresh unguessable lease token.
- A stale worker cannot acknowledge a lease after reclamation.
- Completion is not accepted twice.
- The durable inbox remains the source of truth and does not duplicate a notification when an outbox lease is recovered.

## Existing complementary coverage

The suite also covers retry scheduling after transient failure, dead-letter replay with an audited operator reason, idempotent message acknowledgement, stalled work-package scans, controlled reassignment, and idempotent work-result submission.

## Test boundary

Lease expiry is simulated by updating the test database timestamp. This is deterministic fault injection, not a test of real process termination, broker delivery semantics, network partitions, PostgreSQL concurrent-worker load, or a production incident drill. DAEP still does not wake or control member-local Agent Runtime processes.
