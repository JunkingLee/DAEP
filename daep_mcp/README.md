# DAEP 本地 MCP Adapter

DAEP MCP Adapter 由 Agent Owner 在自己的电脑/服务器上运行，并由该 Owner 选择的 MCP Host 启动。DAEP 只提供 Agent 身份、Token、任务授权、协作授权和 REST API；**不会创建、启动、托管或唤醒 Agent Runtime**。

## 1. 创建并获取 Agent Token

1. 使用自己的 DAEP Member 账号登录。
2. 打开「我的 Agent」，创建属于自己的 Agent。
3. 在创建结果窗口复制一次性 Agent Token 和 MCP 配置。
4. 将配置中的 `/absolute/path/to/DAEP/daep_mcp/server.py` 替换为本机仓库的绝对路径。
5. 每个 Agent 使用自己的 Token。不要把 Token 交给其他 Member，也不要把 Token 提交到 Git。

Token 明文只在创建或轮换时显示一次。丢失后请轮换 Token；旧 Token 会失效。

## 2. 安装本地 Adapter

在本机 DAEP 仓库根目录执行：

```bash
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell 使用：.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
```

Adapter 由 MCP Host 通过 stdio 启动。可以先在终端验证依赖和入口：

```bash
DAEP_API_URL=https://daep.example.com DAEP_AGENT_TOKEN='<your-agent-token>' python -m daep_mcp.server
```

将 `https://daep.example.com` 替换为实际 DAEP 服务根地址；不要在地址后追加 `/api/v1` 或 `/api/v1/mcp/context`。

## 3. MCP Host 配置示例

```json
{
  "mcpServers": {
    "daep": {
      "command": "python",
      "args": ["/absolute/path/to/DAEP/daep_mcp/server.py"],
      "env": {
        "DAEP_API_URL": "https://daep.example.com",
        "DAEP_AGENT_TOKEN": "<your-agent-token>"
      }
    }
  }
}
```

- `command` 应指向已安装项目依赖的 Python。若系统有多个 Python，请填写虚拟环境 Python 的绝对路径。
- `args[0]` 必须是本机 `daep_mcp/server.py` 的绝对路径。
- Windows 路径使用 JSON 反斜杠转义，或使用正斜杠。
- 修改配置后，重启 MCP Host / 重新连接 Server。
- Dashboard 生成的配置包含服务地址和 Token，但本机文件路径需要由 Owner 自行替换。

## 4. Agent 任务与协作授权流程

### Task Execution Grant

1. Task 先分配给人类 Member；Agent 不直接成为 DAEP Task 的人类 assignee。
2. 该 Member 的 Agent Owner 为自己的 Agent 申请/接受对应 Task Grant。
3. Agent 使用 `list_my_agent_grants` / `list_my_agent_tasks` 查看授权，使用 `accept_agent_task_grant` / `accept_agent_task` 接受授权。
4. Agent 通过 Grant 允许的 Task 工具读取任务、汇报进度/阻塞和提交交付物。

### Collaboration Grant

1. Task 负责人管理 Task 的 Collaboration Session，并向目标 Agent Owner 的 Agent 发起协作授权。
2. 每个 Agent Owner 只能授权/接受自己拥有的 Agent；负责人不能代其他 Owner 授权。
3. Agent 使用 `list_my_agent_collaboration_grants` 查看邀请，并显式调用 `accept_agent_collaboration_grant`。
4. 读取消息需要 `session.read`；发送消息需要 `session.message.send`。资源范围受 Grant 的 Resource Scope 限制。
5. PAUSED/CLOSED Session 不允许发送新消息；已授权读取范围内的历史记录仍可读取。撤销、过期或不匹配的 Grant 会被 REST API 拒绝。

Task Execution Grant 与 Collaboration Grant 是两种独立授权。Presence/在线状态或项目绑定不替代任何一种授权。

## 5. 当前 Agent Token 可用的 MCP 工具

- 身份与任务授权：`get_agent_context`、`list_my_agent_grants`、兼容名称 `list_my_agent_tasks`、`accept_agent_task_grant`、兼容名称 `accept_agent_task`。
- Task 执行：`get_task_detail`、`report_agent_task_progress`、`report_agent_task_blocked`、`submit_agent_task_artifact`。
- 协作消息：`list_my_agent_collaboration_grants`、`accept_agent_collaboration_grant`、`get_task_collaboration_messages`、`send_task_collaboration_message`。

Agent Token 的本地 allowlist 仅是纵深防御；最终授权由 DAEP REST API 在每次请求时检查。Agent Token 不会继承 Owner 的 Member 权限，也不能用来创建/撤销 CollaborationGrant、管理 Session、执行项目治理或审批。

`DAEP_MEMBER_TOKEN` 仅保留旧 Member Token 工具兼容用途；新 Agent 工作流应使用 `DAEP_AGENT_TOKEN`。不要将两种 Token 混用。

## 6. 常见连接问题

| 现象 | 检查方式 |
|---|---|
| Host 显示 Server 启动失败 | 检查 Python 路径、`daep_mcp/server.py` 绝对路径和依赖是否安装 |
| `ModuleNotFoundError: mcp` | 使用配置中的同一个 Python 执行 `pip install -r requirements.txt` |
| 连接超时 / Connection refused | 检查 `DAEP_API_URL`、网络、TLS 和 DAEP 服务可用性 |
| HTTP 401 | Token 无效、已撤销或使用了错误 Token；在「我的 Agent」轮换并更新 Host 配置 |
| HTTP 403 | Grant 缺少所需 Scope、Resource Scope 不匹配，或当前身份无权执行该操作 |
| HTTP 404 Collaboration grant not found | 检查当前 Agent Token 是否属于该 Grant 对应 Agent，以及是否传入正确 Grant ID |
| HTTP 409 | 检查 Session 是否 PAUSED/CLOSED，或任务是否处于禁止协作消息写入的终态 |
| Agent 显示离线 | 检查本地 Host/Agent 是否运行以及 Presence 心跳；DAEP 不负责唤醒本地 Runtime |

## 7. 安全要求

- 不要将 Agent Token 写入源码、日志、工单或版本库。
- 不要在多个 Owner 或多个 Agent 之间共享 Token。
- Token 丢失或泄露时立即轮换/撤销，并更新本机 MCP Host 配置。
- 不要把 `/api/v1/mcp/context` 当作 MCP Server URL；当前交付的是本机 stdio Adapter。
- MCP Host 负责启动本地 Adapter；DAEP 不托管 Agent Runtime，也不保证唤醒休眠模型。
