# DAEP RC9 浏览器最终验收 Runbook

## 目标

本 Runbook 用于在具备真实浏览器环境后，对 `release/1.0.0-rc9` 的高保真前端进行最终产品验收。

当前代码已经通过自动化 CI；本 Runbook 不把静态检查冒充为浏览器视觉验收。

## 0. 环境准备

- 启动 Production Compose。
- 确认 `/health` 返回成功。
- 使用真实成员 Token 登录。
- 准备以下角色账号：
  - 系统管理员
  - 项目管理员
  - 产品人员
  - 开发人员
  - 测试人员
  - 项目审核人员
- 准备至少两个项目，并让同一项目管理员拥有两个项目。
- 准备至少两个成员的独立本地 MCP-compatible Agent。

## 1. 平台壳层

### PASS 条件

- 顶部平台栏、当前项目上下文、当前角色信息完整显示。
- 左侧导航与高保真原型的信息架构一致。
- 不出现旧版 `Engineering Control Plane`、`ROLE-AWARE WORKSPACE` 等残留。
- 刷新页面后不会丢失服务端数据。
- 项目切换后页面内容同步切换。

### 需要记录

- 桌面宽度：1440 / 1280 / 1024
- 窄屏：390 / 768
- 首屏布局是否发生重叠、截断或横向溢出。

## 2. 系统管理员

### 操作

1. 登录。
2. 打开“我的项目”。
3. 创建项目。
4. 切换到其他项目。
5. 查看项目成员。
6. 检查项目管理员、审核人员、开发、测试等身份展示。

### PASS

- 只有系统管理员看到创建项目入口。
- 项目切换后所有项目级数据使用新项目上下文。
- 非授权操作不出现可执行入口。

## 3. 项目管理员

### 操作

1. 登录拥有多个项目的管理员。
2. 在两个项目之间切换。
3. 创建需求。
4. 创建任务并分配成员。
5. 打开 Workflow。
6. 修改自定义 Workflow。
7. 打开 Gate。
8. 修改自定义 Gate。
9. 查看治理、异常协调、Work Package。
10. 执行项目收口相关操作。

### PASS

- 项目管理员可管理其被授权的多个项目。
- Workflow 配置只影响当前项目。
- 自定义 Gate 可配置。
- 系统锁定 Gate 不允许被关闭或绕过。
- 治理、异常协调、Work Package 页面均使用当前项目上下文。

## 4. 产品人员

### 操作

1. 登录。
2. 查看产品工作台。
3. 创建/查看需求。
4. 查看需求关联任务。
5. 查看需求验收状态。

### PASS

- 产品工作台显示产品相关内容。
- 不显示项目管理员专属治理控制。
- 不可执行未授权的项目管理操作。

## 5. 开发人员

### 操作

1. 登录。
2. 查看自己的工作。
3. 查看任务详情。
4. 执行允许的 Workflow transition。
5. 上报进度。
6. 添加工程 Artifact。
7. 模拟 Blocked / 恢复。

### PASS

- 只能看到并操作授权范围。
- Workflow transition 受到项目配置和门禁约束。
- 进度 100% 不直接伪装成最终 DONE。
- Artifact 能在任务详情中追踪。

## 6. 测试人员

### 操作

1. 登录。
2. 查看测试工作台。
3. 查看待测试任务。
4. 查看需求验收。
5. 添加测试证据/结果。
6. 查看验收报告。

### PASS

- 测试工作台显示测试相关任务。
- 测试证据与需求/任务保持关联。
- 未授权项目管理入口不可执行。

## 7. 项目审核人员

### 操作

1. 登录。
2. 查看治理。
3. 查看待审核事项。
4. 查看需求验收报告。
5. 执行允许的 Review / Acceptance。

### PASS

- 审核人员可以看到治理/验收相关入口。
- 不出现项目管理员专属管理入口。
- Review 结果能进入审计链路。

## 8. Agent 协作

### 操作

