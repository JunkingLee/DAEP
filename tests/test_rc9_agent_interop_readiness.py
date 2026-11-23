from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_rc9_agent_interop_drill_exists_and_preserves_runtime_boundary():
    doc = (ROOT / "docs" / "RC9_AGENT_INTEROPERABILITY_DRILL.md").read_text()
    assert "双 Agent 实机互操作" in doc
    assert "DAEP 不托管、不启动、不强制唤醒成员本地 Agent Runtime" in doc
    assert "离线恢复" in doc
    assert "Agent Interoperability Ready = PASS" in doc

def test_rc9_agent_interop_preflight_is_non_destructive():
    script = (ROOT / "scripts" / "agent_interop_preflight.sh").read_text()
    assert "DAEP_MEMBER_TOKEN_A" in script
    assert "DAEP_MEMBER_TOKEN_B" in script
    assert "DAEP_MEMBER_TOKEN_A" in script and "DAEP_MEMBER_TOKEN_B" in script
    assert "/readyz" in script
    assert "from daep_mcp.server import mcp" in script
    assert "wake" not in script.lower()
    assert "start Agent Runtime" not in script
    assert "stop Agent Runtime" not in script