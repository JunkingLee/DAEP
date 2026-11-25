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
            # Delay the identity lookup so the session-restoration window is observable.
            # The login screen must stay hidden until the stored token is validated.
            page.add_init_script("""(() => {
                const originalFetch = window.fetch.bind(window);
                window.fetch = async (input, init) => {
                    const url = typeof input === 'string' ? input : input.url;
                    if (url.includes('/api/v1/me') && (!init || !init.method || init.method === 'GET')) {
                        await new Promise(resolve => setTimeout(resolve, 700));
                    }
                    return originalFetch(input, init);
                };
            })();""")
            page.reload(wait_until="domcontentloaded")
            expect(page.get_by_test_id("login-screen")).to_be_hidden()
            expect(page.locator("#boot")).to_be_visible()
            expect(page.get_by_test_id("app-shell")).to_be_visible(timeout=20000)
            expect(page.locator("#boot")).to_be_hidden()
            # app-shell becomes visible before async project bootstrap completes;
            # wait for the initial overview navigation to settle before switching.
            expect(page.locator("#overview.page.active")).to_be_visible(timeout=20000)
            expect(page.locator("#projectSelect option").filter(has_text="Browser E2E Agent Project")).to_have_count(1)

            page.locator('#nav button[data-page="agents"]').click()
            expect(page.locator("#agents.page.active")).to_be_visible()
            expect(page.locator("#agents .page-head button").filter(has_text="创建 Agent")).to_be_visible()
            expect(page.locator("#agentGrid")).to_contain_text("还没有 Agent")

            page.locator("#agents .page-head button").filter(has_text="创建 Agent").click()
            page.locator("#agentName").fill("Browser E2E Agent")
            page.locator("#agentDesc").fill("Agent identity lifecycle acceptance")
            page.get_by_role("button", name="创建并获取 Token").click()
            expect(page.locator("#modal")).to_be_visible()
            expect(page.locator("#modalBody")).to_contain_text("MCP Token")
            first_token = page.locator(".token-box").inner_text().strip()
            assert first_token.startswith("daep_at_")
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
            page.once("dialog", lambda dialog: dialog.accept())
            agent_card.get_by_role("button", name="重新生成 Token").click()
            expect(page.locator("#modal")).to_be_visible()
            rotated_token = page.locator(".token-box").inner_text().strip()
            assert rotated_token.startswith("daep_at_")
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
            # unbindAgentProject refreshes the detail modal after the DELETE.
            page.locator("#modal .modal-head button").click()

            # Seed real Task Execution and Collaboration grants, accept both with the
            # Agent credential, revoke both through Owner governance, and verify the
            # Agent detail UI surfaces the resulting authorization state.
            grant_setup = page.evaluate(
                """async ({agentId, agentToken, projectId}) => {
                    const webToken = localStorage.getItem('daep.web.access_token');
                    const auth = {'Authorization': 'Bearer ' + webToken, 'Content-Type': 'application/json'};
                    const me = await (await fetch('/api/v1/me', {headers: {'Authorization': 'Bearer ' + webToken}})).json();
                    const requirement = await (await fetch('/api/v1/requirements', {
                        method: 'POST', headers: auth,
                        body: JSON.stringify({project_id: projectId, title: 'Authorization state UI task'})
                    })).json();
                    const task = await (await fetch('/api/v1/tasks', {
                        method: 'POST', headers: auth,
                        body: JSON.stringify({requirement_id: requirement.id, title: 'Authorization state UI task', assignee_member_ids: [me.id]})
                    })).json();
                    const taskGrantResponse = await fetch('/api/v1/tasks/' + encodeURIComponent(task.id) + '/agent-grants', {
                        method: 'POST', headers: auth,
                        body: JSON.stringify({agent_id: agentId, requested_scope: ['task.read']})
                    });
                    const taskGrant = await taskGrantResponse.json();
                    const taskAcceptResponse = await fetch('/api/v1/agent-grants/' + encodeURIComponent(taskGrant.id) + '/accept', {
                        method: 'POST', headers: {'Authorization': 'Bearer ' + agentToken, 'Content-Type': 'application/json'}, body: '{}'
                    });
                    const sessionResponse = await fetch('/api/v1/tasks/' + encodeURIComponent(task.id) + '/collaboration-session', {
                        headers: {'Authorization': 'Bearer ' + webToken}
                    });
                    const session = await sessionResponse.json();
                    const collaborationGrantResponse = await fetch('/api/v1/tasks/' + encodeURIComponent(task.id) + '/collaboration-grants', {
                        method: 'POST', headers: auth,
                        body: JSON.stringify({agent_id: agentId, scopes: ['session.read']})
                    });
                    const collaborationGrant = await collaborationGrantResponse.json();
                    const collaborationAcceptResponse = await fetch('/api/v1/collaboration-grants/' + encodeURIComponent(collaborationGrant.id) + '/accept', {
                        method: 'POST', headers: {'Authorization': 'Bearer ' + agentToken, 'Content-Type': 'application/json'}, body: '{}'
                    });
                    const taskRevokeResponse = await fetch('/api/v1/agent-grants/' + encodeURIComponent(taskGrant.id), {
                        method: 'DELETE', headers: auth,
                        body: JSON.stringify({reason: 'Browser authorization-state regression'})
                    });
                    const collaborationRevokeResponse = await fetch('/api/v1/collaboration-grants/' + encodeURIComponent(collaborationGrant.id), {
                        method: 'DELETE', headers: auth,
                        body: JSON.stringify({reason: 'Browser authorization-state regression'})
                    });
                    return {
                        taskId: task.id,
                        sessionId: session.id,
                        taskGrantStatus: taskGrantResponse.status,
                        taskAcceptStatus: taskAcceptResponse.status,
                        collaborationGrantStatus: collaborationGrantResponse.status,
                        collaborationAcceptStatus: collaborationAcceptResponse.status,
                        taskRevokeStatus: taskRevokeResponse.status,
                        collaborationRevokeStatus: collaborationRevokeResponse.status
                    };
                }""",
                {"agentId": agent_id, "agentToken": rotated_token, "projectId": project_id},
            )
            assert grant_setup['taskGrantStatus'] == 200, grant_setup
            assert grant_setup['taskAcceptStatus'] == 200, grant_setup
            assert grant_setup['collaborationGrantStatus'] == 200, grant_setup
            assert grant_setup['collaborationAcceptStatus'] == 200, grant_setup
            assert grant_setup['taskRevokeStatus'] == 200, grant_setup
            assert grant_setup['collaborationRevokeStatus'] == 200, grant_setup
            agent_card.get_by_role("button", name="管理").click()
            expect(page.locator("#modalBody")).to_contain_text("Task Execution Grants")
            expect(page.locator("#modalBody")).to_contain_text("Collaboration Grants")
            expect(page.locator("#modalBody")).to_contain_text("REVOKED")
            page.locator("#modal .modal-head button").click()

            # Revoke the currently active rotated token and verify history.
            agent_card.get_by_role("button", name="管理").click()
            page.once("dialog", lambda dialog: dialog.accept())
            page.get_by_role("button", name="撤销当前 Token").click()
            expect(page.get_by_test_id("toast")).to_contain_text("Token 已撤销")
            agent_card.get_by_role("button", name="管理").click()
            expect(page.locator("#modalBody")).to_contain_text("REVOKED")

            # Disabling an Agent is also destructive and requires confirmation.
            page.locator("#editAgentStatus").select_option("DISABLED")
            page.once("dialog", lambda dialog: dialog.accept())
            page.get_by_role("button", name="保存").click()
            expect(page.get_by_test_id("toast")).to_contain_text("Agent 已更新")
            expect(agent_card).to_contain_text("DISABLED")

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



