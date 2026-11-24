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

## 18. AgentTaskGrant Agent inbox / accept API（2026-11-24）

- 承接第 17 节唯一任务，完成 Agent 侧 Grant inbox 和 accept。新授权流程现已具备 Member create/list/revoke + Agent inbox/accept 的闭环；仍未切换旧 Agent 任务执行 API/MCP。
- 新 API：
  - `GET /api/v1/agents/me/grants`：仅 Agent Token 可访问，只返回当前 Agent 自己的有效 AUTHORIZED/ACCEPTED Grant；不要求 `agent_project_bindings`。
  - `POST /api/v1/agent-grants/{grant_id}/accept`：仅目标 Agent Token 可接受对应 Grant；其他 Agent 查询返回 404。
- Inbox 仅返回最小任务上下文（task title/description/status/progress、requirement title、project name）、grant_id、scope、status 和期限；过滤过期 Grant、禁用 Agent、禁用 owner、非 ACTIVE Project、非可执行 Task、租户不一致、任务当前 assignee 已变化或不唯一的 Grant。
- Accept 的事务内重新校验：
  1. Grant 属于当前 Agent 与当前 Tenant。
  2. Grant 状态为 AUTHORIZED 或 ACCEPTED，且 expires_at 尚未到期。
  3. Agent 为 ACTIVE，且当前 agents.owner_member_id 仍等于 Grant.owner_member_id。
  4. Owner Member 账号 ACTIVE 且 Tenant 一致。
  5. Agent / Project / Grant Tenant 一致，Project ACTIVE。
  6. Task 未完成/取消/关闭/归档。
  7. assignments 当前恰好只有一个 Member，且正是 Grant.human_assignee_member_id；owner_member_id 也必须等于该人类责任人。
  8. 仅在全部条件通过后 AUTHORIZED → ACCEPTED，写 accepted_at / updated_at 和 `agent.task_grant.accepted` 审计事件。已 ACCEPTED 的有效 Grant 幂等返回，不重复写接受事件。
- 测试新增：
  - Agent 无 Project Binding 仍可通过新 Grant inbox 收到任务。
  - 只有目标 Agent 能接受 Grant；Member Token 不能访问 Agent inbox。
  - 接受后 inbox 显示 ACCEPTED 和准确 scope；重复 accept 幂等。
  - 任务责任人改派后拒绝接受；过期 Grant 不显示在 inbox 且不能接受。
  - 验证 accepted 审计事件记录 Agent 身份，不冒充 owner Member。
- 测试夹具修正：首次 CI 暴露过期测试数据违反 `expires_at > created_at` 数据库 CHECK，而非业务 API 缺陷。测试现将 created_at/expires_at 一起设置为过去且保持先后关系；完整重跑通过。
- 关键提交：
  - `9b60a806ab8bd51182dd1891ed2f53bf90d386fd` — Agent Grant inbox / accept API。
  - `70c8ac0628eea1b7542d589f25d5966a9c5be955` — inbox/accept 行为测试。
  - `b03f261c42fbe8cad018c8b0f9f939f742a6167b` — 修正过期测试数据。
- 最新验证：run `45308770379`，对应代码 HEAD `b03f261c42fbe8cad018c8b0f9f939f742a6167b`，全部 jobs success：Python 3.11/3.12/3.13、PostgreSQL migrations/RLS smoke、production-compose、container-build、browser-e2e。最终完整 CI 通过；较早失败 run `45308600734` 已由后续修复 run 覆盖，不作为最终结果。
- 当前分支：`release/1.0.0-rc9`。
- 当前 AgentTaskGrant 功能状态：
  - 已有 schema/RLS、Member create/list/revoke、Agent inbox/accept、Agent/owner disable 撤销联动。
  - 尚未有统一 Grant execution guard；旧 `require_task_access`、Agent task progress/artifact/blocked 等写接口、MCP 仍使用旧 assignment + project binding 规则。
  - 新 Grant ACCEPTED 目前只是授权生命周期状态，不意味着已经允许旧执行 API；执行入口切换前必须完成统一 guard。
  - Scope 在 Member 创建时校验并存储；Agent inbox 暴露 scope；执行动作级校验尚未实现。
- 下一步唯一任务：Stage B 第一项——实现统一 `require_agent_task_grant(c, actor, task_id, action)` 执行授权 guard，并先对现有 Agent task read/progress/blocked/artifact 入口进行逐条路由盘点。guard 必须验证 Agent Token 身份、Grant ACCEPTED/未过期、Agent ACTIVE/owner 仍匹配、Tenant/Project/Task 关系、Project ACTIVE、当前唯一 Human Assignee 与 Grant 快照一致、scope 包含精确 action；Agent 分支不得调用 `require_project_access` 或依赖 `agent_project_bindings`。先迁移最小只读 task detail + progress/blocked 写入口并补全权限矩阵测试，再迁移 artifact/MCP；禁止触及审批、验收、治理、任务重新分配接口。

## 19. Stage B execution guard：task detail / progress / blocked（2026-11-24）

- 承接第 18 节，新增统一 `require_agent_task_grant(c, actor, task_id, action)`，作为 Agent 任务执行入口的最小权限 guard。
- Guard 每次请求都验证：
  - actor 必须是 Agent Token 身份，并匹配当前 agent_id、owner member_id、tenant_id。
  - Grant 必须属于当前 Agent + Task + Tenant，且 status=ACCEPTED、expires_at 尚未到期。
  - Agent 必须 ACTIVE，当前 owner_member_id 与 Grant 快照一致。
  - Owner Member 必须 ACTIVE 且 Tenant 一致。
  - Grant、Agent、Project、Task Tenant 关系必须一致；Project 必须 ACTIVE。
  - Task 不能为 DONE/CANCELLED/CLOSED/ARCHIVED。
  - 当前 assignments 必须恰好只有一个 Member，且等于 Grant.human_assignee_member_id；Grant.owner_member_id 必须等于该责任人。
  - scope_json 必须为合法列表且包含本次精确 action；未知 action 不允许执行。
  - PostgreSQL 请求锁定 Grant 和 Task 行；SQLite 走现有事务模式。
- 已切换入口：
  - `GET /api/v1/tasks/{tid}` → `task.read`
  - `POST /api/v1/tasks/{tid}/progress` → `task.progress.report`
  - `POST /api/v1/tasks/{tid}/blocked` → `task.blocked.report`
- 安全边界：
  - Agent 分支不调用 `require_project_access`，不检查 `agent_project_bindings` 或旧 `agent_task_assignments`。
  - Agent 的 progress=100 一律拒绝，不能通过进度接口请求人类验收。
  - Agent 更新进度/阻塞状态时不触发父任务 work-package 自动同步，避免 Grant 对单个 Task 的授权扩散到父任务。
  - Member/Admin 原有权限路径保持不变。
- `app/main.py` 存在多组历史重复的 `task_detail` 定义。路由 wrapper 动态调用模块级最后一个 `task_detail`，所以必须同步修正全部五个同名定义；本轮已检查五处均调用新 Grant guard，避免只修改前置定义却没有改变实际运行行为。
- 测试调整与新增：
  - 新增 Scope 白名单、无 Grant 拒绝、Agent 无 Project Binding 仍可执行、精确 action 授权、progress=100 拒绝、任务改派拒绝、Grant revoke 拒绝等覆盖。
  - 原有依赖旧 Assignment + Project Binding 执行的测试已更新：旧 assignment 不再授权 task read/progress；解绑只撤销 legacy assignment，不撤销独立 AgentTaskGrant；重新绑定不能复活旧 assignment；只有 Member owner 撤销 Grant 才终止新模型执行权限。
  - Python 3.11 / 3.12 / 3.13：每个版本 `212 passed, 1 skipped`。
- 关键提交：
  - `743d163b553811aa3bc0180a4906e981b63af387` — guard + task read/progress/blocked 首轮切换。
  - `3dab920c819e909b10267a7662d68a08c0f6b0a8` — Guard 权限矩阵测试。
  - `d093d721ac52e9d6acd6e4f4ed318dcbc806d059` — 阻止 Agent progress/blocked 修改父任务。
  - `a7c91e3b36c74f2eeb2ca0268039218c34ee2211` — 修正全部重复 task_detail 定义的实际执行路径。
  - `658a90ac6d8a44100c6767af4daa9149373137ff` — 旧 assignment 测试迁移到 owner Grant 语义。
  - `222441992ecb0ee83d6e9813d129f6fdc016321a` — 验证 project unbind 不会撤销独立 owner Grant。
- CI run `45310315758` 对应代码 HEAD `222441992ecb0ee83d6e9813d129f6fdc016321a`：Python 3.11/3.12/3.13 全部 success（每个 212 passed / 1 skipped）；PostgreSQL migrations、production-compose、container-build success。browser-e2e 在本次记录时仍停留于 Install Chromium，尚未完成，不能声称全 CI 通过；继续观察 run 结果。
- 当前未切换：
  - `POST /api/v1/tasks/{tid}/artifacts` 仍使用旧 assignment + binding guard。
  - Artifact read/versions/quality、events、MCP task tools 仍需逐项盘点和迁移。
  - 旧 Agent inbox/accept/heartbeat/assignment API 保留兼容；新 Grant 已成为 task detail/progress/blocked 的唯一 Agent 授权来源。
  - Grant 在 Task 完成后目前仍保留 ACCEPTED 状态；后续应评估任务完成时将 Grant 标记 COMPLETED 的生命周期联动。
- 下一步唯一任务：将 Artifact submit/read 入口迁移到同一 Grant guard：`task.artifact.submit`、`task.read`，逐条审查 artifact quality、artifact versions、events 的数据暴露和副作用；保证 Agent 只能提交自己授权任务的产物，不能 review/approve 或改变质量治理数据。为迁移后的 artifact API 增加无 binding、scope 不足、过期/撤销、租户隔离、任务改派、审计归属测试。MCP task tools 暂不同时切换，待 REST API 完成后单独迁移。


## 20. Stage B Artifact REST API Grant 切换（2026-11-24）

- 承接第 19 节唯一任务，将 Artifact 提交、Artifact 列表、Artifact Versions 和单任务 Artifact Quality 读取切换到 AgentTaskGrant。
- Agent 执行入口规则：
  - `POST /api/v1/tasks/{tid}/artifacts`：Agent 必须通过 `require_agent_task_grant(c, actor, tid, 'task.artifact.submit')`；Member 继续使用原有 assigned-task 权限。
  - `GET /api/v1/tasks/{tid}/artifacts`、`GET /api/v1/tasks/{tid}/artifact-versions`、`GET /api/v1/tasks/{tid}/artifact-quality`：Agent 必须持有 ACCEPTED 且包含 `task.read` 的 Grant；Member 权限路径不变。
  - 所有历史重复定义的 artifact submit/list handler 均同步更新，避免同一路由的备用定义保留旧权限行为。
- 权限边界：
  - Agent 不需要、也不依赖 `agent_project_bindings` 或 `agent_task_assignments`；只有其 owner Member 对当前唯一责任人任务签发并由目标 Agent 接受的 Grant 才能执行。
  - Agent 的 artifact review/approve 路由继续显式拒绝 Agent；项目质量策略、风险整改、审批/验收等治理 API 未开放给 Agent。
  - Artifact 提交触发的质量评估与风险事件归并属于服务端既有自动化，不代表 Agent 获得风险治理写权限；审计仍使用 actor_type=AGENT、agent_id，actor_member_id 为空。
  - Task events 列表和 MCP task tools 尚未切换；本轮没有扩大 Agent 对审计事件或项目治理数据的读取范围。
- 测试更新：
  - 生命周期回归使用包含 `task.artifact.submit` 的 owner Grant；在解绑项目后仍能提交/读取该任务 Artifact，证明 Grant 独立于项目 binding。
  - Artifact version 测试改为 owner Member 主动授权，无项目绑定、无旧 assignment；覆盖 Agent 提交多个版本、读取 artifact/version/quality、审计身份和人类审核边界。
  - 测试源已更新；本轮不声称本地 pytest 已运行，提交后的 GitHub CI 负责执行 Python 矩阵、PostgreSQL RLS/migration、容器和浏览器检查。
- 代码文件：`app/main.py`、`tests/test_api.py`。
- 当前分支：`release/1.0.0-rc9`；本节提交后的 HEAD/CI 以本节提交和随后实时查询为准。
- 已知限制：Task events 读取仍走原权限入口；MCP tools 仍待单独盘点迁移；Artifact quality 自动生成风险事件沿用现有后端服务逻辑，Agent 不可直接调用风险治理 API。
- 下一步唯一任务：Stage B 下一片——逐条盘点并迁移 MCP task tools 到 AgentTaskGrant，区分 task.read、progress/blocked、artifact.submit 的精确 scope；保持 Agent 不可读取未授权任务、不可访问项目审计/治理工具、不可审批验收。MCP 切换完成后再处理 Task events 的读取授权与 Grant 完成生命周期联动。


## 21. Stage B MCP AgentTaskGrant 工具切换（2026-11-24）

- 承接第 20 节，更新本机 stdio MCP adapter `daep_mcp/server.py`，Agent Token 不再调用旧 `agent_task_assignments` inbox/accept。
- Agent Grant 工具：
  - `list_my_agent_tasks` 作为历史工具名兼容别名，改为 `GET /api/v1/agents/me/grants`。
  - 新增语义清晰的 `list_my_agent_grants`。
  - `accept_agent_task` 改为接受 Grant ID，调用 `POST /api/v1/agent-grants/{grant_id}/accept`。
  - 新增 `accept_agent_task_grant` 明确命名工具。
