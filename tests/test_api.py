import os, tempfile, hashlib, sqlite3, json
os.environ['DAEP_DB_PATH']=os.path.join(tempfile.gettempdir(),'daep-test-suite-v3.db')
os.environ['DAEP_ADMIN_TOKEN']='test-admin-token-with-32-characters-minimum'
os.environ['DAEP_WORKER_TOKEN']='test-worker-token-with-32-characters-minimum'
try: os.remove(os.environ['DAEP_DB_PATH'])
except FileNotFoundError: pass
from fastapi.testclient import TestClient
from app.main import app, init
import app.main as main_module
init()
client=TestClient(app)
ADMIN={'Authorization':'Bearer test-admin-token-with-32-characters-minimum'}
WORKER={'Authorization':'Bearer test-worker-token-with-32-characters-minimum'}

def test_health():
    assert client.get('/health').json()['status']=='ok'
    assert client.get('/readyz').json()['status']=='ready'

def test_readiness_does_not_leak_database_exception(monkeypatch):
    def fail_conn():
        raise RuntimeError('postgres://secret-password@db/daep')
    monkeypatch.setattr(main_module,'conn',fail_conn)
    response=client.get('/readyz')
    assert response.status_code==503
    assert 'secret-password' not in response.text
    assert 'readiness check failed' in response.text

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
    duplicate=client.post('/api/v1/messages/'+msg.json()['id']+'/ack',headers=nh,json={'status':'ACKNOWLEDGED'})
    assert duplicate.status_code==200 and duplicate.json()['idempotent'] is True
    conflict=client.post('/api/v1/messages/'+msg.json()['id']+'/ack',headers=nh,json={'status':'REJECTED'})
    assert conflict.status_code==409
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



def test_rc26_stage9_expired_outbox_lease_reclaims_and_rejects_stale_worker():
    import sqlite3
    _,member_id,member_token,task_id=setup_project_task()
    sent=client.post('/api/v1/messages',headers=ADMIN,json={
        'recipient_member_id':member_id,'task_id':task_id,
        'title':'Lease recovery','content':'Recover after worker interruption'})
    assert sent.status_code==200
    first_claim=client.post('/internal/v1/outbox/claim',headers=WORKER,json={
        'worker_id':'worker-interrupted','lease_seconds':30,'limit':100})
    assert first_claim.status_code==200
    item=next(x for x in first_claim.json()['items']
              if x['payload'].get('message_id')==sent.json()['id'])
    old_token=item['lease_token']

    # Simulate process death after claim: the lease expires without completion.
    db=sqlite3.connect(os.environ['DAEP_DB_PATH'])
    db.execute("UPDATE outbox SET lease_until='2000-01-01T00:00:00+00:00' WHERE id=?",(item['id'],))
    db.commit();db.close()

    second_claim=client.post('/internal/v1/outbox/claim',headers=WORKER,json={
        'worker_id':'worker-recovery','lease_seconds':30,'limit':100})
    assert second_claim.status_code==200
    recovered=next(x for x in second_claim.json()['items'] if x['id']==item['id'])
    assert recovered['attempts']==item['attempts']+1
    assert recovered['lease_token']!=old_token

    stale=client.post(f"/internal/v1/outbox/{item['id']}/complete",headers=WORKER,json={
        'worker_id':'worker-interrupted','lease_token':old_token})
    assert stale.status_code==409
    completed=client.post(f"/internal/v1/outbox/{item['id']}/complete",headers=WORKER,json={
        'worker_id':'worker-recovery','lease_token':recovered['lease_token']})
    assert completed.status_code==200 and completed.json()['status']=='SENT'
    duplicate=client.post(f"/internal/v1/outbox/{item['id']}/complete",headers=WORKER,json={
        'worker_id':'worker-recovery','lease_token':recovered['lease_token']})
    assert duplicate.status_code==409

    inbox=client.get('/api/v1/me/notifications',headers={'Authorization':'Bearer '+member_token})
    assert inbox.status_code==200
    assert sum(1 for x in inbox.json()['items'] if x['id']==sent.json()['id'])==1


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
    assert '0022_rc20_approvals (head)' in heads
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


def test_dead_letter_operator_replay_is_audited_and_admin_only():
    import sqlite3
    _,mid,_,tid=setup_project_task()
    sent=client.post('/api/v1/messages',headers=ADMIN,json={'recipient_member_id':mid,'task_id':tid,'title':'Dead letter','content':'recover me'})
    assert sent.status_code==200
    db=sqlite3.connect(os.environ['DAEP_DB_PATH'])
    outbox_id=db.execute("SELECT id FROM outbox WHERE json_extract(payload,'$.message_id')=?",(sent.json()['id'],)).fetchone()[0]
    db.execute("UPDATE outbox SET status='DEAD',attempts=8,last_error='gateway unavailable' WHERE id=?",(outbox_id,))
    db.commit(); db.close()
    _,_,member_token,_=setup_project_task()
    member_headers={'Authorization':f'Bearer {member_token}'}
    assert client.get('/api/v1/admin/outbox/dead',headers=member_headers).status_code==403
    listing=client.get('/api/v1/admin/outbox/dead',headers=ADMIN)
    assert listing.status_code==200 and any(x['id']==outbox_id for x in listing.json()['items'])
    missing_reason=client.post(f'/api/v1/admin/outbox/{outbox_id}/replay',headers=ADMIN,json={})
    assert missing_reason.status_code==422
    replay=client.post(f'/api/v1/admin/outbox/{outbox_id}/replay',headers=ADMIN,json={'reason':'Broker credentials rotated'})
    assert replay.status_code==200 and replay.json()['status']=='PENDING'
    db=sqlite3.connect(os.environ['DAEP_DB_PATH'])
    row=db.execute("SELECT status,attempts,lease_token,last_error FROM outbox WHERE id=?",(outbox_id,)).fetchone()
    audit=db.execute("SELECT payload FROM events WHERE event_type='outbox.dead.replayed' ORDER BY created_at DESC LIMIT 1").fetchone()
    db.close()
    assert row==('PENDING',0,None,None)
    assert json.loads(audit[0])['reason']=='Broker credentials rotated'
    duplicate=client.post(f'/api/v1/admin/outbox/{outbox_id}/replay',headers=ADMIN,json={'reason':'duplicate'})
    assert duplicate.status_code==409


def test_websocket_can_resume_from_client_cursor():
    _,mid,token,tid=setup_project_task()
    first=client.post('/api/v1/messages',headers=ADMIN,json={'recipient_member_id':mid,'task_id':tid,'title':'Cursor one','content':'one'}).json()
    second=client.post('/api/v1/messages',headers=ADMIN,json={'recipient_member_id':mid,'task_id':tid,'title':'Cursor two','content':'two'}).json()
    headers={'Authorization':f'Bearer {token}'}
    inbox=client.get('/api/v1/me/notifications',headers=headers).json()
    seqs={x['id']:x['seq'] for x in inbox['items']}
    with client.websocket_connect(f"/ws/v1?token={token}&after={seqs[first['id']]}") as ws:
        connected=ws.receive_json()
        assert connected['type']=='connected' and connected['cursor']==seqs[first['id']]
        event=ws.receive_json()
        assert event['type']=='notification' and event['message']['id']==second['id']


