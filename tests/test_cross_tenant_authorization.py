import os, sqlite3, tempfile, json, json

os.environ.setdefault('DAEP_DB_PATH', os.path.join(tempfile.gettempdir(), 'daep-cross-tenant-v1.db'))
os.environ.setdefault('DAEP_ADMIN_TOKEN', 'test-admin-token-with-32-characters-minimum')
os.environ.setdefault('DAEP_WORKER_TOKEN', 'test-worker-token-with-32-characters-minimum')

try:
    os.remove(os.environ['DAEP_DB_PATH'])
except FileNotFoundError:
    pass

from fastapi.testclient import TestClient
from app.main import app, init
import app.main as main_module
from app.agent_identity import ensure_agent_schema

init()
ensure_agent_schema(main_module.conn)
client = TestClient(app)
ADMIN = {'Authorization': 'Bearer test-admin-token-with-32-characters-minimum'}


def _create_member(name):
    response = client.post('/api/v1/members', headers=ADMIN, json={'name': name})
    assert response.status_code == 200, response.text
    body = response.json()
    return body['id'], body['token']


def _set_member_tenant(member_id, tenant_id):
    with sqlite3.connect(os.environ['DAEP_DB_PATH']) as db:
        db.execute('UPDATE members SET tenant_id=? WHERE id=?', (tenant_id, member_id))
        db.commit()