- MCP Agent Token 路径 allowlist：只允许 Agent context、Grant inbox/accept，以及受 REST Grant guard 保护的 task detail、progress、blocked、artifact submit/read/versions/quality 路由。Agent Token 调用其他 Member、项目治理、通知、协作、旧 assignment、委派、Presence 管理和 work-package 工具时，在 MCP adapter 调用层直接拒绝；不会将 owner_member_id 当作可继承的 Member 权限。
- Member Token 的原有工具调用行为保持兼容。MCP adapter allowlist 属于纵深防御；REST API 仍为最终权限边界。
- 新增 `tests/test_mcp_adapter.py`，覆盖 Agent allowlist 允许/拒绝矩阵、Agent Token 阻断 owner Member 权限、Grant inbox/accept endpoint 映射、Member Token 兼容。
- 文档更新：`docs/MCP_INTEGRATION.md`、`daep_mcp/README.md`。
- 本轮代码提交：`fbbb99fb2ee24808f2422ee679c77e8357eccdeb`（MCP Grant 切换）；随后修正 allowlist 的 task progress/blocked 路由段位判断，代码提交 `f82c613e6bf599f52cf488667f08a91be0b70577`。最新代码 HEAD 为该修正提交；本轮没有本地运行 pytest，必须以最新 HEAD 对应 CI 验证为准。
- 已知限制：Agent Task events 读取仍未开放；MCP 不提供 Agent 对项目审计、审批、治理、消息/通知、委派或 work-package 操作。旧 Member Token MCP 工具保留兼容，但 Agent Token 无法调用。
- 下一步唯一任务：Stage B 后续安全收口——将 `GET /api/v1/tasks/{tid}/events` 改为 Agent 仅持有 `task.read` Grant 才能读取，确认事件 payload 不泄露无关项目/成员敏感信息；随后实现 Task 完成/关闭/撤销时 AgentTaskGrant 自动 COMPLETED/REVOKED 的生命周期联动，并补充跨租户与多责任人负向测试。禁止 Agent 访问项目级审计 API。


---

## 22. 正式冻结：TEAM 多 Agent 协作与无固定数量上限（2026-11-24）

### 用户已确认的产品规则
- 协作模式：`TEAM`，Agent 团队协作。
- 最大数量：不设置固定数量，由任务负责人决定。
- 每个 Agent 仍归属其 Member；任务负责人开放多 Agent 不代表代替各 Agent Owner 授权。
- Agent Runtime 完全运行在各 Member 自己的环境；DAEP 只负责接入、授权、协作治理和审计，不启动/托管 Runtime。

### 本轮实时仓库核验
- 仓库：`JunkingLee/DAEP`
- 分支：`release/1.0.0-rc9`
- 本轮开始时实时分支 HEAD：`d09eb19e9eed9646b1b4fdca763f03e76745c15e`；本轮文档提交后的已核实 HEAD：`3fe45d08c09909afa923ebdb5f6c40b868b18aae`；本次交接文件更新本身会再产生一个文档提交，需以该更新响应/后续实时查询为准。
- 该 HEAD 的 combined status 查询未返回 status checks；commit workflow runs 查询返回空列表。当前不能据此宣称该 HEAD CI 通过，也没有可确认的 pending run。
- 原领域模型和迁移设计存在冲突：迁移设计旧版规定同一 Task 仅一个有效 Grant，并把多 Agent 推迟到未来；本轮已用下列正式规则覆盖旧条款。

### 冻结的领域/数据库规则
- `AgentTaskExecutionPolicy`：每 Task 一条；`collaboration_mode='TEAM'`；由人类任务负责人维护 `allow_multiple_agents`。
- `max_agents` 为 nullable positive integer；NULL 明确表示负责人不设置任务级固定上限；不得隐式默认 3/5/10。
- `AgentTaskGrant` 改为 Task 1:N；有效 Grant 唯一性改为 `(task_id, agent_id)`，不再对 task_id 单独唯一。
- 多 Grant 创建必须在事务中锁定 Task/Policy 行，并校验 allow_multiple_agents、max_agents 和同 Agent 重复授权。
- 新增 `AgentTaskContribution`，按 grant_id/agent_id 分离进度、阻塞和产物贡献；Agent 不直接覆盖 Task 人类总体进度。
- 新增独立 `AgentCollaborationGrant`，明确消息读写、Agent 发现、邀请/工作包/委派提议等协作 scopes 与 Task 资源范围。
- 复用 messages、task_work_packages、task_delegations；Agent 消息以 Agent 身份署名；Agent proposal 不直接改变人类 assignee、正式工作包治理、审批或验收。
- ProjectAgentPresence 只用于能力/在线发现，不构成执行或协作授权。
- 旧 Agent Assignment 保留只读历史，不静默转换为新 Grant；旧 project binding 不构成授权。

### 文档变更
- `docs/DOMAIN_MODEL_AGENT_OWNERSHIP.md`：追加正式 TEAM 多 Agent 领域模型和授权边界，声明覆盖旧单 Agent 描述。
- `docs/AGENT_TASK_GRANT_MIGRATION_DESIGN.md`：追加数据库实体、1:N 索引迁移、并发事务、协作授权、贡献模型、API/MCP 迁移顺序及负向测试矩阵。
- 本次仅冻结文档设计，尚未实施数据库 migration、API、MCP 或前端改造。

### 本轮提交与验证
- 文档提交：`a92ffea5cc0d8c0fe0d2d1b58afb0e8d37fa5587`（领域模型）；`0d64133f6ac16653eaa392fa2a1b27b57da27760`（数据库迁移设计）；`8241324ebbf121cc519cb7b2e4d3cb6259714506`（交接章节初次写入）；`3fe45d08c09909afa923ebdb5f6c40b868b18aae`（补全提交引用）。
- 本轮未运行 pytest；未执行 PostgreSQL migration/RLS 或真实浏览器/MCP Host 测试。
- CI 状态以本节提交对应的 GitHub workflow 为准；在结果可查之前不得声称通过。

### 下一步唯一任务
依据冻结设计实施数据库 schema/migration：新增 AgentTaskExecutionPolicy、AgentTaskContribution、AgentCollaborationGrant；将 AgentTaskGrant 有效唯一索引由 task_id 改为 (task_id, agent_id)；补充 PostgreSQL RLS、SQLite bootstrap/schema parity、历史数据检查与并发迁移测试。先完成数据库层，不提前开放协作 API/MCP。


---

## 23. AgentCollaborationSession 与开发阶段初始 Schema（2026-11-24）

### 用户本轮明确要求
- 接受建议：新增 `AgentCollaborationSession`，作为 Task 级逻辑协作空间。
- 当前项目仍处于开发阶段：**不考虑数据库迁移、生产数据迁移、历史数据回填、利旧、旧版本兼容或 legacy 退役**。
- 本阶段应直接实现正确的目标初始 Schema；可重建的开发数据库从空库按目标结构初始化。不要为了未发布的开发结构设计迁移链。

### 本轮开始时核验
- 仓库：`JunkingLee/DAEP`
- 分支：`release/1.0.0-rc9`
- 本轮开始 HEAD：`ed88646c0ad5492e2fd4d3710c699ec50b5bae75`
- 该 SHA combined status 为空，workflow runs 查询为空；无可确认 CI 通过记录。本轮不将空结果描述为 CI 通过。
- 本轮开始时未执行 pytest 或 PostgreSQL 测试。

### 本轮文档设计结果
- `docs/DOMAIN_MODEL_AGENT_OWNERSHIP.md` 新增 AgentCollaborationSession 领域定义：
  - 一个 Task 最多一个默认 Session（Task 1:0..1）。
  - Session 是逻辑协作空间，不是 Agent、Runtime、调度器或授权凭证。
  - Session 管理协作消息、提议、参与者投影、活动和审计。
  - Agent 参与权限由 AgentCollaborationGrant 决定；不额外建一份可独立授权的 Session membership，避免双重权限源。
  - Session 状态 OPEN / PAUSED / CLOSED；Task 终态关闭 Session。
- `docs/AGENT_TASK_GRANT_MIGRATION_DESIGN.md` 已调整为开发阶段数据库 Schema 设计文档，并新增：
  - `agent_collaboration_sessions` 初始表结构和 Task 唯一关系。
  - AgentCollaborationGrant 绑定 session_id。
  - messages 复用现有消息表并记录 Agent 作者身份与授权来源。
  - Agent 协作 proposal 数据结构。
  - Task 1:N Grant、Session 1:N CollaborationGrant、并发授权与 RLS 约束。
  - 从空数据库建立目标 schema 的实施顺序。
- 文档开头明确：旧章节 migration/legacy 方案只作为历史讨论背景；实施以第 12 节初始 Schema 为准，不执行历史数据回填、旧表兼容、旧 assignment 转换或 legacy 清理。

### 本轮提交
- `229792232a89c78da785c7952c373e6c4fb77816` — 增加 AgentCollaborationSession 领域模型。
- `140060ea4611e9a251c5334340dd52e0f901b108` — 增加 Session 与初始 Schema 设计。
- `1905389e1caa14a7a27b237f93875f58cfd2bf56` — 明确开发阶段不做迁移/利旧，调整文档标题和执行口径。
- 本轮仅修改文档；没有修改数据库模型、bootstrap、Alembic baseline、API、MCP 或前端。
- 未运行 pytest；未验证 PostgreSQL RLS；未运行真实 MCP Host / 浏览器测试；CI 需以本节后续核验为准。

### 下一步唯一任务
直接检查当前 SQLAlchemy models、SQLite bootstrap schema、Alembic 初始基线和 PostgreSQL RLS 定义，依据冻结的目标结构实现初始数据库 Schema（不是历史迁移）：
1. AgentTaskExecutionPolicy；
2. AgentTaskGrant Task 1:N；
3. AgentTaskContribution；
4. AgentCollaborationSession Task 1:0..1；
5. AgentCollaborationGrant 绑定 Session；
6. 消息 Agent identity/session 关联和 proposal 表（先确认现有消息/工作包结构是否可直接复用）。
同步实现干净数据库初始化、SQLite schema contract tests、PostgreSQL RLS/schema tests 和并发授权测试。完成数据库层后再开发 API/MCP。


---

## 24. TEAM 协作初始数据库 Schema 第一轮实现（2026-11-24）

### 本轮目标与边界
- 承接第 23 节：实际检查并实现 TEAM 协作的初始数据库结构。
- 用户明确：当前仍是开发阶段，不做历史数据库迁移、生产数据迁移、旧数据回填、利旧或旧版本兼容。
- 未新增 Alembic revision 文件；修改当前开发版 PostgreSQL schema 定义 `0036_rc46_agent_task_grants.py`，SQLite 使用当前 Bootstrap + Agent Identity 初始化。面向干净数据库建库，不做旧数据库转换脚本。
- 当前仓库没有独立 SQLAlchemy declarative Models 层；实际结构由 `app/main.py` SQLite Bootstrap、`app/agent_identity.py` Agent 身份初始化和 Alembic PostgreSQL DDL 维护。不要再按不存在的 ORM 层组织实现。

### 代码审查发现并处理
1. 旧有效 Grant 唯一索引是 `UNIQUE(task_id)`，与 TEAM 多 Agent 冲突；已改为 `UNIQUE(task_id, agent_id)`，同一 Task 可有多个不同 Agent，同一 Agent 同一 Task 不可重复有效授权。
2. 新 Grant schema 不再包含 `legacy_assignment_id`。
3. 现有 `messages` 是成员收件箱/通知投递记录，只有 recipient 语义，不是共享会话；因此没有把它错误扩展成聊天表，新增 `agent_collaboration_messages`。
4. Session 不另建可独立授权的 Agent membership 表；Agent 的 Session 权限由 AgentCollaborationGrant 唯一决定。
5. Contribution、Agent 消息和 Agent proposal 使用复合外键绑定 Grant、Task、Session、Agent、Owner，避免仅凭 grant_id 或 session_id 形成错误归属。

### 已实现的初始 Schema
- `agent_task_execution_policies`：每 Task 唯一；TEAM 固定；allow_multiple_agents；max_agents nullable，NULL 无任务级固定数量上限。
- `agent_task_grants`：有效唯一键调整为 (task_id, agent_id)。
- `agent_task_contributions`：按 grant/task/agent 保存独立贡献。
- `agent_collaboration_sessions`：每 Task 最多一个默认 Session，OPEN/PAUSED/CLOSED。
- `agent_collaboration_grants`：按 Session + Agent 独立授权，具备 scopes/resource scope/有效期/撤销字段。
- `agent_collaboration_messages`：Member/Agent 明确作者身份；Agent 消息强制带 Owner 和 CollaborationGrant 来源。
- `agent_collaboration_proposals`：邀请、工作包、Member 委派、帮助请求等提议。
- SQLite 由新增 `app/agent_collaboration_schema.py` 创建协作表；`app/agent_identity.py` 初始化 Agent 身份后调用。
- PostgreSQL 在现有开发 schema 定义 `alembic/versions/0036_rc46_agent_task_grants.py` 中定义相同实体和索引；对所有新租户表 ENABLE + FORCE RLS，使用 `daep_tenant_visible(tenant_id)`，并撤销 `daep_authenticator` 直接表权限。
- `tests/postgres_rls_smoke.sql` 增加双 Tenant 的 Policy、Contribution、Session、CollaborationGrant、Message、Proposal 夹具和隔离断言。
- 新增 `tests/test_agent_collaboration_schema.py`，检查 SQLite 表/索引/字段、TEAM + max_agents=NULL，以及同一 Task 多个不同 Agent Grant 可并存、同一 Agent 不可重复有效授权。

### 本轮提交
- `04185f72716bb85ee68261601f43c2a86cbd8860` — 新增 SQLite 协作 Schema 模块。
- `cc9f5eb8a2b6dcc01a498d2dcc287b5b0e638a1b` — Task Grant 唯一索引按 Task + Agent。
- `c1e3f106a627aeb5d2cfcf0bbcf17a7e2a58ce01` — Agent Identity 初始化后创建协作 Schema。
- `bcb0c080c564d725afabd517d28e1f35692915c7` — PostgreSQL 初始 schema 加入协作实体和 RLS。
- `c5d4a03ddbb8cf0292f39bdc76c2e945a2586007` — PostgreSQL RLS smoke 增加协作表租户隔离覆盖。
- `71425748408e4ece11da1edc6e57194f26bb4169` — 新增 SQLite schema contract tests。
- `3e670ce8d0b11603af8c6e02e081ad98ff0085d3` — 新增多 Agent Grant 数据库约束测试。
- `b5d89a4cae673ab3d57556ae9f17b80341be936b` — PostgreSQL 复合外键完整性约束。
- `dc506ff426c4d98f9587b2c4d0a33cc17df5a4fe` — SQLite Grant 复合唯一键。
- `8c8bf0d1fadd46da31e39f40e60fb9a9c86caa20` — SQLite CollaborationGrant 复合唯一键。
- `363bbbbb3b52a5a492d8d84457412e57d4933004` — 修订领域模型，明确协作消息与通知 Inbox 分离。
- `fb3fef6332194599b04bc6cdd93159e85dde096a` — 更新 Schema 设计与实际代码实现一致。
- 本节提交 SHA 是本轮 handoff 更新前 HEAD；handoff 文件更新会生成新的最终 HEAD。