def test_project_agent_registry_is_member_scoped_and_discoverable():
    pid,_,member_token,_=setup_project_task()
    headers={'Authorization':f'Bearer {member_token}'}
    registered=client.post(f'/api/v1/projects/{pid}/agents/register',headers=headers,json={
        'agent_name':'local-coder','capabilities':['python','code-review','python'],
        'protocols':['mcp'],'status':'AVAILABLE','metadata':{'host':'workstation-1'}})
    assert registered.status_code==200
    agent=registered.json()
    assert agent['capabilities']==['code-review','python'] and agent['protocols']==['mcp']
    duplicate=client.post(f'/api/v1/projects/{pid}/agents/register',headers=headers,json={
        'agent_name':'local-coder','capabilities':['python','testing'],'protocols':['mcp'],'status':'BUSY'})
    assert duplicate.status_code==200 and duplicate.json()['id']==agent['id']
    found=client.get(f'/api/v1/projects/{pid}/agents?capability=testing&protocol=mcp',headers=headers)
    assert found.status_code==200 and found.json()['count']==1
    assert found.json()['items'][0]['status']=='BUSY'
    heartbeat=client.post(f'/api/v1/projects/{pid}/agents/heartbeat',headers=headers,json={'agent_name':'local-coder','status':'AVAILABLE'})
    assert heartbeat.status_code==200 and heartbeat.json()['status']=='AVAILABLE'
    filtered=client.get(f'/api/v1/projects/{pid}/agents?capability=missing',headers=headers)
    assert filtered.status_code==200 and filtered.json()['count']==0


def test_project_agent_registry_rejects_nonmember_and_invalid_protocol():
    pid,_,member_token,_=setup_project_task()
    outsider=client.post('/api/v1/members',headers=ADMIN,json={'name':'Agent outsider'}).json()
    oh={'Authorization':f"Bearer {outsider['token']}"}
    denied=client.post(f'/api/v1/projects/{pid}/agents/register',headers=oh,json={'agent_name':'intruder','protocols':['mcp']})
    assert denied.status_code==403
    mh={'Authorization':f'Bearer {member_token}'}
    invalid=client.post(f'/api/v1/projects/{pid}/agents/register',headers=mh,json={'agent_name':'bad-agent','protocols':[]})
    assert invalid.status_code==422
    missing=client.post(f'/api/v1/projects/{pid}/agents/heartbeat',headers=mh,json={'agent_name':'not-registered'})
    assert missing.status_code==404

def test_rc14_task_delegation_accept_reject_and_audit():
    pid,requester_id,requester_token,tid=setup_project_task()
    recipient=client.post('/api/v1/members',headers=ADMIN,json={'name':'Delegation Recipient'}).json()
    assert client.post(f'/api/v1/projects/{pid}/members',headers=ADMIN,json={'member_id':recipient['id'],'role':'member'}).status_code==200
    rh={'Authorization':'Bearer '+recipient['token']}
    registered=client.post(f'/api/v1/projects/{pid}/agents/register',headers=rh,json={
        'agent_name':'local-coder','capabilities':['python'],'protocols':['mcp'],'status':'AVAILABLE'})
    assert registered.status_code==200
    qh={'Authorization':'Bearer '+requester_token}
    offered=client.post(f'/api/v1/tasks/{tid}/delegations',headers=qh,json={
        'recipient_member_id':recipient['id'],'agent_name':'local-coder','reason':'Implement the API client'})
    assert offered.status_code==200 and offered.json()['status']=='PENDING'
    inbox=client.get('/api/v1/me/notifications',headers=rh).json()['items']
    assert any(x['id']==offered.json()['message_id'] and x['message_type']=='TASK_DELEGATION' for x in inbox)
    accepted=client.post(f"/api/v1/delegations/{offered.json()['id']}/respond",headers=rh,json={'decision':'ACCEPT'})
    assert accepted.status_code==200 and accepted.json()['status']=='ACCEPTED'
    detail=client.get(f'/api/v1/tasks/{tid}',headers=qh).json()
    assert any(x['id']==recipient['id'] for x in detail['assignees'])
    history=client.get(f'/api/v1/tasks/{tid}/delegations',headers=qh).json()
    assert history[0]['status']=='ACCEPTED'
    events=client.get(f'/api/v1/tasks/{tid}/events',headers=qh).json()
    assert any(x['event_type']=='task.delegation.offered' for x in events)
    assert any(x['event_type']=='task.delegation.accepted' for x in events)
    rejected_offer=client.post(f'/api/v1/tasks/{tid}/delegations',headers=qh,json={
        'recipient_member_id':recipient['id'],'agent_name':'local-coder','reason':'Second work package'})
    assert rejected_offer.status_code==200
    rejected=client.post(f"/api/v1/delegations/{rejected_offer.json()['id']}/respond",headers=rh,json={'decision':'REJECT'})
    assert rejected.status_code==200 and rejected.json()['status']=='REJECTED'


def test_rc15_work_packages_progress_blockers_and_artifact_aggregation():
    pid,owner_id,owner_token,parent_id=setup_project_task()
    recipient=client.post('/api/v1/members',headers=ADMIN,json={'name':'Work Package Agent'}).json()
    assert client.post(f'/api/v1/projects/{pid}/members',headers=ADMIN,json={'member_id':recipient['id'],'role':'member'}).status_code==200
    rh={'Authorization':'Bearer '+recipient['token']}
    assert client.post(f'/api/v1/projects/{pid}/agents/register',headers=rh,json={
        'agent_name':'worker-python','capabilities':['python'],'protocols':['mcp'],'status':'AVAILABLE'}).status_code==200
    oh=ADMIN
    created=client.post(f'/api/v1/tasks/{parent_id}/work-packages',headers=oh,json={
        'title':'Implement API layer','description':'Build and test endpoints',
        'assignee_member_id':recipient['id'],'agent_name':'worker-python'})
    assert created.status_code==200,created.text
    package=created.json()
    inbox=client.get('/api/v1/me/notifications',headers=rh).json()['items']
    assert any(x['id']==package['message_id'] and x['message_type']=='WORK_PACKAGE_ASSIGNED' for x in inbox)
    summary=client.get(f'/api/v1/tasks/{parent_id}/work-summary',headers=oh).json()
    assert summary['work_package_count']==1 and summary['progress']==0
    child=package['task_id']
    assert client.post(f'/api/v1/tasks/{child}/progress',headers=rh,json={'progress':40,'note':'API scaffold'}).status_code==200
    summary=client.get(f'/api/v1/tasks/{parent_id}/work-summary',headers=oh).json()
    assert summary['progress']==40 and summary['status_counts']['IN_PROGRESS']==1
    assert client.post(f'/api/v1/tasks/{child}/artifacts',headers=rh,json={
        'artifact_type':'git_commit','uri':'https://github.com/example/repo/commit/abc123',
        'commit_sha':'abc123','metadata':{}}).status_code==200
    assert client.post(f'/api/v1/tasks/{child}/blocked',headers=rh,json={'reason':'Waiting for schema'}).status_code==200
    summary=client.get(f'/api/v1/tasks/{parent_id}/work-summary',headers=oh).json()
    assert summary['status_counts']['BLOCKED']==1 and summary['blocked_tasks'][0]['id']==child
    assert summary['artifact_count']==1
    listed=client.get(f'/api/v1/tasks/{parent_id}/work-packages',headers=oh).json()
    assert listed[0]['agent_name']=='worker-python' and len(listed[0]['artifacts'])==1
    events=client.get(f'/api/v1/tasks/{parent_id}/events',headers=oh).json()
    assert any(e['event_type']=='task.work_package.created' for e in events)

def test_rc15_work_package_rejects_offline_agent_and_cross_project_dependency():
    pid,_,owner_token,parent_id=setup_project_task()
    member=client.post('/api/v1/members',headers=ADMIN,json={'name':'Offline Agent'}).json()
    assert client.post(f'/api/v1/projects/{pid}/members',headers=ADMIN,json={'member_id':member['id'],'role':'member'}).status_code==200
    h={'Authorization':'Bearer '+member['token']}
    assert client.post(f'/api/v1/projects/{pid}/agents/register',headers=h,json={
        'agent_name':'offline','capabilities':[],'protocols':['mcp'],'status':'OFFLINE'}).status_code==200
    res=client.post(f'/api/v1/tasks/{parent_id}/work-packages',headers=ADMIN,json={
        'title':'Should fail','assignee_member_id':member['id'],'agent_name':'offline'})
    assert res.status_code==409



