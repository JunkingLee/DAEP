# DAEP 项目开发交接与进度基准

> 本文件是跨聊天窗口恢复工作的唯一项目进度基准。聊天摘要仅作辅助；若聊天记录与本文件、Git 分支或实际代码不一致，以 Git 仓库当前状态和可验证的 CI 结果为准。

## 1. 项目定位

- 仓库：`JunkingLee/DAEP`
- 当前唯一开发基准分支：`release/1.0.0-rc9`
- 禁止未经用户明确同意切换到 `main` 或其他分支继续当前任务。
- 平台定位：DAEP 是任务驱动的工程协作与 Agent 接入控制平台；Agent Runtime 运行在成员自己的工作站，DAEP 不负责启动、托管、监督或唤醒本地 Runtime。
- 代码变更必须直接落在上述分支，或先明确说明另建分支的原因并征得同意。

## 2. 最近一次已核实仓库状态

- 核实时间：2026-11-23
- 分支：`release/1.0.0-rc9`
- 当前代码 HEAD（最近核实）：`9fa767ae98701ed34a46a03ce2ef0eba7a414f67`。
- 最近 Agent 管理 UI 回归 CI：run `45142200504`，对应 HEAD `152cd2827d2bf07ffdc491ea0d7bf5dd0578e14d`，已成功；Python 3.11/3.12/3.13、Agent UI JS 语法、pytest、PostgreSQL migration/RLS、production compose 和容器构建均通过。
- 最近一次完整 CI 成功：run `45139802325`，对应 HEAD `e88266fa27a684a7272af4e228c8b3f12129fbd6`，Python 3.11/3.12/3.13 均为 `194 passed`，PostgreSQL migration/RLS、production compose、容器构建均成功。该成功结果覆盖风险 API，不覆盖之后的前端 UI 修改。
- 注意：本文件自身每次更新都会产生新 HEAD；新聊天必须实时查询分支 HEAD 和 CI，不能把这里记录的 SHA 当成永久最新值。
- 最近质量治理实现提交：
  - `f6e35b072c741c1a141bde377fbca7e51ca3645f` — 质量 Dashboard 增加 7/30/90 天范围和多维统计 API。
  - `9c38cab3dd7b07bd636559118c43731cd5828c7e` — 前端增加 7/30/90 时间范围及任务/交付类型/Agent/成员维度。
  - `da6fb6209023ec8246ee7fd80d4c88911f2ac077` — 趋势统计保留时间范围内全部交付版本。
  - `6ea9e83160bb6ac203b5f5d327f692b14a441a6b` — 每日通过/失败/待确认分段趋势。
  - `1e0cafbb22299d96bb9fbe106bd3c0f64479aa45` — Agent 质量记录按 Agent 所有者归属成员维度。
  - `e4a858158d6179087de6f57c67604b858f337b99` — 交付提交时执行质量评估，失败自动创建/归并项目风险并写审计事件。
  - `021c9466cad22f6ea90a883bd7b1c49035905c88` — 增加风险创建、重复失败升级和 Dashboard 无副作用测试。
  - `043cf5afc3f523640164399fd31786eae6877f4e` — 新增 PostgreSQL 风险事件/发生记录迁移及租户 RLS。
  - `2e060091cf38ee2a28ec0923c515a7be47faf7cf` — 迁移改为兼容 bootstrap 已创建表和索引。
  - `6a02ab816d3720bd525fe19e097732f301555e9a`、`d10ea324e3c405b9a5db4dceb6615351a9d903c9` — 更新 Alembic head/RLS 合约测试。
  - `8ecc75f2c516ab8d57a3766ef1be025314130cd9` — 增加项目风险列表、详情、整改更新 API。
  - `283c36b33096e223d13ddf2711c40d7f88b7cedd`、`f0fb35526fa54df623c1ea50d359d4ae53e8f495` — 风险 API 权限/整改流程测试和关闭备注校验。
  - `8ecc75f2c516ab8d57a3766ef1be025314130cd9` — 项目风险列表、详情和整改 API。
  - `c0f2815119c967046f0db107a99d84e126666ded` — 项目质量风险列表、详情弹窗、整改表单、发生记录和审计时间线 UI。
  - `9fa767ae98701ed34a46a03ce2ef0eba7a414f67` — 增加风险 UI 与 API 的静态集成检查。
- CI 首轮暴露的测试合约问题已修复；最终 CI 对最新代码 HEAD 全绿。

## 3. 当前开发阶段（不得擅自改题）

当前阶段名称：**项目质量运营与风险治理**。

阶段范围固定为以下六项：

1. 项目质量趋势图支持 7 天、30 天、90 天。
2. 按任务、交付类型、Agent、成员维度进行质量统计。
3. 质量失败自动生成项目风险事件。
4. 识别重复质量失败并自动升级风险等级。
5. 质量问题支持责任人、整改期限、处理状态。
6. 质量问题关联项目审计时间线。

### 进度状态

| 工作项 | 状态 | 说明 |
|---|---|---|
| 7/30/90 天质量趋势 | 已实现，CI 已通过 | API 参数校验和前端范围切换已提交 |
| 按任务/交付类型/Agent/成员统计 | 已实现，CI 已通过 | Agent 提交记录可归属 Agent 所有者成员 |
| 质量失败自动生成风险事件 | 已实现，CI 已通过 | 交付提交路径执行质量评估；每个任务/交付类型/失败检查项归并一个风险 |
| 重复失败归并与风险升级 | 已实现，CI 已通过 | 同一风险记录累计发生次数；第 1 次 LOW、第 2 次 MEDIUM、第 3 次及以上 HIGH；解决/忽略后再次失败会重新打开 |
| 责任人/期限/状态整改闭环 | API 与 UI 已实现，CI 已通过 | PATCH API 支持责任人、整改期限、状态和处理备注；前端有整改表单，权限由服务端校验 |
| 风险关联审计时间线 | API 与 UI 已实现，CI 已通过 | 风险详情 API 返回 occurrence 历史及审计事件；前端详情弹窗展示两条时间线 |

## 4. 下一步执行顺序

严格按顺序推进，不要跳回 Agent 管理或 MCP 功能优化：

