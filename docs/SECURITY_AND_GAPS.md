# Security Posture and Known Gaps — DAEP 1.0.0-rc9

Date: 2026-11-25  
Branch: `release/1.0.0-rc9`

This document distinguishes controls implemented in the RC9 codebase, controls exercised by CI, and controls that still require verification in the target deployment environment. A CI pass is not a substitute for production security acceptance.

## 1. Implemented Security Controls

### Identity and credentials
- Human Member authentication is account/password based; API and MCP Bearer Tokens remain machine/API credentials.
- Member and Agent credentials are separate.
- Token material is stored as a digest; plaintext is shown only at issuance/rotation.
- Agent identity is privately owned by one human Member.
- Agent management endpoints (create/list/detail/update, token rotate/revoke, project bind/unbind) require a human Member token; Agent credentials cannot act through their owner's Member ID.
- Worker operations use a dedicated Worker Token, separate from Member and Agent credentials.
- OIDC authorization-code flow validates browser-bound state, nonce, PKCE S256, ID-token signature/JWKS, issuer, audience and expiry.

### Authorization and tenancy
- Tenant-scoped project/task access checks are implemented.
- Platform roles and project roles are separate; platform-administrator bypasses are restricted to the platform role in `tenant-default`.
- Project creation is available to a regular Member within their own Tenant; the creator becomes Project Owner.
- Agent Presence/discovery does not grant execution or collaboration authorization.
- Task Execution Grants and Collaboration Grants are separate authorization domains.
- An Agent Owner must authorize their own Agent; a Task owner cannot authorize another Member's Agent.
- Removing an Agent Owner from a project revokes their active Collaboration Grants in that project, records audit events and queues a durable notification.
- Proposal withdrawal requires the originating Agent's still-active accepted Collaboration Grant, an OPEN Session and a non-terminal Task; revocation/expiry blocks further Agent-side proposal changes.
- Agent actors cannot review or approve delivery.
- Worker-only endpoints require the dedicated Worker identity.

### Data and delivery
- PostgreSQL 17 migrations and Row-Level Security policies are included.
- CI provisions PostgreSQL and checks migration application, RLS policy presence/forced-RLS flags, and a restricted-role isolation smoke test.
- Outbox delivery is at-least-once, with leases, retry and dead-letter handling. Exactly-once delivery is not claimed; downstream consumers must deduplicate by stable message/outbox identity.
- Grant lifecycle, notification preferences, audit and controlled dead-letter replay have automated coverage.

## 2. Current Automated Verification

The RC9 CI workflow includes:
- Python 3.11, 3.12 and 3.13 test suites.
- PostgreSQL migration and RLS checks.
- Chromium E2E for Agent management and Task Collaboration UI.
- Container build and non-root runtime checks.
- Production Compose validation.
- Blocking structural quality scan.

The latest recorded full CI run for the authorization fixes is `45573815527`, with all 8 jobs successful: Python 3.11/3.12/3.13, Browser E2E, PostgreSQL migrations/RLS, container build, Production Compose and quality gate.

## 3. Remaining Deployment / Security Acceptance

The following are not proven by repository CI and remain required before production/GA acceptance:

1. **Real identity provider** — validate the target OIDC provider, redirect URI, TLS, client credentials, group/role mapping, account lifecycle and logout/session behavior.
2. **Production PostgreSQL operations** — execute a real backup, checksum verification, restore into an isolated empty database, RLS/role verification and application smoke test.
3. **Deployment secrets and network** — verify secret injection, rotation, TLS, CORS, database network isolation, firewall rules and log redaction.
4. **Worker and broker** — deploy the Worker profile, validate the external broker gateway, retry/dead-letter/replay and downstream deduplication.
5. **Real Agent interoperability** — validate two independent Members and two independent local MCP-compatible Agents, including offline/recovery and negative authorization cases.
6. **Independent security review** — conduct threat-model review and penetration testing against the deployed configuration; review rate limits, abuse controls, dependency advisories and operational alerting.
7. **Operational resilience** — perform load, capacity, backup retention, disaster recovery and incident-response exercises.

## 4. Integration Boundaries

- DAEP is an Agentic Engineering Control Plane, not an Agent Runtime host.
- Agent Runtime executes in each Member's own environment and is managed by that Member's MCP Host/local environment.
- The current MCP integration uses a local stdio Adapter that calls DAEP REST APIs over HTTPS. DAEP does not currently expose a hosted remote Streamable HTTP MCP Server.
- DAEP does not guarantee wake-up of a sleeping or disconnected local Agent Runtime.
- Capability matching and Presence are discovery signals, not proof of capability or authorization.

## 5. Release Restrictions

Until the deployment acceptance items above have been completed and evidenced:
- Treat RC9 as a Release Candidate, not Production GA.
- Do not expose the service to the public internet without deployment-specific security controls and review.
- Do not use it for regulated or sensitive workloads without the required independent assessment.
- Do not mark real browser acceptance, production backup/restore or dual-Agent interoperability as PASS without evidence from the target environment.

## 6. Related Evidence

- `docs/RC9_RELEASE_READINESS.md`
- `docs/RC9_FINAL_EVIDENCE_PACKAGE.md`
- `docs/DEPLOYMENT_ACCEPTANCE_CHECKLIST.md`
- `docs/RC9_PRODUCTION_BACKUP_RESTORE_DRILL.md`
- `docs/RC9_AGENT_INTEROPERABILITY_DRILL.md`
- `docs/POSTGRES_OIDC_TENANCY.md`
- `docs/CODE_QUALITY_AUDIT.md`
