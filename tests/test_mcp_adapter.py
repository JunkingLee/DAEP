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
    allowed=[
        ('GET','/api/v1/agents/me/collaboration-grants'),
        ('POST','/api/v1/collaboration-grants/acg_123/accept'),
        ('GET','/api/v1/tasks/task_123/collaboration-messages?grant_id=acg_123&limit=50'),
        ('POST','/api/v1/tasks/task_123/collaboration-messages'),
    ]
    assert all(server._agent_path_allowed(method,path) for method,path in allowed)
    denied=[
        ('GET','/api/v1/tasks/task_123/collaboration-messages/'),
        ('DELETE','/api/v1/tasks/task_123/collaboration-messages'),
        ('POST','/api/v1/collaboration-grants/acg_123/revoke'),
        ('GET','/api/v1/agents/other/collaboration-grants'),
    ]
    assert not any(server._agent_path_allowed(method,path) for method,path in denied)


def test_agent_collaboration_tools_use_explicit_grant_endpoints(monkeypatch):
    server=load_server(monkeypatch)
    calls=[]
    monkeypatch.setattr(server,'call',lambda method,path,payload=None: calls.append((method,path,payload)) or {'ok':True})
    assert server.list_my_agent_collaboration_grants()=={'ok':True}
    assert server.accept_agent_collaboration_grant('acg_1')=={'ok':True}
    assert server.get_task_collaboration_messages('task_1','acg_1',25)=={'ok':True}
    assert server.send_task_collaboration_message('task_1','acg_1','hello','resource_1')=={'ok':True}
    assert calls==[
        ('GET','/api/v1/agents/me/collaboration-grants',None),
        ('POST','/api/v1/collaboration-grants/acg_1/accept',{}),
        ('GET','/api/v1/tasks/task_1/collaboration-messages?grant_id=acg_1&limit=25',None),
        ('POST','/api/v1/tasks/task_1/collaboration-messages',{
            'grant_id':'acg_1','content':'hello','resource_id':'resource_1'}),
    ]


def test_agent_collaboration_tools_validate_required_inputs(monkeypatch):
    server=load_server(monkeypatch)
    with pytest.raises(ValueError,match='grant_id is required'):
        server.accept_agent_collaboration_grant('')
    with pytest.raises(ValueError,match='task_id and grant_id are required'):
        server.get_task_collaboration_messages('task_1','')
    with pytest.raises(ValueError,match='limit must be between 1 and 100'):
        server.get_task_collaboration_messages('task_1','acg_1',101)
    with pytest.raises(ValueError,match='task_id, grant_id and content are required'):
        server.send_task_collaboration_message('task_1','acg_1',' ')
