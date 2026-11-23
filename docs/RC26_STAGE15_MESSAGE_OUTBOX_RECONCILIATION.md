# RC26 Stage 15 — Message/Outbox Integrity Reconciliation

Stage 15 adds a platform-admin-only, read-only reconciliation endpoint:

- `GET /api/v1/admin/message-delivery-integrity?limit=5000`
- Cross-checks durable messages against `message.created` outbox payloads.
- Reports messages without an outbox record, duplicate dispatch records, orphaned records, malformed payloads, and tenant/recipient/task context mismatches.
- Bounds each scanned collection to 1–10,000 records and explicitly marks truncated reports; a truncated scan is never reported healthy.
- Returns identifiers and counts only, not message content.
- Performs no automatic repair or mutation. Operators must investigate findings before taking corrective action.

Important semantic distinction: an outbox item in `SENT` means the broker dispatch completed; it does not mean the recipient Agent/member acknowledged the message. Recipient ACK remains the message state machine and audit event.

The automated test injects duplicate and orphan outbox records, verifies they are detected, checks that the report is read-only, and verifies non-admin access is denied. This is deterministic database-level reconciliation coverage, not a live broker reconciliation or production incident drill.
