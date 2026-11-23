# RC26 Stage 12 — Cross-member Collaboration Consistency and Recovery Governance

## Goal

Stage 12 closes a remaining concurrency gap in cross-member work-package governance. A work package is a coordinated delivery boundary: its assignee, Agent identity, task state, review decision, notification, and audit trail must move consistently when human coordinators intervene.

## Serialized reassignment

Work-package reassignment now enters the serialized write path and locks the package row on PostgreSQL. This keeps the package assignment, task assignment row, reassignment notification/outbox record, and audit event inside one transaction boundary.

SQLite uses the existing `BEGIN IMMEDIATE` write serialization; PostgreSQL uses `FOR UPDATE` on the package row.

## Serialized work-package review

Work-package approval/rejection now uses the same transaction discipline. The package row is locked on PostgreSQL, and the child task transition is conditional on `status='REVIEW'`.

Two concurrent reviews therefore cannot both publish `task.work_package.reviewed`. One request performs the transition; the other receives HTTP 409 because the delivery is no longer awaiting review.

This is especially important for cross-member delivery because the review event is consumed by the parent-task governance and collaboration timeline.

## Automated coverage

A barrier-synchronized API test creates a member-local MCP Agent, submits artifact-backed work, moves the work package into review, and concurrently approves it twice. The test verifies exactly one successful approval and exactly one review governance event.

The existing Stage 8 two-member delivery acceptance E2E and Stage 9/10 delivery reliability tests remain complementary: Stage 12 focuses specifically on human governance races at the work-package boundary.

## Scope

This stage provides database transaction consistency and deterministic API behavior. It is not a production load test, network-partition drill, or proof of arbitrary MCP Host wake-up. DAEP still does not create, host, control, or wake member-local Agent Runtime processes.
