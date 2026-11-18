# RC8 Integration Test Matrix

| Area | Automated in repository | Requires external environment |
|---|---|---|
| SQLite API regression | Yes | No |
| Alembic graph | Yes | No |
| PostgreSQL RLS SQL generation | Yes (static/migration checks) | Yes: PostgreSQL instance |
| PostgreSQL real migration | No | PostgreSQL |
| OIDC | State/PKCE unit coverage | Real IdP |
| Outbox Worker | Claim/lease API | Broker gateway |
| Agent Bridge | Cursor/ACK unit coverage | Real local Agent/MCP Host |
| Git webhook | Secret/event unit coverage | GitHub/GitLab |
| Load/failover | No | Dedicated test environment |