def test_rc16_work_package_result_requires_artifact_and_parent_approval_gate():
    pid,_,owner_token,parent_id=setup_project_task()
    owner_headers={'Authorization':'Bearer '+owner_token}
    recipient=client.post('/api/v1/members',headers=ADMIN,json={'name':'RC16 Result Agent'}).json()
    assert client.post(f'/api/v1/projects/{pid}/members',headers=ADMIN,json={'member_id':recipient['id'],'role':'member'}).status_code==200
    rh={'Authorization':'Bearer '+recipient['token']}
    assert client.post(f'/api/v1/projects/{pid}/agents/register',headers=rh,json={
        'agent_name':'result-agent','capabilities':['python'],'protocols':['mcp'],'status':'AVAILABLE'}).status_code==200
    created=client.post(f'/api/v1/tasks/{parent_id}/work-packages',headers=ADMIN,json={
        'title':'Implement feature','assignee_member_id':recipient['id'],'agent_name':'result-agent'})
    assert created.status_code==200
    child=created.json()['task_id']
    no_artifact=client.post(f'/api/v1/tasks/{child}/work-result',headers=rh,json={
        'outcome':'COMPLETE','summary':'Implementation finished','idempotency_key':'result-1'})
    assert no_artifact.status_code==409
    artifact=client.post(f'/api/v1/tasks/{child}/artifacts',headers=rh,json={
        'artifact_type':'git_commit','uri':'https://github.com/example/repo/commit/def456',
        'commit_sha':'def456','metadata':{}})
    assert artifact.status_code==200
    reported=client.post(f'/api/v1/tasks/{child}/work-result',headers=rh,json={
        'outcome':'COMPLETE','summary':'Implementation and tests finished','idempotency_key':'result-1'})
    assert reported.status_code==200 and reported.json()['status']=='REVIEW'
    replay=client.post(f'/api/v1/tasks/{child}/work-result',headers=rh,json={
        'outcome':'COMPLETE','summary':'Implementation and tests finished','idempotency_key':'result-1'})
    assert replay.status_code==200 and replay.json()['idempotent_replay'] is True
    assert client.post(f'/api/v1/tasks/{parent_id}/progress',headers=owner_headers,json={'progress':100,'note':'Ready for review'}).status_code==200
    parent_blocked=client.post(f'/api/v1/tasks/{parent_id}/review',headers=ADMIN,json={'decision':'APPROVE'})
    assert parent_blocked.status_code==409
    child_approved=client.post(f'/api/v1/tasks/{child}/review',headers=ADMIN,json={'decision':'APPROVE'})
    assert child_approved.status_code==200 and child_approved.json()['status']=='DONE'
    parent_approved=client.post(f'/api/v1/tasks/{parent_id}/review',headers=ADMIN,json={'decision':'APPROVE'})
    assert parent_approved.status_code==200 and parent_approved.json()['status']=='DONE'
    summary=client.get(f'/api/v1/tasks/{parent_id}/work-summary',headers=ADMIN).json()
    assert summary['all_done'] is True and summary['artifact_count']==1
    assert summary['artifacts'][0]['commit_sha']=='def456'


def test_rc16_failed_work_package_becomes_blocked():
    pid,_,_,parent_id=setup_project_task()
    recipient=client.post('/api/v1/members',headers=ADMIN,json={'name':'RC16 Failed Agent'}).json()
    assert client.post(f'/api/v1/projects/{pid}/members',headers=ADMIN,json={'member_id':recipient['id'],'role':'member'}).status_code==200
    rh={'Authorization':'Bearer '+recipient['token']}
    assert client.post(f'/api/v1/projects/{pid}/agents/register',headers=rh,json={
        'agent_name':'failure-agent','protocols':['mcp'],'status':'AVAILABLE'}).status_code==200
    created=client.post(f'/api/v1/tasks/{parent_id}/work-packages',headers=ADMIN,json={
        'title':'Potential failure','assignee_member_id':recipient['id'],'agent_name':'failure-agent'})
    assert created.status_code==200
    child=created.json()['task_id']
    failed=client.post(f'/api/v1/tasks/{child}/work-result',headers=rh,json={
        'outcome':'FAILED','summary':'External dependency unavailable'})
    assert failed.status_code==200 and failed.json()['status']=='BLOCKED'
    detail=client.get(f'/api/v1/tasks/{child}',headers=ADMIN).json()
    assert detail['status']=='BLOCKED'


def test_rc17_stalled_work_package_requires_manager_reassignment_and_notifies_new_agent():
    pid,_,_,parent_id=setup_project_task()
    old_member=client.post('/api/v1/members',headers=ADMIN,json={'name':'Stalled Agent'}).json()
    new_member=client.post('/api/v1/members',headers=ADMIN,json={'name':'Replacement Agent'}).json()
    for member,name in ((old_member,'old-agent'),(new_member,'replacement-agent')):
        h={'Authorization':'Bearer '+member['token']}
        assert client.post(f'/api/v1/projects/{pid}/members',headers=ADMIN,json={'member_id':member['id'],'role':'member'}).status_code==200
        assert client.post(f'/api/v1/projects/{pid}/agents/register',headers=h,json={
            'agent_name':name,'capabilities':['python'],'protocols':['mcp'],'status':'AVAILABLE'}).status_code==200
    created=client.post(f'/api/v1/tasks/{parent_id}/work-packages',headers=ADMIN,json={
        'title':'Stalled implementation','assignee_member_id':old_member['id'],'agent_name':'old-agent'})
    assert created.status_code==200
    package_id=created.json()['id']; child=created.json()['task_id']
    db=sqlite3.connect(os.environ['DAEP_DB_PATH'])
    db.execute("UPDATE tasks SET updated_at='2000-01-01T00:00:00+00:00' WHERE id=?",(child,))
    db.commit(); db.close()
    premature=client.post(f'/api/v1/work-packages/{package_id}/reassign',headers=ADMIN,json={
        'assignee_member_id':new_member['id'],'agent_name':'replacement-agent','reason':'Not yet reviewed'})
    assert premature.status_code==409
    scanned=client.post(f'/api/v1/projects/{pid}/work-packages/scan-stalled',headers=ADMIN,json={'stale_after_seconds':300})
    assert scanned.status_code==200 and scanned.json()['marked_count']==1
    assert scanned.json()['items'][0]['child_task_id']==child
    repeated=client.post(f'/api/v1/projects/{pid}/work-packages/scan-stalled',headers=ADMIN,json={'stale_after_seconds':300})
    assert repeated.status_code==200 and repeated.json()['marked_count']==0
    reassigned=client.post(f'/api/v1/work-packages/{package_id}/reassign',headers=ADMIN,json={
        'assignee_member_id':new_member['id'],'agent_name':'replacement-agent','reason':'Original Agent has been inactive'})
    assert reassigned.status_code==200 and reassigned.json()['needs_attention'] is False
    detail=client.get(f'/api/v1/tasks/{child}',headers=ADMIN).json()
    assert any(x['id']==new_member['id'] for x in detail['assignees'])
    assert not any(x['id']==old_member['id'] for x in detail['assignees'])
    inbox=client.get('/api/v1/me/notifications',headers={'Authorization':'Bearer '+new_member['token']}).json()['items']
    assert any(x['message_type']=='WORK_PACKAGE_REASSIGNED' and x['task_id']==child for x in inbox)
    packages=client.get(f'/api/v1/tasks/{parent_id}/work-packages',headers=ADMIN).json()
    row=next(x for x in packages if x['id']==package_id)
    assert row['assignee_member_id']==new_member['id'] and row['needs_attention']==0 and row['stalled_at'] is None
    events=client.get(f'/api/v1/tasks/{parent_id}/events',headers=ADMIN).json()
    assert any(x['event_type']=='task.work_package.stalled' for x in events)
    assert any(x['event_type']=='task.work_package.reassigned' for x in events)


