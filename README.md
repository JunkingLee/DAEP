# DAEP Enterprise Release — 1.0.0-rc25

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

- Python 3.11/3.12/3.13 CI tests: 45 passed on each version.
- PostgreSQL 17 migrations and RLS isolation: passed in CI.
- Production Compose rendering: passed in CI with required secret interpolation.
- Production container build and non-root runtime check: passed in CI.
- Cross-member Agent collaboration end-to-end acceptance: passed in CI.
- Real MCP Host compatibility, live TLS/OIDC/webhooks/broker and production deployment: still require deployment-owner acceptance.

## Release boundary

This is a release candidate, not a production-certified GA release. The current release supports tenant-scoped accounts/resources, a PostgreSQL compatibility path via `DATABASE_URL`, optional OIDC with state/nonce/PKCE protections, member token lifecycle, a standalone broker worker with a separate least-privilege credential and provider-neutral Git webhook ingestion. It is still a release candidate: no live PostgreSQL, external IdP, broker, Git provider, Docker build, load, disaster-recovery or independent security certification was performed in this offline build environment. PostgreSQL RLS and Alembic are implemented in RC8, but live PostgreSQL integration and RLS isolation testing remain required. See `docs/OUTBOX_WORKER.md` for downstream delivery semantics and `docs/SECURITY_AND_GAPS.md` before deployment. Do not use this baseline for regulated or sensitive workloads or expose it to the public internet without additional controls.


## RC22 candidate acceptance

RC22 adds automated production Compose validation, a production smoke-check script, and an end-to-end cross-member Agent collaboration acceptance path covering delegation, explicit acceptance, work-package delivery, durable message ACK, artifact/result reporting, parent review gating, correlation timeline and outbox consumption. See `docs/RC22_CANDIDATE_ACCEPTANCE.md` and `scripts/production_smoke.sh`.

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

## RC23 release safety gate

RC23 hardens PostgreSQL restore safety (source-database refusal, empty-target guard, atomic restore) and adds rendered production Compose security assertions to CI. See `docs/RC23_RELEASE_SAFETY.md` and `scripts/verify_production_compose.py`. RC23 remains a release candidate; live deployment, external integrations, encrypted off-host backup/restore, and product-owner approval remain required before GA.

## RC24 restored database verification

After restoring a backup into a separately provisioned empty database, run `DAEP_RESTORE_DATABASE=<target> scripts/verify_restored_postgres.sh`. The gate compares the restored Alembic revision with the repository head and verifies the 15 tenant-scoped tables, forced RLS policies, narrow authentication function, and database-role boundaries before traffic cutover. See `docs/RC24_RESTORE_VERIFICATION.md`. CI checks the verifier's shell syntax and static guardrails; it does not claim a live disaster-recovery drill.

## RC25 project and task visual workspace

The existing lightweight dashboard now provides project metrics, a five-lane task board with search/status filters, and task detail panels showing assignees, dependencies, multi-Agent work packages, SLA/risk metadata, artifacts and collaboration timeline. The project health score is explicitly scoped to registered active work packages. The workspace includes an interactive dependency graph and a manager-only dependency editor with same-project and cycle guards, plus a project-wide work-package risk board and manager-triggered risk scan. See `docs/RC25_PROJECT_WORKSPACE.md`. The dashboard uses existing authenticated APIs and does not operate local Agent runtimes.

## RC26 Stage 1 — Local Agent collaboration topology

The dashboard now combines the project-scoped Agent registry and active work-package health data to show each registered local Agent, its member identity, reported presence, last heartbeat, declared MCP/protocol capabilities, and associated work packages. Unmatched work packages are surfaced separately. A project-wide delegation board tracks pending, accepted, rejected and expired cross-member task offers and links them to task timelines. Presence is informational and uses the existing freshness window; DAEP does not host, start, stop, inspect or wake local Agent Runtime processes. See `docs/RC26_AGENT_TOPOLOGY.md`.


## RC26 Stage 2 — Explainable local Agent matching

The project-scoped `GET /api/v1/projects/{project_id}/agent-matches` endpoint ranks registered local Agents against a comma-separated required-capability list and protocol (MCP by default). Each result reports matched and missing capabilities, presence freshness, availability, protocol compatibility, score and an explicit eligibility decision. Results are recommendations only: the endpoint does not assign tasks, create delegations, send messages, invoke an MCP tool or control a local Agent Runtime. Only recently-heartbeating `AVAILABLE` Agents with every requested capability and the requested protocol are marked eligible. See `docs/RC26_STAGE2_AGENT_MATCHING.md`.


