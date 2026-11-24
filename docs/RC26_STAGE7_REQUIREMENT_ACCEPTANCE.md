# RC26 Stage 7 — Requirement Acceptance and Delivery Evidence

## Purpose

Connect requirement-level acceptance criteria to completed tasks, concrete delivery artifacts, and an explicit human decision. This is a governance and evidence gate, not an Agent execution feature.

## APIs

### Acceptance report

`GET /api/v1/requirements/{requirement_id}/acceptance-report`

Returns the requirement status and criteria, its tasks and artifact counts, whether all tasks are DONE, task IDs missing completion or evidence, and a conservative `ready_for_acceptance` flag. A requirement is ready only when it has at least one task, at least one criterion, every task is DONE, and every task has at least one artifact.

### Acceptance decision

`POST /api/v1/requirements/{requirement_id}/acceptance`

Example:

```json
{
  "decision": "APPROVE",
  "verified_criteria": [0, 1],
  "comment": "Reviewed test report and delivery artifacts"
}
```

- `verified_criteria` contains zero-based criterion indexes. Every criterion must be explicitly listed for approval.
- Approval requires every linked task to be DONE and each task to have at least one artifact.
- A successful approval changes requirement status to `ACCEPTED`.
- Rejection records a `requirement.acceptance.reject` audit event and leaves the requirement `OPEN`.
- A previously accepted requirement cannot be approved or rejected again through this endpoint.
- Decisions are project-scoped and restricted to Owner, Manager, Reviewer, or platform administrator.
- Acceptance events include the project and requirement IDs, verified criteria, comment, and linked task IDs in the existing audit stream.

## Workspace

The requirement list now exposes an acceptance report. Reviewers can inspect criteria, task status, and artifact counts, then explicitly enter verified criterion indexes before approving. The UI does not assume that the presence of an artifact proves a criterion; the human reviewer makes that determination.

## Validation

Automated tests cover the incomplete-task gate, artifact requirement, partial criterion verification, successful approval, duplicate decision conflict, audit visibility, role and project access restrictions, and frontend review hooks.

## Runtime boundary

DAEP records the evidence and human acceptance decision only. It does not execute, host, wake, or control member-local Agent Runtime processes.
