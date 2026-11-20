# DAEP RC9 Release Readiness

## 当前结论

release/1.0.0-rc9 当前进入 RC 最终验收准备阶段。

代码侧已经完成高保真前端替换、旧 UI 清理、角色工作台、Agent 协作界面、稳定浏览器验收选择器和静态契约测试。

尚不能宣布 GA，因为真实浏览器验收、Production PostgreSQL 备份恢复演练、双成员真实 MCP Agent 实机互操作仍需要实际环境证据。

## 已完成

### 1. 高保真前端

- 新版统一 DAEP Shell。
- 我的项目 / 项目总览 / 工作台 / 工作 / 协作 / 治理 / 依赖关系 / 异常协调 / Work Package / 消息收件箱信息架构完整。
- 角色工作台按项目成员角色和工作职能展示。
- 项目切换后重新加载项目级数据。
- 响应式 CSS 已覆盖桌面与窄屏。
- Modal、Escape 关闭、首次可交互控件聚焦等基础可访问性行为已加入。

### 2. 旧 UI 清理

静态检查确认以下旧版标记和兼容代码标识不存在：

- Engineering Control Plane
- ROLE-AWARE WORKSPACE
- daep-sidebar
- compatWorkbench
- myWorkbenchPanel
- managerWorkbenchPanel
- workflowDesignerPanel
- showRequirementAcceptanceLegacy
- renderTaskBoardLegacy
- openMembersLegacy

当前页面 section 仅保留新的十个产品区域：

portfolio, overview, workbench, work, collaboration, governance, dependencies, exceptions, packages, inbox

### 3. 浏览器验收契约

前端已提供稳定的 data-testid：

- login-screen
- token-input
- login-submit
- app-shell
- project-switcher
- primary-nav
- current-role
- page-portfolio
- page-overview
- page-workbench
- page-work
- page-collaboration
- page-governance
- page-dependencies
- page-exceptions
- page-packages
- page-inbox

同时保留 role=status aria-live=polite 的 Toast 状态区域。

### 4. 自动化验证

RC 阶段已有 Python 多版本、迁移、Production Compose、容器构建、角色交付 E2E、Agent 交付 E2E、消息恢复、并发 claim、幂等竞争、角色隔离、Workflow/Gate 等自动化验证。

## 尚未完成

### A. 真实浏览器验收 — BLOCKING

必须在真实浏览器执行：

1. 系统管理员
2. 多项目项目管理员
3. 产品人员
4. 开发人员
5. 测试人员
6. 项目审核人员
7. Agent 协作
8. Workflow / Gate
9. 异常协调
10. Work Package
11. 消息收件箱
12. 响应式尺寸验收

详细步骤见 docs/RC9_BROWSER_ACCEPTANCE_RUNBOOK.md。

当前开发环境没有可用的浏览器自动化工具，因此不得把静态检查写成“浏览器验收 PASS”。

### B. Production Restore — BLOCKING

必须使用真实 PostgreSQL 完成：

- backup
- restore 到空数据库
- restored DB verification
- 应用重新启动
- 核心接口验证
- 记录恢复耗时和异常

### C. 双 Agent 实机互操作 — BLOCKING

必须使用两个独立成员和两个独立本地 MCP-compatible Agent：

- heartbeat / presence
- capability matching
- cross-member work package
- durable inbox/outbox
- ACK
- artifact/result
- offline/recovery
- timeline

必须保持产品边界：

DAEP 负责协作、消息、状态和治理，不托管、不启动、不强制唤醒成员本地 Agent Runtime。

## 发布门禁

| 门禁 | 当前状态 | 是否阻塞 GA |
|---|---|---|
| 代码级 CI | 已完成历史验证 | 否 |
| 高保真 UI 静态契约 | 已完成 | 否 |
| 旧 UI 清理 | 已完成 | 否 |
| 真实浏览器验收 | 待执行 | 是 |
| Production Backup/Restore | 待执行 | 是 |
| 双 Agent 实机互操作 | 待执行 | 是 |
| GA 发布签署 | 待上述全部完成 | 是 |

## 下一执行顺序

1. 获得真实浏览器环境，执行 docs/RC9_BROWSER_ACCEPTANCE_RUNBOOK.md。
2. 修复浏览器验收中发现的真实交互/布局问题。
3. 重新执行自动化 CI。
4. 执行 Production PostgreSQL backup/restore。
5. 执行双 Agent MCP 实机互操作。
6. 汇总证据并形成 RC → GA 决策。
7. 在明确授权后，再考虑合并到 main。

## 当前发布原则

不因为代码“看起来完成”就宣布 GA。

只有浏览器、生产恢复、双 Agent 实机互操作三类真实证据全部通过，才允许进入 GA 讨论。
