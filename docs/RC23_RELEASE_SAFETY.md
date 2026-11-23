# RC23 Release Safety and GA Candidate Gate

RC23 hardens the production release boundary. It does not declare GA and does not authorize a merge to `main`.

## Changes

### Restore safety

`scripts/restore_postgres.sh` now:

- requires explicit `DAEP_CONFIRM_RESTORE=YES`;
- verifies the SHA-256 manifest, including the dump and globals snapshot;
- detects the configured source database from the running PostgreSQL service and refuses to restore into it;
- refuses a target containing user relations before starting a restore;
- uses PostgreSQL `pg_restore --single-transaction --exit-on-error` to avoid a partially restored target on SQL failure;
- applies role grants and ownership transfer using a syntactically valid PL/pgSQL anonymous block.

The target database must be provisioned empty and the cluster-level DAEP roles must already exist. A DBA must validate the restored schema and RLS policies before any traffic cutover.

### Production Compose security assertions

`scripts/verify_production_compose.py` inspects the rendered Docker Compose model and fails unless:

- PostgreSQL publishes no host ports;
- API data-plane access uses `daep_runtime`;
- API privileged access uses `daep_privileged_login`;
- API receives no bootstrap database credential;
- API filesystem is read-only, all Linux capabilities are dropped, and no-new-privileges is enabled;
- API waits for the one-shot migration service to complete successfully;
- API host binding defaults to loopback;
- the worker remains opt-in behind the `broker` profile.

CI runs this verifier with non-production dummy secrets. It does not print the rendered configuration.

## CI coverage

RC23 CI includes:

- Python tests on 3.11, 3.12, and 3.13;
- PostgreSQL 17 migrations and tenant RLS isolation;
- Docker Compose rendering and security invariant checks;
- shell syntax validation;
- Docker image build and non-root runtime assertion;
- unit assertions for restore safeguards and Compose guardrails.

## Deployment-owner GA gate

The following cannot be proven by repository CI and must be completed in the target environment:

- deploy the exact reviewed commit and pin production image digests;
- validate TLS termination, DNS, firewall, rate limiting, and CORS;
- configure and exercise real OIDC login and account lifecycle;
- deliver real signed GitHub/GitLab webhooks and verify idempotency;
- if enabled, exercise the external broker with its independently managed secret;
- take an encrypted off-host backup and perform a restore into a separately provisioned empty database;
- run API read/write tests and PostgreSQL tenant-isolation checks against the restored database;
- verify metrics, alerting, log retention, on-call ownership, and incident response;
- validate the chosen MCP Hosts and multi-member local Agent connectivity, including offline/sleeping behavior;
- record product-owner approval and rollback decision.

A successful CI run is necessary but is not proof of production deployment, a completed disaster-recovery drill, or GA readiness.
