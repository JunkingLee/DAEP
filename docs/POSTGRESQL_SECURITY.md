# PostgreSQL security roles (RC11)

DAEP uses PostgreSQL Row-Level Security (RLS). RC11 removes trust in caller-settable custom GUC flags for platform-admin and internal-service bypass. The bypass now requires the PostgreSQL login identity (session_user) to be a member of daep_privileged.

## Required connection separation

- DATABASE_URL: ordinary application connection. Its login must not be a member of daep_privileged, must not be a superuser, and must not have BYPASSRLS.
- DAEP_PRIVILEGED_DATABASE_URL: dedicated connection used only for bootstrap, platform-admin and internal-service operations. Its login must be a member of daep_privileged.
- Never point either URL at a PostgreSQL superuser in production.

The Alembic RC11 migration creates the daep_privileged NOLOGIN role. A DBA must create and grant a dedicated login. Example (replace passwords and role names to match the deployment):

```sql
CREATE ROLE daep_runtime LOGIN PASSWORD 'replace-runtime-password' NOSUPERUSER NOBYPASSRLS;
CREATE ROLE daep_privileged_login LOGIN PASSWORD 'replace-privileged-password' NOSUPERUSER NOBYPASSRLS;
GRANT daep_privileged TO daep_privileged_login;
GRANT CONNECT ON DATABASE daep TO daep_runtime, daep_privileged_login;
GRANT USAGE ON SCHEMA public TO daep_runtime, daep_privileged_login;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO daep_runtime, daep_privileged_login;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO daep_runtime, daep_privileged_login;
```

Configure DATABASE_URL with daep_runtime and DAEP_PRIVILEGED_DATABASE_URL with daep_privileged_login. Restrict the privileged URL as a secret and rotate it independently.

## Important boundary

The tenant ID GUC remains application-supplied context. RLS is defense-in-depth against omitted tenant predicates; a party holding the ordinary database credential can set arbitrary custom GUC values and therefore impersonate a tenant. Do not expose database credentials to end users or agents. Use a least-privilege runtime role, parameterized SQL, and protect the API process. A future hardening step should bind tenant context to a signed database assertion or per-tenant database identity if the threat model includes a compromised application database credential.

## Verification

CI runs tests/postgres_rls_smoke.sql under a restricted session identity. It asserts that setting app.platform_admin=true or app.internal_service=true does not expose another tenant's rows.

## Authentication lookup (RC12)

The caller-settable app.auth_lookup flag is no longer an authorization mechanism.
RC12 removes the members auth-lookup RLS policy and replaces direct PostgreSQL
member-token SELECTs with public.daep_authenticate_member(token_hash, now).
That function is SECURITY DEFINER, owned by a dedicated NOLOGIN BYPASSRLS role,
and returns only the row matching the supplied SHA-256 token hash when the
token is active and unexpired. The application stores only token hashes.

The BYPASSRLS role is not a login and should not be granted to application
logins. EXECUTE on the narrow function is granted so the runtime can validate
a bearer token without broad SELECT access to the members table. The raw
database credential remains trusted infrastructure: protect it and do not
expose it to Agents or end users.