### 验证状态与限制
- 本环境本轮未执行本地 pytest，也未连接 PostgreSQL 实际运行 RLS smoke。
- 对提交 `fb3fef6332194599b04bc6cdd93159e85dde096a` 查询 combined status 返回空 statuses，workflow runs 查询返回空列表；不能宣称 CI 通过。
- SQLite schema contract tests 已写入但未执行；PostgreSQL RLS smoke 已更新但未执行。
- 当前只完成数据库初始结构；没有实现策略 API、事务级 max_agents/allow_multiple_agents 并发校验、Session/CollaborationGrant API、消息 API/MCP 或前端。
- `allow_multiple_agents` 和 `max_agents` 的业务数量校验必须在后续 Grant 写入服务中锁定 Policy/Task 行事务内实现；静态唯一索引只负责同一 Agent 同一 Task 不重复授权。

### 下一步唯一任务
先以最新提交的 CI 结果验证本轮数据库结构：
1. 检查 Python 测试矩阵中的 `tests/test_agent_collaboration_schema.py`。
2. 检查 PostgreSQL Alembic 干净建库和 `tests/postgres_rls_smoke.sql`，重点检查复合 FK、RLS 和 authenticator 权限。
3. 修复 CI 暴露的 schema/test 问题；不要在 CI 结果未知时宣称数据库层已验证通过。
4. 数据库层验证完成后，下一阶段才实现 AgentTaskExecutionPolicy 和 AgentTaskGrant 事务服务/API；在同一事务锁定 Policy 行校验 allow_multiple_agents/max_agents，随后再实现 Session/CollaborationGrant API。仍不做历史迁移或利旧。


### CI 首轮反馈与修复（2026-11-24）
- 初始 schema 代码提交 `e7f28ad05bce430a0bd8b43392453c649bc67d67` 触发 run `45321152370`。
- PostgreSQL migrations job 成功，production-compose 和 container-build 成功。
- Python 3.11/3.12/3.13 均因既有 `tests/test_api.py::test_rc46_agent_task_grants_schema_and_migration_contract` 仍断言 `legacy_assignment_id` 和旧 `UNIQUE(task_id)` 而失败；每个版本其余测试为 219 passed、1 skipped。
- 这属于测试合约仍描述旧模型，不是新 schema 测试失败。已将该测试调整为初始 Schema 合约：删除 legacy 字段/外键，改为 (task_id, agent_id) 唯一索引和复合键。
- 修复提交：`484dc155f2203502e4aa7b2bdf377554e27e48e5`、`2424ca2bf6cdf519b591d72c842a3be0b3a2db69`、`2eb5699d0694d648ad70833ee349411f01ac0ee7`（最后一项修正测试 DDL 中误写的转义换行）。
- 最新代码提交 `2eb5699d0694d648ad70833ee349411f01ac0ee7` 对应 CI run `45321394737` 已创建，当前查询状态为 pending；不得提前宣称通过。
- 旧 run 的 browser-e2e 因新提交触发后续运行而 cancelled，不作为结果。继续以最新 run 为准。

## 25. AgentTaskExecutionPolicy 与多 Agent Grant 事务服务（2026-11-24）

### 本轮恢复核验
- 分支：release/1.0.0-rc9
- 本轮开始 HEAD：156df1ee5a49a7ee88b96b22a0e5a56204c66456
- 上一阶段数据库 Schema CI run 45321445919 已完成且所有 jobs 成功：Python 3.11/3.12/3.13、PostgreSQL migrations（包含 bootstrap、schema upgrade、migration SQL、RLS policy 和受限角色租户隔离步骤）、production-compose、browser-e2e、container-build。
- 较早 run 45321394737 已取消，不作为最终验证依据。

### 本轮代码实现
- 修改 app/main.py：
  - 新增 GET /api/v1/tasks/{task_id}/agent-execution-policy，读取/初始化任务的默认 TEAM 策略。
  - 新增 PUT /api/v1/tasks/{task_id}/agent-execution-policy，仅当前唯一人类任务负责人可设置 allow_multiple_agents 和 max_agents。
  - 默认策略为 collaboration_mode=TEAM、allow_multiple_agents=false、max_agents=NULL。
  - allow_multiple_agents=false 时有效上限为 1；此时 max_agents 仅允许 NULL 或 1。
  - allow_multiple_agents=true 且 max_agents=NULL 时不设置固定 Agent 数量上限。
  - 更新策略前检查现有有效 Grant 数量，禁止把策略改成低于当前活跃授权数量的配置。
  - Grant 创建现在在同一写事务中锁定 Task 行（PostgreSQL SELECT ... FOR UPDATE；SQLite BEGIN IMMEDIATE），再锁定/读取 Policy，清理过期 Grant，校验是否允许多 Agent、max_agents 数量上限、同一 Agent 重复授权。
  - Policy/Grant 都验证 Task 当前只有一个人类 assignee、调用者就是该 assignee、Agent 与调用者同 Owner、Tenant/Project/Task 关系有效；不依赖 Presence 或 agent_project_bindings。
  - Grant 审计事件增加 policy_id、policy_version 和授权后的活跃 Agent 数。
- 修改 tests/test_api.py：
  - 新增 test_agent_task_execution_policy_controls_team_grant_cardinality。
  - 覆盖默认单 Agent 策略、打开多 Agent、max_agents=2 上限、max_agents=NULL 无固定上限、同一 Agent 重复授权拒绝、非任务负责人不可修改策略、无效策略参数拒绝，以及策略版本递增和 Grant 数量。
- 保留既有 Grant 接受、撤销、Agent Inbox 和执行 scope API；本轮不改 Agent Runtime，也不开放 Session/CollaborationGrant/MCP 协作消息 API。

### 本轮提交
- d6056094c04a24ebca69a9a4fccb85d80b5592be — feat: enforce task agent execution policies
- da59b59d724d56c2c239be27555569aca0356e56 — test: cover task agent execution policy limits
- 本节文档更新前 HEAD：da59b59d724d56c2c239be27555569aca0356e56。

### 验证状态与限制
- 本轮未在当前执行环境直接运行 pytest。
- 最新代码/测试提交对应 CI run 45330959551，查询时状态为 pending；不能提前宣称 Python 测试、PostgreSQL 或浏览器验证通过。
- 需要重点观察新测试与既有单 Agent Grant 测试是否兼容；PostgreSQL 重点检查 Task/Policy 行锁和 RLS 下策略读写。
- 当前 Policy 初始化为惰性初始化：首次读取策略或授权 Agent 时创建默认策略行；不会为历史任务批量回填。
- SQLite 使用 BEGIN IMMEDIATE 串行化 Grant 写入；PostgreSQL 使用 Task 行锁作为同一 Task Policy/Grant 写入的串行化点。任务分配变更的其他写入口是否也统一锁 Task 行，仍需后续审查。
- 当前不做历史数据迁移、旧结构兼容、数据回填或利旧。

### 下一步唯一任务
检查 CI run 45330959551（或其后续更新 run）：
1. 检查 Python 3.11/3.12/3.13，尤其新 Policy/多 Agent Grant 测试和既有 Grant 生命周期测试。
2. 检查 PostgreSQL migration/RLS job 与 browser-e2e。
3. 若失败，定位并修复实际问题，更新本文件并提交。
4. 若通过，继续审查任务重新分配、Task 终态、Agent 禁用/Token 撤销与 Policy/Grant 生命周期的一致性；确保所有任务责任人变化路径与 Grant 创建共享同一 Task 锁定约定。

### Policy 负责人变更收口补充（2026-11-24）
- 复核任务重新分配场景后，补充 app/main.py：
  - Policy GET 现在也在写事务中锁定 Task，避免首次惰性初始化策略时与 Grant 创建并发竞争。
  - 当前 Task assignee 可通过 PUT 策略接口接管原负责人留下的 Policy；接管时更新 responsible_member_id 并递增 policy_version。
  - 普通读取和 Grant 创建仍拒绝使用负责人已过期的 Policy，只有当前 assignee 主动 PUT 才能接管，防止旧 assignee 继续控制策略。
- 修复提交：53d7274c2e65472258e0b90392c065e00c4e83c4 — fix: allow task assignee to take over agent policy。
- 此修复提交触发的新 CI 运行应作为当前最终验证依据；此前 run 45330959551 可能因新提交被取消，不能据此宣称完整通过。

## 26. AgentTaskGrant 生命周期与责任人变更收口（2026-11-24）

### CI 状态复核
- 上一轮执行策略提交 736b12d79ab5b235c7405f22eceacde09badbf35 对应 run 45331167815：
  - Python 3.11/3.12/3.13：SUCCESS。
  - PostgreSQL migrations/RLS：SUCCESS。
  - production-compose：SUCCESS。
  - container-build：SUCCESS。
  - browser-e2e：后续提交触发后被 CANCELLED，未完成验证，不能宣称该 run 全绿。

### 本轮审查发现
- Task 终态转换此前只更新 Task 状态，没有同步结束有效 AgentTaskGrant。
- Owner 主动撤销 Grant 没有先锁 Task 行，和并发授权没有统一串行化点。
- Agent 禁用会撤销 Grant，但没有统一锁定所有关联 Task；Token 显式撤销此前只撤销旧 Assignment，不撤销新 Grant。
- 人类 assignee 从项目移除、工作包重新分配时，没有同步撤销原 assignee Owner 授权的 Agent Grant。

### 本轮实现
- app/main.py：
  - 新增 _close_task_agent_grants：Task 进入 DONE 时把所有有效 Grant 置为 COMPLETED；进入 CANCELLED/CLOSED/ARCHIVED 时置为 REVOKED，写入时间、撤销人、原因和审计事件。
  - 所有五处重复定义的 transition_task_workflow 实现均在同一事务中锁 Task 行，并执行终态 Grant 收口，避免不同数据库后端路径遗漏。
  - Owner 撤销单个 Grant 前先锁定所属 Task 行，再重新读取 Grant 并更新。
  - 新增 _revoke_task_agent_grants_for_assignee_change：任务人类 assignee 变化/移出项目时，撤销原 Owner 授权的有效 Grant。
  - 工作包重新分配的各后端重复实现加入 Task 锁和 Grant 撤销。
  - 项目成员移除路径使用 SQLite BEGIN IMMEDIATE / PostgreSQL Task 行锁后，再清理关联 Grant。
- app/agent_identity.py：
  - Agent 禁用在同一写事务中锁定关联 Task，撤销该 Agent 的有效 Grant 和 Token。
  - Agent Token 显式撤销现在锁定关联 Task，并撤销该 Agent 的有效 Grant；返回 revoked_grant_count。
  - Token 轮换不撤销 Grant：Owner 只是更换凭证，Agent 身份和 Owner 授权关系仍然存在；旧 Token 失效，新 Token 可继续使用现有 Grant。
- tests/test_api.py：
  - 新增 Agent 禁用和 Token 显式撤销联动测试。
  - 新增 DONE -> COMPLETED、CANCELLED -> REVOKED 的 Grant 生命周期辅助函数测试。

### 本轮提交
- 9b773262b8449bc6f534c8aa400e1955b8c34de3 — Task 终态 Grant 生命周期处理。
- 0046022683bea8835fbae866a7ab916fb065eb94 — Token 撤销同步撤销 Grant。
- 494b6b34a2ff6261dd485231bf35cbecb12d641e — Task 终态转换串行化。
- fb5df6ada063c127f480484aa6f52e66cd520cdc — Agent 禁用/Token 撤销生命周期测试。
- 24ef0cbc16016a2ab648da0f0728f5cad2886949 — 所有 workflow 实现统一终态收口。
- 349430340e95abc8d2f1ef06ab832e18940de4a9 — assignee 变化时撤销旧 Grant。
- 2f9d8968e42323fbc23f8bb4eeca20284b446042 — 使用本地 Task 锁 helper。
- ae455c4baa988160ad0ef7dc076625bd722cbf65 — 项目成员移除路径串行化。
- a114cfbb3df2ba4ee87cd5af9f668ec99d1fcf36 — 补齐各 workflow 后端锁。
- 098f45595ad20fe55b372a5beaa651762dcf8ea8 — 补齐所有 workflow 实现的终态 Grant 关闭。
- 本节文档更新前代码 HEAD：098f45595ad20fe55b372a5beaa651762dcf8ea8。

### 验证状态与限制
- 本轮没有在当前执行环境直接运行 pytest。
- 最新代码提交触发的 CI 需以本节文档提交后最新 workflow run 为准；当前不能宣称本轮新增测试、PostgreSQL 并发锁或浏览器 E2E 已通过。
- test_task_terminal_lifecycle_completes_or_revokes_agent_grants 直接覆盖生命周期 helper 的 DONE/CANCELLED 分支；真实 workflow HTTP 端到端路径仍需 CI/后续集成测试确认。
- Token 显式撤销会终止 Grant；Token 轮换保留 Grant 是有意设计。
- 本轮不做数据库历史迁移、回填或利旧。

### 下一步唯一任务
检查本节最新提交触发的 CI：
1. Python 3.11/3.12/3.13，重点新增长生命周期测试和原 Grant 测试。
2. PostgreSQL migrations/RLS、production-compose、container-build。
3. browser-e2e 是否完整成功。
4. 若失败先定位修复；通过后增加真实 workflow HTTP 终态路径、Task assignee 变更和并发 Grant 撤销/授权的集成测试，再进入 AgentCollaborationSession / AgentCollaborationGrant 服务 API。

## 27. Task workflow HTTP 与 Agent Grant 终态集成测试（2026-11-24）

### 恢复核验
- 指定分支：`release/1.0.0-rc9`。
- 第 26 节交接提交 `a52f5f4b077706834c4ca8d4dd821a71cf812d1c` 已通过 GitHub commit 查询确认存在，内容为 Grant 生命周期收口文档。
- 该提交的 combined status 查询返回空 statuses，commit workflow runs 查询返回空列表；不能据此宣称 CI 通过或失败。workflow runs 查询接口只返回 PR 触发记录，空列表不代表不存在 push CI。
- 分支内容与第 26 节记录一致；仓库工具没有提供可直接读取分支 HEAD SHA 的 ref 查询接口。本轮以分支文件读取结果作为内容基准，后续需用新提交 SHA 和 CI 结果继续核验。

