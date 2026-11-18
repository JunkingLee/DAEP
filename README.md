# DAEP Enterprise Release — 1.0.0-rc8

**Distributed Agentic Engineering Platform** is a task-centric engineering control plane. It manages organizations' project work, requirements, task assignments, collaboration messages, artifacts and acceptance workflow. Developers start and operate their own local Agent Runtime; DAEP does not create, host or control those runtimes. Local Agents connect through the MCP-compatible adapter.

## Quick start

```bash
cp .env.example .env
# Set DAEP_ADMIN_TOKEN and DAEP_WORKER_TOKEN to different unique random secrets (at least 32 characters each)
docker compose -f docker-compose.rc8.yaml up --build -d
# Optional broker delivery (configure DAEP_BROKER_WEBHOOK_URL first):
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

Install dependencies on the developer's own workstation and configure the Host to launch `daep_mcp/server.py` using that member's token. See `daep_mcp/README.md`. The adapter does not start an Agent Runtime and cannot force an idle MCP Host to wake its model. Platform messages remain in the durable inbox and can be polled after reconnecting. Message creation also writes a durable transactional outbox record; a separate worker can claim, retry and complete those records through the internal API. The separate broker worker uses its own `DAEP_WORKER_TOKEN`; do not reuse the platform admin token.

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
