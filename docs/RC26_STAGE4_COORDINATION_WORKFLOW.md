# RC26 Stage 4 — Human Coordination Workflow

## Goal

Turn the existing collaboration APIs into a complete human-controlled work-package lifecycle:

1. inspect capability matches;
2. manually choose a member + registered local Agent;
3. create a bounded work package with dependencies and optional SLA;
4. receive durable assignment notification;
5. submit artifacts and a result;
6. review, approve, or reject the result;
7. on rejection, continue the same child task and resubmit;
8. keep the parent task governed by the existing review gate.

## Review semantics

- POST /api/v1/work-packages/{package_id}/review
- Only platform administrators or project Owner/Manager/Reviewer can review.
- The package must be active and its child task must be REVIEW.
- APPROVE requires at least one artifact and moves the child task to DONE.
- REJECT moves the child task back to IN_PROGRESS at 90%, allowing the assignee to continue and resubmit.
- The review is recorded as task.work_package.reviewed and therefore appears in the collaboration timeline.

## UI workflow

The task detail view now provides:

- manual work-package creation;
- project-scoped member and Agent selection;
- optional SLA and dependency selection;
- one-click use of an eligible capability-match candidate;
- review approve/reject actions for reviewable packages;
- direct navigation to the child work-package task.

## Boundary

This workflow is orchestration and governance only. DAEP does not create, host, control, or wake local Agent Runtime processes. Agent availability remains based on the member's own registration and heartbeat.