### 本轮代码
- 修改 `tests/test_api.py`，新增 `test_workflow_transition_http_revokes_agent_grant_on_task_cancellation`。
- 测试通过真实 HTTP 路径创建 Member 自有 Agent、创建 Task Agent Grant、配置含 CANCELLED 阶段的工作流，再调用 `POST /api/v1/tasks/{task_id}/workflow-transition`。
- 验证 Task 状态变为 CANCELLED；对应有效 Grant 同步变为 REVOKED；撤销原因、撤销人和审计事件均正确。
- 该测试补足此前只直接调用 `_close_task_agent_grants` helper 的覆盖缺口，确保 API endpoint -> workflow transition -> Task 锁 -> Grant 生命周期逻辑端到端联动。
- 代码提交：`b76ca38cd9f36a4803fa806e7e8dacb4d761444c` — `test: cover HTTP workflow grant lifecycle`。

### 验证状态与限制
- 当前执行环境没有运行本地 pytest。
- 新提交尚无已核实 CI 结果；不得宣称新增测试或整个测试矩阵通过。
- 本轮没有改动生产逻辑、数据库结构、历史迁移或兼容逻辑。
- 尚未补齐任务 assignee 变化的真实 HTTP 集成测试，以及并发授权/撤销交错测试。

### 下一步唯一任务
- 继续补充真实 HTTP 集成测试：任务重新分配给另一 Member 后，原 Owner 的 Agent Grant 必须撤销；新 assignee 必须先通过策略接管，再由其 Owner 身份授权自己的 Agent。
- 随后补充并发 Grant 创建与撤销的事务一致性测试；确认 SQLite 与 PostgreSQL 使用同一 Task 串行化约定。
- 这些测试通过并完成 CI 核验后，再进入 `AgentCollaborationSession` / `AgentCollaborationGrant` 服务 API。仍不考虑数据库历史迁移、回填或利旧。

### CI 反馈与测试夹具修正（补记）
- 查询 run `45332129938` 的 jobs/logs 后确认：
  - Python 3.11/3.12/3.13 均失败于同一既有测试 `test_task_terminal_lifecycle_completes_or_revokes_agent_grants`。
  - 失败点是该测试用普通 Member Token 创建第二个 Requirement；当前权限模型要求 Project Manager 或 product work function，接口正确返回 403。
  - 每个 Python 版本为 222 passed、1 failed、1 skipped。
  - PostgreSQL migrations/RLS、production-compose、container-build、browser-e2e 均 SUCCESS。
- 已修正测试夹具：第二个 Requirement/Task 由 ADMIN 创建并分配给 Member；Agent 仍由该 Member 自己创建并授权，保留 Owner 私有归属边界。
- 修复提交：`4375e1baba63cc363a07579c784267f76e46761f` — `test: use project admin for lifecycle fixture`。
- 本轮新增真实 HTTP workflow 测试提交：`b76ca38cd9f36a4803fa806e7e8dacb4d761444c` — `test: cover HTTP workflow grant lifecycle`。
- 交接文档补记之前，CI 运行 `45332129938` 只覆盖此前代码；修复提交和 HTTP 集成测试尚待新 CI 验证。

## 28. Task assignee 变更与并发 Grant 集成测试（2026-11-24）

### 本轮实现
- 扩展既有真实 HTTP 工作包重新分配测试 `test_rc17_stalled_work_package_requires_manager_reassignment_and_notifies_new_agent`：
  - 由旧 assignee Member 自己创建私有 Agent，并通过 `POST /api/v1/tasks/{task_id}/agent-grants` 授权。
  - 通过真实 `POST /api/v1/work-packages/{package_id}/reassign` 将任务重新分配给另一 Member。
  - 验证旧 Owner 的 Grant 被撤销，撤销原因是 `Human task assignee changed`，并记录执行重新分配的 Member。
  - 新 assignee 创建自己的 Agent，调用策略 PUT 主动接管 Policy，再授权自己的 Agent。
  - 旧 assignee 在重新分配后尝试继续授权会得到 403。
- 新增 `test_agent_task_grant_concurrent_create_and_revoke_share_task_lock`：
  - 两个并发创建请求竞争 `max_agents=1`，断言只有一个成功，另一个得到 409。
  - 随后并发撤销当前 Grant 与创建替代 Grant，断言最终有效 Grant 数量不超过 1；如果替代授权成功，则仅替代 Agent 保持有效。
  - 测试使用 SQLite + FastAPI HTTP TestClient；PostgreSQL 的真实并发执行仍需 CI PostgreSQL job 或专门的 PostgreSQL 并发集成环境确认，不能仅凭 SQLite 测试推断。
- 前述 HTTP Task CANCELLED 终态测试与权限夹具修复仍保留。

### 本轮提交
- `35f50a4c98371367aa1552ceb77bf3d9b96db7fa` — test: cover assignee takeover of task agent grants。
- `30e85cc3e5ab62041b8be119d1f89b1c8ea012bc` — test: assert assignee change audit reason。
- `6a5ab628e75b85262b781083086af350e0cab998` — test: cover concurrent task agent grant writes。
- `ef716f6f735127b338f4e1e8fad4e5bf209c1b56` — test: read grant list response items。

### CI 与限制
- 以上测试提交尚未在本地运行；GitHub Actions 新一轮 CI 尚待检查。
- 前一轮 run `45332129938` 的失败是测试夹具使用普通 Member 创建 Requirement 导致 403；已在 `4375e1b` 修正为 ADMIN 创建 Requirement/Task，Agent 仍由 Owner 自己创建和授权。
- 需要核实本轮最新 CI 的 Python 3.11/3.12/3.13、PostgreSQL migration/RLS、production Compose、container build 和 browser E2E。
- 本轮只增加测试，没有修改生产权限逻辑、Schema 或历史迁移；不做回填、利旧或兼容。

### 下一步唯一任务
- 先核实本轮 CI；若失败，按真实日志修复并更新本交接文档。
- 若通过，开始 `AgentCollaborationSession` / `AgentCollaborationGrant` 服务 API：任务内默认 Session、Member 负责人创建/暂停/关闭、Agent Owner 独立授权加入、会话级 Scope/资源范围校验、撤销/过期处理和审计。
- Session 不创建/启动/调度 Agent Runtime；Agent 仍属于 Member，Runtime 仍由 Owner 自己的环境运行。协作授权不得自动授予 Project 全域权限。

## 29. 并发 Grant 测试的 HTTP 客户端兼容修复（2026-11-24）

### CI 结果与根因
- 核验 run `45334198996`，对应分支 `release/1.0.0-rc9`、提交 `a1372d7020d7cfdbfedf798e74575bfba2c22fa1`。
- Python 3.11/3.12/3.13 均在同一个新增测试失败：`test_agent_task_grant_concurrent_create_and_revoke_share_task_lock`。
- 唯一失败原因为 Starlette/FastAPI TestClient 的 `delete()` 方法不接受 `json` 关键字参数：`TypeError: TestClient.delete() got an unexpected keyword argument 'json'`。不是服务端 Grant 并发逻辑失败。
- 各 Python 版本分别为 224 passed、1 failed、1 skipped。
- PostgreSQL migrations/RLS、container-build、production-compose、browser-e2e 均 SUCCESS。

### 修复
- 将并发测试中的 `client.delete(url, json=...)` 改为通用 `client.request('DELETE', url, json=...)`，保留撤销请求体和原并发测试语义。
- 修复提交：`42ef3aedc67225330a8b2b95b9a93fafe10b9084` — `test: use request for delete JSON payload`。

### 验证限制
- 本轮通过 GitHub Actions 日志定位并提交修复；没有在当前执行环境直接运行 pytest。
- 修复提交触发的新 CI 尚待核验，不能将前一轮失败 run 视为修复后的通过结果。
- PostgreSQL job 验证 migrations/RLS，不等同于 PostgreSQL 多连接并发授权/撤销压力测试。
- 未修改生产逻辑、Schema 或历史迁移；不做历史数据回填、利旧或兼容。

### 下一步唯一任务
- 检查提交 `42ef3aedc67225330a8b2b95b9a93fafe10b9084` 触发的 CI 全部 jobs。
- 若 Python 测试通过且其他 jobs 全绿，再进入 `AgentCollaborationSession` / `AgentCollaborationGrant` 服务 API；若失败，按日志先修复。

## 30. AgentCollaborationSession / AgentCollaborationGrant API 第一阶段（2026-11-24）

### 上一阶段 CI 核验
- 修复并发测试 HTTP 客户端调用后，最新完整 CI 为 run `45334887299`，对应交接文档提交 `eded651fb478ad72bc26f0ec086e28b8f72b6173`。
- 以下七个 Job 全部 SUCCESS：Python 3.11、Python 3.12、Python 3.13、PostgreSQL migrations/RLS、container-build、production-compose、browser-e2e。
- run `45334857782` 因后续文档提交触发新 workflow 而 CANCELLED，不作为验证依据；以 `45334887299` 为完整验证依据。

### 本轮实现
- 新增 `app/agent_collaboration_api.py`，通过独立 APIRouter 注册协作 API；不把协作服务继续堆入大型 `app/main.py`。
- `app/main.py` 仅负责注入现有数据库连接、Actor 认证、Task 行锁、Task 负责人上下文、Policy helper 和审计函数。
- 默认 Session：
  - `GET /api/v1/tasks/{task_id}/collaboration-session` 在首次访问时幂等创建 Task 唯一默认 Session。
  - Session 的责任人沿用 Task Agent Execution Policy 的 responsible Member。
  - 任务 assignee 变更后，必须先显式接管 Execution Policy；Session 责任人随后才与 Policy 责任人对齐。
- Session 生命周期：
  - `PATCH /api/v1/tasks/{task_id}/collaboration-session` 支持 OPEN、PAUSED、CLOSED。
  - 仅当前 Task assignee 且已持有 Policy 责任权的 Member 可管理。
  - CLOSED 为终态，禁止重新打开；PAUSED/CLOSED 不允许新增 Agent Collaboration Grant。
  - Session 关闭不会自动撤销独立的 AgentTaskGrant。
- Owner 独立协作授权：
  - `POST /api/v1/tasks/{task_id}/collaboration-grants` 由当前 Member 为自己拥有的 Agent 授权，不允许负责人代其他 Owner 授权。
  - 校验 Agent ACTIVE、Tenant、Owner、Scope、Resource Scope、有效期；支持 1-90 天。
  - 当前协作 Scope：`session.read`、`session.message.send`、`session.proposal.create`。
  - Resource Scope 当前采用受限结构 `resource_ids`，不隐式扩大为 Project 全域权限。
  - 同一 Session + Agent 只允许一个有效授权；写操作先锁 Task，SQLite 使用 BEGIN IMMEDIATE，PostgreSQL 使用 Task 行 FOR UPDATE。
  - Agent 可查看自己的协作授权 Inbox，并通过 `POST /api/v1/collaboration-grants/{grant_id}/accept` 主动接受；校验 Agent 身份、Owner 关系、Session OPEN、Project ACTIVE 和过期状态。
  - Owner 可通过 `DELETE /api/v1/collaboration-grants/{grant_id}` 撤销自己的授权；其他 Member 不可代撤销。
  - 关键授权、接受、撤销和 Session 状态变更写入审计事件。
- 新增测试：
  - 默认 Session 重复访问保持唯一。
  - PAUSED 阻止新 Grant；恢复 OPEN 后可授权。
  - Owner 创建 Grant、Agent Inbox 查看和 Agent 接受。
  - Agent 不可管理 Session。
  - Owner 撤销授权、CLOSED 禁止重新打开和加入。
  - CLOSED Session 不影响独立 AgentTaskGrant。
  - 非 Owner Member 不可为他人 Agent 授权。

### 本轮提交
- `6eb1c658106c8a4619e42922fafb4ed79d00fd26` — feat: add task collaboration session and grant API。
- `dace1f25e30618738b6f1fcefc2091991bb35610` — feat: register task collaboration API routes。
- `abb8d39fb35f477ed7f16c693e9494863a79db14` — test: cover task collaboration session and grants。
- 本节交接文档提交 SHA 以本次文档提交结果为准。

### 验证状态与限制
- 上一阶段完整 CI 已全绿；本轮 API 和测试提交尚待本轮 CI 验证。
- 当前没有在执行环境直接运行 pytest；不得宣称新 API 测试已经通过。
- 本轮未新增数据库表或历史迁移；沿用已存在的 Session/CollaborationGrant 初始 Schema 定义。
- 本轮尚未开放 MCP 工具或前端界面；消息发送、提议处理、Presence 和实时协作消息流仍未实现。
- 当前 Scope/Resource Scope 是协作授权边界的第一版；具体消息/提议接口必须复用同一 Grant 有效性和 Scope 检查，不能绕过授权。
- PostgreSQL Job 通过 migration/RLS 不等于已完成真实 PostgreSQL 多连接并发压力测试。

### 下一步唯一任务
- 核验本轮 API CI 的 Python 3.11/3.12/3.13、PostgreSQL migrations/RLS、container-build、production-compose、browser-e2e。
- 若失败按日志修复；通过后继续实现 Agent Collaboration Grant 的统一有效性/Scope/Resource Scope 校验 helper，并以此为基础增加 Session 消息读写 API。Agent 消息必须携带有效 CollaborationGrant；Session 非 OPEN 时禁止新消息；消息历史和 Owner 归属可审计。
- 继续保持：DAEP 不创建、不启动、不托管 Agent Runtime；Agent 始终归属 Member；Presence 发现不代表调用授权；不新增历史迁移、回填或利旧逻辑。

### 首轮 CI 反馈与测试断言修正（补记）
- 首轮 API 测试 run `45335647552` 的 Python 3.11 和 3.13 均定位到同一测试断言问题：`test_task_collaboration_session_owner_grant_and_agent_acceptance_lifecycle` 将 Agent 协作授权 Inbox 字段误读为 `id`。
- 实际 API 为兼容 Agent Task Grant Inbox 结构，返回字段名是 `grant_id`；授权创建响应仍返回 `id`。服务端行为正确，失败是测试读取字段错误。
- 失败版本各自为 226 passed、1 failed、1 skipped；PostgreSQL migrations 和 Production Compose 已 SUCCESS。该 run 其余尚未结束的 jobs 因后续提交触发新 workflow 被 CANCELLED，不能视为全绿。
- 已修正测试断言为 `item["grant_id"]`，提交：`b7daf0ad6fdd8e787fa15174d8c530f702b68782` — `test: use collaboration grant inbox identifier`。
- 修复后 CI 尚待检查；本轮 API 仍不得标记为验证通过。


