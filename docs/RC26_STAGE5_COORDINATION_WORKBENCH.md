# RC26 Stage 5 — Exception Coordination Workbench

## Purpose

Provide one project-scoped view for human triage across active Agent work packages and ordinary tasks.

## Coordination API

- `GET /api/v1/projects/{pid}/coordination` returns exception work packages, unclaimed tasks, tasks awaiting review, and pending delegations.
- Exception work packages include current task state, assignee, Agent registration/presence, SLA, stall reason, and unresolved dependency details.
- The endpoint is read-only and requires project membership/access. It does not assign work or send messages.

## Actions

- `POST /api/v1/projects/{pid}/work-packages/scan-health` refreshes SLA, dependency, review, and completion risk classifications.
- `POST /api/v1/projects/{pid}/work-packages/scan-stalled` marks tasks with no activity past the requested threshold; the workbench uses a one-hour threshold.
- `POST /api/v1/work-packages/{package_id}/reassign` can reassign a stalled package after a human selects a project member and one of that member's registered Agents. The existing API validates project membership and fresh Agent presence, records the reason, updates task assignment, and emits a durable notification.
- Unclaimed tasks, review queues, and pending delegations link directly to task detail and the collaboration timeline for human action.

## Safety and boundaries

- No automatic reassignment, assignment, or Agent wake-up is performed.
- The workbench never starts, hosts, controls, or supervises a local Agent Runtime.
- Agent presence is based on member-managed registration and heartbeat; a stale/offline Agent cannot be selected successfully by the reassignment API.
- The feed is a point-in-time snapshot; refresh it after any action.

## Validation

API tests cover project access isolation and exception/unclaimed-task aggregation. UI tests cover the coordination panel, stalled scan, and reassignment controls. CI remains the release gate; browser rendering and multi-computer Agent operation still require separate validation.