def test_cross_tenant_project_requirement_task_agent_and_governance_are_isolated():
    tenant_response = client.post('/api/v1/tenants', headers=ADMIN, json={'name': 'Cross Tenant B'})
    assert tenant_response.status_code == 200, tenant_response.text
    tenant_b = tenant_response.json()['id']

    member_a_id, member_a_token = _create_member('Tenant A Member')
    member_b_id, member_b_token = _create_member('Tenant B Member')
    _set_member_tenant(member_b_id, tenant_b)

    headers_a = {'Authorization': f'Bearer {member_a_token}'}
    headers_b = {'Authorization': f'Bearer {member_b_token}'}

    # A malicious tenant_id must not let an ordinary Member create in another tenant.
    project_a = client.post('/api/v1/projects', headers=headers_a, json={
        'name': 'Tenant A Project',
        'tenant_id': tenant_b,
    })
    assert project_a.status_code == 200, project_a.text
    assert project_a.json()['tenant_id'] == 'tenant-default'
    project_a_id = project_a.json()['id']

    project_b = client.post('/api/v1/projects', headers=headers_b, json={
        'name': 'Tenant B Project',
        'tenant_id': 'tenant-default',
    })
    assert project_b.status_code == 200, project_b.text
    assert project_b.json()['tenant_id'] == tenant_b
    project_b_id = project_b.json()['id']

    req_b = client.post('/api/v1/requirements', headers=headers_b, json={
        'project_id': project_b_id,
        'title': 'Tenant B Requirement',
    })
    assert req_b.status_code == 200, req_b.text
    req_b_id = req_b.json()['id']

    task_b = client.post('/api/v1/tasks', headers=headers_b, json={
        'requirement_id': req_b_id,
        'title': 'Tenant B Task',
        'assignee_member_ids': [member_b_id],
    })
    assert task_b.status_code == 200, task_b.text
    task_b_id = task_b.json()['id']

    # Project-bound resource reads must not cross the tenant boundary.
    for path in (
        f'/api/v1/projects/{project_b_id}/members',
        f'/api/v1/projects/{project_b_id}/requirements',
        f'/api/v1/projects/{project_b_id}/tasks',
        f'/api/v1/projects/{project_b_id}/workflow',
        f'/api/v1/projects/{project_b_id}/gates',
        f'/api/v1/projects/{project_b_id}/audit',
        f'/api/v1/projects/{project_b_id}/governance',
        f'/api/v1/projects/{project_b_id}/coordination',
        f'/api/v1/projects/{project_b_id}/work-health',
        f'/api/v1/projects/{project_b_id}/delegations',
    ):
        denied = client.get(path, headers=headers_a)
        assert denied.status_code in (403, 404), (path, denied.status_code, denied.text)

    # Resource IDs alone are insufficient for direct Requirement/Task access.
    denied_requirement = client.get(f'/api/v1/requirements/{req_b_id}', headers=headers_a)
    assert denied_requirement.status_code in (403, 404), denied_requirement.text
    denied_task = client.get(f'/api/v1/tasks/{task_b_id}', headers=headers_a)
    assert denied_task.status_code in (403, 404), denied_task.text

    # A cannot create or mutate B resources by supplying B identifiers.
    denied_requirement_create = client.post('/api/v1/requirements', headers=headers_a, json={
        'project_id': project_b_id,
        'title': 'Cross Tenant Injection',
    })
    assert denied_requirement_create.status_code in (403, 404), denied_requirement_create.text

    denied_task_create = client.post('/api/v1/tasks', headers=headers_a, json={
        'requirement_id': req_b_id,
        'title': 'Cross Tenant Task Injection',
        'assignee_member_ids': [member_a_id],
    })
    assert denied_task_create.status_code in (403, 404), denied_task_create.text

    denied_workflow = client.put(
        f'/api/v1/projects/{project_b_id}/workflow',
        headers=headers_a,
        json={
            'enabled': True,
            'stages': [
                {'key': 'OPEN', 'name': 'Open', 'order': 1, 'approval_role': 'none'},
                {'key': 'REVIEW', 'name': 'Review', 'order': 2, 'approval_role': 'reviewer'},
            ],
        },
    )
    assert denied_workflow.status_code in (403, 404), denied_workflow.text

    # Project membership cannot be used as a cross-tenant write primitive.
    denied_member_add = client.post(
        f'/api/v1/projects/{project_b_id}/members',
        headers=headers_a,
        json={'member_id': member_a_id, 'role': 'member', 'work_function': 'developer'},
    )
    assert denied_member_add.status_code in (403, 404), denied_member_add.text

    # Agent identities are tenant-scoped independently of their owner.
    agent_b = client.post('/api/v1/agents', headers=headers_b, json={
        'name': 'Tenant B Agent',
        'description': 'Cross-tenant isolation test',
    })
    assert agent_b.status_code == 200, agent_b.text
    agent_b_id = agent_b.json()['agent']['id']

    visible_agents_a = client.get('/api/v1/agents', headers=headers_a)
    assert visible_agents_a.status_code == 200, visible_agents_a.text
    assert all(item['id'] != agent_b_id for item in visible_agents_a.json())

    denied_agent = client.get(f'/api/v1/agents/{agent_b_id}', headers=headers_a)
    assert denied_agent.status_code in (403, 404), denied_agent.text

    # Project Agent presence is also project/tenant scoped.
    register_b = client.post(
        f'/api/v1/projects/{project_b_id}/agents/register',
        headers=headers_b,
        json={'agent_name': 'Tenant B Agent', 'capabilities': ['testing'], 'protocols': ['mcp']},
    )
    assert register_b.status_code == 200, register_b.text

    denied_presence = client.get(f'/api/v1/projects/{project_b_id}/agents', headers=headers_a)
    assert denied_presence.status_code in (403, 404), denied_presence.text

    # Cross-tenant delegation must fail before any recipient or Agent mutation occurs.
    denied_delegation = client.post(
        f'/api/v1/tasks/{task_b_id}/delegations',
        headers=headers_a,
        json={
            'recipient_member_id': member_a_id,
            'agent_name': 'Tenant B Agent',
            'reason': 'Cross-tenant delegation attempt',
        },
    )
    assert denied_delegation.status_code in (403, 404), denied_delegation.text

    # Tenant A's own project remains visible, proving the isolation test did not
    # simply revoke all ordinary-member project access.
    own_projects = client.get('/api/v1/projects', headers=headers_a)
    assert own_projects.status_code == 200, own_projects.text
    assert any(item['id'] == project_a_id for item in own_projects.json())
    assert all(item['id'] != project_b_id for item in own_projects.json())


    # Task-level collaboration context is tenant/project scoped even when the
    # caller knows the target Task UUID.
    for path in (
        f'/api/v1/tasks/{task_b_id}/collaboration-grants',
        f'/api/v1/tasks/{task_b_id}/collaboration-session',
        f'/api/v1/tasks/{task_b_id}/collaboration-messages',
        f'/api/v1/tasks/{task_b_id}/collaboration-proposals',
        f'/api/v1/tasks/{task_b_id}/delegations',
    ):
        response = client.get(path, headers=headers_a)
        assert response.status_code in (403, 404), (path, response.status_code, response.text)

    # Member-owned notification data must remain scoped to the caller.
    notification_audit = client.get('/api/v1/me/notification-audit', headers=headers_a)
    assert notification_audit.status_code == 200, notification_audit.text
    assert 'Tenant B Task' not in json.dumps(notification_audit.json(), ensure_ascii=False)
    assert str(member_b_id) not in json.dumps(notification_audit.json(), ensure_ascii=False)

    notification_prefs = client.get('/api/v1/me/notification-preferences', headers=headers_a)
    assert notification_prefs.status_code == 200, notification_prefs.text
    assert str(member_b_id) not in json.dumps(notification_prefs.json(), ensure_ascii=False)