## 31. Agent Collaboration 消息 API 第一阶段（2026-11-24）

### CI 核验
- 上一阶段 Session/CollaborationGrant API 及 Inbox 字段修复对应 run 45335830556，提交 d93743564ab912dab5c00807faf70dcbb3bea32b，七个 Job 全部 SUCCESS：Python 3.11/3.12/3.13、PostgreSQL migrations/RLS、container-build、production-compose、browser-e2e。
- 本轮开始时分支 HEAD 为 d93743564ab912dab5c00807faf70dcbb3bea32b，分支仍为 release/1.0.0-rc9。

### 本轮实现
- app/agent_collaboration_api.py：
  - 新增统一 _agent_collaboration_grant_context 校验入口，按 Agent Token 身份加载 Grant，并校验 Tenant、Agent、Owner、Project、Task、Session 关系。
  - 仅接受 ACCEPTED、未过期、未撤销、Agent ACTIVE、Project ACTIVE 的 CollaborationGrant。
  - 按操作校验 session.read / session.message.send Scope。
  - Resource Scope 非空时，Agent 发送消息必须指定允许的 resource_id；Agent 读取历史时只返回授权资源范围内的消息。
  - 新增 GET /api/v1/tasks/{task_id}/collaboration-messages：Member 使用当前 Task 负责人权限查看；Agent 必须显式传 grant_id 并持有 session.read。PAUSED/CLOSED 保留历史读取。
  - 新增 POST /api/v1/tasks/{task_id}/collaboration-messages：Member 以本人身份发言；Agent 必须携带 Grant、拥有 session.message.send 且 Session OPEN。
  - Agent 作者身份、Owner 和 Grant 来源由服务端从认证上下文和 Grant 推导，不能通过请求体伪装为 Member。
  - 消息写入 agent_collaboration_messages 并记录 agent.collaboration_message.created 审计事件；消息 API 不修改 Task 总体进度、assignee、审批或工作包治理。
- tests/test_api.py 新增消息生命周期集成测试，覆盖授权与接受、Resource Scope 拒绝、Agent 作者身份防伪、Member/Agent 双向消息、历史读取、PAUSED/CLOSED 只读、撤销后访问拒绝和审计记录。

### 本轮提交
- 52c7ad308a577b1f7a8fa5a7f48930aec8200807 — feat: add scoped collaboration message API。
- e6c0b4d15c6368efa4ca1fb09f81f5cd43a914a4 — test: cover scoped collaboration message lifecycle。
- 代码提交已完成；当前待补交接文档并核验最新 CI。当前执行环境未直接运行 pytest。

### 验证状态与限制
- 本轮消息 API 尚未通过 CI 验证，不得宣称测试通过。
- 未新增数据库表或历史迁移；复用现有 agent_collaboration_messages Schema。
- PostgreSQL migration/RLS job 通过只验证建库和租户隔离，不等于真实 PostgreSQL 多连接并发压力测试。
- 当前 Member 历史读取沿用 Task 当前负责人/Policy 责任权校验；Agent 历史读取要求有效 Accepted CollaborationGrant 和 session.read。
- 本轮未开放 MCP 工具或前端界面。

### 下一步唯一任务
- 检查本轮最新 CI 的 Python 3.11/3.12/3.13、PostgreSQL migrations/RLS、container-build、production-compose、browser-e2e。
- 若失败，按失败日志修复；若通过，再审计现有 MCP 身份认证/工具注册边界，评估消息 API 的 MCP 暴露与前端协作时间线接线。
- 继续遵守：Agent 属于 Member，Runtime 自托管，DAEP 不创建/启动/调度 Agent；Presence 不构成授权；不做历史迁移、回填或利旧。


### 31 节补充：关系校验加固与 CI 调度情况
- 在统一 Grant helper 中进一步验证 Task 实际所属 Project、Owner Member Tenant 与 Grant/Agent/Session/Project 的一致性；Agent 消息发送还会拒绝 Task 已进入 DONE/CANCELLED/CLOSED/ARCHIVED 的情况。
- 测试中不再依赖消息时间戳/ID 的排序来断言 Agent 消息先后，按 author_type 定位对应记录。
- 补充提交：
  - 81eb905e5e1e4cce8c3bfb2b3423a031deb4a3bd — fix: tighten collaboration grant relationship checks。
  - 05a8719e9f5c23e085a2d84f99284d5a714c7a9d — test: make collaboration message assertions order independent。
- 初始代码/测试 CI run 45337149416 与 45337154182 因同分支后续提交触发并发取消/部分 Job 被取消，不作为验证结果。以本补充提交后的最新 CI 为准。
- 当前消息 API 仍待完整 CI 验证；没有本地 pytest 执行证据。


### 31 节最终收口补充
- Member 历史读取不再依赖 Task 仍处于可执行状态：改为校验当前唯一人类 assignee、有效 Member、Policy 责任人、Tenant/Project/Session 关系后读取既有消息；不自动创建新 Session。Task 已结束时保留历史读取能力。
- Agent 发送消息继续拒绝 Task 终态；Agent 读取历史在 Grant 仍有效且具备 session.read 时可访问。
- 新增 session.read-only Agent 负向测试，确保没有 session.message.send 时不能发送消息。
- 本轮最终原子提交包含 API、测试和本交接文件；以该提交 SHA 和其 CI run 为最终验证依据。


### 31 节 CI 失败修复记录
- CI run 45337587717（提交 d68b5b55b289cb0b87b65b05c06601219226fb98）Python 3.11/3.12/3.13 均在同一集成测试失败：Agent 的 Resource Scope 历史过滤把 Member 发布的普通 Session 消息（无 resource_id）错误排除，导致 Agent 只读到自己的资源消息。
- 该问题属于服务端历史过滤规则过窄，不是 CI 环境差异。修正为：Resource Scope 限制带 resource_id 的资源消息；没有 resource_id 的普通 Session 消息仍属于会话公共对话，可见于具备 session.read 的 Agent。
- 扩展测试断言，明确 Agent 历史中同时能看到 Agent 自己的资源消息和 Member 普通消息。
- 当前修复提交后需重新执行完整 CI；原 run 45337587717 的 Python 失败仍保留为历史结果，不得覆盖为通过。



## 32. Agent Collaboration 消息 MCP 工具接入第一阶段（2026-11-24）

### 上一轮 CI 核验
- 修复提交 `4fade0bb9cb191c8c8e45afe40d91b284bd8b1eb` 对应 CI run `45338024126`：最新检查时 Python 3.11/3.12/3.13、PostgreSQL migrations/RLS、container-build、production-compose 均 SUCCESS；`browser-e2e` 仍在安装 Chromium，run 尚未完成。不得将该 run 标记为全绿；需后续核验最终结果。

### MCP 边界审计结论
- 本机 MCP Server 为 `daep_mcp/server.py`，由成员自己的 MCP Host 启动；DAEP 不托管 Agent Runtime。
- Agent Token 在本机适配器使用 `_agent_path_allowed` 白名单，不继承 Owner Member 权限；REST 的 `actor()` 将 Agent Token 解析为 `actor_type=AGENT`，协作 API 再独立执行 CollaborationGrant 检查。
- 现有协作 REST 路由：
  - `GET /api/v1/agents/me/collaboration-grants`
  - `POST /api/v1/collaboration-grants/{grant_id}/accept`
  - `GET /api/v1/tasks/{task_id}/collaboration-messages`
  - `POST /api/v1/tasks/{task_id}/collaboration-messages`
- Agent 消息读取必须指定 Grant 且有 `session.read`；发送必须指定 Grant 且有 `session.message.send`。REST 每次校验 Agent、Owner、Tenant、Project、Task、Session 关系、Grant ACCEPTED/未过期/未撤销、Agent/Project 状态和 Resource Scope。Session 非 OPEN 禁止发送；历史读取保留。
- 不开放 Agent 创建/撤销 CollaborationGrant、创建/管理 Session、Member 收件箱或旧 Member 消息 API；Task Execution Grant 和 Presence 不能替代 CollaborationGrant。

### 本轮实现
- `daep_mcp/server.py`：
  - 将 Agent Collaboration Grant Inbox、接受 Grant、读取 Task 协作消息、发送 Task 协作消息四条 REST 路由加入 Agent Token 精确白名单。
  - 新增 MCP tools：`list_my_agent_collaboration_grants`、`accept_agent_collaboration_grant`、`get_task_collaboration_messages`、`send_task_collaboration_message`。
  - 读取/发送消息显式携带 CollaborationGrant ID；读取限制 limit 1-100；资源范围发送时由 REST 要求合法 resource_id。
  - 不改变 Member Token 既有工具行为；不将 Agent Token 转换为 Member Token。
- `tests/test_mcp_adapter.py`：新增 Agent 路由 allowlist 正/负向检查、四个工具的 API 路由/参数映射和输入校验。
- `daep_mcp/README.md`、`docs/MCP_INTEGRATION.md`：记录工具用途和双层授权边界。

### 提交与验证
- 本轮实现包含 MCP adapter、适配器测试、README、MCP 集成规范和本交接文件；提交 SHA 以本节最终文档提交为准。
- 当前没有在执行环境直接运行 pytest；本轮测试状态为待 CI 验证。
- 未修改 REST 协作 API、Schema 或数据库结构；未新增历史迁移、回填或兼容逻辑。
- CI 必须验证 Python 3.11/3.12/3.13、MCP adapter tests、PostgreSQL migrations/RLS、container-build、production-compose、browser-e2e。

### 下一步唯一任务
- 核验本轮 MCP 工具提交对应 CI 全部 Job；若失败按日志修复。
- 全绿后补充真实 HTTP 集成测试：Agent 仅凭有效 CollaborationGrant 读取/发送消息；缺少 Scope、错误 Agent/Owner、未接受、过期、撤销、Resource Scope 越权、PAUSED/CLOSED Session 均拒绝；Member Token 和既有 MCP 工具回归保持兼容。
- 继续遵守：Agent 属于 Member，Runtime 自托管；DAEP 不创建/启动/调度 Agent；Owner 分别授权自己的 Agent；不扩大 Project 权限；不做数据库迁移/利旧/回填。


### 32 节首轮 CI 反馈与测试断言修正
- MCP 工具提交 `a5f280be9a0658f5dbad65adc0caf4ae1396eb6c` 对应 CI run `45339056341`。Python 3.11 的 pytest 为 231 passed、1 failed、1 skipped；失败仅在新增 Agent 路由 allowlist 负向测试。
- 根因：`_agent_path_allowed` 使用 `strip('/')` 规范化路径，故协作消息路由尾部斜杠与标准路由等价；测试错误地把尾斜杠路径断言为拒绝。该行为不扩大路由范围，也不是授权绕过。
- 修正测试为拒绝多余路径段 `/collaboration-messages/extra`，保留对真实额外路由的负向检查；未修改生产授权逻辑。
- 首轮 CI 其余 Python 版本和 Browser E2E 在本修正前仍处于运行中；该 run 不作为完整通过依据。
- 修正提交后的 CI 尚待验证；当前未在本地直接运行 pytest。


### 32 节第二轮安全集成测试补充（待 CI）
- 增加真实 FastAPI TestClient 集成测试，验证未接受邀请不能读/写；其他 Agent 不能借用目标 Agent 的 Grant；Grant 到期后读/写均拒绝；Agent 当前 Owner 与 Grant Owner 关系不一致时 fail-closed。
- 测试直接操作当前开发 SQLite 测试库模拟过期和 Owner 关系漂移，不改变生产 Schema/API。
- 本轮测试变更提交后需重新核验 Python 3.11/3.12/3.13、migrations/RLS、容器构建、Production Compose 和 Browser E2E；本地 pytest 未执行，测试结果以 CI 为准。

- 提交前复核发现成员创建 API 返回的成员 ID 位于顶层 `id`，并非 `member.id`；已修正 Owner 关系漂移测试使用 `other.json()["id"]`。该更正先于本轮 CI 结果，后续 CI 将验证最终测试版本。

- 后续 CI（run `45340136793`，基于提交 `e5b83676f0f687fca58b3187beac4040febf1feb`）在新增测试中暴露两个夹具问题：SQLite Grant 表要求 `expires_at > created_at`，过期模拟需同时回拨创建时间；成员创建 API 的 ID 顶层字段修正已进入下一提交 `88cdf4292648ae8aff1b0d8a1020c2ac15aff4e3`。当前进一步修复过期夹具，将 `created_at` 设为 1999、`expires_at` 设为 2000，保证约束成立且相对当前时间已过期。


## 33. Agent Collaboration MCP 工具实际接线与 HTTP 传输验证（2026-11-24）

### 加速审计发现
- 对当前分支 HEAD `ff400858f855a4f0acdad1d017e13dec37e2bd0a` 重新核对 `daep_mcp/server.py` 后，发现上一节交接记录描述了四个 Collaboration MCP 工具，但该分支文件实际缺少对应函数，Agent 路由白名单也未包含 Collaboration REST 路由。
- 因此此前的 MCP 工具“已接入”记录与当前代码不一致；本节以本次实际代码提交为准，纠正这一差异，不把旧交接描述当作验证证据。

### 本轮实现
- `daep_mcp/server.py` 增加四个 MCP 工具：`list_my_agent_collaboration_grants`、`accept_agent_collaboration_grant`、`get_task_collaboration_messages`、`send_task_collaboration_message`。
- Agent Token 精确白名单只放行协作授权 Inbox、接受 Grant、Task 协作消息 GET/POST；不开放 Session 管理、Grant 创建/撤销或其他 Member 治理接口。
- 所有协作操作仍通过 REST API 执行；MCP 白名单只限制可调用路径，REST 每次请求继续校验 Agent、Owner、Tenant、Project、Task、Session、Grant 状态、Scope、Resource Scope 和 Session 状态。
- 消息读取显式携带 `grant_id`，limit 限制为 1-100；发送显式携带 `grant_id`，可选 resource_id 和 metadata。工具不将 Agent Token 转换为 Owner Member Token。
- `tests/test_mcp_adapter.py` 增加路由正/负向测试、工具参数映射/校验，以及本地 TCP HTTP Server 传输测试，验证 MCP adapter 的 urllib 请求确实携带 Agent Bearer Token、路径、查询参数和消息 JSON。
- REST 层真实 FastAPI 集成测试仍独立覆盖未接受、错误 Agent、过期和 Owner 关系漂移拒绝；两层测试组合验证 MCP 传输与 REST 授权边界。

