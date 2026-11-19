# RC26 Role Workbench

## Scope

The DAEP web shell now exposes a project-scoped **My Workbench** entry.

The workbench is presentation-layer aggregation over existing project APIs; it does not create a new authorization boundary.

## Role views

- **Developer / member**: own tasks, active work, own Work Packages, risks and collaboration entry points.
- **Tester**: own tasks, validation/review queue and acceptance-oriented entry points.
- **Reviewer**: review-oriented queue using the same project-scoped task context.
- **Project Owner / Manager**: project task distribution, exception work packages, pending reviews and pending delegations.
- **Product / Architect**: own-work view with the same project-scoped task and Work Package aggregation.
- **Platform Admin**: retains platform-wide navigation and can inspect project workbench data subject to backend authorization.

## Design constraints

1. Project membership and project role remain the source of authorization.
2. UI role navigation only controls presentation; it is not a security boundary.
3. Agent runtime remains local to each member computer. The workbench only shows DAEP's registered Agent and collaboration state.
4. Workbench data is derived from existing task, work-health and coordination APIs to avoid duplicating workflow state.

## Access

The workbench is available from the left navigation after authentication and project selection. It follows the selected project's role/work-function context, so one user can see different workbench views when switching projects.


## Tester execution flow

Tester / reviewer workbench now exposes task-level test actions using existing governed APIs:
- update progress to 50% for in-progress validation;
- update progress to 100% to enter REVIEW;
- mark a task BLOCKED with a reason when validation is blocked;
- submit test-report / acceptance evidence through the durable artifact API;
- open the requirement acceptance report from the workbench when a requirement reference is available.

The UI does not introduce a separate defect entity. Blocking remains task governance, while artifacts provide durable verification evidence and the existing Review / Requirement Acceptance APIs remain the approval boundary.


## Manager / Owner Governance Workbench

项目管理员与系统管理员现在拥有独立的“项目治理台”，直接消费已有治理 API，不新增重复业务模型：

- 项目治理快照：任务总数、完成率、待审核、Work Package 风险、责任分布、完成门禁、消息交付事件。
- 项目决策登记：标题、决策内容、依据、责任人、截止时间、关联任务；沿用既有 `POST /api/v1/projects/{project_id}/decisions`。
- 项目收口判断：仅展示治理条件，不自动关闭项目；要求完成门禁满足、无活动风险工作包、无待审核任务。
- 异常协调、健康扫描、停滞扫描均复用现有治理接口。
- 多项目切换后治理台随项目角色上下文刷新。

UI 仍然只是操作入口，后端项目角色权限与治理规则继续作为唯一安全边界。