1. 已完成：检查基准分支 HEAD、CI，审查 artifact version 提交路径、质量评估函数、events 审计事件、SQLite bootstrap 和 Alembic/RLS 迁移约定。
2. 已完成：交付提交时自动评估质量；FAIL 检查项自动生成风险事件。
3. 已完成：按 task + normalized artifact_type + quality_check_key 归并风险；每个 artifact version/check 只产生一次 occurrence；重复失败升级级别（1 LOW、2 MEDIUM、3+ HIGH）。
4. 已完成：风险发生记录保留每次失败对应的 artifact_version_id、检查项、消息、操作者和时间；风险变化写入 events 审计时间线。
5. 已完成并验证：SQLite/应用测试、PostgreSQL migration/RLS、Python 3.11/3.12/3.13 CI。
6. 已完成：项目风险列表 API，支持状态/严重等级筛选和分页上限。
7. 已完成：项目风险详情 API，返回关联任务、交付版本、每次失败 occurrence 和风险审计事件。
8. 已完成：风险整改 PATCH API，支持责任人、整改期限、OPEN/IN_PROGRESS/RESOLVED/DISMISSED、处理备注；关闭/忽略必须保留非空处理备注；仅项目 owner/manager/reviewer 或平台管理员可修改。
9. 已实现前端项目质量风险列表、详情弹窗和整改表单，展示严重等级、发生次数、责任人、截止时间、状态、失败 occurrence 历史和审计时间线；已接入风险 API。
10. 已完成：风险 UI 代码的 CI 验证及静态集成检查；最新 Agent 管理 UI 回归覆盖亦已完成并通过 CI（详见第 10 节）。
11. 已完成：Playwright 真实浏览器 E2E，覆盖登录/刷新恢复、Agent 列表、创建和一次性 Token、详情编辑、Token 轮换/撤销、项目绑定/解绑；CI run `45144014967` 对应 HEAD `7758b62f87d6e3ebc84c966a74ee411b18a217aa` 全部成功。下一项唯一任务：补充 Agent 所有权、项目角色和撤销 Token 的负向安全 E2E。

## 5. 跨聊天窗口恢复协议（每次新聊天必须执行）

新聊天开始时，先执行以下恢复步骤，再接受“继续”指令：

1. 读取本文件：`docs/PROJECT_HANDOFF.md`。
2. 从 GitHub 核实 `release/1.0.0-rc9` 当前 HEAD；不能只相信本文件记录的旧 SHA。
3. 检查该 HEAD 对应的最近 CI 运行状态和结论。
4. 对照本文件的阶段目标、完成项、待办项及下一步，核对实际代码是否吻合。
5. 如仓库状态与交接文档不一致，先修正文档或解释差异；不要直接假定旧进度仍然有效。
6. 给用户简短报告：当前分支/HEAD、当前阶段、已完成、未完成、CI 状态、准备执行的下一项。
7. 用户说“继续”时，从明确的下一项开始，不重新规划阶段、不重复已经完成的工作，也不擅自转向其他模块。

## 6. 每次开发结束时的强制交接更新

每一轮产生代码提交后，都必须同步更新本文件，至少记录：

- 本轮目标与实际完成内容。
- 修改文件及关键实现。
- 每个新提交的完整 SHA。
- 测试命令、测试范围、通过/失败/未执行情况。
- 对应 CI run ID、状态和结论；尚未完成时写明 pending。
- 已知问题、未验证事项及其证据。
- 下一步唯一明确任务。
- 当前分支和 HEAD SHA。

禁止只在聊天消息里汇报进度而不更新交接文件。若本轮没有代码变更，也要在确有阶段状态变化时更新。

## 7. 事实与状态表达规则

所有状态必须区分：

- **已实现**：代码已存在；不自动代表测试通过。
- **已验证**：明确写出执行过的测试或检查及其结果。
- **CI 通过**：必须对应具体 HEAD SHA 和 workflow run。
- **待验证**：没有足够证据，既不能说正常，也不能说存在故障。
- **计划实现**：未来工作，不代表当前项目有缺陷。

不得把计划中的 Agent/MCP 端到端验证描述为已经发现 Agent/MCP 故障。当前开发主线仍是“项目质量运营与风险治理”，除非用户明确调整。

## 8. 新聊天可直接使用的恢复提示

请先读取仓库 `JunkingLee/DAEP` 的 `docs/PROJECT_HANDOFF.md`，并核实 `release/1.0.0-rc9` 当前 HEAD 和对应 CI。严格按交接文档恢复项目进度，不要切换分支，不要重复已完成事项，不要擅自改变当前阶段。先向我汇报恢复结果，然后从文档中标记的下一项继续开发；每次提交后同步更新交接文档。

## 9. 静态资源 404 修复（2026-11-23）

- 问题确认：`web/index.html` 引用 `/agents.js`，但 `app/main.py` 未挂载静态目录，也没有 `/agents.js` 专用路由；`Dockerfile` 虽然复制 `web/`，但文件不会因此自动通过 HTTP 提供。
- 已实现：
  - `app/main.py` 引入 FastAPI `StaticFiles`，将仓库 `web/` 目录挂载到 `/static`；静态目录使用相对源码文件位置计算的绝对路径，避免依赖进程工作目录。
  - `web/index.html` 将 Agent 脚本引用改为 `/static/agents.js`。
  - 新增 `tests/test_static_assets.py`，覆盖首页引用、脚本 HTTP 200、JavaScript Content-Type、脚本内容，以及 `/readyz` API 未被静态挂载影响。
- 提交：
  - `f1256da8925305c30f06fa7f30d97cf56e9d15ab` — `fix: serve dashboard static assets`
  - `96f36a3cb897d1f61ae8e937718a35fe3d6a56dd` — `fix: load agent script from static mount`
  - `8ff5ca60df2b2bf8ef265dbdaf498192b079b430` — `test: cover dashboard static asset serving`
