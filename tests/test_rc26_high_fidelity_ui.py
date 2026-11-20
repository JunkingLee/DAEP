import re
from html.parser import HTMLParser
from pathlib import Path


HTML = Path("web/index.html").read_text(encoding="utf-8")


class _IdParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key == "id" and value:
                self.ids.append(value)


def test_rc26_high_fidelity_shell_has_required_information_architecture():
    required = [
        "DAEP · Build Together · Deliver Better",
        'id="portfolio"',
        'id="overview"',
        'id="workbench"',
        'id="work"',
        'id="collaboration"',
        'id="governance"',
        'id="dependencies"',
        'id="exceptions"',
        'id="packages"',
        'id="inbox"',
        'id="myWorkbenchPanel"',
        'id="managerWorkbenchPanel"',
        'id="workflowDesignerPanel"',
        'id="agentTopologyPanel"',
        'id="delegationPanel"',
        'id="coordinationPanel"',
        'id="workPackageBoard"',
        'id="dependencyView"',
    ]
    for marker in required:
        assert marker in HTML, f"missing high-fidelity UI marker: {marker}"


def test_rc26_high_fidelity_shell_has_role_workbenches_and_governance_controls():
    for marker in [
        "系统管理员",
        "项目管理员",
        "产品工作台",
        "开发工作台",
        "测试 / 验收工作台",
        "项目审核人员",
        "Workflow",
        "Gate",
        "项目收口",
        "需求验收",
        "TEST_EVIDENCE",
    ]:
        assert marker in HTML, f"missing role/governance UI contract: {marker}"


def test_rc26_high_fidelity_shell_has_agent_collaboration_surface():
    for marker in [
        "Agent 协作",
        "能力匹配",
        "agentRequiredCapabilities",
        "agentRequiredProtocol",
        "/agent-matches?",
        "跨成员委派",
        "跨成员工作包",
        "协作事件时间线",
        "DAEP 不托管或唤醒 Agent Runtime",
        "/delegations?limit=200",
        "/work-packages",
        "/work-timeline",
    ]:
        assert marker in HTML, f"missing collaboration UI contract: {marker}"


def test_rc26_high_fidelity_shell_has_responsive_visual_system():
    for marker in [
        "@media",
        "--navy:",
        "--blue:",
        "--bg:",
        "grid-template-columns",
        "border-radius:",
        "box-shadow:",
    ]:
        assert marker in HTML, f"missing visual-system marker: {marker}"


def test_rc26_high_fidelity_shell_has_no_legacy_ui_markers():
    forbidden = [
        "Engineering Control Plane",
        "ROLE-AWARE WORKSPACE",
        "daep-sidebar",
        "RC26 UI Architecture",
    ]
    for marker in forbidden:
        assert marker not in HTML, f"legacy UI residue remains: {marker}"


def test_rc26_high_fidelity_shell_has_unique_dom_ids():
    parser = _IdParser()
    parser.feed(HTML)
    duplicates = sorted({x for x in parser.ids if parser.ids.count(x) > 1})
    assert not duplicates, f"duplicate DOM ids remain: {duplicates}"


def test_rc26_high_fidelity_shell_has_role_visibility_and_core_api_wiring():
    for marker in [
        "function applyRolePanels()",
        "role-hidden",
        "/api/v1/projects/'+selectedProject+'/workflow",
        "/api/v1/projects/'+selectedProject+'/gates/",
        "/api/v1/projects/'+selectedProject+'/governance",
        "/api/v1/projects/'+selectedProject+'/decisions",
        "/api/v1/requirements/'+id+'/acceptance",
        "/api/v1/tasks/'+id+'/workflow-transition",
        "/api/v1/tasks/'+id+'/progress",
        "/api/v1/tasks/'+id+'/blocked",
        "/api/v1/tasks/'+id+'/artifacts",
    ]:
        assert marker in HTML, f"missing UI/API wiring: {marker}"


def test_rc26_high_fidelity_shell_has_no_accidental_escaped_script_tokens():
    assert "\\nfunction" not in HTML
    assert "\\\\'" not in HTML
    assert not re.search(r"<script[^>]*>[^<]*\\n", HTML)