## RC26 Stage 3 — Cross-member collaboration trace

The task work timeline now includes parent-task governance events, child work-package events, delivery artifacts, message acknowledgement state, and delegation offer/decision milestones with requester and recipient identities. It also returns the dependency edges for the parent task and its work-package children, including prerequisite status and whether each edge is currently blocking. The task detail view presents delegation history, work packages, dependency edges, and a chronological collaboration trace. This is a read-only governance view: it does not invoke or wake any member-local Agent Runtime. See `docs/RC26_STAGE3_COLLABORATION_TRACE.md`.


## RC26 Stage 4 — Human Coordination Workflow

Stage 4 completes the human-facing work-package loop without taking ownership of any local Agent Runtime:

- Task detail can create multiple Agent work packages with an explicit project member + registered local Agent, optional SLA, description, and project-scoped dependencies.
- Capability-match results can be selected as a manual candidate and copied into the work-package creation form; matching never auto-assigns or wakes an Agent.
- Reviewers (Owner/Manager/Reviewer) can approve or reject a work-package result. Rejection returns the child task to `IN_PROGRESS`; the assignee can resubmit it through the existing progress/result flow.
- Approval requires at least one artifact and moves the work package task to `DONE`.
- Existing dependency editing, health scanning, stalled-work governance, reassignment, durable messages, and collaboration timeline remain the source of truth.
- DAEP still does not create, host, control, or wake local Agent Runtime processes.


## RC26 Stage 5 — Exception Coordination Workbench

A project-scoped coordination center now aggregates exception work packages (overdue, dependency-blocked, stalled, or awaiting review), unclaimed tasks, pending reviews, and pending delegations. Human coordinators can refresh risk scans, mark stale packages for attention, open task timelines, and reassign a stalled package to a selected project member and that member's registered local Agent. Reassignment requires a reason and validates fresh Agent presence; it does not start or wake an Agent Runtime. See `docs/RC26_STAGE5_COORDINATION_WORKBENCH.md`.


## RC26 Stage 6 — Project Governance Closure

Project governance now has an explicit, auditable decision register and a project completion/responsibility snapshot:

- Project owners/managers can record a decision with its rationale, accountable project member, optional due date, and up to 50 related task IDs. The decision is persisted as an immutable project-scoped audit event.
- Project members can read the decision register with accountable-member and recorder identities; access remains project-scoped.
- The governance snapshot reports task totals/status distribution, completed/open work, completion percentage and gate state, active work-package risk counts, and assigned-task responsibility by member.
- Related tasks must belong to the same project, and the accountable person must be a project member. These records document human decisions; they do not auto-assign work or control local Agent Runtime processes.

See `docs/RC26_STAGE6_PROJECT_GOVERNANCE.md`.


## RC26 Stage 7 — Requirement Acceptance and Delivery Evidence

Requirements now have an explicit acceptance gate:

- `GET /api/v1/requirements/{requirement_id}/acceptance-report` presents acceptance criteria, task status, artifact counts, and missing delivery evidence.
- `POST /api/v1/requirements/{requirement_id}/acceptance` records an auditable APPROVE or REJECT decision. Approval requires every acceptance criterion to be explicitly verified, at least one task, every task in DONE state, and at least one artifact for each task.
- Approval changes the requirement status to `ACCEPTED`; rejection returns it to `OPEN`. Only project owners, managers, reviewers, or platform administrators may decide.
- The project workspace exposes an acceptance report and requires explicit criterion-index confirmation before approval.

This closes the human acceptance loop without making DAEP execute or control local Agent Runtime processes. See `docs/RC26_STAGE7_REQUIREMENT_ACCEPTANCE.md`.


## RC26 Stage 8 — Two-member Agent Delivery Acceptance E2E

A complete API-level integration scenario now exercises two independently authenticated project members and their separately registered local MCP-compatible Agents from work assignment through final requirement acceptance:

