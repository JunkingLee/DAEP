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
                    grant_id:grant.id,message_type:'MESSAGE',content:'Agent collaboration message from browser E2E'
                },agentToken);
                return {taskId:task.id,proposalId:proposal.id,sessionId:session.id,grantId:grant.id,agentId,agentToken};
            }""")
            page.evaluate("(id) => openTask(id)", setup["taskId"])
            modal = page.locator("#modalBody")
            expect(modal).to_contain_text("Task 协作空间")
            expect(modal).to_contain_text("Session OPEN")
            expect(modal).to_contain_text("Agent 授权")
            expect(modal).to_contain_text("已生效")
            expect(modal).to_contain_text("读取协作历史")
            expect(modal).to_contain_text("Agent collaboration message from browser E2E")
            expect(modal).to_contain_text("Need human review from browser E2E")
            expect(modal.get_by_role("button", name="接受建议")).to_be_visible()

            # The Member owner can review and revoke only their own Agent grants
            # from the dedicated inbox, independently of the Task workspace.
            page.evaluate("loadCollaborationGrantInbox()")
            expect(modal).to_contain_text("Collaboration UI Browser Agent")
            expect(modal).to_contain_text("已生效")
            page.evaluate("closeModal()")
            page.evaluate("(id) => openTask(id)", setup["taskId"])
            expect(modal).to_contain_text("Task 协作空间")
            expect(modal).to_contain_text("接受建议")


            page.once("dialog", lambda dialog: dialog.accept("Approved in browser E2E"))
            modal.get_by_role("button", name="接受建议").click()
            expect(modal).to_contain_text("已接受", timeout=15000)

            modal.locator("#taskCollabMessage").fill("Human collaboration message from browser E2E")
            # Wait for the actual write request rather than the transient toast: the
            # proposal decision and message composer both refresh this modal async.
            with page.expect_response(
                lambda response: "/api/v1/tasks/" + setup["taskId"] + "/collaboration-messages" in response.url
                and response.request.method == "POST"
            ) as message_response:
                modal.get_by_role("button", name="发送消息").click()
            assert message_response.value.status == 201, message_response.value.text()
            expect(modal).to_contain_text("Human collaboration message from browser E2E", timeout=15000)

            # The responsible Member controls the Session from the Task workspace.
            modal.get_by_role("button", name="暂停协作").click()
            expect(modal).to_contain_text("Session PAUSED", timeout=15000)
            expect(modal.locator("#taskCollabMessage")).to_have_count(0)
            modal.get_by_role("button", name="恢复协作").click()
            expect(modal).to_contain_text("Session OPEN", timeout=15000)
            page.once("dialog", lambda dialog: dialog.accept())
            modal.get_by_role("button", name="关闭协作").click()
            expect(modal).to_contain_text("Session CLOSED", timeout=15000)
            expect(modal.get_by_role("button", name="恢复协作")).to_have_count(0)
            expect(modal.get_by_role("button", name="关闭协作")).to_have_count(0)

            # CLOSED is history-readable but rejects Agent messages and proposals,
            # as well as a Member's attempt to authorize another Agent.
            lifecycle = page.evaluate("""async ({taskId,grantId,agentId,agentToken}) => {
                const memberToken=localStorage.getItem('daep.web.access_token');
                const call=async(path,method,body,token) => {
                    const response=await fetch(path,{method,headers:{
                        'Authorization':'Bearer '+token,'Content-Type':'application/json'
                    },body:body===undefined?undefined:JSON.stringify(body)});
                    return {status:response.status,data:await response.json().catch(()=>null)};
                };
                const history=await call('/api/v1/tasks/'+taskId+'/collaboration-messages?grant_id='+grantId,'GET',undefined,agentToken);
                const message=await call('/api/v1/tasks/'+taskId+'/collaboration-messages','POST',{
                    grant_id:grantId,content:'must be rejected after close'
                },agentToken);
                const proposal=await call('/api/v1/tasks/'+taskId+'/collaboration-proposals','POST',{
                    grant_id:grantId,proposal_type:'HELP_REQUEST',payload:{summary:'must be rejected'}
                },agentToken);
                const grant=await call('/api/v1/tasks/'+taskId+'/collaboration-grants','POST',{
                    agent_id:agentId
                },memberToken);
                return {history:history.status,message:message.status,proposal:proposal.status,grant:grant.status};
            }""", {"taskId":setup["taskId"],"grantId":setup["grantId"],"agentId":setup["agentId"],"agentToken":setup["agentToken"]})
            assert lifecycle["history"] == 200, lifecycle
            assert lifecycle["message"] == 409, lifecycle
            assert lifecycle["proposal"] == 409, lifecycle
            assert lifecycle["grant"] == 409, lifecycle
            # Owner revocation from the Task workspace removes history and write access.
            page.on("dialog", lambda dialog: dialog.accept("Owner revoked from browser E2E") if dialog.type == "prompt" else dialog.accept())
            modal.get_by_role("button", name="撤销我的授权").click()
            expect(modal).to_contain_text("已撤销", timeout=15000)
            revoked_access = page.evaluate("""async ({taskId,grantId,agentToken}) => {
                const call=async(path,method,body) => {
                    const response=await fetch(path,{method,headers:{
                        'Authorization':'Bearer '+agentToken,'Content-Type':'application/json'
                    },body:body===undefined?undefined:JSON.stringify(body)});
                    return response.status;
                };
                const history=await call('/api/v1/tasks/'+taskId+'/collaboration-messages?grant_id='+grantId,'GET');
                const message=await call('/api/v1/tasks/'+taskId+'/collaboration-messages','POST',{grant_id:grantId,content:'must be rejected after revoke'});
                const proposal=await call('/api/v1/tasks/'+taskId+'/collaboration-proposals','POST',{grant_id:grantId,proposal_type:'HELP_REQUEST',payload:{summary:'must be rejected'}});
                return {history,message,proposal};
            }""", {"taskId":setup["taskId"],"grantId":setup["grantId"],"agentToken":setup["agentToken"]})
            assert revoked_access == {"history":403,"message":403,"proposal":403}, revoked_access

            # Validate the durable Member inbox after the Task workspace flow is complete.
            page.evaluate("closeModal(); go('inbox'); loadInbox('ALL')")
            inbox = page.locator("#inbox")
            notice_button = inbox.get_by_role("button", name="标记已读").first
            expect(notice_button).to_be_visible()
            notice_button.click()
            expect(page.locator("#toast")).to_contain_text("消息已标记为已读", timeout=10000)
            page.evaluate("loadInbox('ACKNOWLEDGED')")
            expect(inbox).to_contain_text("已读")
            expect(inbox).to_contain_text("Agent")
        finally:
            browser.close()
