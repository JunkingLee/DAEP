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
    assert "showRequirementAcceptance(t.requirement_id)" in html
    assert "查看验收报告" in html
