"""Real-browser acceptance test for the user-owned Agent management workflow.

Run with:
    DAEP_RUN_BROWSER_E2E=1 pytest -q tests/test_agent_management_e2e.py

The test starts an isolated SQLite-backed DAEP server and never touches a
shared or production database.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

if os.getenv("DAEP_RUN_BROWSER_E2E") != "1":
    pytest.skip("set DAEP_RUN_BROWSER_E2E=1 to run browser acceptance tests", allow_module_level=True)

playwright_api = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "browser-e2e-admin-password-2026"


@pytest.fixture(scope="session")
def daep_server(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("daep-browser-e2e")
    db_path = data_dir / "daep-e2e.sqlite3"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.update(
        {
            "DAEP_DB_PATH": str(db_path),
            "DAEP_ADMIN_TOKEN": "browser-e2e-admin-token-" + ("x" * 40),
            "DAEP_WORKER_TOKEN": "browser-e2e-worker-token-" + ("y" * 40),
            "DAEP_BOOTSTRAP_ADMIN_PASSWORD": ADMIN_PASSWORD,
            "PYTHONUNBUFFERED": "1",
        }
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"DAEP test server exited with code {process.returncode}")
            try:
                with urllib.request.urlopen(base_url + "/readyz", timeout=2) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError, OSError):
                time.sleep(0.4)
        else:
            raise RuntimeError("DAEP test server did not become ready within 60 seconds")
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_agent_management_full_browser_lifecycle(daep_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        try:
            page.goto(daep_server, wait_until="domcontentloaded")
            expect(page.get_by_test_id("login-screen")).to_be_visible()
            page.get_by_test_id("username-input").fill(ADMIN_USERNAME)
            page.get_by_test_id("password-input").fill(ADMIN_PASSWORD)
            page.get_by_test_id("login-submit").click()
            expect(page.get_by_test_id("app-shell")).to_be_visible(timeout=20000)

            # Seed one project through the authenticated test session. The
            # Agent create/edit/token/binding flow itself is driven by clicks.
            project_result = page.evaluate(
                """async () => {
                    const token = localStorage.getItem('daep.web.access_token');
                    const response = await fetch('/api/v1/projects', {
                        method: 'POST',
                        headers: {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            name: 'Browser E2E Agent Project',
                            description: 'Isolated project for browser acceptance',
                            tenant_id: 'tenant-default'
                        })
                    });
                    return {status: response.status, body: await response.json()};
                }"""
            )
            assert project_result["status"] == 200, project_result
            project_id = project_result["body"]["id"]

            # Reload to let the real session restoration and project bootstrap
            # populate the browser-side project collection.
            page.reload(wait_until="domcontentloaded")
            expect(page.get_by_test_id("app-shell")).to_be_visible(timeout=20000)
            # app-shell becomes visible before async project bootstrap completes;
            # wait for the initial overview navigation to settle before switching.
            expect(page.locator("#overview.page.active")).to_be_visible(timeout=20000)
            expect(page.locator("#projectSelect option").filter(has_text="Browser E2E Agent Project")).to_have_count(1)

            page.locator('#nav button[data-page="agents"]').click()
            expect(page.locator("#agents.page.active")).to_be_visible()
            expect(page.locator("#agents .page-head button")).to_be_visible()
            expect(page.locator("#agentGrid")).to_contain_text("还没有 Agent")

            page.locator("#agents .page-head button").click()
            page.locator("#agentName").fill("Browser E2E Agent")
            page.locator("#agentDesc").fill("Agent identity lifecycle acceptance")
            page.get_by_role("button", name="创建并获取 Token").click()
            expect(page.locator("#modal")).to_be_visible()
            expect(page.locator("#modalBody")).to_contain_text("MCP Token")
            first_token = page.evaluate("window.__daepLastAgentToken")
            assert first_token and first_token.startswith("daep_at_")
            expect(page.locator(".token-box")).to_contain_text(first_token)
            page.locator("#modal .modal-head button").click()

            agent_card = page.locator("#agentGrid .agent-card").filter(has_text="Browser E2E Agent")
            expect(agent_card).to_be_visible()
            agent_id = agent_card.locator(".agent-id").inner_text()

            # Detail and update.
            agent_card.get_by_role("button", name="管理").click()
            expect(page.locator("#modal")).to_be_visible()
            page.locator("#editAgentName").fill("Browser E2E Agent Updated")
            page.locator("#editAgentDesc").fill("Updated by real browser")
            page.locator("#editAgentStatus").select_option("ACTIVE")
            page.get_by_role("button", name="保存").click()
            expect(page.get_by_test_id("toast")).to_contain_text("Agent 已更新")
            agent_card = page.locator("#agentGrid .agent-card").filter(has_text="Browser E2E Agent Updated")
            expect(agent_card).to_be_visible()

            # Rotate the token; the replacement must differ from the initial
            # one and is displayed only in the rotation response modal.
            agent_card.get_by_role("button", name="重新生成 Token").click()
            expect(page.locator("#modal")).to_be_visible()
            rotated_token = page.evaluate("window.__daepLastAgentToken")
            assert rotated_token and rotated_token.startswith("daep_at_")
            assert rotated_token != first_token
            page.locator("#modal .modal-head button").click()

            # Bind a project through the management UI.
            agent_card.get_by_role("button", name="绑定项目").click()
            expect(page.locator("#agentProject")).to_be_visible()
            page.locator("#agentProject").select_option(project_id)
            page.locator("#agentFunction").select_option("developer")
            page.get_by_role("button", name="确认绑定").click()
            expect(page.get_by_test_id("toast")).to_contain_text("Agent 已绑定到项目")
            expect(agent_card).to_contain_text("Browser E2E Agent Project")

            # Unbind through the detail UI and confirm the destructive action.
            agent_card.get_by_role("button", name="管理").click()
            expect(page.locator("#modalBody")).to_contain_text("Browser E2E Agent Project")
            page.once("dialog", lambda dialog: dialog.accept())
            page.get_by_role("button", name="解除绑定").click()
            expect(page.get_by_test_id("toast")).to_contain_text("项目绑定已解除")
            expect(agent_card).to_contain_text("尚未绑定项目")

            # Revoke the currently active rotated token and verify history.
            agent_card.get_by_role("button", name="管理").click()
            page.get_by_role("button", name="撤销当前 Token").click()
            expect(page.get_by_test_id("toast")).to_contain_text("Token 已撤销")
            agent_card.get_by_role("button", name="管理").click()
            expect(page.locator("#modalBody")).to_contain_text("REVOKED")

            # The detail response must never expose either raw token again.
            detail = page.evaluate(
                """async (agentId) => {
                    const token = localStorage.getItem('daep.web.access_token');
                    const response = await fetch('/api/v1/agents/' + encodeURIComponent(agentId), {
                        headers: {'Authorization': 'Bearer ' + token}
                    });
                    return {status: response.status, body: await response.json()};
                }""",
                agent_id,
            )
            assert detail["status"] == 200
            serialized_detail = str(detail["body"])
            assert first_token not in serialized_detail
            assert rotated_token not in serialized_detail
        finally:
            browser.close()