- Two member-local Agents receive distinct work packages under one parent task.
- One member sends a durable coordination message to the other; the recipient retrieves and acknowledges it.
- Both members submit artifact-backed work results, which enter review.
- Parent approval is rejected until both child deliveries are reviewed and approved.
- The work summary and collaboration timeline are checked for both packages, artifacts, and the acknowledged cross-member message.
- The coordinator attaches the parent delivery bundle, approves the parent task, verifies the requirement acceptance report, and explicitly approves every acceptance criterion.
- The final requirement decision is checked in the project audit trail.

This is a server-side integration test, not proof of real MCP Host interoperability, sleeping-Agent wake-up, multi-computer networking, browser rendering, or production operations. DAEP continues to govern work and evidence while each member retains ownership of their local Agent Runtime. See `docs/RC26_STAGE8_TWO_MEMBER_E2E.md`.


## RC26 Stage 9 — Delivery Reliability and Recovery

The reliability suite now injects an interrupted outbox worker scenario: worker A claims a durable message and loses its lease, worker B reclaims it with a rotated lease token, and the stale worker is prevented from completing the reclaimed row. The test verifies one-time completion and confirms the member inbox retains exactly one notification. This complements existing retry/backoff, dead-letter replay with audit reason, ACK idempotency, stalled-package detection, controlled reassignment, and work-result idempotency coverage.

The lease-expiry scenario uses deterministic test-database fault injection; it is not a production broker/network partition drill or proof of physical multi-computer MCP Host interoperability. DAEP continues to coordinate durable work and evidence without managing member-local Agent Runtime processes. See `docs/RC26_STAGE9_DELIVERY_RELIABILITY.md`.


## RC26 Stage 10 — Concurrent Outbox Claim Safety

A barrier-synchronized API test now makes two independent workers compete for the same durable outbox queue. It verifies that no outbox row is returned to both workers and that the target notification receives exactly one active lease. The test covers the existing SQLite `BEGIN IMMEDIATE` and PostgreSQL `FOR UPDATE SKIP LOCKED` claim paths in CI. This is automated concurrency coverage, not a production load or broker-failure drill. See `docs/RC26_STAGE10_CONCURRENCY_SAFETY.md`.


## RC26 Stage 11 — Idempotency and State Transition Race Governance

Stage 11 hardens concurrent state transitions at the API/database boundary:

- Work-result submissions with the same idempotency key are serialized and converge on one canonical event; reuse with a different payload returns HTTP 409.
- SQLite uses `BEGIN IMMEDIATE` for the affected write paths, while PostgreSQL uses row-level `FOR UPDATE` locking.
- Task review uses a conditional `status='REVIEW'` transition, so concurrent approvals can produce at most one `task.reviewed` governance event.
- Barrier-synchronized tests verify duplicate work-result convergence, conflicting idempotency-key reuse, and duplicate task-approval rejection.

This is deterministic transaction/concurrency coverage, not a production-scale load test, broker partition drill, or proof of arbitrary MCP Host wake-up. DAEP continues to govern work and evidence without creating, hosting, controlling, or waking member-local Agent Runtime processes. See `docs/RC26_STAGE11_IDEMPOTENCY_STATE_TRANSITIONS.md`.


## RC26 Stage 12 — Cross-member Collaboration Consistency and Recovery Governance

Stage 12 serializes work-package governance transitions that can be triggered by multiple coordinators at the same time:

- Work-package reassignment locks the package state before changing assignee/Agent, task assignment, notification/outbox delivery, and audit evidence.
- Work-package review locks the package on PostgreSQL and uses a conditional `REVIEW` task transition, preventing duplicate approval/rejection governance events.
- SQLite uses `BEGIN IMMEDIATE`; PostgreSQL uses row-level `FOR UPDATE` locking.
- A barrier-synchronized test verifies that concurrent work-package approvals produce exactly one successful transition and one `task.work_package.reviewed` event.

This strengthens cross-member delivery consistency without creating, hosting, controlling, or waking member-local Agent Runtime processes. See `docs/RC26_STAGE12_COLLABORATION_CONSISTENCY.md`.

## RC26 Stage 13 — Delegation Decision Consistency

Stage 13 hardens concurrent task-delegation decisions at the collaboration boundary:

- Delegation responses use SQLite `BEGIN IMMEDIATE` or PostgreSQL row-level `FOR UPDATE`.
- The terminal `PENDING` transition is conditional; exactly one concurrent decision can win and emit the corresponding governance event.
- Expiration observers emit `task.delegation.expired` only when they actually perform the state transition, preventing duplicate audit events.
- Barrier-synchronized tests cover concurrent `ACCEPT`/`REJECT` decisions and concurrent expiration observation.

