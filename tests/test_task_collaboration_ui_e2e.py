"""Browser regression for the Task Collaboration workspace.

Run with DAEP_RUN_BROWSER_E2E=1 and a working Playwright Chromium install.
"""
from __future__ import annotations

import os

import pytest

if os.getenv("DAEP_RUN_BROWSER_E2E") != "1":
    pytest.skip("set DAEP_RUN_BROWSER_E2E=1 to run browser acceptance tests", allow_module_level=True)

playwright_api = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright

from test_agent_management_e2e import ADMIN_PASSWORD, ADMIN_USERNAME, daep_server


def test_task_collaboration_workspace_proposal_and_messages(daep_server):
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

            setup = page.evaluate("""async () => {
                const webToken = localStorage.getItem('daep.web.access_token');
                const auth = {'Authorization':'Bearer '+webToken,'Content-Type':'application/json'};
                const call = async (path, method='GET', body, bearer=webToken) => {
                    const headers = {'Authorization':'Bearer '+bearer};
                    if (body !== undefined) headers['Content-Type']='application/json';
                    const response = await fetch(path,{method,headers,body:body===undefined?undefined:JSON.stringify(body)});
                    let data=null; try { data=await response.json(); } catch (_) {}
                    if (!response.ok) throw new Error(method+' '+path+' => '+response.status+' '+JSON.stringify(data));
                    return data;
                };
                const me = await call('/api/v1/me');
                const project = await call('/api/v1/projects','POST',{
                    name:'Task Collaboration Browser E2E',description:'Isolated browser test',tenant_id:'tenant-default'
                });
                const requirement = await call('/api/v1/requirements','POST',{
                    project_id:project.id,title:'Collaboration UI requirement'
                });
                const task = await call('/api/v1/tasks','POST',{
                    requirement_id:requirement.id,title:'Collaboration UI browser task',
                    assignee_member_ids:[me.id]
                });
                const created = await call('/api/v1/agents','POST',{
                    name:'Collaboration UI Browser Agent',description:'Proposal and message E2E'
                });
                const agentId = created.agent.id;
                const agentToken = created.token;
                const session = await call('/api/v1/tasks/'+task.id+'/collaboration-session');
                const grant = await call('/api/v1/tasks/'+task.id+'/collaboration-grants','POST',{
                    agent_id:agentId,scopes:['session.read','session.message.send','session.proposal.create']
                });
                await call('/api/v1/collaboration-grants/'+grant.id+'/accept','POST',{},agentToken);
                const proposal = await call('/api/v1/tasks/'+task.id+'/collaboration-proposals','POST',{
                    grant_id:grant.id,proposal_type:'HELP_REQUEST',
                    payload:{summary:'Need human review from browser E2E'}
                },agentToken);
                await call('/api/v1/tasks/'+task.id+'/collaboration-messages','POST',{
                    grant_id:grant.id,message_type:'TEXT',content:'Agent collaboration message from browser E2E'
                },agentToken);
                return {taskId:task.id,proposalId:proposal.id,sessionId:session.id};
            }""")
            page.evaluate("(id) => openTask(id)", setup["taskId"])
            modal = page.locator("#modalBody")
            expect(modal).to_contain_text("Task 协作空间")
            expect(modal).to_contain_text("Session OPEN")
            expect(modal).to_contain_text("Agent collaboration message from browser E2E")
            expect(modal).to_contain_text("Need human review from browser E2E")
            expect(modal.get_by_role("button", name="接受建议")).to_be_visible()

            page.once("dialog", lambda dialog: dialog.accept("Approved in browser E2E"))
            modal.get_by_role("button", name="接受建议").click()
            expect(modal).to_contain_text("已接受", timeout=15000)

            modal.locator("#taskCollabMessage").fill("Human collaboration message from browser E2E")
            modal.get_by_role("button", name="发送消息").click()
            expect(modal).to_contain_text("Human collaboration message from browser E2E", timeout=15000)
        finally:
            browser.close()
