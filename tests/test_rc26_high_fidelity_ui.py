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
        'id="workbench"',
        'id="collaboration"',
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
        "f==='product'",
        "f==='tester'",
        "else cards=[",
        "项目审核人员",
        "Workflow",
        "Gate",
        "项目收口",
        "需求验收",
        "Gate 配置",
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
        "workCreateActions",
        "/api/v1/projects/'+selectedProject+'/workflow",
        "/api/v1/projects/'+selectedProject+'/gates/",
        "/api/v1/projects/'+selectedProject+'/governance",
        "/api/v1/projects/'+selectedProject+'/decisions",
        "/api/v1/requirements/'+id+'/acceptance",
        "/api/v1/tasks/'+tid+'/workflow-transition",
        "/api/v1/tasks/'+id+'/progress",
        "/api/v1/tasks/'+id+'/blocked",
        "/api/v1/tasks/'+id+'/artifacts",
    ]:
        assert marker in HTML, f"missing UI/API wiring: {marker}"


def test_rc26_high_fidelity_shell_has_no_accidental_escaped_script_tokens():
    assert "\\nfunction" not in HTML
    assert "\\\\'" not in HTML
    assert not re.search(r"<script[^>]*>[^<]*\\n", HTML)


def test_rc26_high_fidelity_shell_has_role_navigation_contracts_and_accessibility_hooks():
    assert "const visible={governance:manager||reviewer,exceptions:manager,packages:Boolean(me)}" in HTML
    assert "function setRoleTab(role)" in HTML
    assert 'aria-current="' in HTML
    assert 'role="dialog" aria-modal="true"' in HTML
    assert "first?.focus()" in HTML
    assert "async function saveProjectGate()" in HTML
    assert "async function saveProjectGate(){return}" not in HTML


def test_rc26_high_fidelity_shell_has_no_duplicate_function_definitions_for_critical_actions():
    for name in ["saveProjectGate", "renderRoleWorkbench", "loadCollaboration", "loadGovernance"]:
        assert len(re.findall(r"function\s+" + re.escape(name) + r"\s*\(", HTML)) == 1, name


def test_rc26_high_fidelity_shell_has_deterministic_browser_acceptance_selectors():
    for marker in [
        'data-testid="login-screen"',
        'data-testid="token-input"',
        'data-testid="login-submit"',
        'data-testid="app-shell"',
        'data-testid="project-switcher"',
        'data-testid="primary-nav"',
        'data-testid="current-role"',
        'data-testid="page-portfolio"',
        'data-testid="page-overview"',
        'data-testid="page-workbench"',
        'data-testid="page-work"',
        'data-testid="page-collaboration"',
        'data-testid="page-governance"',
        'data-testid="page-dependencies"',
        'data-testid="page-exceptions"',
        'data-testid="page-packages"',
        'data-testid="page-inbox"',
        'role="status" aria-live="polite"',
    ]:
        assert marker in HTML, f"missing deterministic browser acceptance hook: {marker}"