def test_rc18_work_timeline_correlates_assignment_result_and_artifact():
    pid,owner_id,owner_token,parent_id=setup_project_task()
    owner_headers={'Authorization':'Bearer '+owner_token}
    member=client.post('/api/v1/members',headers=ADMIN,json={'name':'Timeline Agent'}).json()
    assert client.post(f'/api/v1/projects/{pid}/members',headers=ADMIN,json={'member_id':member['id'],'role':'member'}).status_code==200
    mh={'Authorization':'Bearer '+member['token']}
    assert client.post(f'/api/v1/projects/{pid}/agents/register',headers=mh,json={'agent_name':'timeline-agent','protocols':['mcp'],'status':'AVAILABLE'}).status_code==200
    recipient=client.post('/api/v1/members',headers=ADMIN,json={'name':'Timeline Recipient'}).json()
    assert client.post(f'/api/v1/projects/{pid}/members',headers=ADMIN,json={'member_id':recipient['id'],'role':'member'}).status_code==200
    rh={'Authorization':'Bearer '+recipient['token']}
    assert client.post(f'/api/v1/projects/{pid}/agents/register',headers=rh,json={'agent_name':'recipient-agent','protocols':['mcp'],'status':'AVAILABLE'}).status_code==200
    prerequisite=client.post('/api/v1/tasks',headers=ADMIN,json={'requirement_id':client.get(f'/api/v1/tasks/{parent_id}',headers=ADMIN).json()['requirement_id'],'title':'Timeline prerequisite','assignee_member_ids':[owner_id]})
    assert prerequisite.status_code==200
    created=client.post(f'/api/v1/tasks/{parent_id}/work-packages',headers=ADMIN,json={'title':'Timeline package','assignee_member_id':member['id'],'agent_name':'timeline-agent','dependencies':[prerequisite.json()['id']]})
    assert created.status_code==200
    package=created.json(); child=package['task_id']; cid=package['correlation_id']
    assert cid.startswith('corr_')
    offer=client.post(f'/api/v1/tasks/{parent_id}/delegations',headers=owner_headers,json={'recipient_member_id':recipient['id'],'agent_name':'recipient-agent','reason':'Cross-member review'})
    assert offer.status_code==200
    decision=client.post(f'/api/v1/delegations/{offer.json()["id"]}/respond',headers=rh,json={'decision':'ACCEPT'})
    assert decision.status_code==200 and decision.json()['status']=='ACCEPTED'
    assert client.post(f'/api/v1/tasks/{child}/artifacts',headers=mh,json={'artifact_type':'git_commit','uri':'https://github.com/example/repo/commit/abc123','commit_sha':'abc123','metadata':{}}).status_code==200
    assert client.post(f'/api/v1/tasks/{child}/work-result',headers=mh,json={'outcome':'COMPLETE','summary':'Completed with artifact','idempotency_key':'timeline-result'}).status_code==200
    timeline=client.get(f'/api/v1/tasks/{parent_id}/work-timeline',headers=ADMIN)
    assert timeline.status_code==200
    body=timeline.json()
    assert body['work_packages'][0]['correlation_id']==cid
    assert any(x['kind']=='message' and x['correlation_id']==cid for x in body['items'])
    assert any(x['kind']=='artifact' and x['correlation_id']==cid for x in body['items'])
    assert any(x['kind']=='delegation' and x['stage']=='OFFERED' for x in body['items'])
    assert any(x['kind']=='delegation' and x['stage']=='ACCEPTED' for x in body['items'])
    assert body['delegations'][0]['requester_name']
    assert body['delegations'][0]['recipient_name']=='Timeline Recipient'
    assert any(x['task_id']==child and x['blocked'] for x in body['dependency_edges'])
    reported=next(x for x in body['items'] if x.get('event_type')=='task.work_package.reported')
    assert reported['payload']['correlation_id']==cid



def test_rc26_stage4_work_package_review_reject_and_approve_gate():
    pid,member_id,token,parent_id=setup_project_task()
    mh={'Authorization':'Bearer '+token}
    assert client.post(f'/api/v1/projects/{pid}/agents/register',headers=mh,json={'agent_name':'stage4-agent','protocols':['mcp'],'status':'AVAILABLE'}).status_code==200
    created=client.post(f'/api/v1/tasks/{parent_id}/work-packages',headers=ADMIN,json={'title':'Reviewable package','description':'stage4','assignee_member_id':member_id,'agent_name':'stage4-agent'})
    assert created.status_code==200
    package=created.json()
    child=package['task_id']
    assert client.post(f'/api/v1/tasks/{child}/artifacts',headers=mh,json={'artifact_type':'git_commit','uri':'https://example.invalid/commit/stage4','commit_sha':'stage4','metadata':{}}).status_code==200
    assert client.post(f'/api/v1/tasks/{child}/work-result',headers=mh,json={'outcome':'COMPLETE','summary':'ready','idempotency_key':'stage4-result'}).status_code==200
    rejected=client.post(f'/api/v1/work-packages/{package["id"]}/review',headers=ADMIN,json={'decision':'REJECT','comment':'Please address review feedback'})
    assert rejected.status_code==200 and rejected.json()['status']=='IN_PROGRESS'
    assert client.get(f'/api/v1/tasks/{child}',headers=ADMIN).json()['status']=='IN_PROGRESS'
    assert client.post(f'/api/v1/tasks/{child}/progress',headers=mh,json={'progress':100,'note':'resubmitted'}).status_code==200
    approved=client.post(f'/api/v1/work-packages/{package["id"]}/review',headers=ADMIN,json={'decision':'APPROVE','comment':'Accepted'})
    assert approved.status_code==200 and approved.json()['status']=='DONE'
    assert client.get(f'/api/v1/tasks/{child}',headers=ADMIN).json()['status']=='DONE'
    outsider=client.post('/api/v1/members',headers=ADMIN,json={'name':'Stage4 outsider'}).json()
    forbidden=client.post(f'/api/v1/work-packages/{package["id"]}/review',headers={'Authorization':'Bearer '+outsider['token']},json={'decision':'APPROVE'})
    assert forbidden.status_code==403



def test_rc26_stage5_coordination_center_collects_unclaimed_reviews_and_exceptions():
    pid,member_id,token,parent_id=setup_project_task()
    db=sqlite3.connect(os.environ['DAEP_DB_PATH'])
    req_id=db.execute('SELECT requirement_id FROM tasks WHERE id=?',(parent_id,)).fetchone()[0]
    db.close()
    unclaimed=client.post('/api/v1/tasks',headers=ADMIN,json={'requirement_id':req_id,'title':'Unclaimed follow-up','assignee_member_ids':[]})
    assert unclaimed.status_code==200
    mh={'Authorization':'Bearer '+token}
    assert client.post(f'/api/v1/projects/{pid}/agents/register',headers=mh,json={'agent_name':'coord-agent','protocols':['mcp'],'status':'AVAILABLE'}).status_code==200
    package=client.post(f'/api/v1/tasks/{parent_id}/work-packages',headers=ADMIN,json={'title':'Stalled coordination package','assignee_member_id':member_id,'agent_name':'coord-agent'})
    assert package.status_code==200
    db=sqlite3.connect(os.environ['DAEP_DB_PATH'])
    db.execute("UPDATE task_work_packages SET needs_attention=1,risk_state='STALLED',stall_reason='coordination test' WHERE id=?",(package.json()['id'],))
    db.commit();db.close()
    report=client.get(f'/api/v1/projects/{pid}/coordination',headers=ADMIN)
    assert report.status_code==200
    body=report.json()
    assert any(x['task_id']==unclaimed.json()['id'] for x in body['unclaimed_tasks'])
    assert any(x['work_package_id']==package.json()['id'] and x['stall_reason']=='coordination test' for x in body['exception_work_packages'])
    assert body['counts']['unclaimed_tasks']==1
    outsider=client.post('/api/v1/members',headers=ADMIN,json={'name':'Coordination outsider'}).json()
    assert client.get(f'/api/v1/projects/{pid}/coordination',headers={'Authorization':'Bearer '+outsider['token']}).status_code==403


