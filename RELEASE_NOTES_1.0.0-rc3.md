# DAEP Enterprise 1.0.0-rc3

## Delivered
- Project membership and role-aware project access.
- Assignment-required Agent writes and reviewer approval workflow.
- Project member/requirement/task list APIs.
- Project-scoped messages and durable inbox sequence cursor with attempt counters.
- Idempotent progress updates; 100% progress enters REVIEW, explicit reviewer approval enters DONE.
- Best-effort WebSocket notification delivery backed by the durable inbox.
- Minimal browser dashboard served at `/`.
- SHA-256 token-at-rest digests and an additive migration for legacy plaintext token records.
- MCP adapter package renamed to `daep_mcp` to avoid shadowing the official `mcp` SDK namespace; cursor API updated.

## Verification
- `python -m py_compile app/main.py daep_mcp/server.py`: passed.
- `pytest -q`: 7 passed.
- MCP SDK installation/runtime startup and real MCP Host compatibility: not verified because the build environment cannot reach the package index.
- Docker image build and production deployment: not run (Docker CLI unavailable in this environment).

## Release classification
Release candidate only. SQLite single-instance, best-effort notification delivery and missing enterprise identity/integration/security operations prevent production GA approval. See `docs/SECURITY_AND_GAPS.md`.