### 验证状态
- 本轮代码/测试尚待 CI 验证；本地 pytest 未执行，不宣称测试通过。
- CI run `45340387898` 的 Python 3.11/3.12/3.13、PostgreSQL migrations/RLS、container-build、production-compose 已 SUCCESS；Browser E2E 仍在 Install Chromium 阶段，未完成。
- 本轮未修改 REST API、数据库 Schema 或历史迁移；不做数据回填、利旧或兼容处理。

### 下一步
- 核验本轮提交 CI；若 Python 测试失败，优先修复 MCP HTTP 传输测试或路由映射。
- CI 通过后，继续补充真实 MCP 工具到 REST API 的完整授权场景联测（Grant scope、撤销、Resource Scope、PAUSED/CLOSED），并回归 Member Token 既有工具。
- 继续保持 Agent 私有归属、Owner 分别授权、DAEP 不创建/启动/托管 Agent Runtime 的边界。


## 34. MCP Agent Token 白名单兼容性修复（2026-11-24）

### CI 失败定位
- 提交 `a89607ce39539971a91478614489afbe4075485b` 对应 CI run `45341270266`：Browser E2E、PostgreSQL migrations/RLS、container-build、production-compose 均 SUCCESS；Python 3.11/3.12/3.13 均因同一个 MCP allowlist 回归测试失败。
- 失败测试为 `test_agent_allowlist_accepts_only_grant_scoped_task_routes`。根因是本轮加入 CollaborationGrant accept 路由时，替换白名单逻辑遗漏原有 `POST /api/v1/agent-grants/{grant_id}/accept` Task Execution Grant 接受路由。
- 这是 Agent 原有任务授权流程的兼容性回归，不是 REST 授权失败。不能通过放宽为通用 POST 来修复。

### 修复
- 在 Agent Token 精确白名单中恢复原 Task Execution Grant accept 路由，同时保留 CollaborationGrant accept 路由，两者分别精确匹配。
- 新增回归测试，明确 Task Grant 与 Collaboration Grant 接受路由都允许，任意 revoke 路由仍拒绝。
- 未扩大 Agent Token 对 Member API、Session 管理、Grant 创建/撤销或项目治理接口的访问能力。

### 验证状态
- 本节修复提交后 CI 待验证；未在本地运行 pytest，不宣称测试通过。
- 上述 run 的 Browser E2E 实际已 SUCCESS，不再是阻塞项；本次失败仅为三种 Python 版本上的同一条 allowlist 测试。
- 未修改 REST API、数据库 Schema 或迁移文件；不做历史数据迁移、回填或利旧。

### 下一步
- 核验修复提交的完整 CI。
- CI 通过后继续做 REST 授权场景与 MCP Agent Token 真实调用链的端到端验证，重点补足 scope 不足、撤销、资源范围和 Session 暂停/关闭场景。


## 35. MCP allowlist 回归测试结构修正（2026-11-24）

- 修复提交 `9f4dc552823645650df899ea08043b32e9875a9a` 对应 CI run `45342319869`：Browser E2E、PostgreSQL migrations/RLS、container-build、production-compose SUCCESS；三个 Python 版本在收集 `tests/test_mcp_adapter.py` 时出现 SyntaxError。
- 根因是新增 Task Grant / CollaborationGrant 独立路由回归测试时，插入位置落在原有 `allowed=[...]` 列表内部，破坏 Python 语法。不是产品逻辑错误。
- 已将新增测试移动到原有 allowlist 测试函数结束之后，保留原始 allowed 列表内容和测试断言。
- 本轮修正提交后需重新验证完整 CI；未在本地运行 pytest，不宣称通过。


## 36. MCP Agent Collaboration 到 REST 的真实调用链集成测试（2026-11-24）

### 本轮新增
- 在 `tests/test_api.py` 增加 MCP adapter 经真实本地 TCP HTTP 请求调用 FastAPI REST API 的集成测试；HTTP Bridge 将 TCP 请求转交给当前测试应用，验证 MCP adapter 的 urllib 客户端、Bearer Token、路由和 REST 授权中间链路，不再只使用 mock `call()`。
- 测试覆盖 Agent Collaboration Grant Inbox、Agent 主动接受、有效 Scope 发送/读取、Resource Scope 越权拒绝、只读 Grant 禁止发送，以及 Session PAUSED 后仍可读历史但禁止发送。
- 使用两个不同 Agent Token 验证不同 Grant 的权限隔离；只读 Agent 无法借用另一个 Agent 的发送能力。
- 既有 REST 测试继续覆盖未接受、错误 Agent、过期、Owner 关系漂移、撤销和 CLOSED Session；既有 MCP adapter 测试继续覆盖 Member Token 工具兼容性。

### 边界与验证
- 测试中的 HTTP Bridge 仅是测试适配层；生产架构仍是 Agent 自己的 MCP Host 通过 HTTP 调用 DAEP REST API，DAEP 不启动/托管 Agent Runtime。
- 本轮仅增加测试，不改 REST API、数据库 Schema 或迁移文件；不涉及历史数据迁移、回填和利旧。
- 本轮测试尚待 CI 验证；本地 pytest 未执行，不宣称通过。

### 下一步
- 核验本轮完整 CI。若通过，进入 MCP 使用文档与 Agent Owner 配置/排障体验收尾；若失败，按日志修复并保持本轮端到端授权覆盖。


## 37. MCP 端到端测试身份切换修正（2026-11-24）

- CI run `45342865003` 的 Python 3.11/3.12/3.13 均运行 236 passed、1 skipped，只有新增 MCP→REST 端到端测试最后一个断言失败；PostgreSQL migrations/RLS、container-build、production-compose 已 SUCCESS，Browser E2E 仍运行中。
- 失败根因是测试将 MCP 模块 Token 切换为只读 Agent Token 后，在后续使用主 Agent Grant 验证 PAUSED Session 拒绝发送时没有恢复主 Agent Token，REST 正确返回该只读 Agent 无权访问主 Agent Grant 的 404。
- 修复仅在 PAUSED Session 发送断言前恢复主 Agent Token；保留只读 Agent 读取允许、发送拒绝的独立断言，不放宽任何 REST 授权逻辑。
- 本修复提交待 CI 验证；未在本地运行 pytest，不宣称测试通过。
- 未修改 REST API、数据库 Schema 或迁移；不做历史数据迁移、回填和利旧。


## 38. MCP 端到端测试双 Agent Token 顺序修正（2026-11-24）

- 修复提交 `8321af00af1da664a75af140596bc627323ef9c3` 对应 CI run `45343235417`：Python 3.11/3.12 仍在端到端测试失败，根因是上一次 Token 恢复插入位置不正确，导致只读 Agent 的 Grant 历史读取使用了主 Agent Token。
- 正确测试顺序现为：切换只读 Agent Token → 验证只读 Agent 可读/不可发送 → PAUSED 后仍用只读 Agent Token 读取历史 → 切换主 Agent Token → 验证主 Agent 的发送因 Session PAUSED 被拒绝。
- 该修复只调整测试中的身份切换顺序，不改变任何产品授权逻辑。
- 修复提交待 CI 验证；本地 pytest 未执行，不宣称通过。


## 39. MCP 本地接入文档与 Owner 配置体验收尾（2026-11-24）

### CI 验证
- 提交 `06da5afb48da7977e58b86c951d4c40367611ec5` 对应 CI run `45343437805` 七个 Job 全部 SUCCESS：Python 3.11/3.12/3.13、PostgreSQL migrations/RLS、Container Build、Production Compose、Browser E2E。
- 该 CI 验证覆盖 MCP→REST 双 Agent Token、Grant Scope、Resource Scope、只读、Session PAUSED 等端到端测试。

### 本轮工作
- 重写 `docs/MCP_INTEGRATION.md`，清除与当前实现不一致的旧工具清单、Member Token 主流程和“远程 Streamable HTTP 已交付”误导；明确当前是 Owner 本机 stdio Adapter。
- 扩充 `daep_mcp/README.md`：补充 Agent Owner 首次接入、Task Execution Grant 与 Collaboration Grant 的区别、精确工具范围、常见 401/403/404/409 排障、安全要求和 Windows/macOS/Linux 配置提示。
- 更新「我的 Agent」页面连接说明和 Token 配置弹窗，明确本机安装依赖、替换脚本绝对路径、使用 `DAEP_AGENT_TOKEN`、重启 MCP Host，以及 DAEP 不托管 Agent Runtime 的边界。
- Token 仍只在创建/轮换时显示一次；没有将 Token 明文写入持久化配置或源码。
- 未修改 REST API、数据库 Schema 或迁移文件；不做历史数据迁移、回填和利旧。

### 下一步
- 验证本轮文档/UI 提交的 Browser E2E 与完整 CI。
- 下一阶段核对「我的 Agent」页面 Token 轮换、撤销、停用和项目绑定流程，与 Task/Collaboration Grant 生命周期是否一致；补充真实浏览器交互覆盖。


## 40. Agent 页面帮助入口路径修正（2026-11-24）

- 复核发现 DAEP Web 服务只挂载 `/static` 静态目录，仓库 `docs/MCP_INTEGRATION.md` 并未通过 `/docs/` 路径提供服务。
- 将「我的 Agent」页面中不成立的 `/docs/MCP_INTEGRATION.md` 超链接改为明确的仓库文档路径提示，避免用户点击后进入 404。
- 不新增文档静态公开路由，避免意外暴露仓库内部文档目录。
- 本修正提交待 CI 验证。


## 41. Agent Token / 身份高影响操作二次确认（2026-11-24）

### 审计发现
- 「我的 Agent」页面的 Token 轮换、Token 撤销和 Agent 停用均会影响运行中的 Agent 连接，但此前 UI 直接执行，没有确认步骤。
- 后端已有相应生命周期处理：Token 轮换立即撤销旧 Token；Token 撤销同步撤销有效 Task Execution Grant；Agent 停用撤销活动 Token 和有效 Task Execution Grant。此轮不改变后端生命周期语义。

### 本轮修改
- Token 轮换前增加确认提示，说明旧 Token 立即失效，Owner 应准备更新本机 MCP Host 配置。
- Token 撤销前增加确认提示，说明使用该凭证的连接立即失效。
- Agent 状态切换为 DISABLED 时增加确认提示，明确活动 Token 和有效 Task Execution Grant 会被撤销。
- 扩展 UI 静态契约测试，锁定三种确认提示。
- 扩展真实浏览器 E2E：轮换、撤销、停用操作均显式接受浏览器确认对话框，并验证停用后的 UI 状态。
- 本轮未修改 REST API、数据库 Schema 或迁移文件；不涉及历史迁移、回填或利旧。

### 验证状态
- 前一轮 MCP 接入文档/UI 提交 `fef5971c254b600576faeae93d92f366b1bc001a` 对应 CI run `45343938237` 七个 Job 全部 SUCCESS。
- 当前二次确认变更待 CI 验证；本地 pytest 未执行，不宣称测试通过。


## 42. Agent 身份停用同步撤销协作授权（2026-11-24）

### 生命周期审计发现
- Agent 停用会撤销活动 Token、旧 Agent Assignment 和 AgentTaskGrant，但此前未把已授权/已接受的 AgentCollaborationGrant 从活动状态转为 REVOKED。
- REST 调用期间因 Agent 状态为 DISABLED，协作 Grant helper 会 fail-closed；但若 Owner 随后重新启用同一 Agent 并轮换 Token，旧的 ACCEPTED CollaborationGrant 仍可能恢复可用。这会让已停用身份的协作授权被意外复活。
- Owner Member 账户停用路径直接将其 Agent 标记为 DISABLED，也存在同样的历史协作授权残留。

### 本轮修复
- Agent 身份停用时，先合并锁定其有效 Task Execution Grant 和 CollaborationGrant 所涉及的 Task，再撤销全部 AUTHORIZED/ACCEPTED CollaborationGrant。
- 每条协作授权写入 REVOKED、revoked_at、revoked_by_member_id、revoke_reason，并产生 agent.collaboration_grant.revoked 审计事件。
- Owner Member 账户停用导致其 Agent 停用时，同步撤销该 Agent 的有效 CollaborationGrant，并写入相同的授权审计。
- Agent 重新启用只恢复身份状态，不恢复旧 Task/Collaboration Grant；Owner 必须重新授权，Agent 必须重新接受。
- Token 单纯轮换不撤销 CollaborationGrant：轮换只替换认证凭证，既有身份授权保持有效；显式撤销 Token 仍按既有策略撤销 Task Execution Grant，但不会把授权治理与凭证轮换混为一谈。
- 项目解除绑定仍不自动撤销 Owner 已明确授予的 Task/Collaboration Grant；项目绑定不是授权本身，执行和协作接口继续按各自 Grant 与 Project 状态判定。
- 新增集成测试覆盖接受后的 CollaborationGrant 在 Agent 停用后被撤销、重新启用和轮换 Token 后不复活。
- 未修改数据库 Schema、初始结构或迁移；未增加历史数据回填/兼容逻辑。

### 验证状态
- 上一阶段提交 `c27281c6be8c358d1fbfc6436968b2fdb2c9b9cc` 对应 CI run `45344307938` 七个 Job 全部 SUCCESS。
- 本轮代码和测试尚待 CI；未在执行环境直接运行 pytest，不宣称通过。

### 下一步
- 核验本轮 CI；通过后继续补充 Owner 账户停用对 CollaborationGrant 的专项回归，以及 Agent Token 撤销/轮换、项目解绑的生命周期契约测试。


## 43. Agent 停用生命周期回归断言修正（2026-11-24）

- CI run `45345525862` 的三个 Python 版本均定位到同一测试断言：撤销的 CollaborationGrant 访问消息接口返回 403（已认证 Agent 缺少有效 Grant），测试错误期待 404。修正为 403，保持 fail-closed 授权语义，不修改 API 行为。
- 新增 Owner Member 账户停用专项集成测试：接受的协作授权被同步撤销，撤销人/时间/原因被记录；Owner 重新启用后 Agent 仍保持 DISABLED，旧 CollaborationGrant 不恢复。
- 上一提交中 Agent 自身停用专项测试仍覆盖重新启用 + Token 轮换后旧 Grant 不复活。
- 本轮测试和文档随修复一次性提交；等待新 CI 验证。


## 44. Token 生命周期与授权分层契约测试（2026-11-24）