This is deterministic concurrency coverage, not a production-scale load test or broker partition drill. See `docs/RC26_STAGE13_DELEGATION_CONSISTENCY.md`.

## RC26 Stage 14 — Message Acknowledgement Consistency

Stage 14 hardens task-scoped member message acknowledgements: concurrent ACKs have a single winning state transition and a single `message.acknowledged` event, while the audit event preserves the originating task and tenant context. See `docs/RC26_STAGE14_MESSAGE_ACK_CONSISTENCY.md`.

## RC26 Stage 15 — Message/Outbox Integrity Reconciliation

A platform-admin-only read-only reconciliation endpoint now cross-checks durable messages and `message.created` outbox records. It reports missing/duplicate/orphaned/malformed records and tenant, recipient, or task-context mismatches, with bounded scans and an explicit truncation indicator. The endpoint does not repair data or expose message bodies. `SENT` denotes broker dispatch completion, not recipient ACK. Automated tests inject duplicate and orphan rows, verify detection and read-only behavior, and enforce admin-only access. See `docs/RC26_STAGE15_MESSAGE_OUTBOX_RECONCILIATION.md`.


## RC26 Stage 16 — Controlled Message Dispatch Recovery

A platform-admin-only recovery operation can restore a `message.created` outbox record only when a durable message has no matching dispatch record. It requires an operator reason, serializes/locks the message state, rechecks for any existing dispatch (including SENT or DEAD), refuses duplicates with HTTP 409, reconstructs the original delivery context, and emits an auditable `message.outbox.restored` event. It does not alter message ACK state or automatically replay dead letters. See `docs/RC26_STAGE16_CONTROLLED_MESSAGE_RECOVERY.md`.


## RC26 Stage 17 — Message Delivery Operations Overview

A platform-admin-only read-only endpoint `GET /api/v1/admin/message-delivery` provides bounded and filterable operational visibility across message delivery. It keeps Outbox dispatch (`PENDING`, `IN_FLIGHT`, `SENT`, `DEAD`, plus missing/duplicate) separate from recipient ACK (`PENDING`, `ACKNOWLEDGED`, `REJECTED`), exposes attempts/retry/lease/error metadata, and omits message titles and bodies. `SENT` explicitly means broker dispatch completion, not recipient acknowledgement. Automated tests cover state combinations, filters, authorization, and data minimization. See `docs/RC26_STAGE17_MESSAGE_DELIVERY_OVERVIEW.md`.


## RC26 Stage 18 — Message Delivery SLA and Incident Governance

Project members can inspect a project-scoped delivery health report that identifies missing/duplicate dispatch records, dead letters, dispatch SLA breaches, and broker-SENT messages whose recipient ACK exceeds a separate ACK SLA (measured from `sent_at`). Project managers/owners can append an incident review disposition and comment to the governance audit trail. The feature is read-only for delivery state and does not retry messages or control Agent Runtime. See `docs/RC26_STAGE18_MESSAGE_DELIVERY_SLA.md`.


## RC26 Stage 19 — Project Governance Message Reliability Integration

The project governance snapshot now includes message dispatch/ACK health, current SLA incidents, latest review disposition, open/resolved/accepted-risk counts, and daily message/terminal-ACK volume. It reuses project-scoped access and does not alter delivery or Agent Runtime state. Historical review decisions remain in the audit stream; the daily trend reports message volume rather than inventing historical incident counts. See `docs/RC26_STAGE19_GOVERNANCE_MESSAGE_RELIABILITY.md`.


## RC26 Stage 20 — Project Workflow and Gate Runtime Enforcement

Project workflow configuration is now enforced at runtime rather than remaining a design-only setting. Managers can define ordered stages, optional stage-exit approval roles, and custom gates with an explicit target stage. Task transitions are validated against the project workflow; leaving a stage with an approval role requires that project role, custom gates can require delivery evidence or all requirement tasks to be complete, and the system REVIEW/DELIVERY gates remain immutable. A dedicated task workflow-transition API provides idempotent controlled state changes, while existing task review and work-package review paths reuse the same enforcement. Runtime coverage is included in tests/test_api.py.


Stage 20 UI also exposes custom gate target stage and renders configured workflow stages on the task board, with controlled transition actions routed through the same backend enforcement API.
