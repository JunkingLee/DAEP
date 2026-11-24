# DAEP RC9 Production Backup / Restore Drill

## 目的

本演练用于把现有 Production Compose、PostgreSQL backup/restore 脚本从“代码已具备”推进到“可执行、可记录、可签署”的运营验收。

**本文件不是一次真实生产演练的结果。** 执行前必须准备独立的恢复目标，禁止直接覆盖生产源数据库。

## 前置条件

- 当前代码：release/1.0.0-rc9
- Docker / Docker Compose 可用
- PostgreSQL 17 镜像可拉取
- 已准备生产环境 .env，不能提交到 Git
- DAEP_BACKUP_DIR 指向受保护目录
- 恢复目标必须是独立、空数据库
- 已获得数据库恢复授权
- 已确认磁盘空间足够

## 1. 启动 Production Compose

配置检查：

~~~bash
export DAEP_COMPOSE_FILE=compose.production.yaml
docker compose -f "$DAEP_COMPOSE_FILE" config --quiet
~~~

启动：

~~~bash
docker compose -f "$DAEP_COMPOSE_FILE" up -d
docker compose -f "$DAEP_COMPOSE_FILE" ps
~~~

等待：

~~~bash
docker compose -f "$DAEP_COMPOSE_FILE" exec -T daep-api   python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/readyz", timeout=5)'
~~~

## 2. 记录源数据库基线

执行前记录 PostgreSQL version、Alembic head、数据库对象数量、项目数量、成员数量、任务/需求数量。

## 3. 执行 Backup

~~~bash
export DAEP_BACKUP_DIR=/protected/path/daep-backups
./scripts/backup_postgres.sh
~~~

必须产生 dump、globals SQL 和 SHA-256 sidecar，并验证 dump 非空、pg_restore --list 成功、SHA-256 成功、权限为 0600。

记录 backup 开始/结束时间、dump 大小、checksum 和执行耗时。

## 4. 准备空恢复数据库

~~~bash
docker compose -f "$DAEP_COMPOSE_FILE" exec -T postgres   psql -U daep_bootstrap -d postgres -v ON_ERROR_STOP=1   -c 'CREATE DATABASE daep_restore'
~~~

确认恢复目标为空后：

~~~bash
export DAEP_RESTORE_DATABASE=daep_restore
export DAEP_BACKUP_FILE=/protected/path/daep-backups/daep-<timestamp>.dump
export DAEP_CONFIRM_RESTORE=YES
~~~

## 5. 执行 Restore

~~~bash
./scripts/restore_postgres.sh
~~~

恢复脚本必须拒绝 checksum 不匹配、backup 不存在、非空目标、source database 与 restore database 相同、未设置 DAEP_CONFIRM_RESTORE=YES 等危险情况。

记录 restore 开始/结束时间、restore 耗时、dump 大小、PostgreSQL 日志异常和是否出现 partial restore。

## 6. 验证恢复数据库

~~~bash
./scripts/verify_restored_postgres.sh
~~~

必须 PASS：

- Alembic revision 与当前代码 head 一致
- 核心表存在
- 核心表全部启用 forced RLS
- 15 个租户 RLS policy 存在
- daep_authenticate_member 为 SECURITY DEFINER
- runtime role 不具备 bypass RLS
- privileged login 角色边界正确
- privileged membership 正确

## 7. 应用级恢复验证

在隔离环境使用恢复数据库启动应用，至少验证：

- /readyz
- /health
- /api/v1/projects
- 成员鉴权
- 项目读取
- 需求读取
- 任务读取
- 治理读取
- RLS 隔离
- Workflow / Gate
- Work Package
- Agent registry / project_agents
- outbox / inbox / message

## 8. 回滚与清理

本演练默认不切换生产流量。

验证结束后删除隔离恢复数据库：

~~~bash
docker compose -f "$DAEP_COMPOSE_FILE" exec -T postgres   psql -U daep_bootstrap -d postgres -v ON_ERROR_STOP=1   -c 'DROP DATABASE daep_restore'
~~~

备份文件按组织保留策略归档，不得因为演练完成而删除唯一备份。

## 9. 证据记录

| 项目 | 结果 | 证据 |
|---|---|---|
| Compose config | ☐ | command output |
| Production startup | ☐ | compose ps |
| Readiness | ☐ | /readyz |
| Source DB baseline | ☐ | SQL output |
| Backup | ☐ | backup log |
| Checksum | ☐ | sha256 output |
| Empty target | ☐ | SQL output |
| Restore | ☐ | restore log |
| Alembic verification | ☐ | verify output |
| RLS verification | ☐ | verify output |
| Application verification | ☐ | API output |
| Cleanup | ☐ | SQL output |

## 10. 通过标准

只有以下全部满足，才可以把 Operations Ready 标记为 PASS：

1. backup 成功并可读取；
2. checksum 成功；
3. restore 到独立空数据库成功；
4. restored DB verification 全部 PASS；
5. 恢复后的应用能够启动并访问核心 API；
6. RLS、角色边界和 Alembic revision 正确；
7. 有完整的耗时、日志和证据记录；
8. 没有修改生产源数据库或生产流量。

## 当前状态

**待真实环境执行。**

仓库已经提供：

- compose.production.yaml
- scripts/backup_postgres.sh
- scripts/restore_postgres.sh
- scripts/verify_restored_postgres.sh
- scripts/production_smoke.sh

下一阶段是实际执行演练并把结果填回发布签署记录。