### CI 失败修正
- 提交 `a7ebe97aa1792b86d0310890caa28f9d66c6394e` 对应 CI run `45345723269`：三个 Python 版本均为 238 passed、1 failed、1 skipped。唯一失败是 Owner disable 测试引用未定义的 `ADMIN_ID`，不是后端逻辑失败。
- 测试改为通过 `GET /api/v1/me` 读取当前 Admin 的真实 Member ID，再核验 `revoked_by_member_id`，不硬编码系统身份。

### Token 与 Grant 契约
- 扩展 Token 生命周期集成测试，同时创建并接受 Task Execution Grant 和 CollaborationGrant。
- Token rotate：旧 Token 立即 401，新 Token 生效；Task Execution Grant 与 CollaborationGrant 均保持 ACCEPTED。
- Token revoke：旧 Token 立即 401；按现有明确策略撤销 Task Execution Grant 和旧 Assignment；不撤销 CollaborationGrant（它是独立的 Agent 身份级协作授权）。
- Revoke 后由 Owner 再次签发凭证：新 Token 可继续使用仍有效的 CollaborationGrant，但不能恢复已撤销的 Task Execution Grant。
- 这明确区分凭证状态、任务执行授权与协作授权，不因 Token 撤销而意外扩大/缩小另一类授权。

### 项目解绑契约复核
- 既有 `test_agent_unbind_revokes_legacy_assignment_but_not_owner_task_grant` 已覆盖：解绑撤销旧 Assignment；Owner 明确授予的 Task Execution Grant 保持 ACCEPTED，任务读取/进度报告继续受该 Grant 控制；显式撤销 Task Grant 后访问才被拒绝。
- 本轮不改变项目绑定和 Grant 的独立语义；项目绑定不是 Owner 授权本身。

### 变更边界与验证
- 仅修改 `tests/test_api.py` 和本交接文档；不修改 REST API、数据库 Schema 或迁移文件，不做历史迁移、回填或利旧。
- 本轮提交后需验证 Python 3.11/3.12/3.13、PostgreSQL migrations/RLS、Container Build、Production Compose、Browser E2E；本地 pytest 未执行，结果以 CI 为准。


## 45. Token 生命周期测试断言修正（2026-11-24）

- CI run `45346355670` 的三个 Python 版本均为 238 passed、1 failed、1 skipped；唯一失败来自测试本身对 Token 状态的错误最终断言。
- 实际契约是：首次 Token、第一次 rotate 后 Token、revoke 时当前 Token 均应为 `REVOKED`；Token revoke 后重新 rotate 签发的最新 Token 应为 `ACTIVE`。
- 因此将测试从“所有 Token 都 REVOKED”修正为“恰好 1 个 ACTIVE，至少 2 个 REVOKED”，不改变后端实现。
- 本轮其他 CI 项目已通过：container-build、migrations、browser-e2e、production-compose。


## 47. Agent 管理页授权状态分层（2026-11-24）

### 恢复与纠正
- 本轮先核实 release/1.0.0-rc9 实际 HEAD，发现上一轮尝试提交 4a48e40307ec3a3d41026489ad8ba54017fbbe22 虽然存在，但其 Git Tree 错误地删除了大量仓库文件；未将该提交作为有效功能实现。
- 已用父提交 f2866a03f42e62295b664aeeb0a601bef0e54569 的完整 Tree 恢复仓库内容，并生成恢复提交 87dc507bd88481d68362ed2567152c5e847d3665，当前分支 HEAD 已恢复到完整代码树。
- 4a48e40307ec3a3d41026489ad8ba54017fbbe22 保留在历史中，但不再位于分支 HEAD 的有效代码树中。

### 本轮实现
- Agent 详情 API 增加 Task Execution Grant 与 Collaboration Grant 的只读状态信息，继续通过 _agent_owner 限制为 Agent Owner/管理员可查看。
- 「我的 Agent」详情弹窗明确拆分 Credential、Task Execution authorization、Collaboration authorization 三层状态；展示 Grant 状态、Task/Session、Scope、Resource Scope、过期/撤销时间及撤销原因。
- UI 明确 Presence 不等于授权；不新增任何跨 Owner 授权/撤销入口，Grant 治理仍由既有 Task 负责人和 Agent Owner 规则执行。
- 增加静态 UI 契约和 Agent 详情 API 回归断言。
- 本轮未修改数据库 Schema、迁移或历史数据；不做数据迁移、回填或利旧。

### 验证
- 本环境未直接运行 pytest/node；代码提交后以 CI 为准。
- 当前恢复提交 87dc507bd88481d68362ed2567152c5e847d3665 尚待 CI。
- 下一步：核验本轮完整 CI，并补充真实浏览器对 DISABLED Agent、REVOKED/EXPIRED Grant 状态展示的回归；Browser E2E 若安装/执行继续耗时，不无限等待。


## 48. Authorization-state test collection fix（2026-11-24）

- CI run 45350956647 对提交 6fc4247b878c072637c1eaa5fcddab5e1de699f6 的 Python 3.12 Job 暴露测试文件插入时把换行写成字面量 \
，导致 tests/test_agent_management_ui.py 与 tests/test_api.py 在 collection 阶段 SyntaxError。
- 已修正为真实换行；这是测试文件格式问题，不改变 Agent 详情 API 或 UI 运行逻辑。
- 同一 CI run 中 node --check web/agents.js、Python compile 已通过；其他 Job 尚在运行或已通过，最终结论以修复提交后的完整 CI 为准。
- 下一步唯一任务：核验修复提交的完整 CI。


## 49. Agent 授权状态真实浏览器回归（2026-11-24）

- 在现有 Agent 管理 Browser E2E 中补充真实 Task Execution Grant 与 Collaboration Grant 生命周期：由浏览器会话创建任务、授权并接受两个 Grant，再通过既有 Owner 治理 API 分别撤销。
- 重新打开「Agent 管理」详情，验证页面同时展示 Task Execution Grants、Collaboration Grants 和 REVOKED 状态，确认授权状态展示与实际 REST 生命周期一致。
- 该回归不新增 UI 授权入口，不改变 Agent Owner / Task 负责人治理边界；Agent 详情页仍只读展示授权状态。
- EXPIRED Grant 的时间边界仍由现有 API 集成测试覆盖，本轮浏览器回归避免人为等待过期时间。
- 提交后需验证完整 CI；当前 run 45351131519 的 Python 3.11/3.12/3.13、migrations、container-build、production-compose 已 SUCCESS，Browser E2E 仍停留在 Install Chromium。


## 50. 授权状态浏览器回归提交与 CI 交接（2026-11-24）

- 功能测试提交：82e141320214112054776b5a9e13be11c85040f9，新增真实浏览器对 Task Execution Grant / Collaboration Grant 创建、接受、撤销以及 Agent 详情 REVOKED 状态展示的回归。
- 随后文档格式修复提交：7d7c4225a54ffac5ff75352fbabc0569310a649c，将本节交接记录中的字面 \\n 修正为真实换行。
- 当前 CI run：45352042969，对应当前分支功能提交链；container-build、production-compose 已 SUCCESS；Python 3.11/3.12/3.13、migrations、Browser E2E 尚未全部结束，其中 Browser E2E 当前仍在 Install Chromium。
- 当前未观察到新的失败步骤；不能提前宣称完整 CI 或新的 Browser E2E 通过。
- 下一步：等待当前 run 收敛；若 Python 测试失败，优先修复新增浏览器回归；若 Browser E2E 长时间停留在 Chromium 安装，则保留该限制并以已完成的 Python/静态验证结果为准，不无限等待。


## 51. Agent Collaboration Proposal 闭环（2026-11-24）

### 本轮实现
- 补齐既有 `agent_collaboration_proposals` 表对应的 REST 生命周期：Agent 在有效 CollaborationGrant 且具备 `session.proposal.create` Scope 时，可创建 Task 级 Proposal；可通过 `session.read` 读取自己 Grant 范围内的 Proposal。
- Member 侧可读取 Task Proposal，并由 Agent Owner 对自己 Agent 发起的 Proposal 做 ACCEPTED/REJECTED 决策；Agent 可撤回仍处于 PENDING 的 Proposal。
- Proposal 决策只记录人类治理结果，不直接修改 Task assignee、Work Package、审批或验收状态；返回 `formal_mutation_required=true`，保持“Agent 提案、Human 决策、正式业务变更独立”的边界。
- 所有创建、决策、撤回均产生独立审计事件；Proposal 与 Session/Task/Agent/Owner/Grant 继续通过既有复合关系绑定。
- MCP 新增 Proposal 查询、创建、撤回工具；Agent Token allowlist 只增加 Task Proposal GET/POST，不开放 Member 决策接口。
- 新增 REST 生命周期、权限边界、重复决策、审计以及 MCP allowlist 回归测试。

### 变更边界
- 未修改数据库 Schema、迁移或历史数据；既有开发期 Schema 直接使用，不考虑迁移/利旧/回填。
- DAEP 仍不创建、启动或托管 Agent Runtime；Proposal 只是协作治理记录。

### 验证状态
- 本轮代码与测试提交后等待 CI 验证；当前未在本环境直接运行 pytest，不宣称测试通过。
- Browser E2E 仍按当前 CI 实际状态记录，不因本轮后端/MCP 测试完成而提前宣称通过。

### 下一步
- CI 通过后进入 Task Collaboration UI：展示 Session、消息、Proposal 状态，并提供仅限当前 Task 负责人/Agent Owner 的人类决策入口；继续补充浏览器回归。


## 52. Proposal CI 首次失败修正（2026-11-24）

- CI run `45353488944` 的 Python 3.11 已执行 241 passed、1 failed、1 skipped；失败仅来自本轮新增 Proposal 测试对应的实现 bug。
- 根因：`_agent_collaboration_grant_context()` 的返回值是 `(grant, scopes, allowed_resources)`，新 Proposal 路由误把第二项当成 Session；导致创建 Proposal 时出现 `TypeError: 'set' object is not subscriptable`。
- 已修正为从 Grant 的 `session_id` 查询 Session，并显式查询 Task 上下文；不改变 Grant 授权边界或 Proposal 语义。
- 同一 run 的 migrations、container-build、production-compose 已 SUCCESS；3.12/3.13 与 Browser E2E 当时仍在执行。
- 修复提交后的 CI 尚待验证，不能提前宣称通过。


## 53. Task Collaboration UI（2026-11-24）

### 本轮实现
- Task 详情现在直接展示 Collaboration Session、协作消息和 Agent Proposal，避免用户必须在多个页面之间切换才能理解一次 Task 的 Agent 协作状态。
- Session 状态按 OPEN / PAUSED / CLOSED 显示；PAUSED/CLOSED 保留历史读取，但 UI 不提供发送入口。
- Member 可以从 Task 详情发送协作消息；消息明确提示不会直接改变 Task 治理状态。
- 当前登录用户若是 Proposal 对应 Agent 的 Owner，可以在 Task 详情直接 ACCEPTED / REJECTED Proposal；其他成员只读。
- Proposal 展示类型、Agent、状态和 payload；Human 决策继续保持与正式 Task / Work Package / 审批 / 验收变更解耦。
- 增加静态 UI 契约测试。

### 验证状态
- 上一阶段 CI run `45353657122` 全部成功：Python 3.11/3.12/3.13、migrations、container-build、production-compose、Browser E2E 均 SUCCESS。
- 本轮 UI 提交后将触发新的 CI；尚未观察到本轮 CI 结果，不提前宣称通过。

### 下一步
- 补 Task Collaboration Browser E2E：实际创建 Agent Grant / Proposal / Message，并从 Task 详情验证展示与 Human Decision。


## 54. Task Collaboration Workspace 浏览器闭环回归（2026-11-24）

- 新增独立真实浏览器 E2E：浏览器登录后创建隔离 Project、Requirement、Task 和 Owner Agent；创建 Task Collaboration Session / Grant，并由 Agent Token 接受授权。
- Agent 通过真实 REST API 创建 HELP_REQUEST Proposal 并发送协作消息；随后浏览器实际打开 Task 详情，验证 Session、Agent 消息、Proposal payload 与 Owner 决策入口均显示。
- 浏览器点击“接受建议”，验证 Proposal 状态更新为“已接受”；再从 Task 详情发送 Member 消息，验证消息回显。
- 测试复用现有隔离 SQLite 服务 fixture，不触碰共享/生产数据库；不修改 REST API、数据库 Schema 或迁移，不做历史数据迁移、回填或利旧。
- 当前功能提交 `e148ddf4ab6f1b25febf43f215a9d62712bb4363` 已新增测试文件；本轮完整 CI 尚未观察到结果。本地未运行 pytest，不宣称通过。
- 注意：该测试要求 `DAEP_RUN_BROWSER_E2E=1`、Playwright 与 Chromium 可用；若 CI 长时间停留在 Chromium 安装，按实际 Job 状态记录，不无限等待。

### 下一步
- 核验新提交 CI；若失败，按实际失败日志修复测试数据/浏览器选择器或接口契约，不放宽授权规则。


## 55. Collaboration Message 类型契约修正（2026-11-24）

- 复核 REST `POST /api/v1/tasks/{task_id}/collaboration-messages` 后确认当前接口只接受 `message_type=MESSAGE`；Task 详情 UI 与新浏览器 E2E 原先使用 `TEXT`，会被后端以 422 拒绝。
- 已将 `web/index.html` 的 Member 消息发送 payload 和 `tests/test_task_collaboration_ui_e2e.py` 的 Agent 消息 payload 统一改为 `MESSAGE`，不放宽后端校验。
- UI 修正提交：`f3151a3e845c0aa348974a80e102b623019a75cc`；E2E payload 修正提交：`0f68af39aae46a8ccb29d2542604d5d6209dc767`。
- 本地未运行 pytest；修正后的完整 CI 尚未观察到结果，不宣称通过。
- 不修改 REST API、数据库 Schema 或迁移；不涉及历史数据迁移、回填或利旧。

### 下一步
- 核验当前分支最新 CI，重点关注新浏览器测试的 Proposal 决策按钮、消息回显，以及 Python 测试收集是否正常。


## 56. Task Collaboration 浏览器闭环 CI 验证与下一阶段（2026-11-24）

