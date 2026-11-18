# RC6 Enterprise Data, Identity and Tenancy

## PostgreSQL

Set `DATABASE_URL=postgresql://user:password@host:5432/daep`. The API selects psycopg 3 automatically. SQLite remains the default local/test backend. RC6 fixes PostgreSQL handling for SQLite compatibility PRAGMAs, `INSERT OR IGNORE`, parameter markers and the legacy message sequence migration.

Schema evolution is tracked in `schema_migrations` with additive, idempotent startup migrations. RC6 records the RC5 baseline, tenant-index/OIDC-state migration, and platform-admin boundary migration. This is a lightweight application migration ledger, **not Alembic**. A dedicated Alembic migration repository and operational migration command remain future work before a larger production schema lifecycle.

PostgreSQL was not available in the build environment. The SQL translation path has unit coverage, but that is not a substitute for running the full suite against a live supported PostgreSQL instance. Before production rollout, run migrations in a staging clone, verify constraints/indexes, backup/restore and connection/pool behaviour.

## Tenancy

Members and projects carry `tenant_id`; events, artifacts and outbox records retain tenant ownership. Project access checks tenant equality before membership. RC6 adds tenant filters to project and assigned-task listings, filters task assignee details, and removes invalid cross-tenant assignment/project-membership links during startup migration. Ownership metadata on legacy events/outbox records is backfilled from their resource references where possible.

Only the bootstrap administrator identity is a platform administrator and can enumerate tenants. RC5 secondary `admin` accounts are demoted to `manager` during RC6 upgrade; new member provisioning cannot assign the platform-admin role. It is a privileged control-plane identity and should be protected separately. RC6 does not yet implement PostgreSQL Row-Level Security (RLS); application-level authorization remains the primary isolation boundary and requires independent security review.

## Credentials

Member tokens are stored only as SHA-256 digests. Administrators can revoke or rotate member credentials. Configure an independent random `DAEP_WORKER_TOKEN` (at least 32 characters) for the standalone outbox worker. Internal outbox endpoints accept this credential and no longer accept the platform administrator token. Never reuse the admin credential for the worker.

## OIDC

Configure `DAEP_OIDC_ISSUER`, `DAEP_OIDC_CLIENT_ID`, `DAEP_OIDC_CLIENT_SECRET`, and `DAEP_OIDC_REDIRECT_URI`; auto-provisioning remains disabled by default. RC6 uses one-time server-side state records bound to an HttpOnly browser cookie, nonce validation, PKCE S256, provider JWKS key selection, and issuer/audience/signature/expiry checks for ID tokens. OIDC state expires after ten minutes and is consumed once.

The callback still returns a newly issued DAEP API token once; it is not a browser session or refresh-token implementation. A production browser SSO experience needs a hardened session/BFF layer and live IdP security review.

## Git integration

`POST /api/v1/integrations/git/webhook` remains provider-neutral shared-secret ingestion. Native GitHub/GitLab signature verification and CI status adapters remain future work.
