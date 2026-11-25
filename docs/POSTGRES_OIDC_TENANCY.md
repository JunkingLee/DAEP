# PostgreSQL、OIDC 与租户隔离部署说明

本文档描述当前 `release/1.0.0-rc9` 的实现，不再沿用早期 RC6 的迁移与权限说明。

## PostgreSQL 与 Alembic

- 生产后端使用 PostgreSQL 17 与 psycopg 3；SQLite 主要用于本地开发和测试。
- 当前 Schema 版本由仓库内 Alembic migration chain 管理，部署时执行 `alembic upgrade head`。
- Production Compose 的一次性 `migrate` 服务按顺序执行应用 bootstrap、`alembic upgrade head` 和 PostgreSQL 应用角色收尾配置；API 等待该服务成功后才启动。
- CI 使用真实 PostgreSQL 17 服务执行 bootstrap、Alembic upgrade、SQL 生成、RLS policy 检查和受限数据库角色隔离测试。
- 本项目处于开发阶段。本说明只覆盖当前 Schema 初始化/升级，不定义旧系统历史数据迁移、回填或旧库利旧流程。

## 数据库角色与 RLS

Production Compose 使用相互独立的数据库凭证：
- `daep_bootstrap`：仅用于初始化和一次性迁移流程，不传给常驻 API。
- `daep_runtime`：常规 API 运行角色，不具备 PostgreSQL superuser、CREATEDB、CREATEROLE 或 BYPASSRLS 权限。
- `daep_privileged_login`：通过成员关系获得 `daep_privileged` 权限，用于受控的平台管理和内部服务操作。

API 的 `DATABASE_URL` 使用 `daep_runtime`；`DAEP_PRIVILEGED_DATABASE_URL` 使用 `daep_privileged_login`。生产 Compose 还限制 API 容器为只读文件系统、丢弃 Linux capabilities、启用 no-new-privileges，并默认仅绑定 loopback 地址，供 TLS 反向代理转发。

受保护表启用并强制 Row-Level Security。策略结合请求上下文中的 Tenant、Member、生命周期操作和内部服务身份。CI 检查 RLS/policy 定义，并以受限角色执行跨租户隔离 smoke test。真实部署仍须使用目标数据库凭证验证角色成员关系、策略与隔离行为。

## OIDC 身份接入

配置项：
- `DAEP_OIDC_ISSUER`
- `DAEP_OIDC_CLIENT_ID`
- `DAEP_OIDC_CLIENT_SECRET`
- `DAEP_OIDC_REDIRECT_URI`
- 可选：`DAEP_OIDC_SCOPES`、`DAEP_OIDC_AUDIENCE`
- `DAEP_OIDC_AUTO_PROVISION` 默认为 false；仅在明确批准自动开户时开启。
- 自动开户开启时，可用 `DAEP_OIDC_DEFAULT_TENANT` 和 `DAEP_OIDC_DEFAULT_ROLE` 指定默认租户与角色。不要将默认角色配置为平台管理员。

OIDC 流程使用授权码、服务端 state 记录、HttpOnly state cookie、nonce、PKCE S256、Provider JWKS，以及 ID Token 的签名、issuer、audience、有效期校验。State 有效期为十分钟且只能消费一次。

**重要边界：** OIDC callback 当前一次性返回新签发的 DAEP API Token；这不是完整的浏览器会话/BFF、Refresh Token 或长期 SSO Session 实现。若生产 Web 体验需要浏览器会话，应另行设计并完成 IdP 与 Session 安全评审。

## Worker 与通知投递

- Worker 必须使用独立的 `DAEP_WORKER_TOKEN`，不可复用管理员或 Member/Agent Token。
- Worker 位于 Compose 的 `broker` profile，需显式使用 `--profile broker` 启动。
- Outbox 传输需要配置 `DAEP_BROKER_WEBHOOK_URL` 与独立的 `DAEP_BROKER_WEBHOOK_TOKEN`；下游必须按 Outbox ID 或 Message ID 去重，因为投递语义为 at-least-once。
- Worker 负责周期性处理 Outbox，并触发 CollaborationGrant 到期提醒与过期状态物化。Worker 未运行时，这些后台处理不会自动发生。
- Member 通知偏好只控制通知生成/提醒，不改变 Grant 的授权、接受、撤销、续期或过期规则。

## 部署前检查

1. 复制 `.env.example` 为部署环境的 `.env`，填入独立随机密钥；禁止提交真实 `.env`。
2. 设置精确的 `CORS_ORIGINS`、公开 HTTPS 域名和 OIDC 回调地址。
3. 执行 `docker compose -f compose.production.yaml config --quiet`。
4. 执行 `python scripts/verify_production_compose.py compose.production.yaml`。
5. 启动 Compose，确认 migrate 成功和 API `/readyz`。
6. 显式启动 Worker profile，并验证 broker gateway 投递、重试和 DEAD 处理。
7. 按 `docs/DEPLOYMENT_ACCEPTANCE_CHECKLIST.md` 在真实环境执行 OIDC、RLS、MCP 和双成员协作验收。

## 备份与恢复

仓库提供 `scripts/backup_postgres.sh`、`scripts/restore_postgres.sh` 和 `scripts/verify_restored_postgres.sh`。真实部署必须在隔离恢复目标执行备份恢复演练；CI 的 migration/RLS 检查不能替代恢复演练。详见 `docs/RC9_PRODUCTION_BACKUP_RESTORE_DRILL.md`。
