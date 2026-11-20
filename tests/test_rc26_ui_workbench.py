from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")


def test_rc26_role_workbench_uses_final_high_fidelity_shell():
    assert 'id="workbench"' in HTML
    assert 'id="workbenchMetrics"' in HTML
    assert 'id="workbenchCards"' in HTML
    assert "function renderRoleWorkbench()" in HTML
    for role in ("项目管理员", "产品人员", "开发人员", "测试人员", "项目审核人员"):
        assert role in HTML
    assert "myWorkbenchPanel" not in HTML


def test_rc26_tester_workbench_links_requirement_acceptance_report():
    assert "showRequirementAcceptance" in HTML
    assert "查看验收报告" in HTML
    assert "/api/v1/requirements/'+id+'/acceptance" in HTML


def test_rc26_tester_workbench_exposes_test_execution_controls():
    for marker in (
        "function testerSetProgress",
        "function testerBlockTask",
        "function testerAddArtifact",
        "测试操作",
        "添加验收证据",
    ):
        assert marker in HTML


def test_rc26_manager_workbench_governance_controls():
    for marker in (
        "function loadManagerGovernance()",
        "function recordManagerDecision()",
        "完成门禁",
        "项目收口状态",
        "/api/v1/projects/'+selectedProject+'/governance",
        "/api/v1/projects/'+selectedProject+'/decisions",
    ):
        assert marker in HTML
    assert "managerWorkbenchPanel" not in HTML


def test_rc26_workflow_gate_designer_is_embedded_in_governance():
    for marker in (
        'id="governance"',
        'id="flow"',
        'id="gates"',
        "function loadWorkflowDesigner()",
        "function saveWorkflowDesigner()",
        "function saveProjectGate()",
        "/api/v1/projects/'+selectedProject+'/workflow",
        "/api/v1/projects/'+selectedProject+'/gates/",
        "系统强制",
    ):
        assert marker in HTML
    assert "workflowDesignerPanel" not in HTML
