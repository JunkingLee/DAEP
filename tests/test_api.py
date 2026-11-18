import os, tempfile, hashlib, sqlite3
os.environ['DAEP_DB_PATH']=os.path.join(tempfile.gettempdir(),'daep-test-suite-v3.db')
os.environ['DAEP_ADMIN_TOKEN']='test-admin-token-with-32-characters-minimum'
os.environ['DAEP_WORKER_TOKEN']='test-worker-token-with-32-characters-minimum'
try: os.remove(os.environ['DAEP_DB_PATH'])
except FileNotFoundError: pass
from fastapi.testclient import TestClient
from app.main import app, init
init()
client=TestClient(app)
ADMIN={'Authorization':'Bearer test-admin-token-with-32-characters-minimum'}
WORKER={'Authorization':'Bearer test-worker-token-with-32-characters-minimum'}

def test_health():
    assert client.get('/health').json()['status']=='ok'

def setup_project_task():
    p=client.post('/api/v1/projects',headers=ADMIN,json={'name':'Demo'}); assert p.status_code==200; pid=p.json()['id']
    m=client.post('/api/v1/members',headers=ADMIN,json={'name':'Developer'}); assert m.status_code==200
    mid,token=m.json()['id'],m.json()['token']
    db=sqlite3.connect(os.environ['DAEP_DB_PATH'])
    stored=db.execute('SELECT token FROM members WHERE id=?',(mid,)).fetchone()[0]
    db.close()
    assert stored==hashlib.sha256(token.encode()).hexdigest() and stored!=token
    r=client.post('/api/v1/requirements',headers=ADMIN,json={'project_id':pid,'title':'Order API'}); assert r.status_code==200
    t=client.post('/api/v1/tasks',headers=ADMIN,json={'requirement_id':r.json()['id'],'title':'Implement API','assignee_member_ids':[mid]}); assert t.status_code==200
    return pid,mid,token,t.json()['id']

def test_project_requirement_task_message_flow():
    _,mid,token,tid=setup_project_task()
    msg=client.post('/api/v1/messages',headers=ADMIN,json={'recipient_member_id':mid,'task_id':tid,'title':'Start','content':'Please begin'}); assert msg.status_code==200
    nh={'Authorization':f'Bearer {token}'}
    n=client.get('/api/v1/me/notifications',headers=nh); assert len(n.json()['items'])==1
    assert n.json()['next_cursor'] > 0
    ack=client.post('/api/v1/messages/'+msg.json()['id']+'/ack',headers=nh,json={'status':'ACKNOWLEDGED'}); assert ack.status_code==200
    pr=client.post(f'/api/v1/tasks/{tid}/progress',headers=nh,json={'progress':100,'note':'Ready for review'}); assert pr.status_code==200
    assert client.get(f'/api/v1/tasks/{tid}',headers=nh).json()['status']=='REVIEW'

def test_project_isolation_and_assignment_enforcement():
    _,mid,token,tid=setup_project_task()
    outsider=client.post('/api/v1/members',headers=ADMIN,json={'name':'Outsider'}).json()
    oh={'Authorization':f"Bearer {outsider['token']}"}
    assert client.get(f'/api/v1/tasks/{tid}',headers=oh).status_code==403
    assert client.get('/api/v1/projects',headers=oh).json()==[]
    assert client.post(f'/api/v1/tasks/{tid}/progress',headers=oh,json={'progress':10}).status_code==403
    assert client.get(f'/api/v1/tasks/{tid}',headers={'Authorization':f'Bearer {token}'}).status_code==200