- 验证状态：新增回归测试已提交；静态资源代码与回归测试提交 HEAD `8ff5ca60df2b2bf8ef265dbdaf498192b079b430` 的 CI run `45141300034` 已完成并通过：Python 3.11/3.12/3.13 测试、Compile、Dashboard JavaScript 检查、PostgreSQL migration/RLS、production compose 和容器构建全部成功。本环境本轮未直接运行 pytest。交接文档随后更新为提交 `c2ccba54bb64f3f5958867670afe6c090d4a7906`，该文档提交自身的 CI run `45141384928` 查询时仍在运行。
- 之前 HEAD `1113e2c8c67dda026852f68667e644934c99cc69` 的 CI run `45140494166` 已成功，但不覆盖本轮静态资源修改。
- 静态资源修复代码 HEAD `8ff5ca60df2b2bf8ef265dbdaf498192b079b430` 的 CI run `45141300034` 已成功；交接文档 HEAD `619fc25dfb8367cf1cf37a2985d125e994adbcce` 的 CI run `45141495590` 也已成功。静态资源修复验证完成。

## 10. Agent 管理页面加载与交互接线回归（2026-11-23）

- 核查范围：`web/agents.js` 初始化、导航按钮注入、Agent 页面动态创建、`go('agents')` 页面切换、Agent 列表加载、创建与一次性 Token 展示、详情/编辑、Token 轮换/撤销、项目绑定/解除绑定。
- 核查结果：Agent 管理脚本通过 `/static/agents.js` 加载；`init()` 在 DOMContentLoaded 后挂接导航和页面；`go` 包装器在进入 agents 页面后触发 `loadAgents()`；`GET /api/v1/agents` 返回列表数组，与前端消费结构匹配；创建接口返回的 `token` 字段与一次性 Token 展示逻辑匹配；详情、PATCH、token rotate/revoke、项目绑定等 UI 操作与后端路由相匹配。
- 新增 `tests/test_agent_management_ui.py`，覆盖页面脚本引用、导航/页面注入、列表空态/错误态、创建与一次性 Token/MCP 配置、详情编辑、Token 管理和项目绑定 UI/API 接线。
- `.github/workflows/ci.yml` 增加 `node --check web/agents.js`，防止外部 Agent 管理脚本语法错误漏检。
- 提交：
  - `ce6521e4fffb578e8361121c5280f9786c5ddace` — `test: cover Agent management UI wiring`
  - `152cd2827d2bf07ffdc491ea0d7bf5dd0578e14d` — `ci: validate Agent management script syntax`
- 验证：CI run `45142200504` 对应 HEAD `152cd2827d2bf07ffdc491ea0d7bf5dd0578e14d` 已成功；Python 3.11/3.12/3.13、pytest、`node --check web/agents.js`、PostgreSQL migration/RLS、production compose、容器构建全部通过。
- 验证边界：当前回归为静态 UI/API 接线合约检查和 JavaScript 语法检查，未在真实浏览器中完成登录后的点击级 E2E；不能将其表述为真实浏览器端到端已通过。
- 下一步唯一任务：增加 Playwright 浏览器 E2E，覆盖真实登录会话下的 Agent 页面加载与关键交互。

## 11. Agent 管理真实浏览器 E2E（2026-11-23）

- 本轮目标：按上一节唯一待办，为真实登录会话增加 Playwright 浏览器验收，而不是继续增加静态源码断言。
- 新增 `tests/test_agent_management_e2e.py`：
  - 仅在设置 `DAEP_RUN_BROWSER_E2E=1` 时运行；普通 pytest 默认跳过，避免要求所有开发者安装浏览器。
  - 测试 fixture 启动独立 Uvicorn 子进程和临时 SQLite 数据库，使用专用 bootstrap 管理员密码；不连接共享/生产数据库。
  - 使用 Chromium 真实打开登录页并登录，刷新后验证会话恢复，进入“我的 Agent”。
  - 通过真实页面交互覆盖列表、创建 Agent、一次性 Token 展示、详情编辑、Token 轮换、项目绑定/解绑、Token 撤销。
  - 最后调用详情读取验证响应中不包含任何 Token 明文。
- 更新 `.github/workflows/ci.yml`，新增独立 `browser-e2e` job：Python 3.12、Playwright 1.52.0、安装 Chromium 后执行该 E2E 测试；不把浏览器依赖加入常规 Python requirements。
- 提交：
  - `9bb7d11a9c1e585cce09553292e77227622036a0` — `test: add Playwright Agent lifecycle browser E2E`
  - `d970bcee7c4a17b468f9f6a1f68217c62fc0a78e` — `ci: run Agent lifecycle Playwright browser E2E`
- 当前分支 HEAD：`7758b62f87d6e3ebc84c966a74ee411b18a217aa`。
- 验证状态：本环境未直接启动 Chromium。CI run `45143047580` 首次执行时，常规 Python 3.12 测试已通过，production-compose 与 container-build 已通过；浏览器安装失败，原因是 `ubuntu-latest` 已解析为 Ubuntu 26.04，而 Playwright 1.52.0 不支持该发行版。已将 `browser-e2e` 专用 runner 固定为 `ubuntu-24.04`（提交 `ec9d14b0fc25a91f447c60108e532cb72add157f`），新 CI run `45143257668` 已成功完成 Python 3.11/3.12/3.13、migration、production-compose、container-build，但浏览器测试在页面初始化竞态处失败：app-shell 刚显示时项目异步初始化尚未结束，测试过早切换到 Agent 页面，随后初始化完成又切回 overview，导致创建按钮不可见。已在 `7d3b939f28d2bb07994fc71ebf156db62984fb66` 中等待 `#overview.page.active` 后再切换，并明确等待 Agent 页面及创建按钮可见。第二次 CI run `45143609777` 的登录、项目初始化、创建/编辑、Token 轮换、绑定和解绑步骤已运行通过；随后发现测试未关闭解绑后重新打开的详情弹窗，导致后续点击被遮挡。已在 `4888c7e66b6bf2c0ded48dc78364946840c65479` 修复。最终 CI run `45144014967` 对应当前 HEAD `7758b62f87d6e3ebc84c966a74ee411b18a217aa`，browser-e2e、Python 3.11/3.12/3.13、PostgreSQL migration/RLS、production-compose、container-build 全部成功；浏览器完整生命周期测试已验证通过。
- 已知边界：浏览器测试使用平台 bootstrap 管理员身份，并通过已登录页面会话创建一个临时项目；Agent 创建/编辑/Token/绑定等关键操作由浏览器点击完成。测试数据库位于 pytest 临时目录，随测试进程结束回收。
- 下一步唯一任务：增加 Agent 安全负向 E2E，至少覆盖非所有者读取/编辑/轮换/撤销其他用户 Agent 被拒绝、无项目管理员权限的用户不能绑定项目，以及 Token 撤销后不能再通过 MCP 身份认证。继续使用独立临时数据库和真实浏览器登录会话。


