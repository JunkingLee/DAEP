# DAEP Enterprise 1.0.0-rc7

## Delivered

- Added Alembic migration infrastructure and RC6 baseline marker.
- Added RC7 additive database indexes for tenant-scoped access, inbox cursor reads and outbox claiming.
- Added the local `daep_agent_bridge` workstation process.
- Bridge uses a member API token, persists its inbox cursor atomically, forwards message JSON to a configured local command without shell execution, and acknowledges only after successful local dispatch.
- Added RC7 Docker Compose configuration.
- Updated Docker image to include the bridge.
- Added bridge regression tests.

## Verification

- `pytest -q`: 24 passed.
- Python compile checks passed.
- Alembic migration scripts parse/import successfully in the development environment.

## Explicit limitations

- PostgreSQL was not connected to a live server in this build environment.
- PostgreSQL RLS is not enabled by default because the current application uses a shared database identity and does not yet set a trusted per-request tenant context; enabling RLS without that context would break legitimate traffic or create unsafe bypasses.
- The bridge is a local delivery adapter, not an Agent Runtime or wake-up mechanism.
- Exactly-once delivery is not claimed; inbox/outbox semantics remain at-least-once.
