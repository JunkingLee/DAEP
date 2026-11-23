# RC25 Project and Task Visual Workspace

RC25 upgrades the existing lightweight dashboard without introducing a new frontend framework or changing the local-Agent execution boundary.

## Project overview

After a member selects a project, the workspace summarizes requirement count, task count, completed/in-progress/blocked tasks, project membership, and average task progress. It also displays the existing work-package health score and at-risk count. That health score is explicitly scoped to registered active work packages, not the entire project.

## Task board

Tasks are grouped into READY, IN_PROGRESS, BLOCKED, REVIEW, and DONE lanes. Users can filter by status and search task title or ID. Selecting a task opens a detail panel with status, progress, assignees, dependency IDs, child work packages, risk/SLA metadata, artifact counts, and the latest collaboration timeline entries.

All data is loaded through existing authenticated APIs. Project authorization remains enforced by the API. Dynamic text is HTML-escaped before rendering. The member token remains in page memory and is not persisted to browser local storage.

## Project-wide Agent work-package view

The dashboard also renders all active project work packages using the existing work-health API. Managers can filter by risk state and trigger the existing risk scan; cards show Agent/assignee, progress, SLA due date, and unresolved blocking dependencies. A card links back to its parent task and collaboration timeline. The scan action is shown only to project Owners/Managers (and platform admins); server-side project write authorization remains authoritative.

## Scope and limits

This is a project/coordination workspace, not an Agent Runtime console. It does not start, stop, execute, inspect, or wake local Agents. The project task API now includes each task's prerequisite IDs. The workspace renders an interactive dependency graph with arrows from prerequisite tasks to downstream tasks; graph nodes and prerequisite/downstream links open task details. Project Owners and Managers can edit prerequisite relationships from task details. The API enforces project write permission, rejects cross-project and self dependencies, detects cycles before replacing relationships, and records a `task.dependencies.updated` audit event. Other project members can inspect and navigate the graph but cannot modify it. Task/work-package state is displayed without adding task mutation controls.

## Verification

CI runs static dashboard assertions as part of pytest and extracts the inline dashboard script for `node --check`. These checks verify dashboard sections, dependency API wiring, and JavaScript syntax; they do not replace browser-based visual, accessibility, or end-to-end acceptance testing in the target deployment.