def test_agent_security_negative_browser_flows(daep_server):
    """Prove ownership, project-role and revoked-token checks in real sessions."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        admin = browser.new_page()
        owner = browser.new_page()
        attacker = browser.new_page()
        try:
            def login(page, username, password):
                page.goto(daep_server, wait_until="domcontentloaded")
                expect(page.get_by_test_id("login-screen")).to_be_visible()
                page.get_by_test_id("username-input").fill(username)
                page.get_by_test_id("password-input").fill(password)
                page.get_by_test_id("login-submit").click()
                expect(page.get_by_test_id("app-shell")).to_be_visible(timeout=20000)

            def api(page, method, path, body=None, bearer=None):
                return page.evaluate(
                    """async ({method, path, body, bearer}) => {
                        const token = bearer || localStorage.getItem('daep.web.access_token');
                        const headers = token ? {'Authorization': 'Bearer ' + token} : {};
                        if (body !== null && body !== undefined) headers['Content-Type'] = 'application/json';
                        const response = await fetch(path, {
                            method, headers,
                            body: body === null || body === undefined ? undefined : JSON.stringify(body)
                        });
                        let data = null;
                        try { data = await response.json(); } catch (_) {}
                        return {status: response.status, body: data};
                    }""",
                    {"method": method, "path": path, "body": body, "bearer": bearer},
                )

            login(admin, ADMIN_USERNAME, ADMIN_PASSWORD)
            suffix = str(time.time_ns())
            owner_username = "e2e.owner." + suffix
            attacker_username = "e2e.attacker." + suffix
            owner_password = "owner-e2e-password-2026"
            attacker_password = "attacker-e2e-password-2026"

            owner_result = api(admin, "POST", "/api/v1/members", {
                "name": "Browser E2E Agent Owner",
                "username": owner_username,
                "password": owner_password,
                "role": "member",
            })
            assert owner_result["status"] == 200, owner_result
            attacker_result = api(admin, "POST", "/api/v1/members", {
                "name": "Browser E2E Agent Attacker",
                "username": attacker_username,
                "password": attacker_password,
                "role": "member",
            })
            assert attacker_result["status"] == 200, attacker_result

            project_result = api(admin, "POST", "/api/v1/projects", {
                "name": "Browser E2E Restricted Project " + suffix,
                "description": "Isolated project for negative authorization checks",
                "tenant_id": "tenant-default",
            })
            assert project_result["status"] == 200, project_result
            project_id = project_result["body"]["id"]
            membership = api(admin, "POST", f"/api/v1/projects/{project_id}/members", {
                "member_id": attacker_result["body"]["id"],
                "role": "member",
                "work_function": "developer",
            })
            assert membership["status"] == 200, membership

            login(owner, owner_username, owner_password)
            owner_agent = api(owner, "POST", "/api/v1/agents", {
                "name": "Private Owner Agent",
                "description": "Must not be accessible by another member",
            })
            assert owner_agent["status"] == 200, owner_agent
            owner_agent_id = owner_agent["body"]["agent"]["id"]
            owner_agent_token = owner_agent["body"]["token"]

            login(attacker, attacker_username, attacker_password)
            attacker_agent = api(attacker, "POST", "/api/v1/agents", {
                "name": "Member Agent Without Manager Role",
                "description": "Cannot bind to a project as a regular member",
            })
            assert attacker_agent["status"] == 200, attacker_agent
            attacker_agent_id = attacker_agent["body"]["agent"]["id"]

            # Every ownership-sensitive operation must be rejected server-side.
            detail = api(attacker, "GET", f"/api/v1/agents/{owner_agent_id}")
            assert detail["status"] == 403, detail
            update = api(attacker, "PATCH", f"/api/v1/agents/{owner_agent_id}", {
                "name": "Unauthorized Rename",
                "description": "must not persist",
                "status": "ACTIVE",
            })
            assert update["status"] == 403, update
            rotate = api(attacker, "POST", f"/api/v1/agents/{owner_agent_id}/tokens/rotate")
            assert rotate["status"] == 403, rotate
            revoke = api(attacker, "POST", f"/api/v1/agents/{owner_agent_id}/tokens/revoke")
            assert revoke["status"] == 403, revoke

            # Project membership alone is insufficient: only owner/manager can bind.
            bind = api(attacker, "POST", f"/api/v1/agents/{attacker_agent_id}/projects", {
                "project_id": project_id,
                "work_function": "developer",
                "role": "member",
            })
            assert bind["status"] == 403, bind

            # The real owner revokes the credential; MCP authentication must fail.
            revoke_own = api(owner, "POST", f"/api/v1/agents/{owner_agent_id}/tokens/revoke")
            assert revoke_own["status"] == 200, revoke_own
            mcp = api(owner, "GET", "/api/v1/mcp/context", bearer=owner_agent_token)
            assert mcp["status"] == 401, mcp
            agent_tasks = api(owner, "GET", "/api/v1/agents/me/tasks", bearer=owner_agent_token)
            assert agent_tasks["status"] == 401, agent_tasks

            # Ensure rejected cross-owner mutations did not rename the resource.
            owner_detail = api(owner, "GET", f"/api/v1/agents/{owner_agent_id}")
            assert owner_detail["status"] == 200, owner_detail
            assert owner_detail["body"]["name"] == "Private Owner Agent"
        finally:
            browser.close()