def test_rc19_project_health_detects_sla_overdue_and_dependency_blockers():
    pid,member_id,token,parent_id=setup_project_task()
    db=sqlite3.connect(os.environ['DAEP_DB_PATH'])
    req_id=db.execute('SELECT requirement_id FROM tasks WHERE id=?',(parent_id,)).fetchone()[0]
    db.close()
    dep=client.post('/api/v1/tasks',headers=ADMIN,json={'requirement_id':req_id,'title':'External prerequisite','assignee_member_ids':[member_id]})
    assert dep.status_code==200
    mh={'Authorization':'Bearer '+token}
    assert client.post(f'/api/v1/projects/{pid}/agents/register',headers=mh,json={'agent_name':'health-agent','protocols':['mcp'],'status':'AVAILABLE'}).status_code==200
    overdue=client.post(f'/api/v1/tasks/{parent_id}/work-packages',headers=ADMIN,json={'title':'SLA package','assignee_member_id':member_id,'agent_name':'health-agent','sla_seconds':300})
    blocked=client.post(f'/api/v1/tasks/{parent_id}/work-packages',headers=ADMIN,json={'title':'Dependent package','assignee_member_id':member_id,'agent_name':'health-agent','dependencies':[dep.json()['id']]})
    assert overdue.status_code==200 and blocked.status_code==200
    db=sqlite3.connect(os.environ['DAEP_DB_PATH'])
    db.execute("UPDATE task_work_packages SET sla_due_at='2000-01-01T00:00:00+00:00' WHERE id=?",(overdue.json()['id'],))
    db.commit();db.close()
    scan=client.post(f'/api/v1/projects/{pid}/work-packages/scan-health',headers=ADMIN)
    assert scan.status_code==200
    assert scan.json()['risk_counts']['OVERDUE']==1
    assert scan.json()['risk_counts']['BLOCKED_DEPENDENCY']==1
    report=client.get(f'/api/v1/projects/{pid}/work-health',headers=ADMIN)
    assert report.status_code==200
    assert report.json()['at_risk_count']==2 and report.json()['health_score']==0
    assert any(x['blocking_dependencies'] for x in report.json()['items'])
    outsider=client.post('/api/v1/members',headers=ADMIN,json={'name':'Health outsider'}).json()
    assert client.get(f'/api/v1/projects/{pid}/work-health',headers={'Authorization':'Bearer '+outsider['token']}).status_code==403


def test_rc20_role_change_requires_independent_owner_approval_and_audit_export():
    pid,member_id,token,parent_id=setup_project_task()
    owner=client.post('/api/v1/members',headers=ADMIN,json={'name':'Second project owner'}).json()
    assert client.post(f'/api/v1/projects/{pid}/members',headers=ADMIN,json={'member_id':owner['id'],'role':'member'}).status_code==200
    # Promote second member to owner only in the test fixture to exercise independent approval authority.
    db=sqlite3.connect(os.environ['DAEP_DB_PATH'])
    db.execute("UPDATE project_members SET role='owner' WHERE project_id=? AND member_id=?",(pid,owner['id']))
    db.commit();db.close()
    req=client.post(f'/api/v1/projects/{pid}/role-change-requests',headers=ADMIN,json={'member_id':member_id,'new_role':'manager','reason':'Needs manager permissions'})
    assert req.status_code==200
    approval_id=req.json()['approval_id']
    self_approve=client.post(f'/api/v1/projects/{pid}/approvals/{approval_id}/decision',headers=ADMIN,json={'decision':'APPROVE','reason':'Not allowed'})
    assert self_approve.status_code==403
    owner_h={'Authorization':'Bearer '+owner['token']}
    nonowner=client.post(f'/api/v1/projects/{pid}/approvals/{approval_id}/decision',headers={'Authorization':'Bearer '+token},json={'decision':'APPROVE','reason':'Not an owner'})
    assert nonowner.status_code==403
    approved=client.post(f'/api/v1/projects/{pid}/approvals/{approval_id}/decision',headers=owner_h,json={'decision':'APPROVE','reason':'Approved for project governance'})
    assert approved.status_code==200 and approved.json()['status']=='APPROVED'
    members=client.get(f'/api/v1/projects/{pid}/members',headers=ADMIN).json()
    assert next(x for x in members if x['id']==member_id)['project_role']=='manager'
    third=client.post('/api/v1/members',headers=ADMIN,json={'name':'Third project member'}).json()
    assert client.post(f'/api/v1/projects/{pid}/members',headers=ADMIN,json={'member_id':third['id'],'role':'member'}).status_code==200
    manager_h={'Authorization':'Bearer '+token}
    forbidden_grant=client.post(f'/api/v1/projects/{pid}/members',headers=manager_h,json={'member_id':third['id'],'role':'manager'})
    assert forbidden_grant.status_code==403
    rejected_req=client.post(f'/api/v1/projects/{pid}/role-change-requests',headers=manager_h,json={'member_id':third['id'],'new_role':'reviewer','reason':'Request reviewer access'})
    assert rejected_req.status_code==200
    rejected_id=rejected_req.json()['approval_id']
    rejected=client.post(f'/api/v1/projects/{pid}/approvals/{rejected_id}/decision',headers=owner_h,json={'decision':'REJECT','reason':'Not required at this time'})
    assert rejected.status_code==200 and rejected.json()['status']=='REJECTED'
    audit=client.get(f'/api/v1/projects/{pid}/audit',headers=ADMIN)
    assert audit.status_code==200 and any(x['event_type']=='project.role_change.approved' for x in audit.json()['items'])
    csv=client.get(f'/api/v1/projects/{pid}/audit.csv',headers=ADMIN)
    assert csv.status_code==200 and 'text/csv' in csv.headers['content-type'] and 'project.role_change.approved' in csv.text
    outsider=client.post('/api/v1/members',headers=ADMIN,json={'name':'Audit outsider'}).json()
    assert client.get(f'/api/v1/projects/{pid}/audit',headers={'Authorization':'Bearer '+outsider['token']}).status_code==403


def test_rc25_dependency_updates_enforce_project_scope_and_prevent_cycles():
    pid, member_id, member_token, first_id = setup_project_task()
    db=sqlite3.connect(os.environ['DAEP_DB_PATH'])
    req_id=db.execute('SELECT requirement_id FROM tasks WHERE id=?',(first_id,)).fetchone()[0]
    db.close()
    second=client.post('/api/v1/tasks',headers=ADMIN,json={'requirement_id':req_id,'title':'Second task','dependencies':[first_id]})
    assert second.status_code==200
    second_id=second.json()['id']
    listed=client.get(f'/api/v1/projects/{pid}/tasks',headers=ADMIN)
    assert listed.status_code==200
    assert next(x for x in listed.json() if x['id']==second_id)['dependencies']==[first_id]

    cycle=client.put(f'/api/v1/tasks/{first_id}/dependencies',headers=ADMIN,json={'dependencies':[second_id]})
    assert cycle.status_code==409 and 'cycle' in cycle.json()['detail'].lower()
    self_link=client.put(f'/api/v1/tasks/{first_id}/dependencies',headers=ADMIN,json={'dependencies':[first_id]})
    assert self_link.status_code==400
    duplicate=client.put(f'/api/v1/tasks/{first_id}/dependencies',headers=ADMIN,json={'dependencies':[second_id,second_id]})
    assert duplicate.status_code==400

    outsider_role={'Authorization':'Bearer '+member_token}
    forbidden=client.put(f'/api/v1/tasks/{first_id}/dependencies',headers=outsider_role,json={'dependencies':[]})
    assert forbidden.status_code==403

    other_project=client.post('/api/v1/projects',headers=ADMIN,json={'name':'Separate project'}).json()
    other_req=client.post('/api/v1/requirements',headers=ADMIN,json={'project_id':other_project['id'],'title':'Separate requirement'}).json()
    other_task=client.post('/api/v1/tasks',headers=ADMIN,json={'requirement_id':other_req['id'],'title':'Other project task'}).json()
    cross=client.put(f'/api/v1/tasks/{first_id}/dependencies',headers=ADMIN,json={'dependencies':[other_task['id']]})
    assert cross.status_code==400

    saved=client.put(f'/api/v1/tasks/{first_id}/dependencies',headers=ADMIN,json={'dependencies':[]})
    assert saved.status_code==200 and saved.json()['dependencies']==[]
    with sqlite3.connect(os.environ['DAEP_DB_PATH']) as db:
        event_row=db.execute("SELECT COUNT(*) FROM events WHERE task_id=? AND event_type='task.dependencies.updated'",(first_id,)).fetchone()
    assert event_row[0]==1