def test_notification_cursor_and_idempotency():
    _,mid,token,tid=setup_project_task()
    nh={'Authorization':f'Bearer {token}'}
    for i in range(3):
        assert client.post('/api/v1/messages',headers=ADMIN,json={'recipient_member_id':mid,'task_id':tid,'title':f'M{i}','content':'x'}).status_code==200
    page1=client.get('/api/v1/me/notifications?limit=2',headers=nh).json()
    assert len(page1['items'])==2 and page1['has_more']
    page2=client.get(f"/api/v1/me/notifications?after={page1['next_cursor']}&limit=2",headers=nh).json()
    assert len(page2['items'])==1 and page2['items'][0]['seq']>page1['next_cursor']
    headers={**nh,'Idempotency-Key':'progress-once'}
    first=client.post(f'/api/v1/tasks/{tid}/progress',headers=headers,json={'progress':30}).json()
    second=client.post(f'/api/v1/tasks/{tid}/progress',headers=headers,json={'progress':30}).json()
    assert first['event_id']==second['event_id'] and second['idempotent_replay']

def test_project_member_management_and_review_gate():
    pid,_,developer_token,tid=setup_project_task()
    reviewer=client.post('/api/v1/members',headers=ADMIN,json={'name':'Reviewer'}).json()
    add=client.post(f'/api/v1/projects/{pid}/members',headers=ADMIN,json={'member_id':reviewer['id'],'role':'reviewer'})
    assert add.status_code==200
    listing=client.get(f'/api/v1/projects/{pid}/members',headers=ADMIN).json()
    assert any(x['id']==reviewer['id'] and x['project_role']=='reviewer' for x in listing)
    rh={'Authorization':f"Bearer {reviewer['token']}"}
    assert client.post(f'/api/v1/tasks/{tid}/review',headers=rh,json={'decision':'APPROVE'}).status_code==409
    dh={'Authorization':f'Bearer {developer_token}'}
    assert client.post(f'/api/v1/tasks/{tid}/progress',headers=dh,json={'progress':100}).status_code==200
    approved=client.post(f'/api/v1/tasks/{tid}/review',headers=rh,json={'decision':'APPROVE','comment':'Acceptance criteria met'})
    assert approved.status_code==200 and approved.json()['status']=='DONE'

def test_dashboard_and_security_headers():
    r=client.get('/')
    assert r.status_code==200 and 'DAEP' in r.text
    assert r.headers['x-frame-options']=='DENY'
    assert r.headers['x-content-type-options']=='nosniff'

def test_rc2_database_migration_is_additive(tmp_path):
    import sqlite3
    import app.main as module
    old_db=module.DB
    target=str(tmp_path/'legacy.db')
    db=sqlite3.connect(target)
    db.execute("CREATE TABLE members(id TEXT PRIMARY KEY,name TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'developer',token TEXT UNIQUE NOT NULL,created_at TEXT NOT NULL)")
    db.execute("INSERT INTO members VALUES('legacy-member','Legacy','developer','legacy-plaintext-token','2026-01-01T00:00:00+00:00')")
    db.execute("CREATE TABLE messages(id TEXT PRIMARY KEY,recipient_member_id TEXT NOT NULL,task_id TEXT,message_type TEXT,title TEXT,content TEXT,priority TEXT,status TEXT NOT NULL DEFAULT 'PENDING',created_at TEXT NOT NULL,acked_at TEXT)")
    db.execute("INSERT INTO messages VALUES('msg-old','member-old',NULL,'COLLABORATION','legacy','body','NORMAL','PENDING','2026-01-01T00:00:00+00:00',NULL)")
    db.commit(); db.close()
    module.DB=target
    try:
        module.init()
        db=sqlite3.connect(target)
        cols={x[1] for x in db.execute('PRAGMA table_info(messages)')}
        row=db.execute("SELECT id,seq,attempts FROM messages WHERE id='msg-old'").fetchone()
        assert {'seq','attempts','last_attempt_at'} <= cols
        assert row[0]=='msg-old' and row[1]>0 and row[2]==0
        digest=db.execute("SELECT token FROM members WHERE id='legacy-member'").fetchone()[0]
        assert digest==hashlib.sha256(b'legacy-plaintext-token').hexdigest()
        db.close()
    finally:
        module.DB=old_db

