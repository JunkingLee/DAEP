# DAEP RC9 双 Agent 实机互操作验收 Drill

## 1. 目的与边界

本 Drill 是 RC9 从 API-level two-member E2E 进入真实双 Agent 实机互操作验收的正式执行手册。

边界声明：DAEP 不托管、不启动、不强制唤醒成员本地 Agent Runtime。

目标：
- 两名真实项目成员分别在两台独立工作站运行各自的本地 MCP-compatible Agent/MCP Host。
- 两个 Agent 使用不同成员 Token、不同 Agent 名称，并分别注册和发送 heartbeat。
- 完成 discovery、能力匹配、人工选择、Work Package、消息、ACK、Artifact、Result、协作时间线。
- 验证 Agent 离线期间 durable inbox/outbox 不丢消息，恢复后可以继续拉取并 ACK。
- 明确 DAEP 只负责项目工作协调和持久化证据，不创建、托管、启动、停止或强制唤醒 Agent Runtime。

本 Drill 不验证通用 MCP Host 兼容性、休眠模型自动唤醒、生产网络故障恢复、生产 PostgreSQL restore 或浏览器视觉验收。

## 2. 强制拓扑与边界

Workstation A：Member A → MCP Host / Local Agent A → DAEP MCP stdio adapter
Workstation B：Member B → MCP Host / Local Agent B → DAEP MCP stdio adapter
平台侧：DAEP API + PostgreSQL → Project / Work Package / Inbox / Outbox / Audit

强制要求：
- A、B 必须使用两个不同成员 Token。
- A、B 必须使用两个不同 Agent 名称。
- A、B 必须分别运行在独立工作站或独立本地进程。
- 不允许用同一个 Agent 进程的两个 UI 标签页冒充双 Agent。
- 不允许使用平台、worker、管理员 Token 作为 Agent Token。
- Agent Runtime 的启动、停止、模型调用由成员自己的 Host/Agent 负责。

## 3. 前置条件

- 使用 release/1.0.0-rc9。
- Production Compose 已启动，/readyz 正常，migration 完成。
- 已准备一个测试项目，成员 A/B 均属于该项目。
- 已准备一个可拆分为至少两个 Work Package 的父任务。
- 两台工作站都安装项目 requirements，并配置 DAEP_API_URL。

Workstation A：
export DAEP_MEMBER_TOKEN='<MEMBER_A_TOKEN>'
python -m daep_mcp.server

Workstation B：
export DAEP_MEMBER_TOKEN='<MEMBER_B_TOKEN>'
python -m daep_mcp.server

Token 不得写入仓库、截图或验收报告。

## 4. Step 1 — 双 Agent 注册与心跳

Agent A 调用 register_local_agent：
project_id=<PROJECT_ID>
agent_name=agent-a
capabilities=[requirements,coordination]
protocols=[mcp]
status=AVAILABLE

Agent B 调用 register_local_agent：
project_id=<PROJECT_ID>
agent_name=agent-b
capabilities=[python,testing]
protocols=[mcp]
status=AVAILABLE

随后分别调用 heartbeat_local_agent。

PASS：
- registry 中存在两条独立记录。
- member_id 不同，agent_name 不同。
- protocol 包含 mcp。
- heartbeat 时间刷新。
- 120 秒 freshness window 内显示为可用。

## 5. Step 2 — Discovery 与能力匹配

调用：
GET /api/v1/projects/<PROJECT_ID>/agent-matches?required_capabilities=python,testing&protocol=mcp

PASS：
- Agent B 对 python/testing + mcp 显示为匹配。
- 不匹配或 stale Agent 不得错误显示为 eligible。
- matching 只提供建议，不创建 delegation、不发送消息、不调用 Agent Runtime。
- capability 是 Agent 自报 metadata，不是平台能力认证。

## 6. Step 3 — 跨成员 Work Package

由 Member A 或项目管理员创建父任务下的 Work Package，并将一个包绑定到 Member B / agent-b。

可通过 MCP tool：
create_task_work_package(parent_task_id, title, assignee_member_id, agent_name, description)

PASS：
- Work Package 与父任务关联。
- Member B 与 agent-b 绑定。
- 平台没有创建本地 Agent 进程。
- Work Package 生命周期可在 API/UI 追踪。

## 7. Step 4 — 真实本地 Agent 执行

Member B 的真实本地 Agent 通过 MCP Host：
1. 拉取自己的任务。
2. 读取任务与 Work Package。
3. 执行真实本地工作。
4. 产生真实 Artifact。
5. 上报 progress。
6. 提交 Work Package result。

示例工具：
report_task_progress(task_id, progress, note)
submit_task_artifact(task_id, artifact_type, uri, commit_sha)
report_work_package_result(task_id, outcome, summary, idempotency_key)

PASS：
- Artifact 可以追溯到 Work Package。
- Result 与 Work Package 对应。
- 相同 idempotency key 的重复提交不会造成重复状态转换。
- 子 Work Package 未满足门禁时父任务不能错误收口。

## 8. Step 5 — 消息与 ACK

Member A 调用 send_collaboration_message，recipient_member_id 指向 B。
Member B 调用 get_my_notifications 拉取。
实际处理消息后调用 acknowledge_notification。

PASS：
- 消息先进入 durable inbox。
- B 能拉取消息。
- ACK 在实际处理后发生。
- 重复 ACK 不产生重复业务结果。
- 刷新 UI 后 ACK 状态保持。
- Work Timeline 能看到消息及 acked_at。

