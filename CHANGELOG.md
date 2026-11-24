# Changelog

## 1.0.0-rc7
- Added Alembic migration infrastructure and additive tenant/inbox/outbox indexes.
- Added local DAEP Agent Message Bridge with durable cursor and ACK-after-success semantics.
- Added bridge tests and RC7 Docker Compose configuration.

## 1.0.0-rc6
- Hardened PostgreSQL compatibility, OIDC state/nonce/PKCE and worker credentials.

## 1.0.0-rc8

- Added transaction-local PostgreSQL tenant context.
- Added PostgreSQL RLS migration with FORCE ROW LEVEL SECURITY.
- Added explicit tenant ownership to inbox messages.
- Hardened auth lookup and WebSocket compatibility with RLS.
- Added RC8 Alembic and RLS contract tests.
- Regression suite: 26 passed.