1. 在两个独立成员账号下启动各自本地 Agent。
2. 确认两个 Agent heartbeat/presence。
3. 打开 Agent 拓扑。
4. 使用能力匹配筛选。
5. 发起跨成员 Work Package。
6. Agent 接收并处理。
7. 回传 artifact/result。
8. ACK 消息。
9. 查看协作事件时间线。
10. 模拟一个 Agent 离线并恢复。

### PASS

- 两个 Agent 使用各自身份出现。
- 能力匹配只提供建议，不直接替 Agent 做运行时调度。
- DAEP 不托管、不启动、不强制唤醒 Agent Runtime。
- 消息具有 durable inbox/outbox 语义。
- ACK、artifact、result、timeline 可追踪。
- Agent 离线期间消息不会因 UI/WS 断开而丢失。

## 9. 治理与门禁

### PASS

至少验证：

- `REVIEW_REQUIRED` 锁定且不可关闭。
- `DELIVERY_EVIDENCE` 锁定且不可关闭。
- 自定义 Gate 可以配置。
- 未满足 Gate 时 transition 被拒绝。
- 满足 Gate 后 transition 成功。
- 重复提交同一个 Idempotency-Key 不产生重复状态变更。

## 10. 异常协调

### PASS

- 打开 Exception Coordination Workbench。
- 查看风险 Work Package。
- 查看负责人、SLA、风险状态。
- 执行允许的 reassignment。
- 查看协调决策记录。
- 非管理员不能执行管理级 reassignment。

## 11. Work Package

### PASS

- 创建/查看 Work Package。
- 查看生命周期状态。
- 查看成员/Agent。
- 查看 SLA 和 risk。
- 查看结果和父任务关联。
- 父任务完成前，未满足 Work Package completion gate 时不能错误收口。

## 12. 消息收件箱

### PASS

- 消息按当前成员隔离。
- ACK 后状态正确变化。
- 刷新页面后状态保持。
- WebSocket 不可用时，刷新/轮询仍可获取 durable inbox。

## 13. 响应式验收

必须使用真实浏览器分别检查：

- 1440×900
- 1280×800
- 1024×768
- 768×1024
- 390×844

### PASS

- 无主要内容横向溢出。
- 导航、卡片、表格、Modal 不互相覆盖。
- 关键按钮仍可点击。
- Modal 在窄屏内可完整操作。
- 角色工作台不会因为卡片折行而出现不可用操作。

## 14. 最终签署

| 验收项 | 状态 | 证据 |
|---|---|---|
| 平台壳层 | ☐ | 截图/录像 |
| 系统管理员 | ☐ | 截图/操作记录 |
| 项目管理员 | ☐ | 截图/操作记录 |
| 产品人员 | ☐ | 截图/操作记录 |
| 开发人员 | ☐ | 截图/操作记录 |
| 测试人员 | ☐ | 截图/操作记录 |
| 审核人员 | ☐ | 截图/操作记录 |
| Agent 双成员协作 | ☐ | Agent 日志/截图 |
| Workflow / Gate | ☐ | API/界面证据 |
| 异常协调 | ☐ | 操作记录 |
| Work Package | ☐ | 操作记录 |
| 消息可靠性 | ☐ | inbox/outbox 证据 |
| 响应式 | ☐ | 多尺寸截图 |
| Production Restore | ☐ | restore 日志 |
| GA 决策 | ☐ | 发布签署 |

## 发布判定

- 自动化 CI 全绿：**代码级 RC Ready**
- 浏览器验收全部 PASS：**UI Acceptance Ready**
- Production PostgreSQL + Backup/Restore 全部 PASS：**Operations Ready**
- 双 Agent 实机互操作全部 PASS：**Agent Interoperability Ready**
- 四项全部满足后，才允许讨论 RC → GA。

**特别说明：当前仓库阶段不应把浏览器、真实生产恢复和双 Agent 实机验证标记为已完成，除非确实取得对应证据。**
