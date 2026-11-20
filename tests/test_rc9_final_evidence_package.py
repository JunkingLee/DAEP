from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_rc9_final_evidence_package_requires_real_evidence():
    doc = (ROOT / "docs" / "RC9_FINAL_EVIDENCE_PACKAGE.md").read_text()
    assert "NOT EXECUTED" in doc
    assert "不得 GA" in doc
    assert "没有真实环境证据时，任何勾选 PASS 都视为无效" in doc
    assert "Real Browser Acceptance" in doc
    assert "Production Backup/Restore" in doc
    assert "Dual-Agent Interoperability" in doc

def test_rc9_evidence_preflight_is_structural_only():
    script = (ROOT / "scripts" / "rc9_evidence_preflight.sh").read_text()
    assert "Structure check only" in script
    assert "never marks real-world gates as PASS" in script
    assert "RC9_FINAL_EVIDENCE_PACKAGE.md" in script
    assert "RC9_BROWSER_ACCEPTANCE_RUNBOOK.md" in script
    assert "RC9_PRODUCTION_BACKUP_RESTORE_DRILL.md" in script
    assert "RC9_AGENT_INTEROPERABILITY_DRILL.md" in script
