# DAEP Enterprise 1.0.0-rc6

## RC6 changes

- Added idempotent schema migration ledger and tenant-focused indexes.
- Restricted platform administrator authority to the bootstrap identity; RC5 secondary admin accounts are demoted during upgrade.
- Fixed PostgreSQL compatibility handling for SQLite PRAGMA statements, metadata inspection, `INSERT OR IGNORE`, placeholders and legacy message sequence migration.
- Added tenant-aware listing/detail filters and startup cleanup of legacy cross-tenant assignments and project memberships.
- Backfilled event/outbox tenant ownership from resource references to correct RC5 administrator-originated cross-tenant records.
- Hardened OIDC authorization-code flow with one-time server-side state bound to an HttpOnly browser cookie, nonce validation, PKCE S256 and PyJWT JWKS key selection.
- Added dedicated `DAEP_WORKER_TOKEN`; outbox internal endpoints no longer accept the platform administrator token.
- Updated the standalone worker and Docker Compose RC6 topology to use the dedicated credential.
- Added regression tests for OIDC replay prevention, PostgreSQL SQL translation, tenant ownership metadata, legacy cross-tenant read isolation and worker credential separation.

## Verification

- `python -m py_compile app/main.py daep_mcp/server.py daep_worker/worker.py`: passed.
- `pytest -q`: 21 passed.
- Live PostgreSQL, external IdP, broker gateway, Docker image build, load/DR and independent penetration testing: not run in this environment.

## Release boundary

RC6 remains a release candidate, not production-certified GA. PostgreSQL RLS and Alembic are not yet implemented. OIDC callback issues a one-time DAEP API token rather than a browser session. Broker delivery remains at-least-once.
