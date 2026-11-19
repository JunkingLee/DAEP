# RC26 Stage 3 — Cross-member collaboration trace

## Purpose

Give project members a task-centric, auditable view of the collaboration lifecycle across member-owned local Agents. The view joins existing governance records; it does not introduce a new Agent execution service.

## Timeline API

`GET /api/v1/tasks/{parent_task_id}/work-timeline?limit=200`

The endpoint remains project/task-access scoped and clamps the requested limit to 1–500. Its response includes:

- Parent task governance events (including review and dependency changes), with actor member identity where available.
- Child work-package events, including result reporting and risk changes.
- Assignment/reassignment messages, message delivery status and acknowledgement timestamp.
- Submitted artifacts, including artifact type, URI, commit SHA and timestamp.
- Delegation offer and decision milestones, requester/recipient names, Agent name, reason, expiry and current state.
- Dependency edges for the parent and its child work packages, including prerequisite task title/status and a blocking boolean.
- Work-package summary with correlation ID, assigned member/Agent, progress, SLA and risk state.

The timeline is sorted chronologically and the limit is applied after aggregation. Delegation records provide the offer and current terminal decision milestones; the endpoint does not fabricate intermediate delivery or execution acknowledgements.

## Workspace

Task detail now shows:
1. Cross-member delegation history and response state.
2. Child work packages and their progress/risk.
3. Dependency edges and unresolved prerequisites.
4. A chronological event/message/artifact/delegation trace, including actor and message acknowledgement details where available.

## Safety and product boundary

This is a read-only collaboration/governance surface. It does not send messages, create delegations, approve results, invoke MCP methods, or start/wake/inspect/control member-local Agent Runtimes. Existing role checks and task-level access checks remain authoritative.

## Verification

Automated tests cover correlated work-package delivery, artifact and result reporting, delegation offer/accept milestones, dependency edge visibility, and the task detail UI sections. CI must pass on all supported Python versions, PostgreSQL migrations, container build and production Compose checks.
