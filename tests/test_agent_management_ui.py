from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
AGENTS = (ROOT / "web" / "agents.js").read_text(encoding="utf-8")


def test_agent_management_script_is_loaded_and_registers_navigation():
    assert '<script src="/static/agents.js"></script>' in HTML
    assert "data-page=\"agents\"" in AGENTS
    assert "id=\"agents\"" in AGENTS
    assert "window.go=wrapped" in AGENTS
    assert "if(page==='agents')loadAgents()" in AGENTS


def test_agent_management_loads_owned_agents_and_renders_empty_and_error_states():
    assert "api('/api/v1/agents')" in AGENTS
    assert "还没有 Agent" in AGENTS
    assert "加载失败：" in AGENTS
    assert "openAgentDetail" in AGENTS
    assert "rotateAgentToken" in AGENTS
    assert "bindAgentProject" in AGENTS


def test_agent_creation_shows_one_time_token_and_mcp_configuration():
    assert "api('/api/v1/agents',{method:'POST'" in AGENTS
    assert "showAgentToken(d,'Agent 创建成功')" in AGENTS
    assert "window.__daepLastAgentToken=d.token" in AGENTS
    assert "window.__daepLastAgentConfig=cfg" in AGENTS
    assert "Token 只显示这一次" in AGENTS
    assert "复制 Token" in AGENTS
    assert "复制配置" in AGENTS


def test_agent_management_actions_are_wired_to_api_endpoints():
    contracts = [
        "api('/api/v1/agents/'+encodeURIComponent(id))",
        "method:'PATCH'",
        "/tokens/rotate",
        "/tokens/revoke",
        "method:'POST'",
        "method:'DELETE'",
        "unbindAgentProject",
        "saveAgentProject",
    ]
    for contract in contracts:
        assert contract in AGENTS, f"missing Agent management action: {contract}"

    assert "重新生成 Token 会立即使当前 Token 失效" in AGENTS
    assert "撤销 Token 后，使用该凭证的 MCP 连接将立即失效" in AGENTS
    assert "停用 Agent 将撤销其当前 Token 和有效 Task Execution Grant" in AGENTS


def test_agent_project_binding_is_restricted_to_project_managers_in_ui():
    assert "if(!isManager()){toast('只有当前项目管理员可以绑定 Agent');return}" in AGENTS
    assert "if(!isManager()||!confirm(" in AGENTS

    
def test_agent_detail_authorization_state_ui_contract():
    source=Path('web/agents.js').read_text()
    assert 'Task Execution Grants' in source
    assert 'Collaboration Grants' in source
    assert 'Credential validity' in source
    assert 'resource_scope_json' in source
    assert 'Presence' in source
