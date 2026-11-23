# RC22 Candidate Acceptance

RC22 is the production-candidate hardening stage for DAEP 1.0.0.

## Automated acceptance

CI now verifies:

- the production Compose file renders successfully with required dummy secrets;
- production shell scripts pass syntax checks;
- the production container builds and runs as the non-root `daep` user;
- Python 3.11/3.12/3.13 tests pass;
- PostgreSQL migrations and RLS isolation pass;
- a cross-member Agent collaboration workflow passes end to end.

The collaboration test covers:

1. two project members are added to one project;
2. the recipient registers a local MCP-compatible Agent;
3. a task delegation is offered and explicitly accepted;
4. a work package is assigned to that Agent;
5. the durable inbox message is acknowledged and replayed idempotently;
6. the Agent reports a Git artifact and a COMPLETE result;
7. the parent review gate blocks premature approval;
8. child approval unlocks parent approval;
9. the correlated work timeline exposes the assignment message, artifact, and lifecycle event;
10. the worker credential consumes the durable outbox;
11. the completed child task is DONE and the project health scan classifies the active work-package record as COMPLETED.

## Production smoke check

After a real deployment, set `DAEP_ADMIN_TOKEN` and run:

    DAEP_ENV_FILE=.env DAEP_ADMIN_TOKEN="$DAEP_ADMIN_TOKEN" ./scripts/production_smoke.sh

The smoke check validates the rendered Compose model, reports service state, checks `/readyz`, and performs an authenticated API request. It does not create, start, stop, or control any local Agent Runtime.

## Acceptance boundary

CI proves code, migrations, RLS, container build, production Compose rendering, and the collaboration workflow against the test application.

A deployment owner must still validate:

- TLS/reverse proxy and certificate renewal;
- DNS, firewall, network policy, and host hardening;
- real OIDC configuration;
- real GitHub/GitLab webhook delivery;
- external broker connectivity if enabled;
- an off-host encrypted backup and isolated restore drill;
- monitoring, alerting, log retention, and incident response;
- real multi-member local Agent connectivity with the chosen MCP Hosts;
- behavior when an Agent Host is offline or sleeping.

DAEP's platform guarantees durable messages and workflow state. MCP itself does not guarantee that an arbitrary sleeping Host can be awakened.

## Release status

RC22 remains a release candidate. It is **not** a GA declaration and does not authorize merging into `main`.
