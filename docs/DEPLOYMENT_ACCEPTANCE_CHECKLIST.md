# DAEP 1.0.0-rc9 部署验收清单

> 本清单用于区分 CI 已覆盖的自动化验证与必须在真实部署环境完成的验收。CI 通过不等于真实环境验收通过。请在执行时填写结果和证据；不要把真实密钥、Token、Cookie 或个人数据写入本文件、工单或日志。

## 1. 验收基本信息

| 项目 | 记录 |
|---|---|
| 环境名称 / URL | 待填写 |
| 部署版本 / Git SHA | 待填写 |
| 部署时间（含时区） | 待填写 |
| 验收人员 | 待填写 |
| DAEP API / Web 版本 | 待填写 |
| PostgreSQL 版本 | 待填写 |
| Agent Runtime 类型 / 版本 | 待填写 |
| 验收结论 | NOT RUN / PASS / FAIL / BLOCKED |

结果约定：每项标记 `PASS`、`FAIL`、`BLOCKED` 或 `N/A`。只有有可复核证据的项目才能标记 PASS。证据记录脱敏后的日志片段、测试记录或内部工单链接，不记录秘密值。

## 2. CI 已验证范围（部署前基线）

以下内容已有仓库 CI 自动化覆盖，但部署后仍需验证真实配置与运行表现：

- Python 3.11、3.12、3.13 单元 / API 测试。
- PostgreSQL Migration 与 RLS 自动化检查。
- Chromium Browser E2E，包括 Task Collaboration UI 流程。
- Container Build。
- Production Compose 配置与启动检查。

