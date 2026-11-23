from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_rc26_agent_topology_uses_project_scoped_registry_and_work_health():
    html = (ROOT / "web" / "index.html").read_text()
    assert 'id="agentTopologyPanel"' in html
    assert 'id="agentTopology"' in html
    assert "function renderAgentTopology()" in html
    assert "'/api/v1/projects/'+selectedProject+'/agents'" in html
    assert "projectAgents=agentData.items||[]" in html
    assert "function agentPresence(status)" in html
    assert "AVAILABLE:{label:'在线 · 空闲'" in html
    assert "BUSY:{label:'执行中'" in html
    assert "OFFLINE:{label:'离线'" in html
    assert "projectHealthItems=h.items||[]" in html
    assert "DAEP 不托管或唤醒 Agent Runtime" in html


def test_rc26_topology_maps_agent_identity_to_work_packages():
    html = (ROOT / "web" / "index.html").read_text()
    assert "w.agent_name===a.agent_name&&w.assignee_member_id===a.member_id" in html
    assert "const orphan=items.filter" in html
    assert "最近心跳" in html


def test_rc26_project_delegation_board_uses_project_scoped_history():
    html = (ROOT / "web" / "index.html").read_text()
    assert 'id="delegationPanel"' in html
    assert 'id="delegationBoard"' in html
    assert "function renderDelegations()" in html
    assert "'/api/v1/projects/'+selectedProject+'/delegations?limit=200'" in html
    assert "projectDelegations=d.items||[]" in html
    assert "PENDING" in html and "ACCEPTED" in html and "REJECTED" in html


def test_rc26_stage2_agent_matching_panel_is_explainable_and_manual():
    html = (ROOT / "web" / "index.html").read_text()
    assert 'id="agentRequiredCapabilities"' in html
    assert 'id="agentRequiredProtocol"' in html
    assert "async function recommendProjectAgents()" in html
    assert "/agent-matches?" in html
    assert "匹配" in html and "缺失：" in html
    assert "不会分配任务或唤醒 Agent" in html


def test_rc26_stage3_task_detail_surfaces_delegation_dependency_and_delivery_trace():
    html = (ROOT / "web" / "index.html").read_text()
    assert "跨成员委派" in html
    assert "跨成员工作包" in html
    assert "依赖关系" in html
    assert "协作事件时间线" in html
    assert "e.actor_name" in html
    assert "e.acked_at" in html


def test_rc26_stage4_task_detail_has_manual_work_package_creation_review_and_candidate_selection():
    html = (ROOT / "web" / "index.html").read_text()
    assert "创建工作包" in html
    assert "createWorkPackageFromDetail" in html
    assert "/api/v1/tasks/'+parentId+'/work-packages" in html
    assert "chooseAgentCandidate" in html
    assert "用于当前工作包" in html
    assert "reviewWorkPackage" in html
    assert "/api/v1/work-packages/'+packageId+'/review" in html
    assert "退回修改" in html


def test_rc26_stage5_coordination_workbench_exposes_exception_triage_and_reassignment():
    html = (ROOT / "web" / "index.html").read_text()
    assert 'id="coordinationPanel"' in html
    assert "/api/v1/projects/'+selectedProject+'/coordination" in html
    assert "renderCoordinationCenter" in html
    assert "未认领任务" in html
    assert "待审核任务" in html
    assert "待响应委派" in html
    assert "scanStalledWorkPackages" in html
    assert "/work-packages/scan-stalled" in html
    assert "reassignCoordinationPackage" in html
    assert "/api/v1/work-packages/'+packageId+'/reassign" in html



def test_requirement_creation_captures_acceptance_criteria():
    html = (ROOT / "web" / "index.html").read_text()
    assert 'id="reqCriteria"' in html
    assert "验收标准（每行一条）" in html
    assert "acceptance_criteria" in html
    assert "map(x=>x.trim()).filter(Boolean)" in html



def test_task_detail_renders_readable_collaboration_timeline():
    html = (ROOT / "web" / "index.html").read_text()
    assert "function renderWorkTimeline(items)" in html
    assert "操作人：" in html
    assert "消息状态：" in html
    assert "已确认：" in html
    assert "查看交付物" in html
    assert "Commit：" in html
    assert "timeline-item" in html
    assert "timeline-head" in html


def test_task_detail_actions_follow_project_roles_and_human_review_boundary():
    html = (ROOT / "web" / "index.html").read_text()
    assert "function canReviewWork()" in html
    assert "function canOperateTask(t)" in html
    assert "canReview&&t.status==='REVIEW'" in html
    assert "只有项目管理员或审核人员可以审核任务" in html
    assert "只有项目管理员可以创建工作包" in html
    assert "t.status!=='REVIEW'" in html
    assert "s.key!=='DONE'" in html
    assert "任务完成必须经过人工审核" in html
    assert "selectedWorkFunction==='tester'&&canOperate" in html



def test_work_package_creation_requires_explicit_registered_agent_selection():
    html = (ROOT / "web" / "index.html").read_text()
    assert "function submitWorkPackageFromDetail(parentId)" in html
    assert 'id="wpAgent"' in html
    assert "assignee_member_id:selected.member_id" in html
    assert "agent_name:selected.agent_name" in html
    assert "请选择在线 Agent" in html


def test_task_timeline_distinguishes_agent_actor_identity():
    html = (ROOT / "web" / "index.html").read_text()
    assert "payload.actor_type==='AGENT'" in html
    assert "'Agent · '+(payload.agent_id||'未知身份')" in html



def test_product_workbench_exposes_only_supported_requirement_and_task_creation():
    html = (ROOT / "web" / "index.html").read_text()
    assert "function canCreateWorkItems()" in html
    assert "return isManager()||selectedWorkFunction==='product'" in html
    assert "toggle('role-hidden',!canCreateWorkItems())" in html
    assert "toggle('role-hidden',closed||!canCreateWorkItems())" in html
    assert "function openCreateRequirement(){if(!canCreateWorkItems())" in html
    assert "function openCreateTask(){if(!canCreateWorkItems())" in html