def test_transactional_outbox_claim_and_lease_ownership():
    _,mid,_,tid=setup_project_task()
    sent=client.post('/api/v1/messages',headers=ADMIN,json={'recipient_member_id':mid,'task_id':tid,'title':'Dispatch','content':'hello'})
    assert sent.status_code==200
    claim=client.post('/internal/v1/outbox/claim',headers=WORKER,json={'worker_id':'worker-a','limit':10,'lease_seconds':30})
    assert claim.status_code==200 and claim.json()['count']>=1
    item=next(x for x in claim.json()['items'] if x['payload']['message_id']==sent.json()['id'])
    wrong=client.post(f"/internal/v1/outbox/{item['id']}/complete",headers=WORKER,json={'worker_id':'worker-a','lease_token':'x'*40})
    assert wrong.status_code==409
    done=client.post(f"/internal/v1/outbox/{item['id']}/complete",headers=WORKER,json={'worker_id':'worker-a','lease_token':item['lease_token']})
    assert done.status_code==200 and done.json()['status']=='SENT'
    empty=client.post('/internal/v1/outbox/claim',headers=WORKER,json={'worker_id':'worker-a','lease_token':item['lease_token']})
    assert empty.json()['count']==0

def test_outbox_failure_schedules_retry():
    _,mid,member_token,tid=setup_project_task()
    client.post('/api/v1/messages',headers=ADMIN,json={'recipient_member_id':mid,'task_id':tid,'title':'Retry','content':'hello'})
    claim=client.post('/internal/v1/outbox/claim',headers=WORKER,json={'worker_id':'worker-retry'}).json()
    item=next(x for x in claim['items'] if x['payload']['title']=='Retry')
    failed=client.post(f"/internal/v1/outbox/{item['id']}/fail",headers=WORKER,json={'worker_id':'worker-retry','lease_token':item['lease_token'],'error':'temporary broker outage'})
    assert failed.status_code==200 and failed.json()['status']=='PENDING'
    # Backoff keeps it unavailable until retry time; the inbox copy remains durable.
    assert client.post('/internal/v1/outbox/claim',headers=WORKER,json={'worker_id':'worker-retry'}).json()['count']==0
    inbox=client.get('/api/v1/me/notifications',headers={'Authorization':f'Bearer {member_token}'})
    assert inbox.status_code==200 and len(inbox.json()['items'])==1


def test_websocket_auth_uses_hashed_member_token():
    _,_,member_token,_=setup_project_task()
    with client.websocket_connect(f'/ws/v1?token={member_token}') as ws:
        greeting=ws.receive_json()
        assert greeting['type']=='connected'

def test_tenant_creation_and_token_lifecycle():
    t=client.post('/api/v1/tenants',headers=ADMIN,json={'name':'Tenant B'}); assert t.status_code==200
    tid=t.json()['id']
    m=client.post('/api/v1/members',headers=ADMIN,json={'name':'Tenant B Dev','tenant_id':tid}); assert m.status_code==200
    token=m.json()['token']; mid=m.json()['id']
    assert client.get('/api/v1/me',headers={'Authorization':f'Bearer {token}'}).json()['id']==mid
    revoked=client.post(f'/api/v1/members/{mid}/revoke-token',headers=ADMIN); assert revoked.status_code==200
    assert client.get('/api/v1/me',headers={'Authorization':f'Bearer {token}'}).status_code==401
    rotated=client.post(f'/api/v1/members/{mid}/rotate-token',headers=ADMIN); assert rotated.status_code==200
    new=rotated.json()['token']
    assert client.get('/api/v1/me',headers={'Authorization':f'Bearer {new}'}).status_code==200

def test_tenant_project_isolation():
    t=client.post('/api/v1/tenants',headers=ADMIN,json={'name':'Tenant C'}).json()['id']
    m=client.post('/api/v1/members',headers=ADMIN,json={'name':'Tenant C Dev','tenant_id':t}).json()
    ch={'Authorization':f"Bearer {m['token']}"}
    p=client.post('/api/v1/projects',headers=ch,json={'name':'Tenant C Project'}); assert p.status_code==200
    # The global admin can see all tenants; a tenant member cannot see default-tenant resources.
    default_project=client.post('/api/v1/projects',headers=ADMIN,json={'name':'Default Tenant Project'}).json()
    listed=client.get('/api/v1/projects',headers=ch).json()
    assert default_project['id'] not in [x['id'] for x in listed]
    assert p.json()['id'] in [x['id'] for x in listed]