最近一次基线：
- 代码修复验证 Run：[45537563659](https://github.com/JunkingLee/DAEP/actions/runs/45537563659)，HEAD `3ffd7abce85357ddfc95fa25c4dd211ae8ab1561`，七个 Job 全部成功。
- 交接文档更新验证 Run：[45537774293](https://github.com/JunkingLee/DAEP/actions/runs/45537774293)，七个 Job 全部成功。
- 上述结果证明 CI 环境中的自动化检查通过，不证明真实 OIDC Provider、外部 Agent Runtime、生产网络、密钥管理或实际 Worker 部署已验收。

## 3. 部署配置与基础设施

| ID | 验收项 | 操作与通过标准 | 结果 / 证据 |
|---|---|---|---|
| ENV-01 | 环境变量完整 | 对照当前部署配置逐项核对数据库连接、应用密钥、OIDC、公开站点/API 地址、CORS、Worker、MCP 等必需配置；无缺失项 | 待执行 |
| ENV-02 | 密钥注入 | 所有秘密通过部署平台 Secret / 环境注入机制提供；仓库、镜像层、Compose 明文、前端资源和日志中均无秘密 | 待执行 |
| ENV-03 | HTTPS 与域名 | Web、API、OIDC 回调和 MCP 对外端点使用预期域名与 TLS；证书有效且续期机制明确 | 待执行 |
| ENV-04 | 网络边界 | 数据库和内部 Worker 接口不暴露公网；仅开放业务必需入口；跨域来源符合白名单策略 | 待执行 |
| ENV-05 | 健康检查 | API、数据库依赖及 Worker 健康检查状态正常；重启后能恢复，不出现持续 CrashLoop | 待执行 |
| ENV-06 | 持久化 | PostgreSQL 数据目录 / 卷持久化，容器重建后业务数据仍存在 | 待执行 |
| ENV-07 | 当前 Schema | 在全新开发/验收数据库上执行当前版本 Schema 初始化与 Alembic upgrade，确认 head 一致且服务可启动 | 待执行 |

说明：本项目当前处于开发阶段，本清单只检查当前 Schema 的初始化/升级能力；不包含旧系统历史数据迁移、数据回填、旧库利旧或迁移兼容性验收。

## 4. 人类用户身份与租户边界

| ID | 验收项 | 操作与通过标准 | 结果 / 证据 |
|---|---|---|---|
| ID-01 | OIDC 登录 | 使用真实 OIDC Provider 完成登录、回调、退出和重新登录；无回调地址或 issuer 错配 | 待执行 |
| ID-02 | Member 身份 | 登录后获得正确 Member 身份、Tenant 和角色；浏览器请求不依赖手工伪造身份头 | 待执行 |
| ID-03 | Tenant 隔离 | 使用两个不同 Tenant 的测试账号验证项目、Task、Agent、消息、通知和审计数据不可跨租户读取或修改 | 待执行 |
| ID-04 | 角色边界 | 普通成员不能执行仅管理员/负责人可执行的管理操作；API 返回预期拒绝状态 | 待执行 |
| ID-05 | Task 分配 | 创建项目与 Task，将 Task 分配给人类 Member；确认负责人、参与者与权限显示正确 | 待执行 |

## 5. Agent Runtime 与 MCP 接入

| ID | 验收项 | 操作与通过标准 | 结果 / 证据 |
|---|---|---|---|
| AG-01 | Agent 归属 | Member 创建或绑定自己的 Agent；确认 Agent 唯一归属其 Owner，不存在 Project 级 Agent 归属 | 待执行 |
| AG-02 | 凭证安全 | 使用真实 Agent 凭证完成认证；凭证只在服务端安全存储/传输，不出现在 UI、日志或审计详情中 | 待执行 |
| AG-03 | MCP 连通 | 从外部 Agent Runtime 连接部署后的 MCP endpoint，完成认证、工具发现与调用 | 待执行 |
| AG-04 | 工具白名单 | 验证 Agent 只能调用允许的 Agent 工具；Session 管理、Grant 管理等 Owner/Member 管理接口不能由 Agent 越权调用 | 待执行 |
| AG-05 | 运行时边界 | 确认 DAEP 只管理身份、连接、授权、消息、协作上下文与审计；Agent Runtime 仍运行在用户自己的环境，DAEP 不负责启动或调度 Runtime | 待执行 |

## 6. Task 协作授权与工作流

使用至少两个不同 Member/Owner 及其各自 Agent，完成一条端到端流程。

| ID | 验收项 | 操作与通过标准 | 结果 / 证据 |
|---|---|---|---|
| COL-01 | Task Policy | 配置 TEAM 协作策略；确认多 Agent 开关与数量限制按 Task Policy 生效，`max_agents = NULL` 表示不设固定数量上限 | 待执行 |
| COL-02 | Owner 授权 | Task 负责人邀请另一个 Member 的 Agent 参与；只有该 Agent 的 Owner 能授权自己的 Agent，Task 负责人不能代替 Owner 授权 | 待执行 |
| COL-03 | Agent 接受 | Agent 从自己的 Collaboration Grant inbox 读取授权并接受；未接受、撤销或过期授权不能加入协作 | 待执行 |
| COL-04 | Session 生命周期 | Member Task 负责人创建/打开默认 Session、暂停、恢复并关闭；关闭后保留历史且阻止新协作写入 | 待执行 |
| COL-05 | 协作消息 | 有效授权的 Agent 读取并发送 Task 协作消息；无有效 Grant 的 Agent 无法读取或写入 | 待执行 |
| COL-06 | Proposal | Agent 创建工作包、帮助请求或其他允许的 Proposal；Proposal 本身不直接变更正式负责人、Work Package、审批或验收状态 | 待执行 |
| COL-07 | Owner 决策 | 对 Proposal 执行接受/拒绝/撤回等决策；确认正式变更仍由有权限的人类 Member 完成 | 待执行 |
| COL-08 | 撤销与过期 | Owner 撤销授权，或将测试 Grant 设置为已过期；后续 Agent 协作操作被拒绝，状态、审计与通知均可查询 | 待执行 |
| COL-09 | 独立进度 | 两个 Agent 分别更新各自工作记录/产物；确认不会互相覆盖或争写 Task 总体进度 | 待执行 |
| COL-10 | 非授权发现 | 验证 Agent 只能发现 Task 范围内允许公开的信息；TEAM 策略和 Presence 不会自动授予 Project 全域访问权 | 待执行 |

## 7. 通知、Outbox 与 Worker

注意：Worker 位于 Compose `broker` profile，普通 `docker compose up -d` 不会启动它。未启动 Worker 时，Outbox 投递、Grant 到期提醒和到期状态物化均不会周期执行。生产环境必须按 NOT-01 显式启动并配置 Broker Gateway。

| ID | 验收项 | 操作与通过标准 | 结果 / 证据 |
|---|---|---|---|
| NOT-01 | Worker Token 与启动方式 | 使用独立 Worker Token 调用内部调度接口成功；Member / Agent Token 调用被拒绝；生产环境显式执行 `docker compose -f compose.production.yaml --profile broker up -d daep-worker` 并确认 Worker 运行 | 待执行 |
| NOT-02 | Outbox 投递 | 配置有效的 `DAEP_BROKER_WEBHOOK_URL` 与独立 `DAEP_BROKER_WEBHOOK_TOKEN`；触发授权事件，确认 Inbox 与 Outbox 记录生成、Worker 取件并完成投递；下游按 Outbox ID / Message ID 去重（at-least-once） | 待执行 |
| NOT-03 | 重试与 DEAD | 在隔离测试环境制造可控投递失败，确认重试次数、退避、最终 DEAD 状态和错误记录符合预期 | 待执行 |
| NOT-04 | 恢复审计 | 对 DEAD 事件执行受控恢复/重放；确认操作原因、操作者与结果可审计，且不会无意重复产生业务副作用 | 待执行 |
| NOT-05 | 到期提醒 | 配置短期测试 Grant 与提醒节点，确认 Worker 按 Owner 偏好提醒且同一周期幂等 | 待执行 |
| NOT-06 | 到期物化 | 让测试 Grant 到期，确认状态转为 EXPIRED，审计和 Owner 通知产生 | 待执行 |
| NOT-07 | 偏好边界 | 关闭某类通知后确认只抑制相应通知生成；Grant 授权、撤销、接受、续期和过期生命周期不受影响；重新开启不补发历史通知 | 待执行 |
| NOT-08 | Member 可见性 | Member 查看自己的通知、投递状态、ACK 与通知审计；不能查看其他 Owner 的收件箱或 Worker lease 凭据 | 待执行 |

## 8. 安全、审计与运维

| ID | 验收项 | 操作与通过标准 | 结果 / 证据 |
|---|---|---|---|
| OPS-01 | 日志脱敏 | 检查 API、Worker、反向代理日志，不包含密码、Token、Cookie、Authorization Header 或敏感请求体 | 待执行 |
| OPS-02 | 审计完整性 | 对 Grant 创建、接受、续期、撤销、过期及 Proposal 决策执行操作；确认审计记录包含正确主体、目标、Tenant、Task 和时间 | 待执行 |
| OPS-03 | 权限负向测试 | 对关键 Member / Agent / Worker API 执行未认证、错误身份、跨租户、错误 Owner 和过期 Grant 请求，均按预期拒绝 | 待执行 |
| OPS-04 | 备份 | 确认 PostgreSQL 备份计划、保留策略、访问权限与加密方式 | 待执行 |
| OPS-05 | 恢复演练 | 在隔离环境执行一次备份恢复，验证 API、用户、Task、Grant、消息与审计数据可用 | 待执行 |
| OPS-06 | 监控告警 | 为 API 错误率、Worker 停滞、Outbox DEAD、数据库容量与连接耗尽设置告警并验证告警可达 | 待执行 |

## 9. 验收记录模板

每次验收建议按以下格式记录，证据链接应指向受控内部系统：

| 字段 | 内容 |
|---|---|
| 验收 ID | 例如 COL-03 |
| 结果 | PASS / FAIL / BLOCKED / N/A |
| 执行时间 | 含时区 |
| 执行人 | Member / 运维人员标识 |
| 环境与版本 SHA | 环境名、部署版本 |
| 操作步骤 | 实际执行的步骤 |
| 预期结果 | 本清单定义的通过标准 |
| 实际结果 | 实际观察到的行为 |
| 证据 | 脱敏日志、截图或工单链接 |
| 缺陷 / 后续动作 | 责任人与计划完成时间 |

## 10. 交付门槛

- 所有身份、租户隔离、Agent Owner 授权、Grant 生命周期与 MCP 工具边界项目必须 PASS。
- 所有部署基础设施与 Worker/Outbox 关键项目必须 PASS；若某项不适用，需记录理由并经负责人确认。
- 不允许存在未评估的 FAIL；BLOCKED 项必须明确阻塞原因、责任人和解除条件。
- 代码 CI 全绿仅代表自动化基线通过。真实 OIDC、生产 PostgreSQL/RLS、Worker Token、外部 Agent Runtime/MCP 连通性和端到端用户流程，必须在目标部署环境实际验收后，才能宣布部署交付完成。