## 12. Agent 管理安全负向浏览器 E2E（2026-11-23）

- 本轮目标：在隔离 SQLite 测试服务和真实浏览器登录会话下验证 Agent 所有权、项目角色授权与 MCP Token 撤销后的认证失效。
- 新增 test_agent_security_negative_browser_flows（位于 tests/test_agent_management_e2e.py），通过管理端创建两个普通成员和隔离项目，再分别使用两个成员的真实密码登录浏览器：
  - 非所有者读取、PATCH 编辑、轮换 Token、撤销 Token 均必须返回 HTTP 403。
  - 仅具备项目普通成员身份的用户，尝试绑定自己拥有的 Agent 必须返回 HTTP 403。
  - Agent 所有者撤销 Token 后，使用该 Token 请求 GET /api/v1/mcp/context 必须返回 HTTP 401。
  - 复核被拒绝的跨所有者编辑未改变 Agent 名称。
- 本轮仅新增安全 E2E 测试，没有修改 Agent 授权业务逻辑；普通用户与项目成员均在临时 SQLite 数据库内创建。
- 代码提交：f2f93f406c5104f42539a4dec8bdb4e4841ff4b7 — test: cover Agent ownership and revoked-token security in browser E2E。
- 验证：最终交接 HEAD `411b36f7cb6b7bd592c07582cea9539644dae8c7` 对应 CI run `45144971209` 已完成并成功；`browser-e2e` job 的 `pytest -q tests/test_agent_management_e2e.py` 明确输出 `2 passed in 4.27s`。Python 3.11/3.12/3.13、PostgreSQL migrations/RLS、production-compose、container-build 与 browser-e2e 全部成功。中间提交对应 run `45144832506`、`45144896295`、`45144953887` 均因同分支新提交触发并发取消，不作为验证依据。
- 当前阶段：Agent 管理基础安全负向浏览器 E2E 已实现并通过 CI；服务端越权访问与撤销后 MCP 凭证失效已得到浏览器会话验证。
- 当前分支：release/1.0.0-rc9；当前 HEAD：411b36f7cb6b7bd592c07582cea9539644dae8c7。
- 下一步唯一任务：审计 Agent/MCP 的租户边界与项目授权矩阵，补充跨租户读取/操作拒绝、项目普通成员与 owner/manager 的授权差异，以及撤销凭证对所有 MCP 入口的一致性测试；若发现服务端缺口，先修复授权实现再补 E2E。

- 后续检查发现浏览器 E2E API helper 对无请求体的 GET/POST 传入了 JSON null；已修复为不为 GET/HEAD 构造 request body，避免浏览器 Fetch 规范拒绝该请求。
- 修复提交：f200b4c458c238e9e575dc3c539edd404a31a7f1 — test: avoid GET request bodies in Agent security browser checks。
- 本轮完整验证结果以最终交接 HEAD `411b36f7cb6b7bd592c07582cea9539644dae8c7` 和 CI run `45144971209` 为准；所有 job 成功。

## 13. Agent / MCP 租户边界与授权矩阵审计（2026-11-23）

- 本轮承接第 12 节唯一任务：审计 Agent/MCP 租户隔离、项目角色授权及撤销凭证在 MCP 入口的一致性。
- 代码审计范围：
  - `app/agent_identity.py`：Agent owner 校验、列表/详情/更新、Token rotate/revoke、项目绑定/解绑、MCP Context。
  - `app/main.py`：`actor()` 的 Member/Agent 认证分流、`require_project_access()`、Agent task assignment/list/accept/heartbeat/revoke 入口。
  - `daep_mcp/server.py`：MCP stdio 工具实际调用的 HTTP 路由，包括 Agent Context、Agent task inbox、任务接受、任务读写、项目发现和管理工具。
  - Alembic Agent identity / assignment RLS 迁移和 PostgreSQL smoke test。
- 审计发现并修复：
  1. **Agent Token 的 PostgreSQL RLS 认证缺口**：原实现直接查询启用 RLS 的 `agent_tokens` 与 `agents`，但没有与 Member Token 对等的受限认证查询通道。新增 `0035_rc45_agent_auth_lookup`，复用 NOLOGIN/BYPASSRLS 的 `daep_authenticator`，只授予 Agent credential 表 SELECT，并新增 `SECURITY DEFINER` 函数 `daep_authenticate_agent_token`；函数只返回 token hash 精确匹配、Token ACTIVE、Agent ACTIVE 且未过期的身份字段，不向应用暴露 token hash。
  2. **认证后的租户上下文**：`authenticate_agent_token` 在受限查询后，临时切换租户上下文更新 Token last_used / Agent last_seen，随后恢复原上下文，保持身份解析函数本身不污染调用方上下文。MCP Context 路由改为使用公共 `actor()`，由统一身份解析建立请求级 tenant/member/agent context，再读取该 Agent 已绑定的项目。
  3. **Agent 解绑租户边界**：解绑路径原先只验证项目 tenant，没有先确认 Agent 同属该 tenant。现先按 `agent_id + project.tenant_id` 解析 Agent；任务分配撤销查询和绑定删除均增加 `tenant_id` 条件，跨租户 Agent ID 返回 404，不再触碰其他租户的授权记录。
- 新增/更新验证：
  - `tests/test_api.py` 增加跨租户 Agent 解绑拒绝、租户内 Agent 绑定及 MCP Context 项目范围验证；同时更新 Alembic head 合约，要求 RC45 Agent auth lookup migration 为 head。
  - `tests/postgres_rls_smoke.sql` 增加受限数据库角色调用 `daep_authenticate_agent_token` 的验证：有效 Tenant A 凭证能解析为 Tenant A Agent，未知 hash 不返回身份；既有 Agent/Token/Binding/Assignment 直接表访问仍受租户 RLS 限制。
  - `tests/test_agent_management_e2e.py` 在撤销 Token 后，除 `GET /api/v1/mcp/context` 返回 401 外，也验证 `GET /api/v1/agents/me/tasks` 返回 401。
  - 现有项目角色边界复核：普通成员绑定 Agent 被拒绝（第 12 节真实浏览器负向 E2E）；项目 manager 在同租户项目中可以绑定 Agent（新增 API 矩阵测试）；Agent 不能继承 owner/manager/reviewer 的人工治理权限（既有 API 测试）。