def test_cross_tenant_membership_and_assignment_rejected():
    t=client.post('/api/v1/tenants',headers=ADMIN,json={'name':'Tenant D'}).json()['id']
    m=client.post('/api/v1/members',headers=ADMIN,json={'name':'Tenant D Dev','tenant_id':t}).json()
    project=client.post('/api/v1/projects',headers=ADMIN,json={'name':'Default Only'}).json()
    add=client.post(f"/api/v1/projects/{project['id']}/members",headers=ADMIN,json={'member_id':m['id'],'role':'member'})
    assert add.status_code==400


def test_oidc_state_is_one_time_and_pkce_verifier_is_server_side():
    import app.main as module
    state, nonce, verifier = module._oidc_state_record()
    assert len(state) > 30 and len(nonce) > 30 and len(verifier) > 40
    module._verify_oidc_browser_state(state,state)
    from fastapi import HTTPException
    try:
        module._verify_oidc_browser_state(state,'attacker-controlled-state')
        assert False, 'OIDC state must be bound to the initiating browser'
    except HTTPException as exc:
        assert exc.status_code == 400
    consumed_nonce, consumed_verifier = module._consume_oidc_state(state)
    assert consumed_nonce == nonce and consumed_verifier == verifier
    try:
        module._consume_oidc_state(state)
        assert False, 'OIDC state must not be reusable'
    except HTTPException as exc:
        assert exc.status_code == 400


def test_postgres_adapter_translates_sqlite_compatibility_statements():
    import app.main as module

    class FakeCursor:
        rowcount = 1
        def fetchone(self): return {'name': 'tenant_id'}
        def fetchall(self): return [{'name': 'tenant_id'}]

    class FakeConnection:
        def __init__(self): self.calls=[]
        def execute(self, sql, args=()):
            self.calls.append((sql,args))
            return FakeCursor()

    pg = module._PGConn.__new__(module._PGConn)
    pg.c = FakeConnection()
    noop = pg.execute('PRAGMA foreign_keys=ON')
    assert noop.rowcount == 0 and pg.c.calls == []
    pg.execute('PRAGMA table_info(members)')
    assert 'information_schema.columns' in pg.c.calls[-1][0]
    pg.execute("INSERT OR IGNORE INTO tenants(id,name,status) VALUES(?,?,?)", ('t1','Tenant','ACTIVE'))
    sql,args = pg.c.calls[-1]
    assert sql == 'INSERT INTO tenants(id,name,status) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING'
    assert args == ('t1','Tenant','ACTIVE')
    pg.execute('BEGIN IMMEDIATE')
    assert pg.c.calls[-1][0] == 'BEGIN'


def test_outbox_and_audit_events_use_resource_tenant():
    import sqlite3, os
    tenant = client.post('/api/v1/tenants',headers=ADMIN,json={'name':'Outbox Tenant'}).json()['id']
    member = client.post('/api/v1/members',headers=ADMIN,json={'name':'Tenant User','tenant_id':tenant}).json()
    mh={'Authorization':f"Bearer {member['token']}"}
    project=client.post('/api/v1/projects',headers=mh,json={'name':'Tenant Project'}).json()
    req=client.post('/api/v1/requirements',headers=mh,json={'project_id':project['id'],'title':'Tenant Req'}).json()
    task=client.post('/api/v1/tasks',headers=mh,json={'requirement_id':req['id'],'title':'Tenant Task','assignee_member_ids':[member['id']]}).json()
    sent=client.post('/api/v1/messages',headers=ADMIN,json={'recipient_member_id':member['id'],'project_id':project['id'],'task_id':task['id'],'title':'Tenant dispatch','content':'hello'})
    assert sent.status_code == 200
    db=sqlite3.connect(os.environ['DAEP_DB_PATH'])
    outbox_tenant=db.execute("SELECT tenant_id FROM outbox WHERE json_extract(payload,'$.message_id')=?",(sent.json()['id'],)).fetchone()[0]
    assert outbox_tenant == tenant
    db.close()
    revoke=client.post(f"/api/v1/members/{member['id']}/revoke-token",headers=ADMIN)
    assert revoke.status_code == 200
    db=sqlite3.connect(os.environ['DAEP_DB_PATH'])
    audit=db.execute("SELECT tenant_id FROM events WHERE event_type='member.token.revoked' ORDER BY created_at DESC LIMIT 1").fetchone()[0]
    db.close()
    assert audit == tenant


