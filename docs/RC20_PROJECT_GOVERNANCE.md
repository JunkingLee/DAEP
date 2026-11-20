# RC20 — Project governance, approvals and audit

## Project role matrix

| Role | Read project data | Create/update project work | Manage membership | Grant manager directly | Approve role requests |
|---|---:|---:|---:|---:|---:|
| Owner | Yes | Yes | Yes | Yes | Yes, except own request |
| Manager | Yes | Yes | Yes | No | No |
| Member | Yes | No (unless task-specific endpoint allows assigned work) | No | No | No |
| Reviewer | Yes | No | No | No | No |

Platform administrators retain their tenant-scoped administrative bypass. A project manager cannot promote another member to manager directly. They must submit a role-change request. An owner other than the requester must approve or reject it. Owners can also submit requests, but cannot approve their own requests.

## Approval lifecycle

1. Submit `POST /api/v1/projects/{project_id}/role-change-requests` with `member_id`, `new_role` and a reason.
2. Read pending requests with `GET /api/v1/projects/{project_id}/approvals?status=PENDING`.
3. A different project owner decides through `POST /api/v1/projects/{project_id}/approvals/{approval_id}/decision` with `decision=APPROVE|REJECT` and a reason.
4. Approval rechecks the target's previous role before applying the change. If the role changed meanwhile, the request is rejected as stale and must be resubmitted.
5. Requests, decisions and direct membership role assignments are written to the project audit stream.

Approval states are `PENDING`, `APPROVED` and `REJECTED`. The approval table has tenant-level PostgreSQL RLS.

## Audit access and export

- `GET /api/v1/projects/{project_id}/audit?limit=100&before={timestamp}&event_type={type}`
- `GET /api/v1/projects/{project_id}/audit.csv?limit=5000`

The JSON endpoint supports bounded page size (1–500), timestamp cursor and exact event-type filtering. CSV export is bounded to 10,000 records. Both require project membership or platform administrator access and include task-associated events plus project-level role governance events. CSV fields are quoted and escaped.

## MCP

- `request_project_role_change`
- `list_project_approvals`
- `decide_project_approval`
- `get_project_audit`
- `export_project_audit_csv`

The MCP adapter returns non-JSON API responses as a content-type/body object, so CSV exports remain usable.

## Security boundaries

Role approvals do not change Agent Runtime ownership. DAEP does not start, stop, supervise or wake local Agents. Audit export is project-scoped and tenant-scoped; it is not a platform-wide export endpoint.
