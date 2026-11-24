# MCP 集成规范与实施边界

## 目标拓扑
Agent Host（由成员自行运行）→ MCP Client（Host 管理）→ DAEP MCP Server → DAEP REST/API 服务。
平台不创建、不托管、不控制 Agent Runtime。

## 建议 MCP Tools
- `get_my_tasks` → `GET /api/v1/me/tasks`
- `get_task_detail` → `GET /api/v1/tasks/{task_id}`
- `get_my_notifications` → `GET /api/v1/me/notifications`
- `acknowledge_notification` → `POST /api/v1/messages/{message_id}/ack`
- `report_task_progress` → `POST /api/v1/tasks/{task_id}/progress`
- `report_task_blocked` → `POST /api/v1/tasks/{task_id}/blocked`
- `submit_task_artifact` → `POST /api/v1/tasks/{task_id}/artifacts`
- `send_collaboration_message` → `POST /api/v1/messages`

## 双向消息语义
Agent→平台：MCP Tool 调用 API，平台写入事件与业务状态。  
平台→Agent：平台先持久化消息到成员收件箱；Agent 调用 `get_my_notifications` 拉取并使用 ack 确认。WebSocket 可用于在线通知用户/本地桥接，但不能保证所有 Host 自动唤醒模型。

## MCP Server 正式实施要求
独立实现并发布 Streamable HTTP MCP Server；锁定 MCP SDK 与协议版本；使用 OAuth 2.1/OIDC 或符合 MCP 授权规范的认证；工具调用需绑定成员身份、设备和组织授权；为不同 Host 建立 tools、resources、notifications 能力兼容矩阵；至少选两种 MCP Host 完成端到端测试。

本交付包包含由成员本机 MCP Host 启动的 stdio MCP Server 适配器；它不是由 DAEP 托管的远程 Streamable HTTP MCP 服务，也不负责唤醒休眠的 Agent 模型。

## Executable MCP adapter (rc2)

The `daep_mcp/server.py` file is an executable stdio MCP server using the Python MCP SDK. It is launched by each developer's MCP Host on that developer's computer. Configure `DAEP_API_URL` and that member's individual `DAEP_MEMBER_TOKEN`, then point the Host to `python /absolute/path/to/daep_mcp/server.py`. See `daep_mcp/README.md` for a complete client configuration example.

The adapter currently exposes eight tools: `get_my_tasks`, `get_task_detail`, `get_my_notifications`, `acknowledge_notification`, `report_task_progress`, `report_task_blocked`, `submit_task_artifact`, and `send_collaboration_message`.

This is request/response MCP tool integration. It does not force a Host to wake an idle model, and does not claim full compatibility with every MCP Host. Validate against the actual Host versions selected by the deploying organization.


## AgentTaskGrant 安全模型（rc9 Stage B）

使用 `DAEP_AGENT_TOKEN` 时，MCP adapter 在本地调用层实施 Agent 路径 allowlist：只允许 Agent context、Agent 自己的 Grant inbox/accept，以及 task detail、progress、blocked、artifact submit/read/versions/quality REST 路由。Agent Token 不会回退成其 owner Member Token；所有其他 Member 收件箱、通知 ack、协作消息、任务委派、项目发现/注册、项目审计、审批、work-package 治理及旧 Agent Assignment 工具调用都会在 adapter 内拒绝。

- `list_my_agent_tasks`（兼容旧工具名）现在读取 `GET /api/v1/agents/me/grants`，不再查询旧 `agent_task_assignments`。
- `list_my_agent_grants` 是语义明确的新工具名。
- `accept_agent_task`（兼容旧工具名，参数现为 `grant_id`）和 `accept_agent_task_grant` 都调用 `POST /api/v1/agent-grants/{grant_id}/accept`。
- Agent task detail/progress/blocked/artifact 工具继续由 REST 层 `require_agent_task_grant` 对 ACCEPTED 状态、期限、租户、当前唯一人类责任人和精确 scope 做逐请求验证。
- Member Token 的兼容工具集保持原有行为；这不代表 Agent 可以使用 Member 权限。

此 allowlist 是 MCP 工具适配层的纵深防御；REST API 仍是最终授权边界。项目 Agent Presence 仅用于能力发现，不构成 task execution grant。