def test_rc26_project_delegation_history_is_scoped_and_includes_member_names():
    pid, requester_id, requester_token, task_id = setup_project_task()
    recipient=client.post('/api/v1/members',headers=ADMIN,json={'name':'Topology Recipient'}).json()
    assert client.post(f'/api/v1/projects/{pid}/members',headers=ADMIN,json={'member_id':recipient['id'],'role':'member'}).status_code==200
    recipient_headers={'Authorization':'Bearer '+recipient['token']}
    assert client.post(f'/api/v1/projects/{pid}/agents/register',headers=recipient_headers,json={'agent_name':'topology-agent','protocols':['mcp'],'status':'AVAILABLE'}).status_code==200
    requester_headers={'Authorization':'Bearer '+requester_token}
    offer=client.post(f'/api/v1/tasks/{task_id}/delegations',headers=requester_headers,json={'recipient_member_id':recipient['id'],'agent_name':'topology-agent','reason':'Topology test'})
    assert offer.status_code==200
    response=client.post(f"/api/v1/delegations/{offer.json()['id']}/respond",headers=recipient_headers,json={'decision':'ACCEPT'})
    assert response.status_code==200
    history=client.get(f'/api/v1/projects/{pid}/delegations',headers=ADMIN)
    assert history.status_code==200
    item=history.json()['items'][0]
    assert item['id']==offer.json()['id']
    assert item['requester_name'] and item['recipient_name']=='Topology Recipient'
    assert item['task_title']=='Implement API'
    outsider=client.post('/api/v1/members',headers=ADMIN,json={'name':'Delegation Outsider'}).json()
    assert client.get(f'/api/v1/projects/{pid}/delegations',headers={'Authorization':'Bearer '+outsider['token']}).status_code==403
    limited=client.get(f'/api/v1/projects/{pid}/delegations?limit=0',headers=ADMIN)
    assert limited.status_code==200 and limited.json()['count']==1



def test_rc26_stage2_agent_matching_ranks_capabilities_and_presence_without_assignment():
    pid,member_id,member_token,task_id=setup_project_task()
    headers={'Authorization':'Bearer '+member_token}
    second=client.post('/api/v1/members',headers=ADMIN,json={'name':'Matching Member'}).json()
    assert client.post(f'/api/v1/projects/{pid}/members',headers=ADMIN,json={'member_id':second['id'],'role':'member'}).status_code==200
    second_headers={'Authorization':'Bearer '+second['token']}
    exact=client.post(f'/api/v1/projects/{pid}/agents/register',headers=headers,json={
        'agent_name':'full-match','capabilities':['python','testing'],'protocols':['mcp'],'status':'AVAILABLE'})
    partial=client.post(f'/api/v1/projects/{pid}/agents/register',headers=second_headers,json={
        'agent_name':'partial-match','capabilities':['python'],'protocols':['mcp'],'status':'AVAILABLE'})
    assert exact.status_code==200 and partial.status_code==200
    result=client.get(f'/api/v1/projects/{pid}/agent-matches?required_capabilities=python%2Ctesting&protocol=mcp',headers=headers)
    assert result.status_code==200
    data=result.json()
    assert data['eligible_count']==1 and data['recommendation_only'] is True and data['runtime_controlled'] is False
    assert data['items'][0]['agent_name']=='full-match' and data['items'][0]['eligible'] is True
    partial_item=next(x for x in data['items'] if x['agent_name']=='partial-match')
    assert partial_item['matched_capabilities']==['python']
    assert partial_item['missing_capabilities']==['testing'] and partial_item['eligible'] is False
    before=client.get(f'/api/v1/tasks/{task_id}',headers=headers).json()
    assert [x['id'] for x in before['assignees']]==[member_id]
    after=client.get(f'/api/v1/tasks/{task_id}',headers=headers).json()
    assert [x['id'] for x in after['assignees']]==[member_id]


def test_rc26_stage2_agent_matching_enforces_project_scope_and_input_bounds():
    pid,_,member_token,_=setup_project_task()
    headers={'Authorization':'Bearer '+member_token}
    outsider=client.post('/api/v1/members',headers=ADMIN,json={'name':'Matching outsider'}).json()
    denied=client.get(f'/api/v1/projects/{pid}/agent-matches?required_capabilities=python',headers={'Authorization':'Bearer '+outsider['token']})
    assert denied.status_code==403
    too_many=','.join(f'cap{i}' for i in range(51))
    invalid=client.get(f'/api/v1/projects/{pid}/agent-matches',params={'required_capabilities':too_many},headers=headers)
    assert invalid.status_code==422



def test_rc26_stage6_project_decisions_and_governance_snapshot_are_auditable_and_scoped():
    pid,member_id,member_token,task_id=setup_project_task()
    headers={'Authorization':'Bearer '+member_token}
    created=client.post(f'/api/v1/projects/{pid}/decisions',headers=ADMIN,json={
        'title':'Adopt MCP collaboration','decision':'Use MCP-compatible local Agents',
        'rationale':'Keep runtime ownership with each member','accountable_member_id':member_id,
        'related_task_ids':[task_id]})
    assert created.status_code==200, created.text
    assert created.json()['status']=='RECORDED'
    listed=client.get(f'/api/v1/projects/{pid}/decisions',headers=headers)
    assert listed.status_code==200 and listed.json()['count']==1
    decision=listed.json()['items'][0]
    assert decision['title']=='Adopt MCP collaboration'
    assert decision['accountable_member_id']==member_id
    assert decision['related_task_ids']==[task_id]
    governance=client.get(f'/api/v1/projects/{pid}/governance',headers=headers)
    assert governance.status_code==200
    snapshot=governance.json()
    assert snapshot['task_total']==1 and snapshot['open_tasks']==1
    assert snapshot['completion_gate']=='OPEN'
    assert snapshot['responsibility'][0]['member_id']==member_id
    outsider=client.post('/api/v1/members',headers=ADMIN,json={'name':'Governance outsider'}).json()
    outsider_headers={'Authorization':'Bearer '+outsider['token']}
    assert client.get(f'/api/v1/projects/{pid}/governance',headers=outsider_headers).status_code==403
    assert client.get(f'/api/v1/projects/{pid}/decisions',headers=outsider_headers).status_code==403


def test_rc26_stage6_project_decision_rejects_cross_project_task_and_nonmember_owner():
    pid,member_id,member_token,task_id=setup_project_task()
    headers={'Authorization':'Bearer '+member_token}
    other_pid,_,_,other_task=setup_project_task()
    cross=client.post(f'/api/v1/projects/{pid}/decisions',headers=ADMIN,json={
        'title':'Invalid scope','decision':'Do not accept','accountable_member_id':member_id,'related_task_ids':[other_task]})
    assert cross.status_code==422
    outsider=client.post('/api/v1/members',headers=ADMIN,json={'name':'Not a project member'}).json()
    invalid_owner=client.post(f'/api/v1/projects/{pid}/decisions',headers=ADMIN,json={
        'title':'Invalid owner','decision':'Do not accept','accountable_member_id':outsider['id']})
    assert invalid_owner.status_code==422



