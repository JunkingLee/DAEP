# DAEP Enterprise Release — 1.0.0-rc8

**Distributed Agentic Engineering Platform** is a task-centric engineering control plane. It manages organizations' project work, requirements, task assignments, collaboration messages, artifacts and acceptance workflow. Developers start and operate their own local Agent Runtime; DAEP does not create, host or control those runtimes. Local Agents connect through the MCP-compatible adapter.

## Quick start

```bash
cp .env.example .env
# Set DAEP_ADMIN_TOKEN and DAEP_WORKER_TOKEN to different unique random secrets (at least 32 characters each)
# For broker delivery also set DAEP_BROKER_WEBHOOK_URL and DAEP_BROKER_WEBHOOK_TOKEN (at least 32 characters)
docker compose -f docker-compose.rc8.yaml up --build -d
# Optional broker delivery (configure both broker URL and its independent credential):
docker compose -f docker-compose.rc8.yaml --profile broker up --build -d
```

The default Compose run starts the API. The optional `broker` profile starts the separate delivery worker. Open `http://localhost:8000/` for the lightweight dashboard and `http://localhost:8000/docs` for the API. `/health` is the unauthenticated health endpoint. Business APIs require a member Bearer token; OIDC callbacks and the Git webhook use their own authentication flows, while outbox endpoints require the dedicated worker credential.

The first administrator token is `DAEP_ADMIN_TOKEN`. Create individual members through `POST /api/v1/members`; the generated token is returned once. Deliver it over an approved secret channel. Do not share tokens or commit them to source control.

## Core workflow

1. Admin/member creates a project; creator becomes project owner.
2. Owner/manager adds members with project roles (`member`, `manager`, `reviewer`).
3. Create requirements and tasks; tasks can be assigned to multiple members.
4. Each developer's local Agent reads assigned tasks and the durable notification inbox through the local MCP adapter.
5. Assigned Agents report progress, blockers and artifacts. A 100% progress report moves the task to `REVIEW`, not `DONE`.
6. A project owner, manager or reviewer explicitly approves/rejects the task.

## Local MCP adapter

Install dependencies on the developer's own workstation and configure the Host to launch `daep_mcp/server.py` using that member's token. See `daep_mcp/README.md`. The adapter does not start an Agent Runtime and cannot force an idle MCP Host to wake its model. Platform messages remain in the durable inbox and can be polled after reconnecting. Message creation also writes a durable transactional outbox record; a separate worker can claim, retry and complete those records through the internal API. The separate broker worker uses its own `DAEP_WORKER_TOKEN`; do not reuse the platform admin token. Its HTTP gateway also requires an independent `DAEP_BROKER_WEBHOOK_TOKEN`. Outbox claims include a per-lease capability token, and gateway requests include the stable outbox ID for deduplication.

## Verification

- Python syntax compilation: passed.
- API and workflow tests: 26 passed.
- MCP SDK runtime and real Host compatibility: not verified in this offline build environment.
- Docker image build and production deployment: not run here.

## Release boundary

This is a release candidate, not a production-certified GA release. The current release supports tenant-scoped accounts/resources, a PostgreSQL compatibility path via `DATABASE_URL`, optional OIDC with state/nonce/PKCE protections, member token lifecycle, a standalone broker worker with a separate least-privilege credential and provider-neutral Git webhook ingestion. It is still a release candidate: no live PostgreSQL, external IdP, broker, Git provider, Docker build, load, disaster-recovery or independent security certification was performed in this offline build environment. PostgreSQL RLS and Alembic are implemented in RC8, but live PostgreSQL integration and RLS isolation testing remain required. See `docs/OUTBOX_WORKER.md` for downstream delivery semantics and `docs/SECURITY_AND_GAPS.md` before deployment. Do not use this baseline for regulated or sensitive workloads or expose it to the public internet without additional controls.


## RC6 enterprise hardening

RC6 hardens tenant-aware reads and legacy data cleanup, adds one-time OIDC state/nonce/PKCE, fixes PostgreSQL SQL compatibility, introduces a versioned additive migration ledger, and separates worker credentials from platform administration. See `RELEASE_NOTES_1.0.0-rc6.md`, `docs/POSTGRES_OIDC_TENANCY.md` and `docs/BROKER_WORKER.md`.

The broker worker is at-least-once and does not host or control Agent Runtime processes.

## RC7 additions

- Alembic migration history is introduced for additive schema changes; the application bootstrap remains responsible for the cross-database core schema.
- `daep_agent_bridge` is an optional workstation-side durable inbox bridge. It never starts or manages an Agent Runtime. It forwards a member's messages to a configured local command and ACKs only after successful exit.
- `docker-compose.rc7.yaml` is the RC7 deployment baseline.


## RC8 hardening

RC8 adds PostgreSQL transaction-local tenant context, explicit inbox tenant ownership, PostgreSQL Row-Level Security migrations (`0009_rc8_message_tenant`, `0010_rc8_postgres_rls`), and a PostgreSQL 17 Compose baseline (`docker-compose.rc8.yaml`). The API bootstraps the core schema, then applies Alembic migrations before serving traffic. Use a dedicated non-superuser PostgreSQL application role and validate RLS with multiple tenants before production. See `docs/POSTGRES_RLS_RC8.md`.
# DAEP


### Local Agent collaboration registry (RC13)

Members can register their own workstation-operated Agents per project, advertise capabilities and MCP protocol support, refresh presence, and discover other project members' Agents. DAEP stores only capability/presence metadata; it does not launch, host, supervise, or wake local Agent runtimes. Presence expires after 120 seconds without a heartbeat. Use the member's MCP adapter tools `register_local_agent`, `discover_project_agents`, and `heartbeat_local_agent`.

 
### Task delegation workflow (RC14)