- 关键提交（均在 `release/1.0.0-rc9`）：
  - `c9917362ba18a01f525ed3f4dadcd9ddcb8cd860` — 解绑时校验 Agent tenant。
  - `d29039af718c70ec40812acae74f14c66a68b1a5` — 初版跨租户回归测试；该提交 CI 失败是测试误用平台管理员专用的项目创建 API，并非业务代码失败。
  - `53e2f55c7e1aef1e9a4df367f20fc124882b3b0f` — 修正测试数据准备，由平台管理员在指定 tenant 创建项目并授予 manager 成员身份。
  - `e52b9c54e8c396e1af9d0dd19ec57863999e8115` — Agent Token 使用受限数据库认证函数。
  - `5e4514f684f97bc36f4e990ce66ac86911944363` — 新增 RC45 PostgreSQL Agent auth lookup migration。
  - `21366019e9ecbd323807780428206768fc455bdd` — 增加 PostgreSQL RLS smoke 认证函数检查。
  - `f23d219adb764e19dafbe86442925dd12fb65c11` — 撤销 Token 后 Agent task API 也必须认证失败。
  - `7fea19dc1db4a8d74e4fbfc55ea5b2afc187e898` — 保持 Agent credential verification 上下文中立。
  - `874cb1ff6186751816982af069b4e6ad177bd96b` — MCP Context 统一走 actor 认证和租户上下文。
  - `3024b9b9a4810e1863e13e112afbe1886c8ee39f` — 更新迁移 head 合约测试。
- CI 验证：run `45146483749`，对应 HEAD `3024b9b9a4810e1863e13e112afbe1886c8ee39f`。截至本交接更新时，Python 3.11/3.12/3.13 全部成功（每个版本 `203 passed, 1 skipped`）；PostgreSQL migrations/RLS smoke、production-compose、container-build 成功；browser-e2e 正在安装 Chromium，尚未完成，不能记为通过。此前 run `45146208600` 的失败是两项测试契约问题（认证 helper 不应污染上下文、Alembic head 断言仍指向 RC44），已分别修正并包含在当前 HEAD 中。
- 已知验证边界：本轮 PostgreSQL RLS smoke 验证了认证函数与数据库隔离策略，但仍需等待当前 CI browser-e2e 完成；没有在本环境直接连接生产 PostgreSQL 或真实 MCP 客户端。撤销凭证验证覆盖 MCP Context 和 Agent task inbox 两类 HTTP 入口；`daep_mcp/server.py` 中其他工具最终复用这些已审计的 API actor/project authorization 路由。
- 当前分支：`release/1.0.0-rc9`；代码 HEAD：`3024b9b9a4810e1863e13e112afbe1886c8ee39f`。
- 下一步唯一任务：等待并核实 run `45146483749` 的 browser-e2e 最终结果；若通过，更新本节 CI 状态并结束 Agent/MCP 授权矩阵审计；若失败，先按日志修复，再继续做跨聊天交接。完成后再进入下一项产品开发，不提前宣称 Agent/MCP 安全审计全部通过。

## 14. Agent 用户所有权领域模型统一（2026-11-23）

- 用户明确纠正：DAEP 的 Agent 全部归属于某个用户，项目本身不拥有 Agent。本轮先冻结领域模型，不直接修改业务代码或数据库。
- 新增权威领域模型文档：`docs/DOMAIN_MODEL_AGENT_OWNERSHIP.md`。
- 核心原则：
  1. Agent 的唯一业务所有者是 Member；`agents.owner_member_id` 是所有权唯一依据。
  2. Project 是任务、成员角色、治理和审核的协作空间，不是 Agent 容器或 Agent 所有者。
  3. Agent Token 认证 Agent 身份，不等同于 owner 的 Member Token，也不继承 owner 的项目治理角色。
  4. 普通成员可主动授权自己的 Agent 执行分配给自己的任务，无须项目 Manager 为其绑定 Agent。
  5. Agent 只能通过逐任务、明确、可撤销的 AgentTaskGrant 访问任务；项目成员身份、项目 Agent 在线目录、历史项目绑定都不能自动授予任务访问权。
  6. 人对人任务委派（现有 `task_delegations`）与人对 Agent 执行授权（目标 AgentTaskGrant）是两种独立关系。
  7. 项目 Agent 目录如保留，只是成员本地 Agent 的能力/在线状态投影，不代表项目拥有 Agent，也不授予访问权限。
- 对现有模型的初步判断：
  - `agents` + `owner_member_id`、`agent_tokens` 已符合用户拥有 Agent 的基本方向。
  - `agent_project_bindings` 容易造成项目拥有/绑定 Agent 的错误语义，不能再作为任务访问授权依据；需要制定兼容迁移方案后逐步废弃或重构。
  - `agent_task_assignments` 已有逐任务关联，但授权人、Agent owner 同意、任务人类责任人、scope/expiry 等关系尚未按新模型统一。
  - `project_agents`（RC13）是以 project/member/agent_name 为键的能力/心跳目录，应定位为 ProjectAgentPresence，并增加稳定 agent_id 关联；目录可发现性不等于授权。
  - `task_delegations` 是 Member 到 Member 的委派/邀请，必须与 AgentTaskGrant 分开。
  - `/api/v1/mcp/context` 当前返回 project bindings，不应将其作为 Agent 的授权来源；`/api/v1/agents/me/tasks` 应严格由当前 Agent 的有效任务 Grant 驱动。
