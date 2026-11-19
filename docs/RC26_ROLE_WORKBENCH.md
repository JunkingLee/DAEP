# RC26 Role Workbench

## Scope

The DAEP web shell now exposes a project-scoped **My Workbench** entry.

The workbench is presentation-layer aggregation over existing project APIs; it does not create a new authorization boundary.

## Role views

- **Developer / member**: own tasks, active work, own Work Packages, risks and collaboration entry points.
- **Tester**: own tasks, validation/review queue and acceptance-oriented entry points.
- **Reviewer**: review-oriented queue using the same project-scoped task context.
- **Project Owner / Manager**: project task distribution, exception work packages, pending reviews and pending delegations.
- **Product / Architect**: own-work view with the same project-scoped task and Work Package aggregation.
- **Platform Admin**: retains platform-wide navigation and can inspect project workbench data subject to backend authorization.

## Design constraints

1. Project membership and project role remain the source of authorization.
2. UI role navigation only controls presentation; it is not a security boundary.
3. Agent runtime remains local to each member computer. The workbench only shows DAEP's registered Agent and collaboration state.
4. Workbench data is derived from existing task, work-health and coordination APIs to avoid duplicating workflow state.

## Access

The workbench is available from the left navigation after authentication and project selection. It follows the selected project's role/work-function context, so one user can see different workbench views when switching projects.


## Tester execution flow

Tester / reviewer workbench now exposes task-level test actions using existing governed APIs:
- update progress to 50% for in-progress validation;
- update progress to 100% to enter REVIEW;
- mark a task BLOCKED with a reason when validation is blocked;
- submit test-report / acceptance evidence through the durable artifact API;
- open the requirement acceptance report from the workbench when a requirement reference is available.

The UI does not introduce a separate defect entity. Blocking remains task governance, while artifacts provide durable verification evidence and the existing Review / Requirement Acceptance APIs remain the approval boundary.