## 9. Step 6 — 离线恢复

停止 Workstation B 的 MCP adapter/Host，但不要删除 Agent registry。
等待超过 120 秒，使 B 的 heartbeat 过期。

然后由 A 发送唯一标识为 OFFLINE-RECOVERY-<ID> 的消息。

PASS：
- 消息仍然持久化。
- 消息不会因为 B 离线而丢失。
- DAEP 不需要也不得唤醒 B。

恢复 B：
1. 启动 MCP adapter/Host。
2. heartbeat_local_agent(project_id, agent_name=agent-b, status=AVAILABLE)。
3. get_my_notifications(after=<LAST_CURSOR>)。
4. 处理并 ACK 离线期间消息。

PASS：
- OFFLINE-RECOVERY-<ID> 被完整取回。
- ACK 成功。
- 不产生重复业务处理。
- 时间线能串起发送 → pending → recovery → ACK。

## 10. Step 7 — 协作时间线与父任务收口

查询：
list_task_work_packages(parent_task_id)
get_task_work_summary(parent_task_id)
get_task_work_timeline(parent_task_id)

时间线至少应能关联：Member A、Member B、Agent A、Agent B、Work Package、Message、ACK、Artifact、Work Result、Review/Approval。

在子 Work Package 未完成 Review 前，父任务不得最终完成。满足必要 Review 后，才允许进入后续收口流程。

## 11. Step 8 — 负向授权验证

| 场景 | 预期 |
|---|---|
| A 使用自己的 Token 读取 B 私有成员数据 | DENY / 不泄露 |
| A 操作 B 的 Agent | DENY |
| B 无授权操作 A 的任务 | DENY |
| 不属于项目的 Agent | 不出现在 discovery |
| stale Agent | 不标记 eligible |
| capability 不匹配 | 不标记 eligible |
| 非管理员 reassignment | DENY |
| matching API | 不创建 delegation |
| DAEP UI | 不提供启动/唤醒 Agent 操作 |

## 12. Step 9 — 证据采集

DAEP 侧至少保存：
- Agent registry。
- 两个 heartbeat 记录。
- Agent matching response。
- Work Package ID。
- Message ID 与 ACK 状态。
- Artifact ID/URI。
- Work Result。
- Work Summary。
- Work Timeline。
- Audit event。
- 离线前后 Agent 状态。

两台工作站至少记录：hostname、agent_name、非 secret 的 member identifier、MCP Host version、adapter commit、启动时间、heartbeat、offline、recovery 时间。

不得记录 member token、OAuth secret、API secret、模型 provider key。

## 13. 最终验收表

| ID | 验收项 | 结果 | 证据 |
|---|---|---|---|
| A01 | 两台独立工作站 | ☐ | 主机记录 |
| A02 | 两个独立成员身份 | ☐ | API/审计 |
| A03 | 两个独立 Agent | ☐ | registry |
| A04 | MCP protocol | ☐ | registry |
| A05 | 双 Agent heartbeat | ☐ | heartbeat |
| A06 | capability matching | ☐ | matching response |
| A07 | Work Package 创建 | ☐ | WP ID |
| A08 | Agent B 真实执行 | ☐ | Agent log |
| A09 | Artifact 提交 | ☐ | artifact ID |
| A10 | Work Result | ☐ | task/WP state |
| A11 | A→B 消息 | ☐ | message ID |
| A12 | B ACK | ☐ | acked_at |
| A13 | 离线消息持久化 | ☐ | inbox |
| A14 | Agent 恢复 | ☐ | heartbeat |
| A15 | 恢复后消息取回 | ☐ | cursor/message |
| A16 | 重复 ACK/result 安全 | ☐ | API response |
| A17 | Work Timeline 完整 | ☐ | timeline |
| A18 | 父任务完成门禁 | ☐ | summary/state |
| A19 | 成员/项目隔离 | ☐ | negative tests |
| A20 | DAEP 不托管 Agent Runtime | ☐ | architecture evidence |

## 14. Pass / Fail 判定

只有以下全部满足，才能标记 Agent Interoperability Ready = PASS：
1. A01–A08 PASS。
2. 至少一个真实 Artifact 从本地 Agent 产生并进入 DAEP。
3. A→B 消息与 B ACK 完成。
4. B 离线期间消息不丢失，恢复后可以继续处理。
5. Work Timeline 串联两个成员、两个 Agent、Work Package、消息、ACK、Artifact、Result。
6. 至少一个负向授权场景 PASS。
7. 全过程没有依赖 DAEP 启动或唤醒 Agent Runtime。
8. 证据没有泄露 secret。

出现以下任一情况即 FAIL：双 Agent 实际由同一进程冒充；使用同一 Token；成员与 Agent 身份错配；离线消息丢失；ACK 早于实际处理；重复请求造成重复业务状态；跨项目越权；Artifact/Result 无法追溯；或 DAEP 直接控制 Agent Runtime。

## 15. 当前状态

API-level two-member Agent delivery E2E：代码级 PASS。
MCP local adapter：已实现。
Agent topology / matching / collaboration UI：已实现。
双 Agent 实机互操作：待真实环境执行。
双机离线恢复：待真实环境执行。
MCP Host 兼容矩阵：待真实环境执行。

因此当前不得把 Agent Interoperability Ready 标记为已完成。完成本 Drill 并取得真实证据后，才进入 RC → GA 最终决策。