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
