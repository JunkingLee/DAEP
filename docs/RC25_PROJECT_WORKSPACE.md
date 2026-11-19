# RC25 Project and Task Visual Workspace

RC25 upgrades the existing lightweight dashboard without introducing a new frontend framework or changing the local-Agent execution boundary.

## Project overview

After a member selects a project, the workspace summarizes requirement count, task count, completed/in-progress/blocked tasks, project membership, and average task progress. It also displays the existing work-package health score and at-risk count. That health score is explicitly scoped to registered active work packages, not the entire project.

## Task board

Tasks are grouped into READY, IN_PROGRESS, BLOCKED, REVIEW, and DONE lanes. Users can filter by status and search task title or ID. Selecting a task opens a detail panel with status, progress, assignees, dependency IDs, child work packages, risk/SLA metadata, artifact counts, and the latest collaboration timeline entries.

All data is loaded through existing authenticated APIs. Project authorization remains enforced by the API. Dynamic text is HTML-escaped before rendering. The member token remains in page memory and is not persisted to browser local storage.

## Scope and limits

This is a project/coordination workspace, not an Agent Runtime console. It does not start, stop, execute, inspect, or wake local Agents. The UI visualizes dependency identifiers rather than rendering a graph editor, and displays task/work-package state without adding task mutation controls. Those can be considered in later product increments.

## Verification

CI runs static dashboard assertions as part of pytest. These assertions verify dashboard sections and API wiring; they do not replace browser-based visual, accessibility, or end-to-end acceptance testing in the target deployment.
