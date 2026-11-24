import importlib
import pytest


def load_server(monkeypatch):
    monkeypatch.setenv('DAEP_AGENT_TOKEN','daep_at_test-agent-token')
    monkeypatch.delenv('DAEP_MEMBER_TOKEN',raising=False)
    import daep_mcp.server as server
    return importlib.reload(server)


def test_agent_allowlist_accepts_only_grant_scoped_task_routes(monkeypatch):
    server=load_server(monkeypatch)
    allowed=[
        ('GET','/api/v1/mcp/context'),
        ('GET','/api/v1/agents/me/grants'),
        ('POST','/api/v1/agent-grants/grant_123/accept'),
        ('GET','/api/v1/tasks/task_123'),
        ('POST','/api/v1/tasks/task_123/progress'),
        ('POST','/api/v1/tasks/task_123/blocked'),
        ('POST','/api/v1/tasks/task_123/artifacts'),
        ('GET','/api/v1/tasks/task_123/artifacts'),
        ('GET','/api/v1/tasks/task_123/artifact-versions'),
        ('GET','/api/v1/tasks/task_123/artifact-quality'),
    ]
    assert all(server._agent_path_allowed(method,path) for method,path in allowed)


def test_agent_allowlist_rejects_member_and_governance_routes(monkeypatch):
    server=load_server(monkeypatch)
    denied=[
        ('GET','/api/v1/me/tasks'),
        ('GET','/api/v1/me/notifications'),
        ('POST','/api/v1/messages/msg_1/ack'),
        ('POST','/api/v1/messages'),
        ('GET','/api/v1/projects/project_1/audit'),
        ('POST','/api/v1/projects/project_1/approvals'),
        ('POST','/api/v1/tasks/task_1/agent-assignments'),
        ('POST','/api/v1/tasks/task_1/delegations'),
        ('POST','/api/v1/tasks/task_1/work-packages'),
        ('GET','/api/v1/agents/me/tasks'),
        ('POST','/api/v1/agent-assignments/old_1/accept'),
    ]
    assert not any(server._agent_path_allowed(method,path) for method,path in denied)


def test_agent_call_blocks_owner_member_permission_fallback(monkeypatch):
    server=load_server(monkeypatch)
    with pytest.raises(RuntimeError,match='owner Member permissions are not inherited'):
        server.call('GET','/api/v1/me/notifications')


def test_agent_inbox_and_accept_tools_use_grant_endpoints(monkeypatch):
    server=load_server(monkeypatch)
    calls=[]
    monkeypatch.setattr(server,'call',lambda method,path,payload=None: calls.append((method,path,payload)) or {'ok':True})
    assert server.list_my_agent_tasks()=={'ok':True}
    assert server.list_my_agent_grants()=={'ok':True}
    assert server.accept_agent_task('grant_1')=={'ok':True}
    assert server.accept_agent_task_grant('grant_2')=={'ok':True}
    assert calls==[
        ('GET','/api/v1/agents/me/grants',None),
        ('GET','/api/v1/agents/me/grants',None),
        ('POST','/api/v1/agent-grants/grant_1/accept',{}),
        ('POST','/api/v1/agent-grants/grant_2/accept',{}),
    ]


def test_member_token_keeps_existing_tool_route_compatibility(monkeypatch):
    monkeypatch.delenv('DAEP_AGENT_TOKEN',raising=False)
    monkeypatch.setenv('DAEP_MEMBER_TOKEN','member-token')
    import daep_mcp.server as server
    server=importlib.reload(server)
    assert server.TOKEN=='member-token'
    calls=[]
    monkeypatch.setattr(server,'call',lambda method,path,payload=None: calls.append((method,path,payload)) or {'ok':True})
    assert server.get_my_notifications()=={'ok':True}
    assert calls[0][1].startswith('/api/v1/me/notifications')

