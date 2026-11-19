from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_rc26_agent_topology_uses_project_scoped_registry_and_work_health():
    html = (ROOT / "web" / "index.html").read_text()
    assert 'id="agentTopologyPanel"' in html
    assert 'id="agentTopology"' in html
    assert "function renderAgentTopology()" in html
    assert "'/api/v1/projects/'+selectedProject+'/agents'" in html
    assert "projectAgents=a.items||[]" in html
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
    assert "依赖边" in html
    assert "协作事件时间线" in html
    assert "e.actor_name" in html
    assert "e.acked_at" in html