- 当前完成内容仅为领域模型文档和交接记录；**尚未实施 schema/API/UI 迁移**，不能把目标设计描述成当前系统已经支持。
- 前一阶段 CI 状态补正：run `45146836965` 对应此前代码/安全审计交接 HEAD `071a62e981e4dd71ed10ca80716ef1dd1bb0650a`，现已全部成功：Python 3.11/3.12/3.13、PostgreSQL migrations/RLS、production-compose、container-build、browser-e2e 均 success。该 CI 覆盖授权审计阶段代码，不覆盖本轮新增领域模型文档提交。
- 领域模型文档提交：`cfcc8e7fe6dea724df9dcdc6710bf8831ece233b` — `docs: define user-owned Agent domain model`。
- 下一步唯一任务：依据领域模型文档，完成“现有表/接口 → 目标实体/授权规则”的逐项迁移设计，明确 AgentTaskGrant 字段、Agent owner 主动授权流程、任务责任人约束、ProjectAgentPresence 与 agents 的关联方式，以及旧 `agent_project_bindings` / `agent_task_assignments` / `project_agents` 数据的兼容迁移策略。该迁移设计评审完成前，不改动生产 schema 或删除现有功能。

## 15. AgentTaskGrant 数据库/API 迁移设计（2026-11-24）

- 承接第 14 节唯一任务：完成现有 Agent 表/API 到用户主动授权逐任务模型的迁移设计。本轮只提交设计文档，不修改业务代码、数据库 schema 或运行时行为。
- 新增设计文档：`docs/AGENT_TASK_GRANT_MIGRATION_DESIGN.md`。
- 审计确认的关键代码事实：
  1. 当前 Manager/Owner 创建 Agent assignment 的接口是 `POST /api/v1/tasks/{task_id}/agent-assignments`；要求项目写权限/Manager 角色，选择 agent_id，并强制要求该 Agent 已有 `agent_project_bindings`。这与目标“Human Assignee 主动授权自己的 Agent”不符。
  2. 当前 Agent inbox `GET /api/v1/agents/me/tasks` 同时 JOIN `agent_task_assignments` 和 active `agent_project_bindings`；Agent accept/heartbeat 也检查 binding。
  3. 当前 Agent 的 `require_task_access` 先走 `require_project_access`（Agent 必须有项目 binding），再校验 ACCEPTED assignment。这需要改成独立 AgentTaskGrant guard。
  4. 当前 `assignments` 表主键是 `(task_id, member_id)`，明确允许同一任务关联多个 Member。因此第一版只有任务恰好一个有效人类 assignee 时才允许创建 Grant；多人协作任务需先定义 primary/responsible member，不能任意挑选 assignee。
  5. `project_agents` 是项目成员的能力/心跳目录，唯一键为 project_id/member_id/agent_name，尚未关联 agents.id；回填只能在 project/member/规范化名称精确唯一匹配时进行，歧义记录不得猜测关联。
- 目标 AgentTaskGrant 设计：
  - 新建独立 `agent_task_grants`，不直接重命名旧表。
  - 关键字段：tenant_id、project_id、task_id、agent_id、owner_member_id、human_assignee_member_id、authorized_by_member_id、scope_json、status、expires_at、accepted_at、revoked_at、completed_at、last_activity_at、audit metadata。
  - 状态：AUTHORIZED → ACCEPTED → COMPLETED，或进入 REVOKED/EXPIRED 终态；只有 ACCEPTED 且未过期的 Grant 才能执行工具。
  - 第一版同一 Task 同时最多一个有效 Grant；固定动作白名单包括 task.read、task.progress.report、task.blocked.report、task.artifact.submit；禁止审批、项目治理、任务重新分配和其他任务读取。
  - 创建必须由当前唯一 Human Assignee 以 Member 身份发起，且 Agent.owner_member_id=当前 Member；不需要项目 Manager 绑定 Agent，也不依赖 project binding。
  - 所有 Agent 任务 API/MCP 工具统一经 Grant 校验器检查 Agent、Tenant、Project、Task、Human Assignee、scope 和 expiry。
- 旧数据兼容策略：
  - `agents`、`agent_tokens` 保留。
  - `agent_project_bindings` 进入兼容期，保留历史，不再作为 Grant 前置或执行权限依据；未来如保留项目发现能力，改由 Agent owner 发布 ProjectAgentPresence。
  - `agent_task_assignments` 不自动转为新 Grant，因为旧记录不能证明 Agent owner 对具体任务主动授权；新表上线切换时将旧活跃 assignment 有审计地撤销，旧行保留只读历史。
  - `project_agents` 增加 nullable agent_id，唯一精确匹配时回填；歧义和不匹配行保持 legacy/unmatched。
  - `task_delegations` 保持 Member→Member 人对人委派，不与 AgentTaskGrant 混用。
- 分阶段顺序：A 新增 schema/API 与测试；B 切换 Agent 执行 API/MCP 到 Grant；C 前端任务详情“使用我的 Agent”和个人委派视图；D 旧 binding/assignment 停止写入并在兼容期后再评估删除。
- 测试要求已列入设计文档：所有权/assignee 拒绝矩阵、跨任务/跨项目隔离、scope/expiry/revoke、Agent/owner/Task/Project 生命周期、并发唯一性、PostgreSQL RLS、真实浏览器 MCP E2E。
- 代码提交：
  - `3072a578de27b7f204ca8997855f3238a85abe2a` — `docs: design Agent task grant migration`。
  - `1794b347b62e58b572d8e8530dd48366b86f7ba7` — `docs: refine Agent grant migration findings`。
- 领域模型文档：`docs/DOMAIN_MODEL_AGENT_OWNERSHIP.md`；迁移设计：`docs/AGENT_TASK_GRANT_MIGRATION_DESIGN.md`。
- CI：领域模型基线 HEAD `4646b585ae40470ac06475f543b2d1eb40c2e0da` 的 run `45148243633` 已全部成功（Python 3.11/3.12/3.13、PostgreSQL migrations、production-compose、container-build、browser-e2e）。本节后续两个文档提交的 CI 仍需以最新 HEAD 对应 run 状态核实，不可引用旧 run 作为最新提交的验证。
- 当前完成状态：领域模型和迁移设计均已文档化；尚未创建 `agent_task_grants` 表、尚未修改 API/MCP/UI，现有 binding/assignment 运行行为仍未改变。
- 下一步唯一任务：进入阶段 A，先审计数据库迁移体系与 assignments/task/project/agent 的复合一致性约束，设计并实现仅新增 `agent_task_grants` 表的迁移（含 PostgreSQL RLS、唯一有效 Grant 约束、索引和 SQLite schema parity），并补充 migration/RLS smoke/API schema 测试；本阶段不切换旧执行 API。

