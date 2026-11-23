# RC26 Stage 16 — Controlled Message Dispatch Recovery

Stage 16 adds a narrowly scoped, explicit recovery operation for a message that has no corresponding `message.created` outbox row:

`POST /api/v1/admin/messages/{message_id}/restore-outbox`

Request body requires an operator reason (1–1,000 characters). The operation:

- Is restricted to platform administrators.
- Locks the message row on PostgreSQL and serializes SQLite writes.
- Rechecks all existing `message.created` payloads for the message before inserting anything.
- Returns HTTP 409 if any matching dispatch record already exists, including a SENT/DEAD record; it never creates a second logical dispatch.
- Reconstructs the dispatch payload from the durable message row and task/project relationship.
- Inserts one PENDING outbox item and writes a `message.outbox.restored` audit event with actor, task, tenant, outbox ID, and operator reason.

This is an operator-triggered recovery for the specific missing-record invariant. It does not automatically replay DEAD items, alter message ACK state, or claim delivery success. The new test verifies missing-record restoration, required reason, admin authorization, duplicate prevention, reconstructed context, and audit evidence. It is deterministic database-level coverage, not a live broker or production recovery drill.
