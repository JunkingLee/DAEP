# RC16 work package lifecycle

## Agent result reporting

- Endpoint: `POST /api/v1/tasks/{child_task_id}/work-result`
- MCP tool: `report_work_package_result(task_id, outcome, summary, idempotency_key)`
- Outcomes: `COMPLETE` or `FAILED`.
- The caller must be assigned to the child task and the child must be an active registered work package.
- `COMPLETE` requires at least one artifact already attached to the child task. It sets progress to 100 and status to `REVIEW`; it never marks the task `DONE`.
- `FAILED` sets status to `BLOCKED` and progress to 0. A member/manager can coordinate remediation through existing assignment and progress workflows.
- An optional idempotency key is scoped to actor and child task. An identical replay returns the original event; a different payload under the same key returns 409.

## Parent completion gate

The existing reviewer endpoint remains the sole approval path. When approving a parent task that has active work packages, DAEP requires every child task to have status `DONE` and at least one artifact. A failed gate returns 409 with the pending child task IDs and child tasks missing artifacts. Reviewers approve child tasks individually before approving the parent.

The work summary includes each child artifact's ID, type, URI, commit SHA and timestamp. This allows a reviewer to inspect evidence rather than relying on an aggregate count.

## Runtime boundary

This is a task lifecycle and governance feature. DAEP stores reports, artifacts, assignments and durable inbox notifications. It does not launch, host, supervise, or wake a local Agent Runtime. MCP Host polling/reconnection is still required for delivery to an idle or sleeping Host.
