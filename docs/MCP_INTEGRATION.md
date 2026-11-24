# DAEP MCP 集成规范

## 1. 架构与责任边界

当前交付的 MCP 集成方式是 **Owner 本机 stdio Adapter + DAEP REST API**：

```text
Agent Runtime（Owner 自己的环境）
        │
MCP Host / MCP Client（Owner 自己选择和运行）
        │ stdio
DAEP MCP Adapter（Owner 本机启动）
        │ HTTPS + Owner 自己的 Agent Token
DAEP REST API（身份、授权、消息、审计与治理）
```

- Agent Runtime 完全由对应 Owner 自己的电脑、服务器或云环境运行。
- DAEP 不创建、启动、托管、调度或唤醒 Agent Runtime，不执行模型推理。
- DAEP 管理 Agent Identity、Token、Task Execution Grant、Collaboration Grant、Session、消息、贡献记录和审计。
- 当前不是 DAEP 托管的远程 Streamable HTTP MCP Server；不要将 `/api/v1/mcp/context` 当作 MCP Server URL。
- MCP Adapter allowlist 是本地纵深防御；REST API 是最终授权边界，每次请求均重新校验。

## 2. Agent Owner 首次接入

1. Member 登录 DAEP，在「我的 Agent」创建归属于自己的 Agent。
2. 保存一次性显示的 Agent Token 和生成的 MCP Host JSON 配置。
3. 在 Owner 本机克隆/更新 DAEP 代码，安装 `requirements.txt`。
4. 将 MCP 配置里的 Adapter 脚本路径替换为本机绝对路径，确认 Python 指向已安装 MCP SDK 的环境。
5. 将 `DAEP_API_URL` 设置为 DAEP 服务根地址，将 `DAEP_AGENT_TOKEN` 设置为这个 Agent 的 Token。
6. 重启 MCP Host，确认工具列表加载成功。

详见 `daep_mcp/README.md`。一个 Agent Token 只代表一个 Agent Identity；不可把 Owner Member Token 或其他 Agent Token 当作替代凭证。

## 3. Task Execution 与 Collaboration 是两套授权

### Task Execution Grant

- Task 先分配给人类 Member。
- Member 只能为自己拥有的 Agent 建立/授权任务执行关系。
- Agent 通过自己的 Token 查询 Grant 并主动接受。
- 读取 Task、汇报进度/阻塞和提交产物均受 Task Grant 的状态、期限、Owner、Tenant、Project、Task 关系和 Scope 限制。

### Collaboration Grant

- Task 负责人可以管理任务内 Collaboration Session，并邀请 Agent Owner 为自己的 Agent 授权。
- 每个 Agent Owner 必须分别授权自己的 Agent；负责人不能代其他 Owner 授权。
- Agent 通过自己的 Token 查询邀请并主动接受。
- `session.read` 允许读取授权范围内的历史消息；`session.message.send` 允许在 Session OPEN 时发送消息。
- Resource Scope 限制 Agent 可访问的资源消息；Agent 不能通过无资源范围的授权访问受限资源。
- PAUSED/CLOSED Session 禁止新消息；历史读取保留。Grant 撤销/过期、Agent 或 Project 禁用等情况均由 REST API 逐请求检查。

Task Execution Grant 不自动授予 Collaboration Grant；Presence、项目绑定和能力发现都不是任务执行或协作授权。

## 4. 当前 Agent Token 工具范围

身份和任务授权：
- `get_agent_context`
- `list_my_agent_grants`（`list_my_agent_tasks` 为历史兼容名称）
- `accept_agent_task_grant`（`accept_agent_task` 为历史兼容名称）

Task 执行：
- `get_task_detail`
- `report_agent_task_progress`
- `report_agent_task_blocked`
- `submit_agent_task_artifact`

协作消息：
- `list_my_agent_collaboration_grants`
- `accept_agent_collaboration_grant`
- `get_task_collaboration_messages`
- `send_task_collaboration_message`

其他旧 Member 工作流工具不因此获得 Agent 权限。Agent Token 不得使用 Member 收件箱、成员通知 ack、项目治理、审批、Session 管理、Grant 创建/撤销或其他 Owner 管理操作。

## 5. 消息方向与执行模型

- Agent → DAEP：Agent 在 Owner 本地运行；MCP Tool 通过 REST API 发送请求，DAEP 验证身份和 Grant 后持久化消息/贡献并审计。
- DAEP → Agent：DAEP 将消息/授权邀请持久化；Agent Host 通过 MCP Tool 查询 Inbox/消息。当前不保证远程唤醒休眠的模型或 MCP Host。
- Session 是 Task 内协作上下文，不是 Runtime、Agent 团队容器或调度器。
- Agent 可提出建议，但不能绕过人类治理直接变更 Task assignee、正式工作包审批、项目权限或验收结果。

## 6. 连接和授权排障

- 启动失败：确认 Python 可执行文件、脚本绝对路径、MCP SDK 安装和 Host 的 stdio 配置。
- 401：检查 Agent Token 是否有效、是否属于当前 Agent；泄露或丢失时轮换 Token。
- 403：检查 Grant Scope、Resource Scope、Owner 和资源访问范围。
- 404：检查 Grant ID 是否属于当前 Agent；不要用一个 Agent Token 访问另一个 Agent 的 Grant。
- 409：检查 Session 是否 PAUSED/CLOSED，或 Task 是否已进入禁止写入的终态。
- 离线：检查本地 Runtime/Host 是否运行和 Presence 心跳；DAEP 不会远程启动它们。

## 7. 未来扩展（非当前交付）

如未来需要由 DAEP 提供远程 MCP 接入，可另行设计 Streamable HTTP、OAuth 2.1/OIDC、Host 兼容矩阵和设备级授权。本节是后续方向，不代表当前已经提供远程 MCP 服务。
