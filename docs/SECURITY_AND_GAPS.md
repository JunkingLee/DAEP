# Security and known gaps — RC8

## Implemented in the current release candidate

- Member API tokens are stored as SHA-256 digests; revoke/rotate operations create tenant-attributed audit events.
- Only the bootstrap identity retains platform-administrator authority; RC5 secondary admin accounts are demoted during upgrade.
- Tenant checks apply to project/task access, project listing, assigned-task listing and task assignee details.
- Startup migration removes legacy cross-tenant assignment and project membership links and repairs event/outbox tenant ownership where payload references permit it.
- OIDC authorization-code flow now uses one-time browser-cookie-bound state, nonce and PKCE S256; ID token signature/JWKS, issuer, audience and expiry are checked.
- PostgreSQL compatibility translation handles PRAGMA no-ops/introspection, parameter markers, `INSERT OR IGNORE` and legacy message sequence migration. RC8 adds transaction-local tenant context and explicit inbox tenant ownership.
- Outbox internal endpoints use a dedicated `DAEP_WORKER_TOKEN`; the worker no longer needs the platform admin token.
- Outbox lease ownership and retry/dead-letter semantics remain enforced; delivery is at-least-once.

## Remaining production blockers

- No live PostgreSQL server was available for integration tests. RC8 now includes PostgreSQL RLS policies and Alembic migrations, but real two-tenant RLS behavior still needs independent integration testing.
- Alembic is now the reviewed additive migration path; the application bootstrap remains responsible for the cross-database core schema. Production needs a preflight/rollback procedure and migration observability.
- No live OIDC IdP was available. Browser session management, logout, refresh, group/role mapping, account linking and tenant provisioning policy need production design/review.
- Git integration remains generic shared-secret webhook ingestion; provider-specific HMAC signature validation, replay controls and PR/MR status synchronization are not bundled.
- Broker worker still requires an HTTP gateway to publish into the chosen enterprise broker. Exactly-once delivery is not claimed; downstream deduplication is required.
- No live broker, Docker build, load test, disaster-recovery exercise or independent penetration test was performed in this environment.
- DAEP cannot guarantee wake-up of an arbitrary sleeping local MCP Host/Agent Runtime.
- MCP SDK/Host interoperability still requires validation against actual supported Hosts.

Do not expose this RC to the public internet or use it for regulated/sensitive workloads without the above controls and verification.