def test_rc26_stage7_requirement_acceptance_requires_all_criteria_tasks_and_artifacts():
    p=client.post('/api/v1/projects',headers=ADMIN,json={'name':'Acceptance project'}).json()
    pid=p['id']
    m=client.post('/api/v1/members',headers=ADMIN,json={'name':'Acceptance developer'}).json()
    req=client.post('/api/v1/requirements',headers=ADMIN,json={'project_id':pid,'title':'Checkout','acceptance_criteria':['Payment is idempotent','Receipt is downloadable']}).json()
    task=client.post('/api/v1/tasks',headers=ADMIN,json={'requirement_id':req['id'],'title':'Implement checkout','assignee_member_ids':[m['id']]}).json()
    report=client.get(f"/api/v1/requirements/{req['id']}/acceptance-report",headers=ADMIN).json()
    assert report['ready_for_acceptance'] is False and report['task_count']==1
    incomplete=client.post(f"/api/v1/requirements/{req['id']}/acceptance",headers=ADMIN,json={'decision':'APPROVE','verified_criteria':[0,1]})
    assert incomplete.status_code==409
    db=sqlite3.connect(os.environ['DAEP_DB_PATH'])
    db.execute("UPDATE tasks SET status='DONE',progress=100 WHERE id=?",(task['id'],))
    db.execute("INSERT INTO artifacts(id,task_id,artifact_type,uri,commit_sha,metadata,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)",
        ('art_acceptance',task['id'],'TEST_REPORT','https://example.invalid/report',None,'{}','2026-01-01T00:00:00+00:00','tenant-default'))
    db.commit(); db.close()
    report=client.get(f"/api/v1/requirements/{req['id']}/acceptance-report",headers=ADMIN).json()
    assert report['ready_for_acceptance'] is True and report['missing_delivery_evidence_task_ids']==[]
    partial=client.post(f"/api/v1/requirements/{req['id']}/acceptance",headers=ADMIN,json={'decision':'APPROVE','verified_criteria':[0]})
    assert partial.status_code==409
    accepted=client.post(f"/api/v1/requirements/{req['id']}/acceptance",headers=ADMIN,json={'decision':'APPROVE','verified_criteria':[0,1],'comment':'Evidence checked'})
    assert accepted.status_code==200 and accepted.json()['status']=='ACCEPTED'
    duplicate=client.post(f"/api/v1/requirements/{req['id']}/acceptance",headers=ADMIN,json={'decision':'APPROVE','verified_criteria':[0,1]})
    assert duplicate.status_code==409
    events=client.get(f'/api/v1/projects/{pid}/audit',headers=ADMIN).json()['items']
    assert any(x['event_type']=='requirement.acceptance.approve' and x['payload']['requirement_id']==req['id'] for x in events)


def test_rc26_stage7_requirement_acceptance_is_project_scoped_and_reviewer_only():
    pid,member_id,member_token,_=setup_project_task()
    req=client.post('/api/v1/requirements',headers=ADMIN,json={'project_id':pid,'title':'Scoped requirement','acceptance_criteria':['Works']}).json()
    headers={'Authorization':'Bearer '+member_token}
    denied=client.post(f"/api/v1/requirements/{req['id']}/acceptance",headers=headers,json={'decision':'REJECT','comment':'Needs changes'})
    assert denied.status_code==403
    report=client.get(f"/api/v1/requirements/{req['id']}/acceptance-report",headers=headers)
    assert report.status_code==200
    outsider=client.post('/api/v1/members',headers=ADMIN,json={'name':'Acceptance outsider'}).json()
    denied_report=client.get(f"/api/v1/requirements/{req['id']}/acceptance-report",headers={'Authorization':'Bearer '+outsider['token']})
    assert denied_report.status_code==403




def test_rc26_stage8_two_member_agent_delivery_to_requirement_acceptance_e2e():
    project=client.post('/api/v1/projects',headers=ADMIN,json={'name':'RC26 Stage 8 E2E'}).json()
    pid=project['id']
    first=client.post('/api/v1/members',headers=ADMIN,json={'name':'Local Agent Member A'}).json()
    second=client.post('/api/v1/members',headers=ADMIN,json={'name':'Local Agent Member B'}).json()
    for member in (first,second):
        added=client.post(f'/api/v1/projects/{pid}/members',headers=ADMIN,json={
            'member_id':member['id'],'role':'member'})
        assert added.status_code==200,added.text
    # Platform administrator acts as the human coordinator for this integration scenario.
    owner_h=ADMIN
    first_h={'Authorization':'Bearer '+first['token']}
    second_h={'Authorization':'Bearer '+second['token']}
    requirement=client.post('/api/v1/requirements',headers=owner_h,json={
        'project_id':pid,'title':'Distributed checkout delivery',
        'acceptance_criteria':['API implementation is delivered','Integration tests are delivered']})
    assert requirement.status_code==200,requirement.text
    parent=client.post('/api/v1/tasks',headers=owner_h,json={
        'requirement_id':requirement.json()['id'],'title':'Deliver distributed checkout'})
    assert parent.status_code==200,parent.text
    parent_id=parent.json()['id']

    for member,agent,capability,headers in (
        (first,'checkout-api-agent','python',first_h),
        (second,'checkout-test-agent','testing',second_h)):
        registered=client.post(f'/api/v1/projects/{pid}/agents/register',headers=headers,json={
            'agent_name':agent,'capabilities':[capability],'protocols':['mcp'],'status':'AVAILABLE'})
        assert registered.status_code==200,registered.text

    api_package=client.post(f'/api/v1/tasks/{parent_id}/work-packages',headers=owner_h,json={
        'title':'Implement checkout API','description':'Implement idempotent checkout API',
        'assignee_member_id':first['id'],'agent_name':'checkout-api-agent'})
    test_package=client.post(f'/api/v1/tasks/{parent_id}/work-packages',headers=owner_h,json={
        'title':'Build integration tests','description':'Verify checkout and idempotency',
        'assignee_member_id':second['id'],'agent_name':'checkout-test-agent'})
    assert api_package.status_code==200 and test_package.status_code==200
    api_child=api_package.json()['task_id']
    test_child=test_package.json()['task_id']

    # A message sent between independently authenticated local-Agent members is
    # durably visible to the recipient and can be acknowledged idempotently.
    coordination=client.post('/api/v1/messages',headers=first_h,json={
        'recipient_member_id':second['id'],'task_id':parent_id,
        'title':'API contract ready','content':'Use POST /checkout with Idempotency-Key.'})
    assert coordination.status_code==200,coordination.text
    inbox=client.get('/api/v1/me/notifications',headers=second_h).json()['items']
    assert any(item['id']==coordination.json()['id'] for item in inbox)
    ack=client.post(f"/api/v1/messages/{coordination.json()['id']}/ack",
        headers=second_h,json={'status':'ACKNOWLEDGED'})
    assert ack.status_code==200 and ack.json()['status']=='ACKNOWLEDGED'

    for child,headers,sha,kind in (
        (api_child,first_h,'api-e2e-commit','git_commit'),
        (test_child,second_h,'tests-e2e-commit','test_report')):
        artifact=client.post(f'/api/v1/tasks/{child}/artifacts',headers=headers,json={
            'artifact_type':kind,'uri':f'https://example.invalid/{sha}',
            'commit_sha':sha,'metadata':{'stage':'rc26-stage8'}})
        assert artifact.status_code==200,artifact.text
        result=client.post(f'/api/v1/tasks/{child}/work-result',headers=headers,json={
            'outcome':'COMPLETE','summary':f'Delivered {kind}','idempotency_key':f'{sha}-result'})
        assert result.status_code==200 and result.json()['status']=='REVIEW'

    # The parent cannot close while either member's package is awaiting review.
    assert client.post(f'/api/v1/tasks/{parent_id}/progress',headers=owner_h,json={
        'progress':100,'note':'Both local Agents submitted their results'}).status_code==200
    blocked=client.post(f'/api/v1/tasks/{parent_id}/review',headers=owner_h,json={'decision':'APPROVE'})
    assert blocked.status_code==409
    for child in (api_child,test_child):
        reviewed=client.post(f'/api/v1/tasks/{child}/review',headers=owner_h,json={
            'decision':'APPROVE','comment':'Artifact evidence reviewed'})
        assert reviewed.status_code==200 and reviewed.json()['status']=='DONE'

    summary=client.get(f'/api/v1/tasks/{parent_id}/work-summary',headers=owner_h).json()
    assert summary['all_done'] is True and summary['work_package_count']==2
    assert summary['artifact_count']==2
    timeline=client.get(f'/api/v1/tasks/{parent_id}/work-timeline',headers=owner_h)
    assert timeline.status_code==200
    trace=timeline.json()
    assert len(trace['work_packages'])==2
    # The message is attached to the parent task; inbox delivery and ACK are
    # asserted above. This timeline currently aggregates child-package messages.
    assert {item['artifact']['commit_sha'] for item in trace['items'] if item.get('kind')=='artifact'} >= {'api-e2e-commit','tests-e2e-commit'}

    parent_artifact=client.post(f'/api/v1/tasks/{parent_id}/artifacts',headers=owner_h,json={
        'artifact_type':'delivery_bundle','uri':'https://example.invalid/checkout-delivery',
        'commit_sha':'delivery-e2e-commit','metadata':{'child_artifacts':2}})
    assert parent_artifact.status_code==200,parent_artifact.text
    closed=client.post(f'/api/v1/tasks/{parent_id}/review',headers=owner_h,json={
        'decision':'APPROVE','comment':'Both member deliveries accepted'})
    assert closed.status_code==200 and closed.json()['status']=='DONE'

    report=client.get(f"/api/v1/requirements/{requirement.json()['id']}/acceptance-report",
        headers=owner_h)
    assert report.status_code==200 and report.json()['ready_for_acceptance'] is True
    accepted=client.post(f"/api/v1/requirements/{requirement.json()['id']}/acceptance",
        headers=owner_h,json={'decision':'APPROVE','verified_criteria':[0,1],
                              'comment':'Verified both member deliverables and parent bundle'})
    assert accepted.status_code==200 and accepted.json()['status']=='ACCEPTED'
    audit=client.get(f'/api/v1/projects/{pid}/audit',headers=owner_h).json()['items']
    assert any(x['event_type']=='requirement.acceptance.approve' and
               x['payload']['requirement_id']==requirement.json()['id'] for x in audit)