def test_outbox_endpoints_reject_admin_credential_and_accept_worker_credential():
    _,mid,_,tid=setup_project_task()
    sent=client.post('/api/v1/messages',headers=ADMIN,json={'recipient_member_id':mid,'task_id':tid,'title':'Worker auth','content':'payload'})
    assert sent.status_code==200
    denied=client.post('/internal/v1/outbox/claim',headers=ADMIN,json={'worker_id':'worker-secure'})
    assert denied.status_code==401
    accepted=client.post('/internal/v1/outbox/claim',headers=WORKER,json={'worker_id':'worker-secure'})
    assert accepted.status_code==200 and accepted.json()['count']>=1


def test_legacy_cross_tenant_links_are_not_exposed_by_reads():
    tenant_a=client.post('/api/v1/tenants',headers=ADMIN,json={'name':'Isolation A'}).json()['id']
    tenant_b=client.post('/api/v1/tenants',headers=ADMIN,json={'name':'Isolation B'}).json()['id']
    member_a=client.post('/api/v1/members',headers=ADMIN,json={'name':'A owner','tenant_id':tenant_a}).json()
    member_b=client.post('/api/v1/members',headers=ADMIN,json={'name':'B outsider','tenant_id':tenant_b}).json()
    ha={'Authorization':f"Bearer {member_a['token']}"}
    hb={'Authorization':f"Bearer {member_b['token']}"}
    project=client.post('/api/v1/projects',headers=ha,json={'name':'A project'}).json()
    req=client.post('/api/v1/requirements',headers=ha,json={'project_id':project['id'],'title':'A requirement'}).json()
    task=client.post('/api/v1/tasks',headers=ha,json={'requirement_id':req['id'],'title':'A task'}).json()
    # Simulate a bad legacy row written before strict tenant checks existed.
    db=sqlite3.connect(os.environ['DAEP_DB_PATH'])
    db.execute('INSERT INTO assignments(task_id,member_id) VALUES(?,?)',(task['id'],member_b['id']))
    db.execute('INSERT INTO project_members(project_id,member_id,role,joined_at) VALUES(?,?,?,?)',(project['id'],member_b['id'],'member','2026-01-01T00:00:00+00:00'))
    db.commit(); db.close()
    from app.main import init
    init()  # Startup migration must quarantine the invalid legacy grants.
    db=sqlite3.connect(os.environ['DAEP_DB_PATH'])
    assert db.execute('SELECT 1 FROM assignments WHERE task_id=? AND member_id=?',(task['id'],member_b['id'])).fetchone() is None
    assert db.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(project['id'],member_b['id'])).fetchone() is None
    db.close()
    assert project['id'] not in [x['id'] for x in client.get('/api/v1/projects',headers=hb).json()]
    assert client.get('/api/v1/me/tasks',headers=hb).json() == []
    detail=client.get(f"/api/v1/tasks/{task['id']}",headers=ha).json()
    assert all(x['id'] != member_b['id'] for x in detail['assignees'])


def test_schema_migration_ledger_is_idempotent():
    import app.main as module
    module.init()
    module.init()
    db=sqlite3.connect(os.environ['DAEP_DB_PATH'])
    versions={row[0] for row in db.execute('SELECT version FROM schema_migrations')}
    db.close()
    assert {'0005-rc5-baseline','0006-tenant-indexes-oidc-state','0007-platform-admin-boundary'} <= versions


