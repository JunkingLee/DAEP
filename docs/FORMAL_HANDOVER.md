# DAEP 1.0.0-rc6 — handover and release boundary

## Delivered

- Task/project/requirement/collaboration governance remains the platform boundary; Agent Runtime processes remain member-owned and locally launched.
- MCP stdio adapter remains available.
- Transactional outbox + standalone worker provide durable at-least-once delivery, using a dedicated worker credential separate from platform administration.
- Tenant-aware read filtering and legacy cross-tenant link cleanup are included.
- Platform administrator authority is restricted to the bootstrap identity; legacy secondary admin accounts are demoted.
- Tenant-attributed audit metadata is maintained for token lifecycle and collaboration events.
- OIDC authorization-code flow includes one-time browser-cookie-bound state, nonce and PKCE S256 validation.
- PostgreSQL SQL compatibility fixes and an idempotent schema migration ledger are included; SQLite remains the default local backend.
- Provider-neutral Git webhook ingestion remains available.

## Verification

- `python -m py_compile app/main.py daep_mcp/server.py daep_worker/worker.py` passed.
- `pytest -q`: **21 passed**.
- PostgreSQL adapter translation unit tests passed; a live PostgreSQL integration test was not possible in this environment.

## Release boundary

RC6 is not production-certified GA. PostgreSQL RLS and Alembic are not implemented. No live PostgreSQL, IdP, broker, Git provider, Docker build, load test, disaster-recovery exercise or independent penetration test was performed. Worker delivery is at-least-once, not exactly-once. DAEP still cannot wake arbitrary sleeping Agent Hosts; local Agent Runtime lifecycle remains outside the platform.

## RC8 handover delta

RC8 introduces PostgreSQL transaction-local tenant context and RLS. The API
sets `app.tenant_id` / `app.platform_admin` for authenticated requests; token
lookup and the dedicated Worker service use narrowly scoped internal contexts.
The database migration `0010_rc8_postgres_rls` enables and forces RLS on tenant
owned tables. A production deployment must use a dedicated non-superuser
PostgreSQL role and perform a two-tenant validation before GA.
