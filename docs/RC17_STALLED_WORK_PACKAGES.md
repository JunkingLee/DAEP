# RC17 stalled work-package governance

## Detecting stalled work

Project owners and managers (or the platform administrator) may call:

`POST /api/v1/projects/{project_id}/work-packages/scan-stalled`

Body: `{"stale_after_seconds":3600}`. The interval is bounded to 300 seconds through 7 days. A package is eligible when it is active, has not been marked for attention, its child task is READY, IN_PROGRESS or BLOCKED, and the task's `updated_at` is older than the cutoff.

The scan sets `needs_attention`, `stalled_at` and `stall_reason`, and emits `task.work_package.stalled`. Repeated scans do not duplicate the same marker/event. Review and DONE tasks are not marked stalled.

## Manager-approved reassignment

`POST /api/v1/work-packages/{work_package_id}/reassign`

Body: `{"assignee_member_id":"...","agent_name":"...","reason":"..."}`. The package must already be marked for attention. The new assignee must be a member of the same project and tenant, and the selected Agent must be registered and recently online. The operation replaces the child-task assignment, clears the attention marker, emits `task.work_package.reassigned`, and writes a durable `WORK_PACKAGE_REASSIGNED` inbox/outbox notification for the new assignee.

There is no automatic reassignment. A scan only flags work for human review. Active package status is preserved, so the RC16 parent-task completion gate cannot be bypassed by marking a child stalled.

## MCP tools

- `scan_stalled_work_packages(project_id, stale_after_seconds=3600)`
- `reassign_stalled_work_package(work_package_id, assignee_member_id, agent_name, reason)`

## Runtime boundary

DAEP records task activity, governance markers, assignments, audit events and durable notifications. It does not start, host, supervise or wake a local Agent Runtime. Scanning is an explicit operation; deployment operators may schedule it externally if desired.
