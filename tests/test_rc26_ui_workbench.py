from pathlib import Path

def test_rc26_role_workbench_ui_shell():
    html = Path("web/index.html").read_text(encoding="utf-8")
    assert 'id="myWorkbenchPanel"' in html
    assert 'id="myWorkbenchMetrics"' in html
    assert "function renderMyWorkbench()" in html
    assert "开发工作台" in html
    assert "测试 / 验收工作台" in html
    assert "项目管理工作台" in html
    assert "myWorkbenchPanel" in html.split("function roleNavTargets()", 1)[1]


def test_rc26_tester_workbench_links_requirement_acceptance_report():
    html = Path("web/index.html").read_text(encoding="utf-8")
    assert "showRequirementAcceptance" in html
    assert "查看验收报告" in html
    assert "查看验收报告" in html


def test_rc26_tester_workbench_exposes_test_execution_controls():
    html = Path("web/index.html").read_text(encoding="utf-8")
    assert "function testerSetProgress" in html
    assert "function testerBlockTask" in html
    assert "function testerAddArtifact" in html
    assert "测试操作" in html
    assert "添加验收证据" in html


def test_rc26_manager_workbench_governance_controls():
    html = Path("web/index.html").read_text(encoding="utf-8")
    assert 'id="managerWorkbenchPanel"' in html
    assert 'id="managerGovernanceMetrics"' in html
    assert 'function loadManagerGovernance()' in html
    assert 'function recordManagerDecision()' in html
    assert "完成门禁" in html
    assert "项目收口状态" in html
    assert "/governance" in html
    assert "/decisions?limit=100" in html
