# RC9 Authorization Matrix

Date: 2026-11-25  
Branch: `release/1.0.0-rc9`  
Status: focused route-level matrix; remaining rows marked for further verification rather than assumed PASS.

This matrix describes the intended actor boundaries and the current implementation checks. It is not a substitute for the deployment-specific security review described in `SECURITY_AND_GAPS.md`.

## Actor boundaries

| Actor | Allowed operations | Explicitly denied / boundary |
|---|---|---|
| Platform Administrator | Platform-level tenant/member administration; cross-tenant project administration where the platform-admin predicate applies; operational admin endpoints | Platform privileges are recognized only when account role is `admin` **and** tenant is `tenant-default`. An admin-like role in a customer tenant is not a platform administrator. |
| Project Owner | Project governance; manage project membership; create and manage own Agents; authorize own Agents; manage task execution and collaboration grants; approve project-owner-only decisions; reopen a closed project | Cannot directly grant another project Owner through the member-add route. Ownership changes use the platform ownership process. Cannot authorize another Member's private Agent. |
| Project Manager | Day-to-day project operations; manage permitted membership changes; plan work; manage project workflow/gates where authorized; close a project when delivery obligations are satisfied | Cannot directly grant Manager or Owner roles; cannot reopen a closed project; cannot bypass formal role-change approval. |
| Project Reviewer | Review/approve eligible task, artifact-version and requirement acceptance work within the project | Cannot perform Owner/Manager project administration, manage Agent identity or change project membership. |
| Project Member / Assignee | Read project/task context within membership; update assigned work; submit artifacts; report progress/blocking; acknowledge own notifications | Cannot perform Owner/Manager governance. Assigned-task writes are scoped to the Member's own assignment. |
| Agent | Read a task with an active accepted Task Execution Grant containing `task.read`; report progress/blocking or submit evidence only when the matching execution scope is granted; read/write collaboration context only with a separate accepted Collaboration Grant and matching scope | Cannot act as its Owner Member; manage Member profile/password/session; list the Owner's projects; manage Agent identities; make project-governance decisions; reopen projects; transition formal workflow stages; create/respond to human delegations; send generic Member messages; report formal Work Package outcomes; review/approve/accept work. |
| Worker | Internal Outbox claim/complete/fail and collaboration-grant reminder dispatch using the dedicated Worker credential | Cannot use Member, Agent or platform-admin credentials as a Worker credential. No public Member/Agent API authority is implied. |

## Authorization domains are independent

| Domain | What it authorizes | What it does not authorize |
|---|---|---|
| Tenant membership | Visibility within the Member's Tenant | Project membership or Agent execution |
| Project membership | Project-level Member access according to Owner / Manager / Reviewer / Member role | Agent execution or Collaboration Session access |
| Agent Project Binding | Project-scoped Agent discovery/read access | Task Execution Grant or Collaboration Grant |
| Task Execution Grant | Specific Agent task actions, task, owner, tenant and expiry | Collaboration messages/proposals unless separately granted |
| Collaboration Grant | Specific Agent session/message/proposal actions and resource scope | Task progress, task status, artifact submission or review approval |
| Worker Token | Internal service endpoints | Member, Agent or project identity |

## Route-level controls verified in RC9

### Human Member identity

The shared `require_member_actor()` guard is applied to:
- `GET /api/v1/me`, `PATCH /api/v1/me`
- `POST /api/v1/auth/change-password`, `POST /api/v1/auth/logout`
- `GET /api/v1/projects`
- `POST /api/v1/projects/{pid}/reopen`
- `POST /api/v1/projects/{pid}/approvals/{approval_id}/decision`
- `POST /api/v1/tasks/{tid}/workflow-transition`
- `POST /api/v1/tasks/{tid}/work-result`
- Human delegation create/respond/list routes
- `POST /api/v1/messages`

### Agent task execution

- `require_agent_task_grant()` validates the Agent identity, owner, tenant, active Agent, current human assignee, Task/Project state, expiry, accepted status and requested action scope.
- Direct Agent progress, blocked and artifact operations require their matching execution scopes.
- Generic task reads now require an active accepted Task Execution Grant with `task.read`; legacy Agent assignment or Project Binding alone does not authorize them.
- Revoking a Task Execution Grant closes these task-read paths immediately.
- Agent review/approval endpoints reject Agent actors.

### Collaboration

- Collaboration operations require a separate accepted Collaboration Grant, valid session/project/task relationships, expiry and the specific collaboration scope.
- The Agent Owner is the only Member who may authorize their own Agent.
- Task Owner cannot authorize another Member's Agent.
- Removing an Agent Owner from a Project revokes that Member's active Collaboration Grants in the Project, emits audit events and queues notifications.

### Worker

All currently registered `/internal/v1/*` routes invoke `require_worker()`. The configured Worker secret is also checked against stored Member and Agent token digests, so a misconfigured Worker secret cannot alias either identity class:
- `POST /internal/v1/collaboration-grants/reminders/dispatch`
- `POST /internal/v1/outbox/claim`
- `POST /internal/v1/outbox/{outbox_id}/complete`
- `POST /internal/v1/outbox/{outbox_id}/fail`

## Regression evidence

The focused Agent identity regression test verifies:
- Agent cannot access or mutate its Owner's Member profile, password or logout session.
- Agent cannot list its Owner's projects.
- Project approval, reopen, workflow transition and formal Work Package result operations reject Agent tokens.
- Human delegation and generic Member messaging reject Agent tokens.
- Task event reads are denied without `task.read`, allowed with an accepted grant, and denied again after grant revocation.
- Denied operations do not mutate Owner profile state, project state or approval state.

Latest full CI run for this matrix update: `45576459940` — 8/8 jobs passed; Python 3.11/3.12/3.13 each reported 265 passed and 2 skipped; Browser E2E, PostgreSQL Migration/RLS, Container Build, Production Compose and Quality Gate passed.

## Remaining verification

The following still need dedicated negative tests or target-environment evidence:
1. Exhaustive route inventory for every mounted router, including routes that use project-level read access by design.
2. Complete Owner / Manager / Reviewer / Member permission matrix across every project governance and quality-policy endpoint.
3. Cross-Tenant attempts for every resource family, including historical/legacy rows and RLS behavior under production roles.
4. Concurrent revoke/expiry versus Agent read/write races on PostgreSQL, not only SQLite functional tests.
5. Concurrent revoke/expiry versus Agent read/write races on PostgreSQL, not only SQLite functional tests.

Do not mark these remaining items PASS based only on the focused tests above.
