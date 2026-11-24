# RC26 Stage 19 — Project Governance Message Reliability Integration

The existing project governance endpoint `GET /api/v1/projects/{pid}/governance` now includes a `message_delivery` section, integrating the Stage 18 project delivery SLA report with project governance.

The section contains checked-message count, dispatch and ACK state counts, active incident count, SLA policy, truncation indicator, and daily message-created/terminal-ACK volume since UTC midnight. Each current delivery incident is enriched with its latest governance review disposition and review timestamp. `UNREVIEWED` and `INVESTIGATING` remain open; `RESOLVED` and `ACCEPTED_RISK` are tracked separately as closed/accepted governance outcomes. Review comments are not copied into the aggregate snapshot.

The integration reuses project access controls and preserves project/tenant scope. It does not mutate delivery state, retry messages, or control Agent Runtime. The trend is message volume/terminal ACK volume, not a fabricated historical incident-rate series; incident history remains in the append-only audit stream.

Automated coverage verifies the governance snapshot reflects a DEAD message, review disposition changes from UNREVIEWED to RESOLVED, message content is absent, and project membership isolation is preserved.
