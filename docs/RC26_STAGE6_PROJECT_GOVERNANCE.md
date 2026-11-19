# RC26 Stage 6 — Project Governance Closure

## Scope

This stage closes the project-level governance loop with auditable human decisions and a measurable completion/responsibility snapshot. It does not change the local-Agent ownership boundary.

## Decision register

- `POST /api/v1/projects/{project_id}/decisions` records a decision, rationale, accountable project member, optional due date, and related task IDs.
- Only project owners/managers can record decisions.
- The accountable member must already belong to the project.
- Every related task must resolve to the same project; duplicate task IDs are rejected.
- The decision is stored as a `project.decision.recorded` event, preserving the original record in the existing audit stream.
- `GET /api/v1/projects/{project_id}/decisions` returns the project-scoped register, including recorder and accountable-member identities.

## Governance snapshot

`GET /api/v1/projects/{project_id}/governance` reports:

- Total tasks, status distribution, completed/open task counts, and completion percentage.
- Completion gate: `SATISFIED` only when the project contains at least one task and every task is `DONE`; `EMPTY` when there are no tasks; otherwise `OPEN`.
- Active work-package risk counts and a count of packages in `OVERDUE`, `BLOCKED_DEPENDENCY`, or `STALLED`.
- Assigned-task responsibility grouped by project member, with DONE, active, review, and blocked counts.

The completion gate is deliberately conservative: pending review or any other non-DONE task keeps it open. Risk counts are a separate signal and do not replace task status.

## Security and boundaries

Both read endpoints require project membership (or platform-admin access). Decision creation requires project owner/manager authorization. Cross-project task references and non-member accountable owners are rejected. Decisions are audit records, not workflow commands: they do not alter task assignments, delegate to Agents, or create/wake/control a local Agent Runtime.

## Validation

Automated API tests cover decision recording/listing, audit persistence, governance aggregation, project access restrictions, cross-project task rejection, and accountable-member validation. CI remains the authoritative execution result for this branch.
