# DAEP RC9 Final Evidence Package

## 目的

本文件是 RC9 → GA 决策前的最终证据汇总模板。它不代表真实浏览器、Production PostgreSQL Restore 或双 Agent 实机互操作已经通过。

任何门禁只有在真实环境执行、保留可复核证据并由执行人填写结果后，才能从“待执行”变为“PASS”。

## 三项阻塞门禁

| 门禁 | 执行基线 | 当前状态 | 必须具备的证据 |
|---|---|---|---|
| Real Browser Acceptance | docs/RC9_BROWSER_ACCEPTANCE_RUNBOOK.md | NOT EXECUTED | 浏览器环境、截图/录像、逐项结果、问题单 |
| Production Backup/Restore | docs/RC9_PRODUCTION_BACKUP_RESTORE_DRILL.md | NOT EXECUTED | backup checksum、restore log、DB verification、API verification、耗时 |
| Dual-Agent Interoperability | docs/RC9_AGENT_INTEROPERABILITY_DRILL.md | NOT EXECUTED | 两台独立主机/Agent、heartbeat、WP、ACK、artifact、offline/recovery、timeline |

## A. Real Browser Acceptance

执行人：
日期/时区：
浏览器及版本：
OS：
环境 URL：
证据位置：

必测角色：
- [ ] 系统管理员
- [ ] 项目管理员（至少两个项目）
- [ ] 产品人员
- [ ] 开发人员
- [ ] 测试人员
- [ ] 项目审核人员

必测区域：
- [ ] 我的项目 / 项目总览 / 工作台 / 工作
- [ ] 协作 / 治理 / 依赖关系 / 异常协调
- [ ] Work Package / 消息收件箱
- [ ] Workflow / Gate / Agent 协作
- [ ] 空态 / Loading / Error / 刷新 / 项目切换
- [ ] 1440×900 / 1280×800 / 1024×768 / 768×1024 / 390×844

结果：
- 总项：
- PASS：
- FAIL：
- BLOCKED：
- [ ] 全部关键项 PASS
- [ ] 所有 FAIL 已修复并重新验证

## B. Production PostgreSQL Backup/Restore

执行人：
日期/时区：
Compose commit：
PostgreSQL 版本：
源数据库：
恢复目标数据库：
备份文件：
SHA-256：
Backup 耗时：
Restore 耗时：

- [ ] Compose 配置通过
- [ ] /readyz PASS
- [ ] backup 文件生成
- [ ] pg_restore --list PASS
- [ ] checksum PASS
- [ ] restore 到空数据库 PASS
- [ ] verify_restored_postgres.sh PASS
- [ ] Alembic head PASS
- [ ] RLS / policies PASS
- [ ] runtime / privileged role boundary PASS
- [ ] 应用重新启动 PASS
- [ ] authenticated project API PASS
- [ ] 核心业务 API PASS

结果：
- [ ] Production Restore Ready = PASS
- [ ] 否则保持 NOT EXECUTED / FAIL，不得进入 GA

## C. Dual-Agent Interoperability

| 项目 | Agent A | Agent B |
|---|---|---|
| 成员 | | |
| 主机 | | |
| MCP Host | | |
| Agent Runtime | | |
| capability | | |
| heartbeat | | |

- [ ] A/B 使用不同成员身份
- [ ] 两个 Agent 独立运行
- [ ] register / heartbeat / presence
- [ ] capability matching
- [ ] cross-member Work Package
- [ ] Agent 实际执行
- [ ] Artifact / Result
- [ ] collaboration message / ACK
- [ ] durable inbox/outbox
- [ ] offline/recovery
- [ ] Work Timeline
- [ ] 无权限操作被拒绝

运行边界：
- [ ] DAEP 没有托管 Agent Runtime
- [ ] DAEP 没有启动 Agent Runtime
- [ ] DAEP 没有强制唤醒 Agent Runtime
- [ ] Agent 由成员自己的 MCP Host/本地运行环境管理

结果：
- [ ] Agent Interoperability Ready = PASS
- [ ] 否则保持 NOT EXECUTED / FAIL，不得进入 GA

## D. RC → GA 决策

只有三个真实门禁全部 PASS 才允许进入 GA release review。

| 门禁 | 结果 |
|---|---|
| Real Browser Acceptance | PASS / FAIL / NOT EXECUTED |
| Production Backup/Restore | PASS / FAIL / NOT EXECUTED |
| Dual-Agent Interoperability | PASS / FAIL / NOT EXECUTED |

规则：
1. 任一项 NOT EXECUTED → 不得 GA。
2. 任一项 FAIL → 不得 GA。
3. 三项全部 PASS → 才能进入 GA release review。
4. GA review 仍需明确授权，不自动合并 main。

## E. Sign-off

QA：
项目管理员：
系统管理员：
Release Owner：
决策日期：
决策：RC / GO / NO-GO
备注：

> 本文件是证据汇总模板。没有真实环境证据时，任何勾选 PASS 都视为无效。