def test_rc26_stage7_acceptance_frontend_exposes_report_and_explicit_criteria_confirmation():
    frontend=open(os.path.join(os.path.dirname(__file__),'..','web','index.html'),encoding='utf-8').read()
    assert 'showRequirementAcceptance' in frontend
    assert '/acceptance-report' in frontend
    assert 'decideRequirementAcceptance' in frontend
    assert 'verified_criteria' in frontend
    assert '请输入已逐项核验的标准编号' in frontend



def test_rc26_stage10_concurrent_outbox_claims_never_lease_same_row_twice():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    _,member_id,_,task_id=setup_project_task()
    sent=client.post('/api/v1/messages',headers=ADMIN,json={
        'recipient_member_id':member_id,'task_id':task_id,
        'title':'Concurrent claim invariant','content':'Only one worker may own this outbox row'})
    assert sent.status_code==200,sent.text

    # Start two independent worker requests together. SQLite serializes claim
    # transactions with BEGIN IMMEDIATE; PostgreSQL uses FOR UPDATE SKIP LOCKED.
    gate=Barrier(2)
    def claim(worker_id):
        gate.wait(timeout=10)
        response=client.post('/internal/v1/outbox/claim',headers=WORKER,json={
            'worker_id':worker_id,'limit':100,'lease_seconds':60})
        assert response.status_code==200,response.text
        return response.json()['items']

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(claim,'stage10-worker-a'),pool.submit(claim,'stage10-worker-b')]
        claimed=[item for future in futures for item in future.result(timeout=30)]

    target=[item for item in claimed if item['payload'].get('message_id')==sent.json()['id']]
    assert len(target)==1, f'target outbox row must have exactly one lease, got {len(target)}'
    ids=[item['id'] for item in claimed]
    assert len(ids)==len(set(ids)), 'competing workers must not receive duplicate outbox rows'
    assert target[0]['status']=='IN_FLIGHT'
    assert target[0]['lease_owner'] in ('stage10-worker-a','stage10-worker-b')
    assert len(target[0]['lease_token'])>=32


def test_rc26_stage11_concurrent_work_result_idempotency_is_single_event_and_conflict_safe():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    pid,_,_,parent_id=setup_project_task()
    recipient=client.post('/api/v1/members',headers=ADMIN,json={'name':'Stage11 Result Agent'}).json()
    assert client.post(f'/api/v1/projects/{pid}/members',headers=ADMIN,json={
        'member_id':recipient['id'],'role':'member'}).status_code==200
    rh={'Authorization':'Bearer '+recipient['token']}
    assert client.post(f'/api/v1/projects/{pid}/agents/register',headers=rh,json={
        'agent_name':'stage11-agent','capabilities':['python'],'protocols':['mcp'],'status':'AVAILABLE'}).status_code==200
    created=client.post(f'/api/v1/tasks/{parent_id}/work-packages',headers=ADMIN,json={
        'title':'Concurrent result','assignee_member_id':recipient['id'],'agent_name':'stage11-agent'})
    assert created.status_code==200,created.text
    child=created.json()['task_id']
    assert client.post(f'/api/v1/tasks/{child}/artifacts',headers=rh,json={
        'artifact_type':'git_commit','uri':'https://github.com/example/repo/commit/stage11',
        'commit_sha':'stage11','metadata':{}}).status_code==200

    payload={'outcome':'COMPLETE','summary':'Concurrent completion','idempotency_key':'stage11-result-once'}
    gate=Barrier(2)
    def submit():
        gate.wait(timeout=10)
        return client.post(f'/api/v1/tasks/{child}/work-result',headers=rh,json=payload)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=[f.result(timeout=30) for f in [pool.submit(submit),pool.submit(submit)]]
    assert all(r.status_code==200 for r in responses),[r.text for r in responses]
    bodies=[r.json() for r in responses]
    assert bodies[0]['event_id']==bodies[1]['event_id']
    events=client.get(f'/api/v1/tasks/{child}/events',headers=ADMIN)
    assert events.status_code==200
    matching=[e for e in events.json() if e['event_type']=='task.work_package.reported']
    assert len(matching)==1

    conflict=client.post(f'/api/v1/tasks/{child}/work-result',headers=rh,json={
        'outcome':'FAILED','summary':'Conflicting reuse','idempotency_key':'stage11-result-once'})
    assert conflict.status_code==409


def test_rc26_stage11_concurrent_task_approval_emits_one_governance_event():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    _,_,owner_token,task_id=setup_project_task()
    owner_headers={'Authorization':'Bearer '+owner_token}
    assert client.post(f'/api/v1/tasks/{task_id}/progress',headers=owner_headers,json={
        'progress':100,'note':'Ready for concurrent review'}).status_code==200

    gate=Barrier(2)
    def approve():
        gate.wait(timeout=10)
        return client.post(f'/api/v1/tasks/{task_id}/review',headers=ADMIN,json={
            'decision':'APPROVE','comment':'Stage11 concurrent approval'})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=[f.result(timeout=30) for f in [pool.submit(approve),pool.submit(approve)]]
    statuses=sorted(r.status_code for r in responses)
    assert statuses==[200,409],[r.text for r in responses]
    assert all(r.json().get('status')=='DONE' for r in responses if r.status_code==200)
    events=client.get(f'/api/v1/tasks/{task_id}/events',headers=ADMIN)
    assert events.status_code==200
    matching=[e for e in events.json() if e['event_type']=='task.reviewed']
    assert len(matching)==1
