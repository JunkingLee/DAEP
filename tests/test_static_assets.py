from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_dashboard_serves_agent_script_from_static_mount():
    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert '<script src="/static/agents.js"></script>' in dashboard.text

    script = client.get("/static/agents.js")
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"].lower()
    assert "function init()" in script.text


def test_static_mount_does_not_intercept_api_routes():
    response = client.get("/readyz")
    assert response.status_code == 200


def test_task_detail_exposes_collaboration_workspace_contract():
    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "Task 协作空间" in dashboard.text
    assert "decideTaskProposal" in dashboard.text
    assert "sendTaskCollaborationMessage" in dashboard.text
    assert "/collaboration-proposals/" in dashboard.text
    assert "/collaboration-messages" in dashboard.text


def test_member_inbox_exposes_unread_read_and_all_views_for_collaboration_notices():
    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert 'data-testid="inbox-pending"' in dashboard.text
    assert 'data-testid="inbox-acknowledged"' in dashboard.text
    assert 'data-testid="inbox-all"' in dashboard.text
    assert "inboxStatus='PENDING'" in dashboard.text
    assert "/api/v1/me/notifications?status=" in dashboard.text
    assert "标记已读" in dashboard.text
    assert "授权到期提醒" in dashboard.text


def test_readme_svg_assets_are_well_formed_xml():
    import xml.etree.ElementTree as ET

    root = Path(__file__).resolve().parents[1]
    svg_files = sorted((root / "docs" / "images").glob("*.svg"))
    assert svg_files, "README SVG assets directory must not be empty"
    for svg_file in svg_files:
        parsed = ET.parse(svg_file)
        assert parsed.getroot().tag == "{http://www.w3.org/2000/svg}svg", svg_file.name


def test_readme_svg_references_resolve_to_existing_assets():
    import re

    root = Path(__file__).resolve().parents[1]
    readmes = (root / "README.md", root / "README.en.md", root / "README.zh-CN.md")
    for readme in readmes:
        content = readme.read_text(encoding="utf-8")
        references = re.findall(r"!\[[^\]]*\]\(([^)]+\.svg)\)", content)
        assert references, f"{readme.name} should include product SVG diagrams"
        for reference in references:
            assert (root / reference).is_file(), f"{readme.name} references missing asset: {reference}"


def test_chinese_readme_uses_localized_diagrams():
    import re

    root = Path(__file__).resolve().parents[1]
    content = (root / "README.zh-CN.md").read_text(encoding="utf-8")
    references = re.findall(r"!\[[^\]]*\]\(([^)]+\.svg)\)", content)
    assert references, "README.zh-CN.md should include product SVG diagrams"
    assert all("-zh-CN.svg" in reference for reference in references), references