def test_agent_allowlist_accepts_only_collaboration_grant_routes(monkeypatch):
    server=load_server(monkeypatch)
    assert server._agent_path_allowed('GET','/api/v1/agents/me/collaboration-grants')
    assert server._agent_path_allowed('POST','/api/v1/collaboration-grants/grant_1/accept')
    assert server._agent_path_allowed('GET','/api/v1/tasks/task_1/collaboration-messages?grant_id=grant_1')
    assert server._agent_path_allowed('POST','/api/v1/tasks/task_1/collaboration-messages')
    assert not server._agent_path_allowed('POST','/api/v1/tasks/task_1/collaboration-session')
    assert not server._agent_path_allowed('POST','/api/v1/tasks/task_1/collaboration-grants')
    assert not server._agent_path_allowed('DELETE','/api/v1/collaboration-grants/grant_1')


def test_agent_collaboration_tools_map_to_grant_scoped_rest_routes(monkeypatch):
    server=load_server(monkeypatch)
    calls=[]
    monkeypatch.setattr(server,'call',lambda method,path,payload=None: calls.append((method,path,payload)) or {'ok':True})
    assert server.list_my_agent_collaboration_grants()=={'ok':True}
    assert server.accept_agent_collaboration_grant('grant 1')=={'ok':True}
    assert server.get_task_collaboration_messages('task/1','grant 1',25)=={'ok':True}
    assert server.send_task_collaboration_message('task-1','grant-1','hello','resource-1',{'kind':'update'})=={'ok':True}
    assert calls==[
        ('GET','/api/v1/agents/me/collaboration-grants',None),
        ('POST','/api/v1/collaboration-grants/grant%201/accept',{}),
        ('GET','/api/v1/tasks/task%2F1/collaboration-messages?grant_id=grant+1&limit=25',None),
        ('POST','/api/v1/tasks/task-1/collaboration-messages',
         {'grant_id':'grant-1','content':'hello','metadata':{'kind':'update'},'resource_id':'resource-1'}),
    ]


def test_agent_collaboration_tool_inputs_are_validated(monkeypatch):
    server=load_server(monkeypatch)
    with pytest.raises(ValueError,match='grant_id'):
        server.accept_agent_collaboration_grant('')
    with pytest.raises(ValueError,match='limit'):
        server.get_task_collaboration_messages('task-1','grant-1',101)
    with pytest.raises(ValueError,match='content'):
        server.send_task_collaboration_message('task-1','grant-1','')


def test_agent_collaboration_tools_use_real_http_transport(monkeypatch):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    server=load_server(monkeypatch)
    received=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            received.append(('GET',self.path,self.headers.get('Authorization'),None))
            body=json.dumps({'items':[]}).encode()
            self.send_response(200); self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
        def do_POST(self):
            raw=self.rfile.read(int(self.headers.get('Content-Length','0')))
            received.append(('POST',self.path,self.headers.get('Authorization'),json.loads(raw or b'{}')))
            body=json.dumps({'status':'ok'}).encode()
            self.send_response(200); self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
        def log_message(self,*args):
            pass

    httpd=HTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=httpd.serve_forever,daemon=True); thread.start()
    monkeypatch.setattr(server,'API',f'http://127.0.0.1:{httpd.server_port}')
    monkeypatch.setattr(server,'TOKEN','daep_at_e2e-agent-token')
    try:
        assert server.list_my_agent_collaboration_grants()=={'items':[]}
        assert server.accept_agent_collaboration_grant('grant-42')=={'status':'ok'}
        assert server.get_task_collaboration_messages('task-42','grant-42',10)=={'items':[]}
        assert server.send_task_collaboration_message('task-42','grant-42','hello','resource-7')=={'status':'ok'}
    finally:
        httpd.shutdown(); thread.join(timeout=2); httpd.server_close()
    assert [item[0] for item in received]==['GET','POST','GET','POST']
    assert all(item[2]=='Bearer daep_at_e2e-agent-token' for item in received)
    assert received[0][1]=='/api/v1/agents/me/collaboration-grants'
    assert received[1][1]=='/api/v1/collaboration-grants/grant-42/accept'
    assert received[2][1]=='/api/v1/tasks/task-42/collaboration-messages?grant_id=grant-42&limit=10'
    assert received[3][1]=='/api/v1/tasks/task-42/collaboration-messages'
    assert received[3][3]=={'grant_id':'grant-42','content':'hello','metadata':{},'resource_id':'resource-7'}