## 16. AgentTaskGrant schema / RLS Stage A（2026-11-24）

- 承接第 15 节唯一任务，已完成 Stage A 的数据库层第一步：新增独立 `agent_task_grants`，未切换旧 Agent assignment/inbox/accept/execution API，也未改 UI/MCP。
- 新增 Alembic migration：`alembic/versions/0036_rc46_agent_task_grants.py`，revision `0036_rc46_agent_task_grants`，down_revision `0035_rc45_agent_auth_lookup`。
- 新表字段覆盖：
  - 身份/归属：`tenant_id`、`project_id`、`task_id`、`agent_id`、`owner_member_id`、`human_assignee_member_id`、`authorized_by_member_id`。
  - 授权范围/状态：`scope_json`、`status`。
  - 生命周期：`created_at`、`updated_at`、`expires_at`、`accepted_at`、`revoked_at`、`completed_at`、`revoked_by_member_id`、`revoke_reason`、`last_activity_at`。
  - 兼容审计：`legacy_assignment_id` 仅保留来源 ID，不建立旧 assignment 外键，避免新表生命周期继续依赖 legacy 表。
- 数据库约束和索引：
  - 状态白名单：AUTHORIZED / ACCEPTED / REVOKED / COMPLETED / EXPIRED。
  - expires_at 必须晚于 created_at；ACCEPTED/REVOKED/COMPLETED 分别要求对应生命周期时间戳。
  - PostgreSQL 与 SQLite 均有 partial unique index：同一 task 同时最多一个 AUTHORIZED/ACCEPTED Grant。
  - 查询索引：tenant+agent+status+expiry、tenant+task+status、owner+status+created_at。
  - PostgreSQL ENABLE + FORCE RLS，policy 复用 `daep_tenant_visible(tenant_id)`；显式 REVOKE `daep_authenticator` 对新表的全部权限。
- SQLite bootstrap 增加同构表、检查约束和索引。PostgreSQL bootstrap 特意跳过新表及其索引，由 RC46 Alembic migration 在 Agent identity/legacy assignment 表创建完成后创建，避免核心 bootstrap 依赖尚未执行的后续迁移。
- 新增/更新测试：
  - `tests/test_api.py`：Alembic head contract 更新至 RC46；检查 migration 的 RLS、权限撤销、partial unique index；检查 SQLite schema 字段和索引（包括真实 app bootstrap）。
  - `tests/postgres_rls_smoke.sql`：加入两个租户的 AgentTaskGrant fixture，验证租户隔离；验证 Agent authenticator role 无权 SELECT 新表。
  - PostgreSQL migrations job 实际完成 core bootstrap、Alembic upgrade、SQL 生成、RLS policy 检查和 restricted-role smoke。
- 实施过程中修复的验证问题：
  - 初版 bootstrap 因引用尚未创建的 legacy assignment 表失败；改为 legacy ID 只作审计引用。
  - 随后修复新建表约束列表尾逗号导致的 PostgreSQL/SQLite SQL 语法错误。
  - PostgreSQL core bootstrap 先于 Alembic，因此新表及索引只由 RC46 migration 创建；SQLite 继续由应用 bootstrap 创建。
  - RLS smoke 新增权限检查时改用具名 dollar-quote delimiter，避免 SQL 文件中的匿名 delimiter 被错误截断。
- 关键提交（均在 `release/1.0.0-rc9`）：
  - `a6f997997bb4f42723597891c4431807692c73a1` — 新增 RC46 AgentTaskGrant PostgreSQL migration。
  - `f420b48f178ef2502960eb65aecea269f3d1173e` — SQLite bootstrap schema parity。
  - `246fdc63d1fecad0ef524ad97fcde9eb1fa8e51c` — PostgreSQL RLS tenant fixtures。
  - `338b993cfd1bd61f05655bd0e3e5abdc3d3d71ad`、`7998bbdbc6c8093562ab39ee3a21fe2e11842628`、`a4428c796b0ce138e851e35b09b0abe099635513`、`7a7b13d93a32355aecf4b255d7bbe2bc222648a0` — 修复 bootstrap 顺序、SQL 语法和 schema contract。
  - `1b943461f6ac184292f1ac5e8cb1110b0cc041e7` — SQLite bootstrap schema 实测。
  - `c57e9aed37e4c36b0a213d53f8b2b0912a077dc7`、`b0b9eef6754bec2959759ba14284b8c55375fbb2` — RLS authenticator 权限测试及 SQL delimiter 修复。
- 验证结果：run `45303582212`，对应代码 HEAD `b0b9eef6754bec2959759ba14284b8c55375fbb2`，所有 jobs 均成功：Python 3.11/3.12/3.13、PostgreSQL migrations/RLS smoke、production-compose、container-build、browser-e2e。此前失败/取消的中间 runs 不作为最终验证依据。
- 当前分支：`release/1.0.0-rc9`。本节交接文档提交后产生的新 HEAD/CI 状态仍需重新核实。
- 已知边界：
  - 当前仅完成数据模型、约束、索引、RLS 和 SQLite parity；Member 创建/查看/撤销 Grant API、Agent inbox/accept API、Grant 执行校验器尚未实现。
  - `scope_json` 目前是 TEXT 存储，固定白名单解析与接口级 scope 校验必须由下一阶段服务端实现。
  - 表的基础 FK 与 tenant RLS 已建立；跨实体的 tenant/project/task/agent/owner 组合一致性仍必须在 Grant API 事务中再次校验，不得仅依赖传入 ID 或项目 binding。
  - 旧 `agent_project_bindings` / `agent_task_assignments` 仍按旧路径运行；没有自动迁移旧 assignment，也没有提前撤销历史任务授权。
- 下一步唯一任务：Stage A API 第一批——实现 Member 主动创建 Grant、按任务/个人列表查看 Grant、授权人撤销 Grant；创建必须校验当前 Member 是任务唯一 assignee、Agent 属于当前 Member 且同 Tenant，期限默认 30 天/最大 90 天，同任务最多一个有效 Grant，写审计事件。先不切换 Agent 执行 API/MCP。