An assigned member can offer a task to another project member's registered, recently-online local Agent. The recipient receives a durable `TASK_DELEGATION` inbox message and must explicitly accept or reject it. Acceptance adds the recipient as a task assignee; rejection leaves assignments unchanged. Offers have a bounded expiry (60 seconds to 7 days), and expired offers are marked when queried or answered. Delegation transitions are recorded in the task event history and delegation records are tenant-isolated by PostgreSQL RLS. MCP tools: `offer_task_delegation`, `respond_task_delegation`, and `list_task_delegations`.

This is a persistent offer/inbox workflow, not a remote execution command. DAEP cannot guarantee that a sleeping MCP Host or local Agent will wake up; recipients process the offer when their Host polls or reconnects.

 
### Multi-Agent work packages (RC15)

A project member with write access can split a parent task into child work packages and assign each package to another project member's registered, recently-online local Agent. The platform creates a child task, assignment, durable `WORK_PACKAGE_ASSIGNED` inbox message and audit event. Agents report progress, blockers and artifacts against their own child task. Parent-level summary endpoints aggregate package counts, average progress, blocked children and artifact counts; the parent task itself remains under the existing review/approval workflow.

MCP tools: `create_task_work_package`, `list_task_work_packages`, and `get_task_work_summary`. Work packages are tenant-isolated in PostgreSQL. This remains coordination metadata: DAEP does not execute, host or wake any local Agent.


### Work package result and parent completion gate (RC16)

A local Agent reports a work-package outcome with `POST /api/v1/tasks/{child_task_id}/work-result` (MCP: `report_work_package_result`). A `COMPLETE` report requires at least one previously submitted artifact and moves the child task to `REVIEW`; it does not approve the work. A `FAILED` report moves the child task to `BLOCKED` for follow-up. Optional idempotency keys make repeated identical reports safe and reject conflicting replays.

A reviewer must approve each child task through the existing review workflow. The parent task cannot be approved until every active child work package is `DONE` and each has at least one artifact. The parent still requires its own explicit review. Work summaries now include artifact references (URI and commit SHA), not only counts. These gates are workflow checks; DAEP still does not execute or wake local Agents.


### Stalled work-package governance (RC17)

Project owners/managers can scan a project for work packages with no task activity for a configurable interval (300 seconds to 7 days). The scan marks eligible active packages as needing attention and records a `task.work_package.stalled` event. It is an explicit API/MCP operation; DAEP does not silently move assignments or run an unconfigured background scheduler.

A manager must then explicitly reassign a marked package to another project member's registered, recently-online Agent, providing a reason. The reassignment updates the child-task assignment, clears the attention marker, writes a `task.work_package.reassigned` audit event, and creates a durable `WORK_PACKAGE_REASSIGNED` inbox/outbox notification. Packages remain active throughout, so the RC16 parent approval gate continues to include them.

MCP tools: `scan_stalled_work_packages` and `reassign_stalled_work_package`. This is human-governed recovery, not Agent Runtime supervision or automatic wake-up.


### Cross-member work-package observability (RC18)

Every work package receives a stable correlation ID propagated through assignment/reassignment inbox messages, lifecycle events, result reports and artifact submissions. Query `GET /api/v1/tasks/{parent_task_id}/work-timeline` (MCP: `get_task_work_timeline`) for a chronological view combining lifecycle events, durable messages and submitted artifacts. Access is inherited from the parent task's project authorization. This is coordination/audit visibility; DAEP does not inspect local Agent internals or guarantee delivery/wakeup.


### Work-package governance and health (RC19)

Work packages may be created with an optional `sla_seconds` value (300 seconds to 30 days). Managers can recalculate project risk with `POST /api/v1/projects/{project_id}/work-packages/scan-health` and read the report at `GET /api/v1/projects/{project_id}/work-health`. The report identifies overdue SLAs, unresolved task dependencies, stalled packages and completion/review states, with a project health score. Risk transitions are audited. Scans never auto-reassign, execute, start, stop or wake local Agents. MCP tools: `scan_project_work_health` and `get_project_work_health`.


### Project governance, approvals and audit export (RC20)

Project roles are explicitly separated: owners and managers may administer project membership; only owners may directly grant the manager role. Managers can submit role-change requests, and a different project owner must approve or reject them. Self-approval is forbidden, and stale requests fail if the target role changed before approval. APIs: `POST /api/v1/projects/{id}/role-change-requests`, `GET /api/v1/projects/{id}/approvals`, and `POST /api/v1/projects/{id}/approvals/{approval_id}/decision`.

Project audit records are available through `GET /api/v1/projects/{id}/audit` with event-type and cursor filters, or as CSV through `GET /api/v1/projects/{id}/audit.csv`. Both endpoints enforce project membership and tenant boundaries. MCP tools cover role-change requests, approval decisions and audit access.


## RC21 production operations

For new production deployments, use `compose.production.yaml` and follow [the RC21 production operations and recovery runbook](docs/RC21_PRODUCTION_OPERATIONS.md). The production topology separates bootstrap, runtime and privileged PostgreSQL identities; keeps PostgreSQL off published host ports; uses a non-root, read-only API container; and provides guarded PostgreSQL backup/restore scripts. The legacy `docker-compose.rc8.yaml` remains for compatibility and local development. Passing CI does not replace a production restore drill, security review or release-owner acceptance.
