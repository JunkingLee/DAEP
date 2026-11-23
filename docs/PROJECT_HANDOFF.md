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