### 本轮验证结果
- 当前代码提交：`2839c1742db12666f6319544f0a3f40b5e8c1e40`（`ci: run task collaboration browser acceptance`）。
- CI run `45356197776`：整体 `success`，七个 Job 全部 SUCCESS：
  - Python 3.11 / 3.12 / 3.13：SUCCESS。
  - PostgreSQL migrations / RLS：SUCCESS。
  - Container Build：SUCCESS。
  - Production Compose：SUCCESS。
  - Browser E2E：SUCCESS。
- Browser E2E 使用真实 Playwright Chromium，命令执行 `pytest -q tests/test_agent_management_e2e.py tests/test_task_collaboration_ui_e2e.py`，结果 `3 passed in 10.42s`。覆盖 Agent 管理既有浏览器回归与 Task Collaboration Session / Grant / Agent Proposal / 消息 / Member 决策闭环。
- 因此，前一节记录的浏览器 E2E 待验证状态已解除；没有通过跳过 Chromium 或关闭测试来获得绿色结果。

### 本轮修正
- 修复 Agent 管理浏览器测试从真实页面 `.token-box` 读取一次性 Token 的断言，避免依赖未稳定的 `window.__daepLastAgentToken`。
- CI Browser E2E Job 同时执行 Agent 管理和 Task Collaboration 两个测试模块。
- 本轮没有修改 REST API、数据库 Schema 或迁移；不做历史数据迁移、回填或利旧。

### 下一步唯一任务
- 进入 **Task Collaboration 治理闭环强化**：补齐 Session OPEN / PAUSED / CLOSED 的真实浏览器操作与权限边界验证，并验证 CLOSED 后历史只读、禁止新消息/Proposal/新 Grant；同时覆盖非 Task 负责人不能管理 Session、非 Proposal Owner 不能决策等负向场景。
- 继续遵守既定规则：Agent 只提案，Member 决策，正式 Task / Work Package / 审批 / 验收变更必须走既有正式业务流程；Agent Owner 只能授权自己的 Agent。
- 本阶段仍不做数据库迁移、历史数据兼容或利旧。
- 当前验证基准 HEAD：`2839c1742db12666f6319544f0a3f40b5e8c1e40`；本交接更新提交后，以新 HEAD 和新 CI 为准。


## 57. Task Collaboration Session 治理闭环强化（2026-11-24）

### 本轮实现
- Task 详情的 Task Collaboration 面板增加 Session 负责人操作入口：
  - OPEN：可暂停或关闭。
  - PAUSED：可恢复或关闭。
  - CLOSED：不显示恢复/关闭操作；关闭前有二次确认。
- 管理按钮仅在当前 Member ID 与 Session `responsible_member_id` 一致时显示。后端仍以现有 Session 负责人/Task Policy 责任人授权校验为准，前端隐藏按钮不作为安全边界。
- 新增 REST 生命周期边界测试，覆盖 PAUSED/CLOSED 下的历史读取、Agent/Member 消息发送拒绝、Proposal 创建拒绝、Grant 创建拒绝、CLOSED 不可重开。
- 新增权限负向验证：非负责人不能管理 Session；非 Agent Owner 不能决策其 Agent 的 Proposal。
- 扩展 Playwright 浏览器 E2E：从 Task 详情实际执行暂停、恢复、关闭；验证页面状态和按钮变化；关闭后验证 Agent 历史读取成功、Agent 消息/Proposal 与 Member 新 Grant 被拒绝。
- 保持 Session 与 Task Execution Grant 生命周期独立；关闭 Session 不撤销 Agent 的 Task Execution Grant。

### 提交与 CI 验证
- Session 控制 UI：`9559a5a1d16a00bbf87f235f8e79afb3850f0938`。
- REST 生命周期/权限边界测试：`c6ea426b46623cde48029831115153d6fec41ea2`。
- 浏览器生命周期测试：`93a84f7f871446c7eb014fee6f1481a7559b2bd3`。
- 修正浏览器测试向关闭后授权检查传递 Agent ID：`dc533f2206e9d708a623b6bfd1349b80862f4771`。
- CI run `45358239090`，HEAD `dc533f2206e9d708a623b6bfd1349b80862f4771`：整体 SUCCESS，七个 Job 全部 SUCCESS（Python 3.11/3.12/3.13、migrations/RLS、container-build、production-compose、Browser E2E）。
- Browser E2E 实际执行 `pytest -q tests/test_agent_management_e2e.py tests/test_task_collaboration_ui_e2e.py`，结果 `3 passed in 10.10s`；Chromium 已实际安装并运行，不是跳过测试。
- Python 三个版本、数据库/RLS、容器构建和生产 Compose 均通过。

### 规则与范围
- Session CLOSED 后保留历史记录；不允许重开，不接受新消息、Proposal 或新 CollaborationGrant。
- PAUSED 与 CLOSED 都保留历史读取能力；PAUSED 可恢复，CLOSED 不可恢复。
- Agent Owner 只授权自己的 Agent；Task Session 负责人负责 Session 管理；Proposal 由对应 Agent Owner 决策。
- Session 关闭不自动撤销独立的 Task Execution Grant。
- 本轮不修改数据库 Schema 或迁移，不涉及历史数据迁移、回填、兼容或利旧；DAEP 仍不托管 Agent Runtime。

### 下一步
- 进入 **Task Collaboration 授权与治理可观测性**：在 Task 协作空间增加 CollaborationGrant 状态/Scope/有效期/撤销信息展示，以及仅 Agent Owner 可执行的授权撤销入口；补齐撤销后 Agent 消息、Proposal、历史读取权限即时失效的 API 与浏览器回归。
- 继续保持 Agent 提案、人类治理决策和正式 Task/Work Package/审批/验收操作分离。
- 当前功能验证基准 HEAD：`dc533f2206e9d708a623b6bfd1349b80862f4771`；本交接更新提交后，以新 HEAD 和新 CI 为准。


## 58. Task CollaborationGrant 可观测性与 Owner 撤销闭环（2026-11-24）

- 本轮目标：在 Task 协作工作区中呈现 CollaborationGrant 的授权状态和权限范围，并将 Agent Owner 撤销授权的服务端能力接入 UI；验证撤销后 Agent 的协作读取和写入立即失效。
- UI（`web/index.html`）：
  - Task 协作空间新增“Agent 授权”面板，列出本 Task 的 Grant 历史。
  - 展示 Agent、有效状态（待 Agent 接受/已生效/已撤销/已过期）、授权人、创建时间、到期时间、Scope、资源范围和撤销时间。
  - 只有当前登录用户等于 Grant 的 `owner_member_id`，且 Grant 状态为 AUTHORIZED/ACCEPTED 时，才显示“撤销我的授权”。
  - 撤销前确认并要求输入原因；调用 `DELETE /api/v1/collaboration-grants/{grant_id}` 后重新加载 Task 工作区。
  - 明确提示 Session 关闭与 Grant 撤销是独立生命周期；Session CLOSED 不会自动撤销 Grant。
- REST/API：
  - 复用既有 Grant list 与 revoke endpoint，不增加重复 API。
  - 新增 `test_collaboration_grant_owner_revoke_invalidates_all_agent_access_and_is_audited`：
    - 验证授权列表返回状态、Owner、Scopes、Resource Scope 和 expires_at。
    - 非 Agent Owner 撤销返回 403；授权该 Agent 的 Owner 撤销成功。
    - 撤销后 Agent 历史读取、消息发送、Proposal 创建均返回 403；重复撤销返回 409。
    - 验证 revoked_at、revoked_by_member_id 和 `agent.collaboration_grant.revoked` 审计事件及原因。
- Browser E2E（`tests/test_task_collaboration_ui_e2e.py`）：
  - 登录后打开 Task 工作区，验证授权面板、已生效状态和 Scope 文案。
  - Session CLOSED 后仍能看到独立的活动 Grant，并由 Owner 在工作区撤销。
  - 撤销后 Agent 的历史读取、消息发送、Proposal 创建均返回 403。
  - CI Browser E2E job 实际运行 Chromium，结果 `3 passed in 7.87s`（包含 Agent 管理和 Task 协作浏览器测试）。
- 代码提交：
  - `a309332358dcc560ee3a06232092fbcc1c8ca580` — Task 工作区展示 Grant 并提供 Owner-only revoke 操作。
  - `cb47cd33eb8b9d14dee320b330bf336252732b69` — 增加 Grant Owner 撤销 API 生命周期和审计测试。
  - `de0662e11a0e2ec4f93909556b465a344d8683c6` — 增加浏览器授权展示/撤销回归。
  - `caa9c32e3241669d2f8b2c03297b8e48266d31b5` — 修正 Browser E2E confirm/prompt 对话框处理。
  - `1401a03c43bbdfb3d47a496bbf8b75c1fa48dbdc` — 修正 Scope 集合断言，不依赖数据库序列化顺序。
  - `12f8237c9e602c6bf472d51c8560f1606adf74df` — 修正 Starlette TestClient 的 DELETE JSON body 调用。
- 验证：
  - CI run `45360811722` 对应代码 HEAD `12f8237c9e602c6bf472d51c8560f1606adf74df` 已完成，结论 SUCCESS。
  - Python 3.11/3.12/3.13 全部通过；Dashboard JavaScript 检查通过；PostgreSQL migration/RLS、container build、production compose 全部通过。
  - Browser E2E 使用 Chromium 实际执行，`3 passed in 7.87s`，未跳过。
  - 首轮 CI 曾暴露测试层的 Scope 顺序断言和 DELETE JSON 调用方式问题，均已修复；最终成功 CI 覆盖修复后的 HEAD。
- 当前分支：`release/1.0.0-rc9`。
- 下一步唯一任务：继续补齐 Task 协作授权的管理体验与安全回归，重点核查 Grant 到期后的状态刷新/权限失效、Agent Owner 视角的授权收件箱，以及授权列表在非负责人 Task Member 下的可见性边界；不要改变“Owner 授权自己的 Agent、Task 负责人不代替其他 Owner 授权”的领域规则。


## 59. CollaborationGrant 到期、Owner 收件箱与可见性边界（2026-11-24）

- 本轮目标：补齐授权到期状态的持久化识别、Agent Owner 的集中授权视图，以及 Task 授权列表的最小可见范围。
- 到期处理（`app/agent_collaboration_api.py`）：
  - Task Grant 列表和 Member Owner 收件箱在读取时识别 `expires_at <= now` 的 AUTHORIZED/ACCEPTED Grant。
  - 将数据库状态实际更新为 `EXPIRED`，不只在响应中临时显示有效状态。
  - 写入 `agent.collaboration_grant.expired` 审计事件，记录 Grant、Agent 和触发来源。
  - 已有 Agent Grant 鉴权仍独立校验有效期；过期不会继续允许 Agent 访问。
- 新增 Member Owner 授权收件箱：
  - `GET /api/v1/members/me/collaboration-grants`，只允许 Member Token。
  - 仅返回当前 Member 本人拥有、本人授权且 Agent 当前仍归属该 Member 的 Grant。
  - 返回 Agent/Task/Project/Session、Scopes、Resource Scope、有效状态、到期与撤销信息。
  - Agent 页面新增“协作授权收件箱”，Owner 可以集中查看并撤销自己的有效授权；不显示或操作其他 Member 的 Agent。
  - 原有 `GET /api/v1/agents/me/collaboration-grants` 继续保留为 Agent Token 视角，不混用两种身份。
- Task Grant 列表可见性：
  - Task 负责人（Session responsible Member）可以查看 Task 范围全部 Grant。
  - 其他有项目成员资格的 Member 只能查看自己授权的 Grant，响应标记 `OWNER_ONLY`。
  - 非项目成员且非 Task assignee 的 Member 无法通过该接口探测 Task 授权信息。
  - 读取列表不再调用 Session 初始化/接管逻辑，不创建 Session，也不改变 Session responsible Member。
  - Grant 列表读取不改变 Agent Owner 主动授权、负责人管理 Session 的既定领域规则。
- UI/测试：
  - `web/agents.js` 新增 Owner 授权收件箱、状态/Scope/资源范围展示和 Owner-only revoke。
  - `tests/test_api.py` 新增 `test_collaboration_grant_expiry_materializes_and_owner_inbox_isolated_from_task_roster`，覆盖到期落库、审计、Owner Inbox 隔离、Task 负责人和普通项目成员可见性差异。
  - `tests/test_agent_management_ui.py` 增加收件箱前端契约。
  - Browser E2E 覆盖 Agent 页面新增入口和 Task 协作工作区中的 Owner 授权收件箱。
  - 修正原 Agent 管理 E2E 对页面头部按钮的唯一性假设，明确定位“创建 Agent”按钮。
- 主要代码提交：
  - `ef2e27b536e44f675a10ca1d2be94aabcff00baf` — Member Owner 授权收件箱 API、到期状态落库与审计、Task Grant 可见性规则。
  - `baf6cc12324175e0b08468c203655839d067839f` — Agent 页面 Owner 授权收件箱。
  - `15b5cebe66d240b61b4e50ea82418917bdc5df88` — 导出收件箱 UI 操作。
  - `b60cec188c6bbf5b6a729db81cce4f0285155ca5` — Grant 到期、Owner Inbox 与可见性 API 测试。
  - `998b23fcfe2515d7c4c0a70679289104c621a5be` — 前端契约测试。
  - `0383f458977259440ba9dafdef16e2eace915724` — Browser E2E 授权收件箱覆盖。
  - `e594706c0b8f1f6fbdc0967fd624dbbcee68b61f` — 允许项目成员读取自己授权的 Grant，其他 Owner 授权仍隔离。
  - `5396c5c0cf930f9014a0594a4648678933ee1c97` — 修正过期测试数据的时间约束。
  - `0adadb2ed9283b7e76b9b4f5bdfadd65df7d70f8` — 修正收件箱 E2E 的 modal body 断言。
  - `6ac4d1602d906fe051a1c0713897da9c7c885ad7` — 修正 Agent 管理 E2E 的创建按钮断言。
- 最终代码 CI：
  - Run `45363910701`，HEAD `6ac4d1602d906fe051a1c0713897da9c7c885ad7`，结论 SUCCESS。
  - Python 3.11/3.12/3.13 均为 `247 passed, 2 skipped`。
  - Browser E2E 使用 Chromium 实际运行，`3 passed in 8.13s`。
  - PostgreSQL Migration/RLS、Container Build、Production Compose 全部 SUCCESS。
- 当前分支：`release/1.0.0-rc9`。
- 后续建议：补齐 Grant 的主动续期/重新授权体验，以及跨 Task 授权审计查询；不要让 Task 负责人代替 Agent Owner 续期或重新授权。