def test_tenant_member_cannot_escalate_to_platform_admin():
    tenant=client.post('/api/v1/tenants',headers=ADMIN,json={'name':'Admin Boundary'}).json()['id']
    denied=client.post('/api/v1/members',headers=ADMIN,json={'name':'Fake Admin','role':'admin','tenant_id':tenant})
    assert denied.status_code==422
    tenant_member=client.post('/api/v1/members',headers=ADMIN,json={'name':'Tenant Manager','role':'manager','tenant_id':tenant}).json()
    headers={'Authorization':f"Bearer {tenant_member['token']}"}
    assert client.get('/api/v1/tenants',headers=headers).status_code==403
    assert client.get('/api/v1/members',headers=headers).status_code==403
    assert client.post('/api/v1/tenants',headers=headers,json={'name':'forbidden'}).status_code==403


def test_rc5_secondary_admin_accounts_are_demoted_on_upgrade():
    legacy_raw='legacy-secondary-admin-token-with-32chars'
    db=sqlite3.connect(os.environ['DAEP_DB_PATH'])
    db.execute('INSERT INTO members(id,name,role,token,created_at,tenant_id,token_status) VALUES(?,?,?,?,?,?,?)',
               ('legacy-admin','Legacy secondary admin','admin',hashlib.sha256(legacy_raw.encode()).hexdigest(),'2026-01-01T00:00:00+00:00','tenant-default','ACTIVE'))
    db.commit(); db.close()
    from app.main import init
    init()
    headers={'Authorization':f'Bearer {legacy_raw}'}
    assert client.get('/api/v1/me',headers=headers).status_code==200
    assert client.get('/api/v1/tenants',headers=headers).status_code==403
    db=sqlite3.connect(os.environ['DAEP_DB_PATH'])
    role=db.execute("SELECT role FROM members WHERE id='legacy-admin'").fetchone()[0]
    db.close()
    assert role=='manager'

def test_rc8_alembic_head_and_rls_migration_contract():
    from pathlib import Path
    import subprocess
    root=Path(__file__).resolve().parents[1]
    heads=subprocess.check_output(['alembic','heads'],cwd=root,text=True)
    assert '0015_rc12_outbox_lease_token (head)' in heads
    migration=(root/'alembic/versions/0010_rc8_postgres_rls.py').read_text()
    assert 'FORCE ROW LEVEL SECURITY' in migration
    assert 'app.tenant_id' in migration
    assert 'WITH CHECK' in migration


def test_rc8_messages_have_explicit_tenant_ownership():
    import sqlite3, app.main as module
    with module.conn() as c:
        cols={r['name'] for r in c.execute('PRAGMA table_info(messages)').fetchall()}
    assert 'tenant_id' in cols

def test_rc8_git_webhook_requires_tenant_for_unscoped_events():
    import app.main as module
    old=module.os.environ.get('DAEP_GIT_WEBHOOK_SECRET')
    module.os.environ['DAEP_GIT_WEBHOOK_SECRET']='git-secret-rc8'
    try:
        missing=client.post('/api/v1/integrations/git/webhook',headers={'X-DAEP-Webhook-Secret':'git-secret-rc8'},json={'event_type':'push','commit_sha':'abc'})
        assert missing.status_code==422
        tenant=client.post('/api/v1/tenants',headers=ADMIN,json={'name':'Git Tenant'}).json()['id']
        accepted=client.post('/api/v1/integrations/git/webhook',headers={'X-DAEP-Webhook-Secret':'git-secret-rc8','X-DAEP-Tenant-ID':tenant},json={'event_type':'push','commit_sha':'abc'})
        assert accepted.status_code==200 and accepted.json()['tenant_id']==tenant
    finally:
        if old is None: module.os.environ.pop('DAEP_GIT_WEBHOOK_SECRET',None)
        else: module.os.environ['DAEP_GIT_WEBHOOK_SECRET']=old
