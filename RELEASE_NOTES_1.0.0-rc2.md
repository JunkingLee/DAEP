# DAEP Enterprise 1.0.0-rc2

## What's new

This release candidate adds an executable MCP stdio adapter, not merely an integration design document. A developer launches the adapter locally; it authenticates to the DAEP API using that member's token. It provides eight MCP tools for task context, inbox messages, acknowledgements and engineering updates.

## Verification status

- Existing REST API tests are included and should be run in the target Python environment.
- MCP source is included and uses the `mcp` Python package pinned in `requirements.txt`.
- Deployment remains a single-node SQLite baseline. Production readiness still requires PostgreSQL migrations, tenant-scoped authorization, hardened secret lifecycle, real Git provider and CI integrations, security/performance testing, backups/restore drills and deployment-specific MCP Host compatibility tests.

## Start

```bash
cp .env.example .env
# Set a long random DAEP_ADMIN_TOKEN in .env
docker compose up --build
```

Create a member through the admin API, then configure the MCP Host with that member's token as described in `daep_mcp/README.md`.