## 17. AgentTaskGrant Member API 第一批（2026-11-24）

- 承接第 16 节唯一任务，新增 Member 主动授权、个人/任务范围查询、授权人撤销 API。旧 Agent assignment/inbox/accept/heartbeat/execution API 暂未切换；本阶段不依赖 `agent_project_bindings`。
- 新 API：
  - `POST /api/v1/tasks/{task_id}/agent-grants`：Member 在本人负责的任务上授权自己的 Agent。请求字段 `agent_id`、可选 `requested_scope`、可选 `expires_in_days`。
  - `GET /api/v1/agent-grants/me`：只列出当前 Member 自己拥有的 Agent Grants。
  - `GET /api/v1/tasks/{task_id}/agent-grants`：只允许当前唯一人类责任人查看自己该任务的 Grant，不向项目 Manager 暴露私人 Agent 记录。
  - `DELETE /api/v1/agent-grants/{grant_id}`：由创建授权的 Agent owner Member 撤销，可附带 reason；撤销不要求任务仍分配给该 Member，避免任务重新分配后授权人失去撤销自己授权的能力。
- 创建授权服务端规则：
  - actor 必须为 MEMBER，Agent Token 不得创建/管理 Grant。
  - Task → Requirement → Project → Tenant 必须存在，Project 必须 ACTIVE，Task 不得为 DONE/CANCELLED/CLOSED/ARCHIVED。
  - assignments 中必须恰好只有一个 Member，且等于当前 Member；多人责任人任务返回 409，其他 Member/Manager/Admin 代授权返回 403。
  - Agent 必须 ACTIVE、Tenant 与 Project 一致，且 `agents.owner_member_id` 必须等于当前 Member；不检查 Project binding。
  - 默认 30 天，允许 1–90 天；拒绝 bool/字符串/越界值。
  - Scope 固定白名单：`task.read`、`task.progress.report`、`task.blocked.report`、`task.artifact.submit`；默认授予上述四项，可显式选择非空子集，拒绝未知/重复 scope。没有开放 task.comment.create。
  - 同一 Task 已有未过期 AUTHORIZED/ACCEPTED Grant 时返回 409；发现已过期但状态仍 active 的旧 Grant 时，在同一写事务中标记 EXPIRED 后再创建。
  - 返回数据不包含 Agent Token；授权和撤销均写 `events` 审计事件，actor_member_id 为真实授权/撤销 Member。
- 列表返回 scope 解析结果和 `effective_status`；对超过 expires_at 的 active 状态显示 EXPIRED。创建新 Grant 时会持久化清理同任务过期 active Grant。
- 生命周期联动：
  - Agent 被 owner 禁用时，自动撤销该 Agent 所有 AUTHORIZED/ACCEPTED AgentTaskGrant，写 revoked_at、revoked_by_member_id、revoke_reason 并记录审计事件。
  - Member 账号被禁用时，对其 Agent 的有效 Grant 同样撤销，原因标记为 Agent owner account disabled。
  - 单纯 Agent Token 撤销仍由 Token 认证阻断请求；Token 轮换策略不在本轮改变。
- 测试新增：
  - `tests/test_api.py` 覆盖：平台管理员/Manager 不能替 Member 授权、非法 scope/expiry、正常创建和 scope、重复 Grant、个人/任务列表隔离、其他 Member 无法读取/撤销、撤销审计、非 owner Agent 拒绝、多人责任人拒绝、任务改派后原授权人仍可撤销、Agent disable 自动撤销 Grant。
  - 最新完整代码 HEAD：`88c86221bcb0a558a9d533179672a695c67bdab6`。
  - 代码阶段 CI run `45308076211`：Python 3.11/3.12/3.13、PostgreSQL migrations/RLS、production-compose、container-build 均 success；browser-e2e 当时仍在 Install Chromium，未完成，不能记为通过。交接文档提交后以新 run 复核最终状态。
- 关键代码提交：
  - `1e2d41a787b45df49bcd4ad994968560b5f6c734` — Member Grant API。
  - `fa2658c42044bd0eb62cf3cc707ef74d53d1b5c9` — 支持任务改派后授权人仍可撤销。
  - `8ac9ee63f952510a48317c9eb9a09e4e22e531b8`、`21202dd6f406978e09c598532c4809b38544952d` — Grant API 权限测试及 DELETE 请求测试修正。
  - `40f9152c6c7182a6b57c2bced0d56938382d5eb7` — Agent disable 撤销 Grant。
  - `64289efa9e72ff2b0d895440b609d7742c9dee12` — Member disable 撤销其 Agent Grants。
  - `88c86221bcb0a558a9d533179672a695c67bdab6` — Agent disable 联动测试。
- 已知限制/后续：
  - AgentTaskGrant 目前仅支持 Member 创建、查询、撤销；Agent 接受 Grant 的 API 尚未实现，故新 Grant 仍为 AUTHORIZED，尚不能驱动新 Agent 执行流程。
  - 旧 Agent inbox/accept/heartbeat/require_task_access 仍由旧 assignment + project binding 驱动。不能把本轮 API 描述为已切换新执行授权。
  - Grant scope 当前仅在创建时校验和存储；统一 AgentTaskGrant 执行 guard 尚未落地，后续 Stage B 必须在每次执行 API/MCP 调用中重新校验 Tenant/Project/Task/Agent/owner/assignee/status/expiry/scope。
  - 数据库仍缺少复合 tenant/project/task/agent/owner 关系约束，当前 API 通过事务内查询做组合校验；后续 migration 可强化数据库级约束。
- 下一步唯一任务：实现 Agent 侧 Grant inbox 与 accept API（`GET /api/v1/agents/me/grants`、`POST /api/v1/agent-grants/{grant_id}/accept`），只允许 Grant 对应 Agent 接受；接受时重验 Agent ACTIVE、owner Member ACTIVE、Project ACTIVE、Tenant/Task 一致、任务仍由 grant.human_assignee_member_id 唯一负责、Grant 未过期且状态 AUTHORIZED。成功后改为 ACCEPTED、记录 accepted_at/审计；幂等处理已接受 Grant。此步骤仍不切换旧执行 API，待 accept/inbox 完成后再实施统一执行 guard 和 MCP/API 切换。
