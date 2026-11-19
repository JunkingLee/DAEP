# RC26 Stage 14 — Message Acknowledgement Consistency

Stage 14 closes the remaining consistency gap at the member-to-member message acknowledgement boundary.

## Changes

- Message acknowledgement now loads the message task and tenant context before the terminal transition.
- The existing conditional PENDING -> ACKNOWLEDGED/REJECTED update remains the single-winner guard for concurrent ACK requests.
- Only the request that changes the message state emits message.acknowledged.
- The acknowledgement audit event now carries the original task ID and tenant, so task collaboration timelines can observe the ACK without losing task context.
- Repeated ACKs with the same terminal status remain idempotent; a different terminal status returns 409 Conflict.

## Verification

Added a barrier-synchronized API test that sends one task-scoped message and performs two concurrent acknowledgements. The test requires one 200, one 409, exactly one acknowledgement event, and verifies that the event remains attached to the originating task.

This verifies deterministic database-level concurrency behavior; it is not a production broker or network partition drill. DAEP still does not create, host, control, or wake member-local Agent Runtime processes.