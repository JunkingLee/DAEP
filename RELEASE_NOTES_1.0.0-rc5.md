# DAEP Enterprise 1.0.0-rc5

RC5 completes the next enterprise-hardening phase while keeping the Agent Runtime outside DAEP.

## Delivered

- Multi-tenant data model with additive migration for existing SQLite databases.
- Tenant-aware project authorization and resource ownership metadata on events, artifacts and outbox records.
- Tenant administration endpoints: create/list tenants.
- Member credential lifecycle: active/revoked state, rotation, optional expiry metadata.
- OIDC/OAuth2 authorization-code integration: discovery, login redirect, callback, ID-token validation against provider JWKS, optional controlled auto-provisioning.
- Transactional outbox remains the durable handoff; a standalone `daep_worker` now claims, delivers to an HTTP broker gateway, completes or retries leases.
- Git webhook ingestion with shared-secret verification and event audit recording.
- PostgreSQL runtime path via `DATABASE_URL` using psycopg 3 compatibility layer, while SQLite remains the default local/test backend.
- Docker image now includes MCP adapter and outbox worker; `docker-compose.rc5.yaml` runs API + worker.
- Token hashes remain the only credential representation stored at rest.

## Semantics

- Outbox delivery is **at least once**, not exactly once.
- MCP remains an adapter/protocol boundary; DAEP does not create or host arbitrary Agent Runtime processes.
- OIDC is optional and disabled unless configured. Auto-provisioning is disabled by default.
- PostgreSQL support is implemented in the application connection path but still requires a real PostgreSQL environment for deployment validation; this release was not tested against a live PostgreSQL server in the offline build environment.

## Verification

- `python -m py_compile app/main.py daep_mcp/server.py daep_worker/worker.py`
- `pytest -q` → **12 passed**
- Live PostgreSQL, external IdP, external broker, GitHub/GitLab production webhook validation, Docker build and load testing remain environment-dependent validation tasks.
