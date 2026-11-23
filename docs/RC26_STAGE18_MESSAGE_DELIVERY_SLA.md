# RC26 Stage 18 — Message Delivery SLA and Incident Governance

Adds a project-member-scoped read-only health report:

`GET /api/v1/projects/{project_id}/message-delivery-health?dispatch_sla_seconds=120&ack_sla_seconds=300&limit=100`

The report identifies missing/duplicate dispatch records, DEAD outbox rows, PENDING/IN_FLIGHT dispatches older than the dispatch SLA, and messages whose broker dispatch is SENT but whose recipient ACK exceeds the ACK SLA. The ACK clock starts at `sent_at`, never at message creation. Thresholds are bounded; the report is project-scoped and omits message content.

Managers/owners can record an incident review through:

`POST /api/v1/projects/{project_id}/message-delivery-incidents/{message_id}/review`

Allowed dispositions are `INVESTIGATING`, `RESOLVED`, and `ACCEPTED_RISK`; a required comment is stored in the append-only governance event `message.delivery.incident.reviewed`. This records human review only: it does not mutate delivery state, retry messages, or wake an Agent Runtime.

Automated tests cover DEAD and ACK-overdue classification, healthy acknowledged messages, project access isolation, manager-only review, and audit creation. These are deterministic database-level tests, not a live broker SLA or production alerting drill.
