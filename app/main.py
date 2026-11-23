import os, json, sqlite3, uuid, asyncio, hashlib, base64, secrets, urllib.parse, urllib.request, time, contextvars, hmac, re
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect, Cookie, Request
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DB=os.getenv('DAEP_DB_PATH','/data/daep.db')
ADMIN_TOKEN=os.getenv('DAEP_ADMIN_TOKEN','change-me-before-use')
@asynccontextmanager
async def lifespan(app):
    bootstrap()
    from app.agent_identity import ensure_agent_schema
    if not DATABASE_URL.startswith(('postgresql://','postgres://')):
        ensure_agent_schema(conn)
    yield

app=FastAPI(title='DAEP Enterprise Platform API',version='1.0.0-rc9',description='Task-centric distributed agent engineering platform',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=os.getenv('CORS_ORIGINS','http://localhost:3000').split(','),allow_credentials=False,allow_methods=['*'],allow_headers=['*'])
@app.middleware('http')
async def tenant_context(request, call_next):
    token=request.headers.get('authorization','')
    tok=token[7:] if token.startswith('Bearer ') else ''
    reset_tenant=_tenant_ctx.set('')
    reset_member=_member_ctx.set('')
    reset_agent=_agent_ctx.set('')
    reset_lifecycle=_lifecycle_action_ctx.set('')
    reset_admin=_admin_ctx.set(False)
    reset_service=_service_ctx.set(False)
    if tok:
        try:
            digest=hashlib.sha256(tok.encode()).hexdigest()
            lookup_reset=_auth_lookup_ctx.set(True)
            try:
                with conn() as c:
                    row=(c.execute("SELECT tenant_id,role FROM daep_authenticate_member(?,?)",(digest,now())).fetchone() if DATABASE_URL.startswith(('postgresql://','postgres://')) else c.execute("SELECT tenant_id,role FROM members WHERE token=? AND token_status='ACTIVE' AND (token_expires_at IS NULL OR token_expires_at>?)",(digest,now())).fetchone())
            finally:
                _auth_lookup_ctx.reset(lookup_reset)
            if row:
                _tenant_ctx.set(row['tenant_id'])
                _admin_ctx.set(row['role']=='admin' and row['tenant_id']=='tenant-default')
        except Exception:
            pass
    try:
        return await call_next(request)
    finally:
        _tenant_ctx.reset(reset_tenant); _member_ctx.reset(reset_member); _agent_ctx.reset(reset_agent); _lifecycle_action_ctx.reset(reset_lifecycle); _admin_ctx.reset(reset_admin); _service_ctx.reset(reset_service)

@app.middleware('http')
async def security_headers(request, call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    return response

class ProjectIn(BaseModel): name:str=Field(min_length=1,max_length=160); description:str=Field(default='',max_length=5000); tenant_id:str=Field(default='tenant-default',min_length=1,max_length=120)
class ProjectMemberFunctionIn(BaseModel): work_function:str=Field(pattern='^(developer|tester|product|architect|other)$')
class RequirementIn(BaseModel): project_id:str; title:str=Field(min_length=1,max_length=200); description:str=Field(default='',max_length=10000); acceptance_criteria:list[str]=Field(default_factory=list)
class TaskIn(BaseModel): requirement_id:str; title:str=Field(min_length=1,max_length=200); description:str=Field(default='',max_length=10000); assignee_member_ids:list[str]=Field(default_factory=list); dependencies:list[str]=Field(default_factory=list)
class TaskDependenciesIn(BaseModel): dependencies:list[str]=Field(default_factory=list,max_length=100)
class ProgressIn(BaseModel): progress:int=Field(ge=0,le=100); note:str=Field(default='',max_length=2000)
class MessageIn(BaseModel): recipient_member_id:str; project_id:Optional[str]=None; task_id:Optional[str]=None; message_type:str='COLLABORATION'; title:str=Field(min_length=1,max_length=200); content:str=Field(min_length=1,max_length=20000); priority:str=Field(default='NORMAL',pattern='^(LOW|NORMAL|HIGH|URGENT)$')
class AckIn(BaseModel): status:str='ACKNOWLEDGED'
class AgentPresenceIn(BaseModel):
    agent_name:str=Field(min_length=1,max_length=120)
    capabilities:list[str]=Field(default_factory=list,max_length=50)
    protocols:list[str]=Field(default_factory=lambda:['mcp'],max_length=10)
    status:str=Field(default='AVAILABLE',pattern='^(AVAILABLE|BUSY|OFFLINE)$')
    metadata:dict=Field(default_factory=dict)
class DelegationIn(BaseModel):
    recipient_member_id:str=Field(min_length=1,max_length=120)
    agent_name:str=Field(min_length=1,max_length=120)
    reason:str=Field(default='',max_length=4000)
    expires_in_seconds:int=Field(default=86400,ge=60,le=604800)
class WorkPackageIn(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    description:str=Field(default='',max_length=10000)
    assignee_member_id:str=Field(min_length=1,max_length=120)
    agent_name:str=Field(min_length=1,max_length=120)
    dependencies:list[str]=Field(default_factory=list)
    sla_seconds:Optional[int]=Field(default=None,ge=300,le=2592000)
class ArtifactIn(BaseModel): artifact_type:str=Field(min_length=1,max_length=80); uri:str=Field(min_length=1,max_length=2048); commit_sha:Optional[str]=None; metadata:dict=Field(default_factory=dict)
class WorkResultIn(BaseModel): outcome:str=Field(pattern='^(COMPLETE|FAILED)$'); summary:str=Field(min_length=1,max_length=5000); idempotency_key:str=Field(default='',max_length=200)
class WorkPackageScanIn(BaseModel): stale_after_seconds:int=Field(default=3600,ge=300,le=604800)
class WorkPackageReassignIn(BaseModel): assignee_member_id:str=Field(min_length=1,max_length=120); agent_name:str=Field(min_length=1,max_length=120); reason:str=Field(min_length=1,max_length=2000)
class ProjectDecisionIn(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    decision:str=Field(min_length=1,max_length=4000)
    rationale:str=Field(default='',max_length=5000)
    accountable_member_id:str=Field(min_length=1,max_length=120)
    related_task_ids:list[str]=Field(default_factory=list,max_length=50)
    due_at:Optional[str]=Field(default=None,max_length=40)
class WorkflowStageIn(BaseModel):
    name:str=Field(min_length=1,max_length=120)
    key:str=Field(min_length=1,max_length=80)
    order:int=Field(ge=1,le=100)
    approval_role:str=Field(default='none',pattern='^(none|owner|manager|reviewer)$')
    sla_seconds:Optional[int]=Field(default=None,ge=300,le=2592000)
class WorkflowConfigIn(BaseModel):
    stages:list[WorkflowStageIn]=Field(min_length=1,max_length=30)
    enabled:bool=True
class GateConfigIn(BaseModel):
    enabled:bool=True
    required_roles:list[str]=Field(default_factory=list,max_length=10)
    required_evidence:bool=False
    required_all_tasks_done:bool=False
    applies_to:str=Field(default='DONE',min_length=1,max_length=80)
class RequirementAcceptanceIn(BaseModel):
    decision:str=Field(pattern='^(APPROVE|REJECT)$')
    verified_criteria:list[int]=Field(default_factory=list,max_length=100)
    comment:str=Field(default='',max_length=4000)
def now(): return datetime.now(timezone.utc).isoformat()

# First-class user-owned Agent identity / MCP token lifecycle.
from app.agent_identity import register_agent_routes
DATABASE_URL=os.getenv('DATABASE_URL','')
PRIVILEGED_DATABASE_URL=os.getenv('DAEP_PRIVILEGED_DATABASE_URL','')
_tenant_ctx=contextvars.ContextVar('daep_tenant_id',default='')
_admin_ctx=contextvars.ContextVar('daep_platform_admin',default=False)
_auth_lookup_ctx=contextvars.ContextVar('daep_auth_lookup',default=False)
_service_ctx=contextvars.ContextVar('daep_internal_service',default=False)
_member_ctx=contextvars.ContextVar('daep_member_id',default='')
_lifecycle_action_ctx=contextvars.ContextVar('daep_lifecycle_action',default='')
_agent_ctx=contextvars.ContextVar('daep_agent_id',default='')

class _PGCursor:
    def __init__(self, cur): self.cur=cur
    @property
    def rowcount(self): return self.cur.rowcount
    def fetchone(self):
        r=self.cur.fetchone();
        if r is None: return None
        return dict(r) if hasattr(r,'keys') else r
    def fetchall(self):
        rows=self.cur.fetchall(); return [dict(r) if hasattr(r,'keys') else r for r in rows]
    def __iter__(self):
        return iter(self.fetchall())

class _PGConn:
    def __init__(self,url):
        import psycopg
        from psycopg.rows import dict_row
        self.c=psycopg.connect(url,row_factory=dict_row)
        self.c.execute("SELECT set_config('app.tenant_id', %s, false), set_config('app.member_id', %s, false), set_config('app.lifecycle_action', %s, false), set_config('app.platform_admin', %s, false), set_config('app.internal_service', %s, false), set_config('app.auth_lookup', %s, false)",(
            _tenant_ctx.get() or '', _member_ctx.get() or '', _lifecycle_action_ctx.get() or '', 'true' if _admin_ctx.get() else 'false', 'true' if _service_ctx.get() else 'false', 'true' if _auth_lookup_ctx.get() else 'false'))
    def __enter__(self): return self
    def __exit__(self,typ,val,tb):
        if typ: self.c.rollback()
        else: self.c.commit()
        self.c.close()
    def execute(self,sql,args=()):
        import sqlite3 as _sqlite
        # SQLite compatibility statements are translated or ignored explicitly.
        if sql.strip().upper() == 'PRAGMA FOREIGN_KEYS=ON':
            return _NoopCursor()
        q=sql.replace('INSERT OR IGNORE INTO','INSERT INTO')
        if 'INSERT INTO' in q and 'ON CONFLICT' not in q and sql.startswith('INSERT OR IGNORE INTO'):
            q += ' ON CONFLICT DO NOTHING'
        q=q.replace('BEGIN IMMEDIATE','BEGIN').replace('?', '%s')
        if q.strip().startswith('PRAGMA table_info('):
            table=q.split('(')[1].split(')')[0]
            cur=self.c.execute("SELECT column_name AS name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",(table,)); return _PGCursor(cur)
        if 'AUTOINCREMENT' in q: q=q.replace('INTEGER PRIMARY KEY AUTOINCREMENT','BIGSERIAL PRIMARY KEY')
        try: return _PGCursor(self.c.execute(q,args))
        except Exception as e:
            if e.__class__.__name__ in ('UniqueViolation','IntegrityError'): raise _sqlite.IntegrityError(str(e)) from e
            raise

class _NoopCursor:
    rowcount=0
    def fetchone(self): return None
    def fetchall(self): return []

def conn():
    if DATABASE_URL.startswith(('postgresql://','postgres://')):
        privileged = _admin_ctx.get() or _service_ctx.get()
        if privileged:
            if not PRIVILEGED_DATABASE_URL:
                raise RuntimeError('DAEP_PRIVILEGED_DATABASE_URL is required for platform-admin and internal-service PostgreSQL operations')
            return _PGConn(PRIVILEGED_DATABASE_URL)
        return _PGConn(DATABASE_URL)
    os.makedirs(os.path.dirname(DB) or '.',exist_ok=True); c=sqlite3.connect(DB,timeout=5); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); c.execute('PRAGMA busy_timeout=5000'); return c
def begin_serialized_write(c):
    """Serialize SQLite write-side state transitions; PostgreSQL uses row locks at call sites."""
    if not DATABASE_URL.startswith(('postgresql://','postgres://')):
        c.execute('BEGIN IMMEDIATE')

def bootstrap():
    service_reset=_service_ctx.set(True)
    try:
        init()
    finally:
        _service_ctx.reset(service_reset)

def init():
    if not ADMIN_TOKEN or ADMIN_TOKEN == 'change-me-before-use' or len(ADMIN_TOKEN) < 32:
        raise RuntimeError('Set a unique DAEP_ADMIN_TOKEN of at least 32 characters before starting DAEP')
    with conn() as c:
        if not DATABASE_URL.startswith(('postgresql://','postgres://')): c.execute('PRAGMA journal_mode=WAL')
        schema='''
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS tenants(id TEXT PRIMARY KEY,name TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'ACTIVE',created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS members(id TEXT PRIMARY KEY,name TEXT NOT NULL,username TEXT UNIQUE,role TEXT NOT NULL DEFAULT 'developer',token TEXT UNIQUE NOT NULL,created_at TEXT NOT NULL,tenant_id TEXT NOT NULL DEFAULT 'tenant-default',token_status TEXT NOT NULL DEFAULT 'ACTIVE',token_created_at TEXT,token_revoked_at TEXT,token_expires_at TEXT,oidc_subject TEXT,oidc_email TEXT,password_hash TEXT,password_status TEXT NOT NULL DEFAULT 'ACTIVE');
        CREATE TABLE IF NOT EXISTS schema_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS oidc_states(state_hash TEXT PRIMARY KEY,nonce TEXT NOT NULL,code_verifier TEXT NOT NULL,expires_at TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT,created_by TEXT,created_at TEXT NOT NULL,tenant_id TEXT NOT NULL DEFAULT 'tenant-default',status TEXT NOT NULL DEFAULT 'ACTIVE');
        CREATE TABLE IF NOT EXISTS project_members(project_id TEXT NOT NULL,member_id TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'member',work_function TEXT NOT NULL DEFAULT 'other',joined_at TEXT NOT NULL,PRIMARY KEY(project_id,member_id),FOREIGN KEY(project_id) REFERENCES projects(id),FOREIGN KEY(member_id) REFERENCES members(id));
        CREATE TABLE IF NOT EXISTS requirements(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,title TEXT NOT NULL,description TEXT,acceptance_criteria TEXT,status TEXT NOT NULL DEFAULT 'OPEN',created_at TEXT NOT NULL,FOREIGN KEY(project_id) REFERENCES projects(id));
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,requirement_id TEXT NOT NULL,title TEXT NOT NULL,description TEXT,status TEXT NOT NULL DEFAULT 'READY',progress INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(requirement_id) REFERENCES requirements(id));
        CREATE TABLE IF NOT EXISTS assignments(task_id TEXT NOT NULL,member_id TEXT NOT NULL,PRIMARY KEY(task_id,member_id),FOREIGN KEY(task_id) REFERENCES tasks(id),FOREIGN KEY(member_id) REFERENCES members(id));
        CREATE TABLE IF NOT EXISTS dependencies(task_id TEXT NOT NULL,depends_on_task_id TEXT NOT NULL,PRIMARY KEY(task_id,depends_on_task_id),FOREIGN KEY(task_id) REFERENCES tasks(id),FOREIGN KEY(depends_on_task_id) REFERENCES tasks(id));
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,event_type TEXT NOT NULL,actor_member_id TEXT,task_id TEXT,payload TEXT NOT NULL,created_at TEXT NOT NULL,idempotency_key TEXT UNIQUE,tenant_id TEXT NOT NULL DEFAULT 'tenant-default');
        CREATE TABLE IF NOT EXISTS messages(seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,recipient_member_id TEXT NOT NULL,tenant_id TEXT NOT NULL DEFAULT 'tenant-default',task_id TEXT,message_type TEXT,title TEXT,content TEXT,priority TEXT,status TEXT NOT NULL DEFAULT 'PENDING',created_at TEXT NOT NULL,acked_at TEXT,attempts INTEGER NOT NULL DEFAULT 0,last_attempt_at TEXT);
        CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY,task_id TEXT NOT NULL,artifact_type TEXT,uri TEXT,commit_sha TEXT,metadata TEXT,created_at TEXT,tenant_id TEXT NOT NULL DEFAULT 'tenant-default',FOREIGN KEY(task_id) REFERENCES tasks(id));
        CREATE TABLE IF NOT EXISTS project_agents(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,member_id TEXT NOT NULL,tenant_id TEXT NOT NULL,agent_name TEXT NOT NULL,capabilities TEXT NOT NULL,protocols TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'AVAILABLE',metadata TEXT NOT NULL DEFAULT '{}',last_seen TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(project_id,member_id,agent_name),FOREIGN KEY(project_id) REFERENCES projects(id),FOREIGN KEY(member_id) REFERENCES members(id));
        CREATE INDEX IF NOT EXISTS idx_project_agents_discovery ON project_agents(project_id,status,last_seen);
        CREATE TABLE IF NOT EXISTS task_delegations(id TEXT PRIMARY KEY,task_id TEXT NOT NULL,project_id TEXT NOT NULL,tenant_id TEXT NOT NULL,requester_member_id TEXT NOT NULL,recipient_member_id TEXT NOT NULL,agent_name TEXT NOT NULL,reason TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'PENDING',message_id TEXT,expires_at TEXT NOT NULL,responded_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(task_id) REFERENCES tasks(id),FOREIGN KEY(project_id) REFERENCES projects(id),FOREIGN KEY(requester_member_id) REFERENCES members(id),FOREIGN KEY(recipient_member_id) REFERENCES members(id));
        CREATE INDEX IF NOT EXISTS idx_task_delegations_recipient ON task_delegations(recipient_member_id,status,expires_at);
        CREATE TABLE IF NOT EXISTS task_work_packages(id TEXT PRIMARY KEY,parent_task_id TEXT NOT NULL,child_task_id TEXT NOT NULL UNIQUE,project_id TEXT NOT NULL,tenant_id TEXT NOT NULL,assignee_member_id TEXT NOT NULL,agent_name TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'ACTIVE',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,correlation_id TEXT,sla_due_at TEXT,risk_state TEXT NOT NULL DEFAULT 'ON_TRACK',needs_attention INTEGER NOT NULL DEFAULT 0,stalled_at TEXT,stall_reason TEXT,FOREIGN KEY(parent_task_id) REFERENCES tasks(id),FOREIGN KEY(child_task_id) REFERENCES tasks(id),FOREIGN KEY(project_id) REFERENCES projects(id),FOREIGN KEY(assignee_member_id) REFERENCES members(id));
        CREATE INDEX IF NOT EXISTS idx_task_work_packages_parent ON task_work_packages(parent_task_id,status);
        CREATE TABLE IF NOT EXISTS project_workflows(project_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,config TEXT NOT NULL,updated_by TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(project_id) REFERENCES projects(id));
        CREATE TABLE IF NOT EXISTS project_gates(project_id TEXT NOT NULL,gate_key TEXT NOT NULL,tenant_id TEXT NOT NULL,config TEXT NOT NULL,updated_by TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(project_id,gate_key),FOREIGN KEY(project_id) REFERENCES projects(id));
        CREATE TABLE IF NOT EXISTS project_approvals(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,tenant_id TEXT NOT NULL,requester_member_id TEXT NOT NULL,action TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'PENDING',decided_by TEXT,decision_reason TEXT,created_at TEXT NOT NULL,decided_at TEXT,FOREIGN KEY(project_id) REFERENCES projects(id),FOREIGN KEY(requester_member_id) REFERENCES members(id));
        CREATE INDEX IF NOT EXISTS idx_project_approvals_status ON project_approvals(project_id,status,created_at);
        CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY,event_type TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'PENDING',attempts INTEGER NOT NULL DEFAULT 0,available_at TEXT NOT NULL,lease_until TEXT,lease_owner TEXT,lease_token TEXT,last_error TEXT,created_at TEXT NOT NULL,sent_at TEXT,tenant_id TEXT NOT NULL DEFAULT 'tenant-default');
        CREATE INDEX IF NOT EXISTS idx_outbox_ready ON outbox(status,available_at,lease_until);
        '''
        if DATABASE_URL.startswith(('postgresql://','postgres://')):
            schema=schema.replace('INTEGER PRIMARY KEY AUTOINCREMENT','BIGSERIAL PRIMARY KEY')
            schema=schema.replace('CREATE TABLE IF NOT EXISTS messages(seq INTEGER PRIMARY KEY AUTOINCREMENT','CREATE TABLE IF NOT EXISTS messages(seq BIGSERIAL PRIMARY KEY')
            schema=schema.replace('CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY','CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY')
            for stmt in [x.strip() for x in schema.split(';') if x.strip()]: c.execute(stmt)
        else: c.executescript(schema)
        c.execute("INSERT OR IGNORE INTO tenants(id,name,status,created_at) VALUES('tenant-default','Default Tenant','ACTIVE',?)",(now(),))
        # Versioned, additive schema ledger. Existing RC databases are baselined without destructive changes.
        c.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        c.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES('0005-rc5-baseline',?)",(now(),))
        c.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES('0006-tenant-indexes-oidc-state',?)",(now(),))
        # Additive tenant and credential lifecycle migrations.
        work_package_cols={r['name'] for r in c.execute('PRAGMA table_info(task_work_packages)').fetchall()}
        for col,ddl in [('needs_attention','INTEGER NOT NULL DEFAULT 0'),('stalled_at','TEXT'),('stall_reason','TEXT'),('correlation_id','TEXT'),('sla_due_at','TEXT'),('risk_state',"TEXT NOT NULL DEFAULT 'ON_TRACK'")]:
            if col not in work_package_cols: c.execute(f'ALTER TABLE task_work_packages ADD COLUMN {col} {ddl}')
        project_cols={r['name'] for r in c.execute('PRAGMA table_info(projects)').fetchall()}
        if 'status' not in project_cols: c.execute("ALTER TABLE projects ADD COLUMN status TEXT NOT NULL DEFAULT 'ACTIVE'")
        project_member_cols={r['name'] for r in c.execute('PRAGMA table_info(project_members)').fetchall()}
        if 'work_function' not in project_member_cols: c.execute("ALTER TABLE project_members ADD COLUMN work_function TEXT NOT NULL DEFAULT 'other'")
        c.execute("UPDATE project_members SET work_function='other' WHERE work_function IS NULL OR work_function=''")
        table_cols = {
            'members': {r['name'] for r in c.execute('PRAGMA table_info(members)').fetchall()},
            'projects': {r['name'] for r in c.execute('PRAGMA table_info(projects)').fetchall()},
            'events': {r['name'] for r in c.execute('PRAGMA table_info(events)').fetchall()},
            'artifacts': {r['name'] for r in c.execute('PRAGMA table_info(artifacts)').fetchall()},
            'outbox': {r['name'] for r in c.execute('PRAGMA table_info(outbox)').fetchall()},
        }
        for col, ddl in [('tenant_id', "TEXT NOT NULL DEFAULT 'tenant-default'"),('token_status',"TEXT NOT NULL DEFAULT 'ACTIVE'"),('token_created_at','TEXT'),('token_revoked_at','TEXT'),('token_expires_at','TEXT'),('oidc_subject','TEXT'),('oidc_email','TEXT'),('username','TEXT'),('password_hash','TEXT'),('password_status',"TEXT NOT NULL DEFAULT 'ACTIVE'")]:
            if col not in table_cols['members']: c.execute(f'ALTER TABLE members ADD COLUMN {col} {ddl}')
        for table in ('projects','events','artifacts','outbox'):
            if 'tenant_id' not in table_cols[table]: c.execute(f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'tenant-default'")
        if 'lease_token' not in table_cols['outbox']:
            c.execute('ALTER TABLE outbox ADD COLUMN lease_token TEXT')
        c.execute("CREATE INDEX IF NOT EXISTS idx_members_tenant ON members(tenant_id)")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_members_username ON members(username) WHERE username IS NOT NULL")
        c.execute("CREATE INDEX IF NOT EXISTS idx_projects_tenant ON projects(tenant_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_events_tenant_created ON events(tenant_id,created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_tenant ON artifacts(tenant_id,created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_outbox_tenant_status ON outbox(tenant_id,status,available_at)")
        c.execute("UPDATE members SET token_created_at=COALESCE(token_created_at,created_at), token_status=COALESCE(token_status,'ACTIVE'), tenant_id=COALESCE(tenant_id,'tenant-default')")
        c.execute("UPDATE projects SET tenant_id=(SELECT tenant_id FROM members m WHERE m.id=projects.created_by) WHERE tenant_id IS NULL OR tenant_id='tenant-default'")
        c.execute("UPDATE events SET tenant_id=(SELECT p.tenant_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE t.id=events.task_id) WHERE events.task_id IS NOT NULL AND EXISTS (SELECT 1 FROM tasks t WHERE t.id=events.task_id)")
        c.execute("UPDATE events SET tenant_id=(SELECT tenant_id FROM members m WHERE m.id=events.actor_member_id) WHERE (tenant_id IS NULL OR tenant_id='tenant-default') AND actor_member_id IS NOT NULL")
        c.execute("UPDATE artifacts SET tenant_id=(SELECT p.tenant_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE t.id=artifacts.task_id) WHERE tenant_id IS NULL OR tenant_id='tenant-default'")
        c.execute("UPDATE outbox SET tenant_id='tenant-default' WHERE tenant_id IS NULL")
        # Correct ownership metadata on RC5 rows emitted by a platform administrator
        # for another tenant. Payloads are intentionally treated as data, not SQL.
        for row in c.execute('SELECT id,event_type,actor_member_id,task_id,payload FROM events').fetchall():
            try: payload=json.loads(row['payload'] or '{}')
            except Exception: payload={}
            tenant_row=None
            if row['task_id']:
                tenant_row=c.execute('SELECT p.tenant_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE t.id=?',(row['task_id'],)).fetchone()
            if not tenant_row:
                project_ref=payload.get('project_id')
                member_ref=payload.get('member_id') or payload.get('recipient')
                if project_ref: tenant_row=c.execute('SELECT tenant_id FROM projects WHERE id=?',(project_ref,)).fetchone()
                if not tenant_row and member_ref: tenant_row=c.execute('SELECT tenant_id FROM members WHERE id=?',(member_ref,)).fetchone()
                if not tenant_row and row['actor_member_id']: tenant_row=c.execute('SELECT tenant_id FROM members WHERE id=?',(row['actor_member_id'],)).fetchone()
            if tenant_row: c.execute('UPDATE events SET tenant_id=? WHERE id=?',(tenant_row['tenant_id'],row['id']))
        for row in c.execute('SELECT id,payload FROM outbox').fetchall():
            try: payload=json.loads(row['payload'] or '{}')
            except Exception: payload={}
            tenant_row=None
            if payload.get('project_id'): tenant_row=c.execute('SELECT tenant_id FROM projects WHERE id=?',(payload['project_id'],)).fetchone()
            if not tenant_row and payload.get('recipient_member_id'): tenant_row=c.execute('SELECT tenant_id FROM members WHERE id=?',(payload['recipient_member_id'],)).fetchone()
            if tenant_row: c.execute('UPDATE outbox SET tenant_id=? WHERE id=?',(tenant_row['tenant_id'],row['id']))
        # Quarantine legacy cross-tenant links before rebuilding project membership grants.
        c.execute("DELETE FROM assignments WHERE EXISTS (SELECT 1 FROM tasks t JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id JOIN members m ON m.id=assignments.member_id WHERE t.id=assignments.task_id AND p.tenant_id<>m.tenant_id)")
        c.execute("DELETE FROM project_members WHERE EXISTS (SELECT 1 FROM projects p JOIN members m ON m.id=project_members.member_id WHERE p.id=project_members.project_id AND p.tenant_id<>m.tenant_id)")
        # API tokens are high-entropy credentials: store only SHA-256 digests at rest.
        hashed=c.execute("SELECT 1 FROM schema_meta WHERE key='member_token_sha256_v1'").fetchone()
        if not hashed:
            for row in c.execute('SELECT id,token FROM members').fetchall():
                c.execute('UPDATE members SET token=? WHERE id=?',(hashlib.sha256(row['token'].encode()).hexdigest(),row['id']))
            c.execute("INSERT INTO schema_meta(key,value) VALUES('member_token_sha256_v1','1')")
        admin_row=c.execute("SELECT id FROM members WHERE id='member-admin'").fetchone()
        admin_digest=hashlib.sha256(ADMIN_TOKEN.encode()).hexdigest()
        if admin_row:
            c.execute("UPDATE members SET token=?,role='admin',name='DAEP Administrator',tenant_id='tenant-default',token_status='ACTIVE',token_created_at=COALESCE(token_created_at,created_at),token_revoked_at=NULL WHERE id='member-admin'",(admin_digest,))
        elif not c.execute('SELECT 1 FROM members WHERE token=?',(admin_digest,)).fetchone():
            c.execute("INSERT INTO members(id,name,role,token,created_at,tenant_id,token_status,token_created_at) VALUES(?,?,?,?,?,?,?,?)",('member-admin','DAEP Administrator','admin',admin_digest,now(),'tenant-default','ACTIVE',now()))
        # RC5 allowed tenant member provisioning with role=admin. Only the bootstrap
        # identity is a platform super-administrator in RC6.
        c.execute("UPDATE members SET role='manager' WHERE role='admin' AND id<>'member-admin'")
        c.execute("UPDATE members SET username=CASE WHEN username IS NULL OR username='' THEN CASE WHEN id='member-admin' THEN 'admin' ELSE lower(replace(replace(name,' ','_'),'@','_')) END ELSE username END WHERE username IS NULL OR username=''")
        bootstrap_password=os.getenv('DAEP_BOOTSTRAP_ADMIN_PASSWORD','')
        if bootstrap_password and len(bootstrap_password)>=12:
            c.execute("UPDATE members SET password_hash=?,password_status='ACTIVE' WHERE id='member-admin' AND (password_hash IS NULL OR password_hash='')",(hash_password(bootstrap_password),))
        c.execute("INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES('0007-platform-admin-boundary',?)",(now(),))
        # Additive migration for databases created by earlier release candidates.
        cols={r['name'] for r in c.execute('PRAGMA table_info(messages)')}
        if 'tenant_id' not in cols:
            c.execute("ALTER TABLE messages ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'tenant-default'")
            c.execute("UPDATE messages SET tenant_id=COALESCE((SELECT tenant_id FROM members WHERE members.id=messages.recipient_member_id), 'tenant-default') WHERE tenant_id='tenant-default'")
        if 'seq' not in cols:
            c.execute('ALTER TABLE messages RENAME TO messages_legacy')
            c.execute("CREATE TABLE messages(seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,recipient_member_id TEXT NOT NULL,tenant_id TEXT NOT NULL DEFAULT 'tenant-default',task_id TEXT,message_type TEXT,title TEXT,content TEXT,priority TEXT,status TEXT NOT NULL DEFAULT 'PENDING',created_at TEXT NOT NULL,acked_at TEXT,attempts INTEGER NOT NULL DEFAULT 0,last_attempt_at TEXT)")
            c.execute('INSERT INTO messages(id,recipient_member_id,task_id,message_type,title,content,priority,status,created_at,acked_at) SELECT id,recipient_member_id,task_id,message_type,title,content,priority,status,created_at,acked_at FROM messages_legacy ORDER BY created_at')
            c.execute('DROP TABLE messages_legacy')
        c.execute('CREATE INDEX IF NOT EXISTS idx_messages_inbox ON messages(recipient_member_id,status,seq)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_messages_tenant_seq ON messages(tenant_id,seq)')
        c.execute("INSERT OR IGNORE INTO project_members(project_id,member_id,role,joined_at) SELECT id,created_by,'owner',created_at FROM projects WHERE created_by IS NOT NULL")
        c.execute("INSERT OR IGNORE INTO project_members(project_id,member_id,role,joined_at) SELECT DISTINCT r.project_id,a.member_id,'member',t.created_at FROM assignments a JOIN tasks t ON t.id=a.task_id JOIN requirements r ON r.id=t.requirement_id")
def hash_password(password):
    salt=secrets.token_bytes(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,310000)
    return 'pbkdf2_sha256$310000$'+base64.urlsafe_b64encode(salt).decode().rstrip('=')+'$'+base64.urlsafe_b64encode(digest).decode().rstrip('=')

def verify_password(password,encoded):
    try:
        scheme,iters,salt_b64,digest_b64=encoded.split('$',3)
        if scheme!='pbkdf2_sha256': return False
        salt=base64.urlsafe_b64decode(salt_b64+'===')
        expected=base64.urlsafe_b64decode(digest_b64+'===')
        actual=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,int(iters))
        return secrets.compare_digest(actual,expected)
    except Exception:
        return False

def issue_member_token(member_id):
    raw=secrets.token_urlsafe(48)
    digest=hashlib.sha256(raw.encode()).hexdigest()
    created=now()
    with conn() as c:
        c.execute("UPDATE members SET token=?,token_status='ACTIVE',token_created_at=?,token_revoked_at=NULL WHERE id=?",(digest,created,member_id))
    return raw

def actor(authorization):
    if not authorization or not authorization.startswith('Bearer '): raise HTTPException(401,'Bearer token required')
    token=hashlib.sha256(authorization[7:].encode()).hexdigest()
    lookup_reset=_auth_lookup_ctx.set(True)
    try:
        with conn() as c:
            r=(c.execute("SELECT * FROM daep_authenticate_member(?,?)",(token,now())).fetchone() if DATABASE_URL.startswith(('postgresql://','postgres://')) else c.execute("SELECT * FROM members WHERE token=? AND token_status='ACTIVE' AND password_status='ACTIVE' AND (token_expires_at IS NULL OR token_expires_at>?)",(token,now())).fetchone())
    finally:
        _auth_lookup_ctx.reset(lookup_reset)
    if not r:
        try:
            from app.agent_identity import authenticate_agent_token
            ident=authenticate_agent_token(conn, authorization[7:])
            data={'id':ident['owner_member_id'],'tenant_id':ident['tenant_id'],'role':'developer','actor_type':'AGENT','agent_id':ident['agent_id'],'agent_status':ident['agent_status']}
            _tenant_ctx.set(data['tenant_id'])
            _member_ctx.set(data['id'])
            _admin_ctx.set(False)
            _agent_ctx.set(data['agent_id'])
            return data
        except HTTPException:
            raise HTTPException(401,'Invalid token')
    data=dict(r)
    data['actor_type']='MEMBER'
    _tenant_ctx.set(data.get('tenant_id',''))
    _member_ctx.set(data.get('id',''))
    _admin_ctx.set(is_admin(data))
    _agent_ctx.set('')
    return data

def is_admin(a): return a.get('role') == 'admin' and a.get('tenant_id') == 'tenant-default'

def require_worker(authorization):
    expected=os.getenv('DAEP_WORKER_TOKEN','')
    if len(expected)<32: raise HTTPException(503,'Dedicated DAEP_WORKER_TOKEN is not configured')
    if secrets.compare_digest(hashlib.sha256(expected.encode()).digest(),hashlib.sha256(ADMIN_TOKEN.encode()).digest()): raise HTTPException(503,'Worker credential must be different from DAEP_ADMIN_TOKEN')
    if not authorization or not authorization.startswith('Bearer '): raise HTTPException(401,'Worker bearer token required')
    supplied=authorization[7:]
    expected_digest=hashlib.sha256(expected.encode()).digest()
    supplied_digest=hashlib.sha256(supplied.encode()).digest()
    if not secrets.compare_digest(supplied_digest,expected_digest): raise HTTPException(401,'Invalid worker credential')
    _service_ctx.set(True)
def require_project_access(c, project_id, a, write=False):
    project=c.execute('SELECT tenant_id,status FROM projects WHERE id=?',(project_id,)).fetchone()
    if not project: raise HTTPException(404,'Project not found')
    if project['tenant_id'] != a.get('tenant_id','tenant-default') and not is_admin(a):
        raise HTTPException(403,'Tenant isolation violation')
    if write and project['status']=='CLOSED': raise HTTPException(409,'Project is closed')
    if is_admin(a): return
    if a.get('actor_type')=='AGENT':
        binding=c.execute("SELECT 1 FROM agent_project_bindings WHERE project_id=? AND agent_id=? AND status='ACTIVE'",
            (project_id,a['agent_id'])).fetchone()
        if not binding: raise HTTPException(403,'Agent project binding required')
        if write: raise HTTPException(403,'Agent cannot perform project-level governance or administration')
        return
    row=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(project_id,a['id'])).fetchone()
    if not row: raise HTTPException(403,'Project membership required')
    if write and row['role'] not in ('owner','manager'): raise HTTPException(403,'Project manager role required')
def require_project_planning_access(c, project_id, a):
    """Allow project product owners to create requirements and tasks, without granting governance rights."""
    require_project_access(c,project_id,a,write=False)
    project=c.execute('SELECT status FROM projects WHERE id=?',(project_id,)).fetchone()
    if project and project['status']=='CLOSED':
        raise HTTPException(409,'Project is closed')
    if is_admin(a): return
    if a.get('actor_type')=='AGENT':
        raise HTTPException(403,'Agent cannot create project requirements or tasks')
    row=c.execute('SELECT role,work_function FROM project_members WHERE project_id=? AND member_id=?',(project_id,a['id'])).fetchone()
    if not row or (row['role'] not in ('owner','manager') and row['work_function']!='product'):
        raise HTTPException(403,'Project manager or product work function required')
def task_project(c, tid):
    r=c.execute('SELECT r.project_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id WHERE t.id=?',(tid,)).fetchone()
    return r['project_id'] if r else None
def require_task_access(c, tid, a, assigned_only=False):
    pid=task_project(c,tid)
    if not pid: raise HTTPException(404,'Task not found')
    project=c.execute('SELECT status FROM projects WHERE id=?',(pid,)).fetchone()
    closed=bool(project and project['status']=='CLOSED')
    if is_admin(a):
        if assigned_only and closed: raise HTTPException(409,'Project is closed')
        return
    if a.get('actor_type')=='AGENT':
        require_project_access(c,pid,a)
        if assigned_only and closed:
            raise HTTPException(409,'Project is closed')
        assignment=c.execute("""SELECT 1 FROM agent_task_assignments
            WHERE task_id=? AND project_id=? AND agent_id=? AND status='ACCEPTED'""",
            (tid,pid,a['agent_id'])).fetchone()
        if not assignment:
            raise HTTPException(403,'Accepted Agent task assignment required')
        return
    if assigned_only:
        if closed: raise HTTPException(409,'Project is closed')
        ok=c.execute('SELECT 1 FROM assignments WHERE task_id=? AND member_id=?',(tid,a['id'])).fetchone()
        if not ok: raise HTTPException(403,'Task assignment required')
    else: require_project_access(c,pid,a)

def event(c,typ,member,task,payload,key=None,tenant_override=None):
    eid='evt_'+uuid.uuid4().hex
    tenant=tenant_override or 'tenant-default'
    if tenant_override:
        pass
    elif task:
        rr=c.execute('SELECT p.tenant_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE t.id=?',(task,)).fetchone()
        if rr: tenant=rr['tenant_id']
    elif member:
        rr=c.execute('SELECT tenant_id FROM members WHERE id=?',(member,)).fetchone()
        if rr: tenant=rr['tenant_id']
    audit_payload=dict(payload or {})
    audit_payload.setdefault('actor_type','AGENT' if _agent_ctx.get() else 'MEMBER')
    if _agent_ctx.get(): audit_payload.setdefault('agent_id',_agent_ctx.get())
    # Agent actions are attributed to the Agent identity, never to its owner's member row.
    actor_member_id=None if _agent_ctx.get() else member
    payload_json=json.dumps(audit_payload)
    if key:
        c.execute('INSERT INTO events(id,event_type,actor_member_id,task_id,payload,created_at,idempotency_key,tenant_id) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(idempotency_key) DO NOTHING',(eid,typ,actor_member_id,task,payload_json,now(),key,tenant))
        prior=c.execute('SELECT id,payload FROM events WHERE idempotency_key=?',(key,)).fetchone()
        if prior:
            if prior['payload'] != payload_json:
                raise HTTPException(409,'Idempotency key was used with a different payload')
            return prior['id']
    else:
        c.execute('INSERT INTO events(id,event_type,actor_member_id,task_id,payload,created_at,idempotency_key,tenant_id) VALUES(?,?,?,?,?,?,?,?)',(eid,typ,actor_member_id,task,payload_json,now(),key,tenant))
    return eid

@app.get('/',include_in_schema=False)
def dashboard(): return FileResponse(os.path.join(os.path.dirname(os.path.dirname(__file__)),'web','index.html'))
def _oidc_discovery():
    issuer=os.getenv('DAEP_OIDC_ISSUER','').rstrip('/')
    if not issuer: raise HTTPException(503,'OIDC is not configured')
    try:
        with urllib.request.urlopen(issuer+'/.well-known/openid-configuration',timeout=10) as r: return json.loads(r.read())
    except Exception as exc: raise HTTPException(503,f'OIDC discovery failed: {exc}')

def _oidc_state_record():
    """Create one-time server-side OIDC state, nonce and PKCE verifier."""
    state=secrets.token_urlsafe(32)
    nonce=secrets.token_urlsafe(32)
    verifier=secrets.token_urlsafe(64)
    expires=datetime.fromtimestamp(time.time()+600,timezone.utc).isoformat()
    with conn() as c:
        c.execute('DELETE FROM oidc_states WHERE expires_at<=?',(now(),))
        c.execute('INSERT INTO oidc_states(state_hash,nonce,code_verifier,expires_at,created_at) VALUES(?,?,?,?,?)',
                  (hashlib.sha256(state.encode()).hexdigest(),nonce,verifier,expires,now()))
    return state,nonce,verifier

def _verify_oidc_browser_state(state,cookie_state):
    if not cookie_state or not secrets.compare_digest(hashlib.sha256(cookie_state.encode()).digest(),hashlib.sha256(state.encode()).digest()):
        raise HTTPException(400,'OIDC browser state cookie mismatch')

def _consume_oidc_state(state):
    if not state or len(state)>512: raise HTTPException(400,'Invalid OIDC state')
    digest=hashlib.sha256(state.encode()).hexdigest()
    with conn() as c:
        row=c.execute('SELECT nonce,code_verifier,expires_at FROM oidc_states WHERE state_hash=?',(digest,)).fetchone()
        if not row: raise HTTPException(400,'Invalid or already used OIDC state')
        c.execute('DELETE FROM oidc_states WHERE state_hash=?',(digest,))
    if row['expires_at'] <= now(): raise HTTPException(400,'Expired OIDC state')
    return row['nonce'],row['code_verifier']

@app.get('/api/v1/auth/oidc/login')
def oidc_login():
    if not (os.getenv('DAEP_OIDC_CLIENT_ID') and os.getenv('DAEP_OIDC_REDIRECT_URI')): raise HTTPException(503,'OIDC is not configured')
    d=_oidc_discovery(); state,nonce,verifier=_oidc_state_record()
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    params={'client_id':os.getenv('DAEP_OIDC_CLIENT_ID'),'response_type':'code','redirect_uri':os.getenv('DAEP_OIDC_REDIRECT_URI'),'scope':os.getenv('DAEP_OIDC_SCOPES','openid profile email'),'state':state,'nonce':nonce,'code_challenge':challenge,'code_challenge_method':'S256'}
    if os.getenv('DAEP_OIDC_AUDIENCE'): params['audience']=os.getenv('DAEP_OIDC_AUDIENCE')
    response=RedirectResponse(d['authorization_endpoint']+'?'+urllib.parse.urlencode(params),status_code=302)
    response.set_cookie('daep_oidc_state',state,max_age=600,httponly=True,secure=os.getenv('DAEP_OIDC_REDIRECT_URI','').startswith('https://'),samesite='lax',path='/api/v1/auth/oidc/callback')
    return response

@app.get('/api/v1/auth/oidc/callback')
def oidc_callback(code:str,state:str,daep_oidc_state:Optional[str]=Cookie(None)):
    client_id=os.getenv('DAEP_OIDC_CLIENT_ID',''); client_secret=os.getenv('DAEP_OIDC_CLIENT_SECRET','')
    redirect_uri=os.getenv('DAEP_OIDC_REDIRECT_URI','')
    if not client_id or not client_secret or not redirect_uri: raise HTTPException(503,'OIDC client is not configured')
    _verify_oidc_browser_state(state,daep_oidc_state)
    nonce,code_verifier=_consume_oidc_state(state); d=_oidc_discovery()
    form=urllib.parse.urlencode({'grant_type':'authorization_code','code':code,'redirect_uri':redirect_uri,'client_id':client_id,'client_secret':client_secret,'code_verifier':code_verifier}).encode()
    req=urllib.request.Request(d['token_endpoint'],data=form,method='POST',headers={'Content-Type':'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req,timeout=15) as r: tokens=json.loads(r.read())
    except Exception: raise HTTPException(502,'OIDC token exchange failed')
    id_token=tokens.get('id_token')
    if not id_token: raise HTTPException(502,'OIDC provider did not return an id_token')
    try:
        import jwt
        jwks_client=jwt.PyJWKClient(d['jwks_uri'],timeout=10)
        signing_key=jwks_client.get_signing_key_from_jwt(id_token).key
        claims=jwt.decode(id_token,signing_key,algorithms=['RS256','RS384','RS512','PS256','ES256'],audience=client_id,issuer=os.getenv('DAEP_OIDC_ISSUER').rstrip('/'),options={'require':['exp','iat','sub','iss','aud']})
        if not secrets.compare_digest(str(claims.get('nonce','')),nonce): raise ValueError('OIDC nonce mismatch')
        audiences=claims.get('aud',[])
        if isinstance(audiences,list) and len(audiences)>1 and claims.get('azp')!=client_id: raise ValueError('OIDC authorized party mismatch')
    except Exception: raise HTTPException(401,'OIDC ID token validation failed')
    subject=str(claims.get('sub','')); email=str(claims.get('email',''))
    if not subject: raise HTTPException(401,'OIDC subject is missing')
    created=now(); raw=uuid.uuid4().hex+uuid.uuid4().hex; digest=hashlib.sha256(raw.encode()).hexdigest()
    service_reset=_service_ctx.set(True)
    try:
        with conn() as c:
            row=c.execute('SELECT id FROM members WHERE oidc_subject=?',(subject,)).fetchone()
            if row:
                c.execute("UPDATE members SET token=?,token_status='ACTIVE',token_created_at=?,token_revoked_at=NULL,oidc_email=? WHERE id=?",(digest,created,email,row['id']))
                member_id=row['id']
            else:
                if os.getenv('DAEP_OIDC_AUTO_PROVISION','false').lower()!='true': raise HTTPException(403,'OIDC identity is not provisioned')
                member_id='mem_'+uuid.uuid4().hex[:12]; tenant_id=os.getenv('DAEP_OIDC_DEFAULT_TENANT','tenant-default'); name=str(claims.get('name') or email or subject)
                if not c.execute("SELECT 1 FROM tenants WHERE id=? AND status='ACTIVE'",(tenant_id,)).fetchone(): raise HTTPException(403,'OIDC default tenant is unavailable')
                oidc_role=os.getenv('DAEP_OIDC_DEFAULT_ROLE','developer')
                if oidc_role not in ('developer','manager','reviewer'): oidc_role='developer'
                c.execute("INSERT INTO members(id,name,role,token,created_at,tenant_id,token_status,token_created_at,oidc_subject,oidc_email) VALUES(?,?,?,?,?,?,?,?,?,?)",(member_id,name,oidc_role,digest,created,tenant_id,'ACTIVE',created,subject,email))
    finally:
        _service_ctx.reset(service_reset)
    response=JSONResponse({'member_id':member_id,'token':raw,'token_expires_at':None,'message':'OIDC authentication succeeded; store this API token securely. It is returned only once.'})
    response.delete_cookie('daep_oidc_state',path='/api/v1/auth/oidc/callback')
    return response

@app.get('/api/v1/auth/oidc/config')
def oidc_config():
    enabled=bool(os.getenv('DAEP_OIDC_ISSUER') and os.getenv('DAEP_OIDC_CLIENT_ID') and os.getenv('DAEP_OIDC_REDIRECT_URI'))
    return {'enabled':enabled,'issuer':os.getenv('DAEP_OIDC_ISSUER',''),'client_id':os.getenv('DAEP_OIDC_CLIENT_ID',''),'redirect_uri':os.getenv('DAEP_OIDC_REDIRECT_URI',''),'scopes':os.getenv('DAEP_OIDC_SCOPES','openid profile email')}

@app.post('/api/v1/integrations/git/webhook')
async def git_webhook(request:Request, body:dict, x_daep_webhook_secret:str=Header('',alias='X-DAEP-Webhook-Secret'), x_daep_tenant_id:str=Header('',alias='X-DAEP-Tenant-ID'), x_daep_provider:str=Header('',alias='X-DAEP-Provider'), x_github_event:str=Header('',alias='X-GitHub-Event'), x_github_delivery:str=Header('',alias='X-GitHub-Delivery'), x_hub_signature_256:str=Header('',alias='X-Hub-Signature-256'), x_gitlab_event:str=Header('',alias='X-Gitlab-Event'), x_gitlab_event_uuid:str=Header('',alias='X-Gitlab-Event-UUID'), x_gitlab_token:str=Header('',alias='X-Gitlab-Token')):
    raw=await request.body()
    provider=(x_daep_provider or ('github' if x_github_event or x_hub_signature_256 else 'gitlab' if x_gitlab_event or x_gitlab_token else 'generic')).lower()
    if provider not in ('github','gitlab','generic'): raise HTTPException(422,'Unsupported Git provider')
    if provider=='github':
        expected=os.getenv('DAEP_GITHUB_WEBHOOK_SECRET') or os.getenv('DAEP_GIT_WEBHOOK_SECRET','')
        if not expected or not x_hub_signature_256 or not x_hub_signature_256.startswith('sha256='): raise HTTPException(401,'GitHub webhook signature is required')
        supplied=x_hub_signature_256.split('=',1)[1]
        actual=hmac.new(expected.encode(),raw,hashlib.sha256).hexdigest()
        if not hmac.compare_digest(actual,supplied): raise HTTPException(401,'Invalid GitHub webhook signature')
        delivery=x_github_delivery
    elif provider=='gitlab':
        expected=os.getenv('DAEP_GITLAB_WEBHOOK_SECRET') or os.getenv('DAEP_GIT_WEBHOOK_SECRET','')
        if not expected or not x_gitlab_token or not secrets.compare_digest(hashlib.sha256(x_gitlab_token.encode()).digest(),hashlib.sha256(expected.encode()).digest()): raise HTTPException(401,'Invalid GitLab webhook token')
        delivery=x_gitlab_event_uuid
    else:
        expected=os.getenv('DAEP_GIT_WEBHOOK_SECRET','')
        if not expected or not x_daep_webhook_secret or not secrets.compare_digest(hashlib.sha256(x_daep_webhook_secret.encode()).digest(),hashlib.sha256(expected.encode()).digest()): raise HTTPException(401,'Invalid webhook secret')
        delivery=request.headers.get('X-DAEP-Delivery','')
    if delivery and len(delivery)>200: raise HTTPException(422,'Webhook delivery id is too long')
    event_type=str(body.get('event_type') or body.get('action') or x_github_event or x_gitlab_event or 'push')[:80]
    task_id=body.get('task_id'); commit=body.get('after') or body.get('commit_sha')
    service_reset=_service_ctx.set(True)
    try:
        with conn() as c:
            if task_id:
                row=c.execute('SELECT p.tenant_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE t.id=?',(task_id,)).fetchone()
                if not row: raise HTTPException(404,'Task not found')
                tenant_id=row['tenant_id']
            else:
                tenant_id=str(x_daep_tenant_id or body.get('tenant_id') or '').strip()
                if not tenant_id: raise HTTPException(422,'X-DAEP-Tenant-ID is required when task_id is absent')
                if not c.execute("SELECT 1 FROM tenants WHERE id=? AND status='ACTIVE'",(tenant_id,)).fetchone(): raise HTTPException(404,'Tenant not found or inactive')
        _tenant_ctx.set(tenant_id); _admin_ctx.set(False)
        _service_ctx.reset(service_reset); service_reset=_service_ctx.set(False)
        with conn() as c:
            eid=event(c,'git.webhook.received',None,task_id,{'provider':provider,'delivery_id':delivery,'event_type':event_type,'commit_sha':commit,'payload':body},key=(f'git:{provider}:{delivery}' if delivery else None),tenant_override=tenant_id)
        return {'accepted':True,'event_id':eid,'event_type':event_type,'commit_sha':commit,'tenant_id':tenant_id,'provider':provider,'delivery_id':delivery}
    finally:
        _service_ctx.reset(service_reset)

@app.post('/api/v1/tasks/{task_id}/agent-assignments')
def assign_task_to_agent(task_id:str, body:dict, authorization:str=Header(None)):
    a=actor(authorization)
    if a.get('actor_type')=='AGENT': raise HTTPException(403,'Only a project manager can assign an Agent')
    agent_id=str(body.get('agent_id','')).strip()
    if not agent_id: raise HTTPException(422,'agent_id is required')
    with conn() as c:
        begin_serialized_write(c)
        pid=task_project(c,task_id)
        if not pid: raise HTTPException(404,'Task not found')
        require_project_access(c,pid,a,write=True)
        if not is_admin(a):
            role=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not role or role['role'] not in ('owner','manager'): raise HTTPException(403,'Project manager role required')
        project=c.execute('SELECT tenant_id,status FROM projects WHERE id=?',(pid,)).fetchone()
        if project['status']=='CLOSED': raise HTTPException(409,'Project is closed')
        agent=c.execute("SELECT id,status FROM agents WHERE id=? AND tenant_id=?",(agent_id,project['tenant_id'])).fetchone()
        if not agent or agent['status']!='ACTIVE': raise HTTPException(404,'Active Agent not found in this tenant')
        binding=c.execute("SELECT 1 FROM agent_project_bindings WHERE project_id=? AND agent_id=? AND status='ACTIVE'",(pid,agent_id)).fetchone()
        if not binding: raise HTTPException(409,'Agent must be actively bound to this project before assignment')
        existing=c.execute("SELECT id,status FROM agent_task_assignments WHERE task_id=? AND agent_id=? AND status IN ('ASSIGNED','ACCEPTED')",(task_id,agent_id)).fetchone()
        if existing: raise HTTPException(409,'Agent already has an active assignment for this task')
        assignment_id='agta_'+uuid.uuid4().hex[:16]; stamp=now()
        c.execute("""INSERT INTO agent_task_assignments
            (id,task_id,project_id,agent_id,tenant_id,assigned_by_member_id,status,created_at,updated_at)
            VALUES(?,?,?,?,?,?,'ASSIGNED',?,?)""",
            (assignment_id,task_id,pid,agent_id,project['tenant_id'],a['id'],stamp,stamp))
        event(c,'task.agent_assigned',a['id'],task_id,{'assignment_id':assignment_id,'agent_id':agent_id,'project_id':pid},tenant_override=project['tenant_id'])
        return {'id':assignment_id,'task_id':task_id,'project_id':pid,'agent_id':agent_id,'status':'ASSIGNED','created_at':stamp}

@app.get('/api/v1/tasks/{task_id}/agent-assignments')
def list_task_agent_assignments(task_id:str, authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        pid=task_project(c,task_id)
        if not pid: raise HTTPException(404,'Task not found')
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT x.id,x.task_id,x.project_id,x.agent_id,g.name agent_name,x.status,
            x.assigned_by_member_id,x.created_at,x.updated_at,x.accepted_at,x.revoked_at
            FROM agent_task_assignments x JOIN agents g ON g.id=x.agent_id
            WHERE x.task_id=? ORDER BY x.created_at DESC""",(task_id,)).fetchall()
        return {'task_id':task_id,'items':[dict(x) for x in rows]}

@app.post('/api/v1/agent-assignments/{assignment_id}/revoke')
def revoke_agent_task_assignment(assignment_id:str, body:dict=None, authorization:str=Header(None)):
    a=actor(authorization); reason=str((body or {}).get('reason','')).strip()
    with conn() as c:
        begin_serialized_write(c)
        row=c.execute('SELECT * FROM agent_task_assignments WHERE id=?',(assignment_id,)).fetchone()
        if not row: raise HTTPException(404,'Agent task assignment not found')
        require_project_access(c,row['project_id'],a,write=True)
        if a.get('actor_type')=='AGENT': raise HTTPException(403,'Agent cannot revoke its own assignment')
        if not is_admin(a):
            role=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(row['project_id'],a['id'])).fetchone()
            if not role or role['role'] not in ('owner','manager'): raise HTTPException(403,'Project manager role required')
        if row['status'] not in ('ASSIGNED','ACCEPTED'): raise HTTPException(409,'Assignment is not active')
        stamp=now()
        c.execute("UPDATE agent_task_assignments SET status='REVOKED',revoked_at=?,updated_at=? WHERE id=?",(stamp,stamp,assignment_id))
        event(c,'task.agent_assignment_revoked',a['id'],row['task_id'],{'assignment_id':assignment_id,'agent_id':row['agent_id'],'reason':reason})
        return {'id':assignment_id,'status':'REVOKED','revoked_at':stamp}

@app.get('/api/v1/agents/me/tasks')
def list_my_agent_tasks(authorization:str=Header(None)):
    a=actor(authorization)
    if a.get('actor_type')!='AGENT': raise HTTPException(403,'Agent Token required')
    with conn() as c:
        rows=c.execute("""SELECT x.id assignment_id,x.status assignment_status,x.created_at assigned_at,x.accepted_at,
            t.id task_id,t.title,t.description,t.status task_status,t.progress,t.updated_at,
            r.id requirement_id,r.title requirement_title,r.project_id,p.name project_name
            FROM agent_task_assignments x JOIN tasks t ON t.id=x.task_id
            JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=x.project_id
            JOIN agent_project_bindings b ON b.project_id=x.project_id AND b.agent_id=x.agent_id AND b.status='ACTIVE'
            WHERE x.agent_id=? AND x.status IN ('ASSIGNED','ACCEPTED') AND p.status='ACTIVE'
            ORDER BY x.created_at DESC""",(a['agent_id'],)).fetchall()
        return {'agent_id':a['agent_id'],'items':[dict(x) for x in rows]}

@app.post('/api/v1/agent-assignments/{assignment_id}/accept')
def accept_agent_task_assignment(assignment_id:str, authorization:str=Header(None)):
    a=actor(authorization)
    if a.get('actor_type')!='AGENT': raise HTTPException(403,'Agent Token required')
    with conn() as c:
        begin_serialized_write(c)
        row=c.execute('SELECT * FROM agent_task_assignments WHERE id=? AND agent_id=?',(assignment_id,a['agent_id'])).fetchone()
        if not row: raise HTTPException(404,'Assignment not found for this Agent')
        require_project_access(c,row['project_id'],a)
        project=c.execute('SELECT status FROM projects WHERE id=?',(row['project_id'],)).fetchone()
        if not project or project['status']=='CLOSED': raise HTTPException(409,'Project is closed or unavailable')
        if row['status']=='ACCEPTED': return {'id':assignment_id,'status':'ACCEPTED'}
        if row['status']!='ASSIGNED': raise HTTPException(409,'Assignment is no longer available')
        binding=c.execute("SELECT 1 FROM agent_project_bindings WHERE project_id=? AND agent_id=? AND status='ACTIVE'",(row['project_id'],a['agent_id'])).fetchone()
        if not binding: raise HTTPException(403,'Active project binding required')
        stamp=now()
        c.execute("UPDATE agent_task_assignments SET status='ACCEPTED',accepted_at=?,updated_at=? WHERE id=? AND status='ASSIGNED'",(stamp,stamp,assignment_id))
        event(c,'task.agent_assignment_accepted',a['id'],row['task_id'],{'assignment_id':assignment_id,'agent_id':a['agent_id']})
        return {'id':assignment_id,'status':'ACCEPTED','accepted_at':stamp}

@app.get('/health')
def health():
    service_reset=_service_ctx.set(True)
    try:
        with conn() as c:
            pending=c.execute("SELECT COUNT(*) n FROM outbox WHERE status IN ('PENDING','IN_FLIGHT')").fetchone()['n']
        return {'status':'ok','service':'daep-api','version':'1.0.0-rc9','outbox_pending':pending}
    finally:
        _service_ctx.reset(service_reset)

@app.get('/readyz')
def readiness():
    service_reset=_service_ctx.set(True)
    try:
        with conn() as c:
            c.execute('SELECT 1').fetchone()
            if DATABASE_URL.startswith(('postgresql://','postgres://')):
                c.execute("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='members'").fetchone()
        return {'status':'ready','service':'daep-api','version':'1.0.0-rc9'}
    except Exception:
        raise HTTPException(503,'DAEP database readiness check failed')
    finally:
        _service_ctx.reset(service_reset)
@app.post('/api/v1/auth/login')
def password_login(body:dict):
    username=str(body.get('username','')).strip().lower()
    password=str(body.get('password',''))
    if not username or len(username)>120 or not password:
        raise HTTPException(422,'Username and password are required')
    with conn() as c:
        row=c.execute("SELECT * FROM members WHERE lower(username)=? AND password_status='ACTIVE' AND token_status='ACTIVE'",(username,)).fetchone()
    if not row or not row['password_hash'] or not verify_password(password,row['password_hash']):
        raise HTTPException(401,'Invalid username or password')
    raw=issue_member_token(row['id'])
    return {'access_token':raw,'token_type':'bearer','member_id':row['id'],'name':row['name']}

@app.post('/api/v1/auth/logout')
def logout(authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        stamp=now()
        c.execute("UPDATE members SET token_status='REVOKED',token_revoked_at=? WHERE id=?",(stamp,a['id']))
        event(c,'member.logout',a['id'],None,{'member_id':a['id']},tenant_override=a.get('tenant_id','tenant-default'))
    return {'logged_out':True}

@app.patch('/api/v1/me')
def update_me(body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    name=str(body.get('name','')).strip()
    username=str(body.get('username','')).strip().lower()
    if not name or len(name)>120: raise HTTPException(422,'Name is required and must be at most 120 characters')
    if not re.fullmatch(r'[a-z0-9][a-z0-9._-]{1,119}',username): raise HTTPException(422,'Invalid username')
    with conn() as c:
        conflict=c.execute('SELECT id FROM members WHERE lower(username)=? AND id<>?',(username,a['id'])).fetchone()
        if conflict: raise HTTPException(409,'Username already exists')
        c.execute('UPDATE members SET name=?,username=? WHERE id=?',(name,username,a['id']))
        event(c,'member.profile.updated',a['id'],None,{'member_id':a['id'],'name':name,'username':username},tenant_override=a.get('tenant_id','tenant-default'))
    return {'id':a['id'],'name':name,'username':username,'role':a['role']}

@app.post('/api/v1/auth/change-password')
def change_password(body:dict,authorization:str=Header(None)):
    a=actor(authorization); current=str(body.get('current_password','')); new=str(body.get('new_password',''))
    if len(new)<12 or len(new)>256 or not current: raise HTTPException(422,'Password must be 12-256 characters')
    with conn() as c:
        row=c.execute("SELECT password_hash FROM members WHERE id=?",(a['id'],)).fetchone()
    if not row or not row['password_hash'] or not verify_password(current,row['password_hash']):
        raise HTTPException(401,'Current password is incorrect')
    with conn() as c: c.execute("UPDATE members SET password_hash=?,password_status='ACTIVE' WHERE id=?",(hash_password(new),a['id']))
    access_token=issue_member_token(a['id'])
    return {'changed':True,'access_token':access_token,'token_type':'bearer'}

@app.get('/api/v1/me')
def me(authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        row=c.execute('SELECT username FROM members WHERE id=?',(a['id'],)).fetchone()
    return {k:a[k] for k in ('id','name','role')} | {'username': row['username'] if row else None}
@app.post('/api/v1/tenants')
def create_tenant(body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    name=str(body.get('name','')).strip()
    if not name or len(name)>160: raise HTTPException(422,'Tenant name is required')
    tid='ten_'+uuid.uuid4().hex[:12]
    with conn() as c: c.execute('INSERT INTO tenants(id,name,status,created_at) VALUES(?,?,?,?)',(tid,name,'ACTIVE',now()))
    return {'id':tid,'name':name,'status':'ACTIVE'}

@app.get('/api/v1/tenants')
def list_tenants(authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    with conn() as c: return [dict(x) for x in c.execute('SELECT * FROM tenants ORDER BY created_at')]

@app.post('/api/v1/members')
def create_member(body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    name=str(body.get('name','')).strip()
    role=str(body.get('role','member')).strip()
    if not name: raise HTTPException(422,'Member name is required')
    if role=='admin': raise HTTPException(422,'Only the bootstrap identity can hold the platform administrator role')
    if role!='member' and role not in ('manager','developer','reviewer'): raise HTTPException(422,'Invalid member role')
    explicit_username=bool(body.get('username'))
    username=str(body.get('username') or re.sub(r'[^a-z0-9]+','.',name.lower()).strip('.') or ('user.'+uuid.uuid4().hex[:8])).lower()
    password=body.get('password')
    if password is None or password=='': password=secrets.token_urlsafe(24)
    if not isinstance(password,str) or len(password)<12 or len(password)>256: raise HTTPException(422,'Password must be 12-256 characters')
    mid='mem_'+uuid.uuid4().hex[:12]; token=uuid.uuid4().hex+uuid.uuid4().hex; created=now()
    tenant_id=str(body.get('tenant_id') or a.get('tenant_id') or 'tenant-default')
    with conn() as c:
        if not c.execute("SELECT 1 FROM tenants WHERE id=? AND status='ACTIVE'",(tenant_id,)).fetchone(): raise HTTPException(404,'Tenant not found or inactive')
        if c.execute("SELECT 1 FROM members WHERE lower(username)=?",(username,)).fetchone():
            if explicit_username: raise HTTPException(409,'Username already exists')
            username=f"{username}.{uuid.uuid4().hex[:6]}"
        c.execute('INSERT INTO members(id,name,username,role,token,created_at,tenant_id,token_status,token_created_at,token_revoked_at,token_expires_at,password_hash,password_status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(mid,name,username,role,hashlib.sha256(token.encode()).hexdigest(),created,tenant_id,'ACTIVE',created,None,body.get('token_expires_at'),hash_password(password),'ACTIVE'))
    return {'id':mid,'name':name,'username':username,'role':role,'tenant_id':tenant_id,'token':token}
@app.get('/api/v1/members')
def members(authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    with conn() as c: return [dict(x) for x in c.execute("SELECT id,name,username,role,tenant_id,token_status,password_status,created_at FROM members ORDER BY created_at")]
@app.get('/api/v1/members/{member_id}')
def member_detail(member_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    with conn() as c:
        row=c.execute("SELECT id,name,username,role,tenant_id,token_status,password_status,created_at FROM members WHERE id=?",(member_id,)).fetchone()
        if not row: raise HTTPException(404,'Member not found')
        projects=c.execute("""
            SELECT p.id,p.name,pm.role AS project_role,pm.work_function,pm.joined_at
            FROM project_members pm JOIN projects p ON p.id=pm.project_id
            WHERE pm.member_id=? ORDER BY p.created_at DESC
        """,(member_id,)).fetchall()
        return {**dict(row),'projects':[dict(x) for x in projects]}

@app.post('/api/v1/members/{member_id}/disable')
def disable_member(member_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    if member_id==a['id']: raise HTTPException(409,'The active platform administrator cannot disable their own account')
    with conn() as c:
        target=c.execute('SELECT tenant_id FROM members WHERE id=?',(member_id,)).fetchone()
        if not target: raise HTTPException(404,'Member not found')
        stamp=now()
        c.execute("UPDATE members SET password_status='DISABLED',token_status='REVOKED',token_revoked_at=? WHERE id=?",(stamp,member_id))
        owned_agents=c.execute("SELECT id FROM agents WHERE owner_member_id=? AND tenant_id=? AND status='ACTIVE'",
            (member_id,target['tenant_id'])).fetchall()
        for agent_row in owned_agents:
            agent_id=agent_row['id']
            c.execute("UPDATE agents SET status='DISABLED',updated_at=? WHERE id=?",(stamp,agent_id))
            c.execute("UPDATE agent_tokens SET status='REVOKED',revoked_at=? WHERE agent_id=? AND status='ACTIVE'",
                (stamp,agent_id))
            assignments=c.execute("""SELECT id,task_id FROM agent_task_assignments
                WHERE agent_id=? AND status IN ('ASSIGNED','ACCEPTED')""",(agent_id,)).fetchall()
            for assignment in assignments:
                c.execute("""UPDATE agent_task_assignments SET status='REVOKED',revoked_at=?,updated_at=?
                    WHERE id=? AND status IN ('ASSIGNED','ACCEPTED')""",(stamp,stamp,assignment['id']))
                event(c,'task.agent_assignment_revoked',a['id'],assignment['task_id'],{
                    'assignment_id':assignment['id'],'agent_id':agent_id,
                    'reason':'Agent owner account disabled'},tenant_override=target['tenant_id'])
            event(c,'agent.owner_account_disabled',a['id'],None,{'agent_id':agent_id,
                'revoked_assignment_count':len(assignments)},tenant_override=target['tenant_id'])
        event(c,'member.account.disabled',a['id'],None,{'member_id':member_id,
            'disabled_agent_count':len(owned_agents)},tenant_override=target['tenant_id'])
    return {'member_id':member_id,'password_status':'DISABLED','token_status':'REVOKED',
        'disabled_agent_count':len(owned_agents)}

@app.post('/api/v1/members/{member_id}/enable')
def enable_member(member_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    with conn() as c:
        target=c.execute('SELECT tenant_id,password_hash FROM members WHERE id=?',(member_id,)).fetchone()
        if not target: raise HTTPException(404,'Member not found')
        if not target['password_hash']: raise HTTPException(409,'Member has no password; reset password first')
        stamp=now()
        c.execute("UPDATE members SET password_status='ACTIVE',token_status='REVOKED',token_revoked_at=COALESCE(token_revoked_at,?) WHERE id=?",(stamp,member_id))
        event(c,'member.account.enabled',a['id'],None,{'member_id':member_id},tenant_override=target['tenant_id'])
    return {'member_id':member_id,'password_status':'ACTIVE','token_status':'REVOKED'}

@app.post('/api/v1/members/{member_id}/reset-password')
def reset_member_password(member_id:str,body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    password=str(body.get('password',''))
    if len(password)<12 or len(password)>256: raise HTTPException(422,'Password must be 12-256 characters')
    with conn() as c:
        target=c.execute('SELECT tenant_id FROM members WHERE id=?',(member_id,)).fetchone()
        if not target: raise HTTPException(404,'Member not found')
        stamp=now()
        c.execute("UPDATE members SET password_hash=?,password_status='ACTIVE',token_status='REVOKED',token_revoked_at=? WHERE id=?",(hash_password(password),stamp,member_id))
        event(c,'member.password.reset',a['id'],None,{'member_id':member_id},tenant_override=target['tenant_id'])
    return {'member_id':member_id,'password_status':'ACTIVE','token_status':'REVOKED'}

@app.post('/api/v1/members/{member_id}/revoke-token')
def revoke_member_token(member_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    with conn() as c:
        target=c.execute('SELECT tenant_id FROM members WHERE id=?',(member_id,)).fetchone()
        if not target: raise HTTPException(404,'Member not found')
        cur=c.execute("UPDATE members SET token_status='REVOKED',token_revoked_at=? WHERE id=?" ,(now(),member_id))
        event(c,'member.token.revoked',a['id'],None,{'member_id':member_id},tenant_override=target['tenant_id'])
    return {'member_id':member_id,'token_status':'REVOKED'}

@app.post('/api/v1/members/{member_id}/rotate-token')
def rotate_member_token(member_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    token=uuid.uuid4().hex+uuid.uuid4().hex; created=now(); digest=hashlib.sha256(token.encode()).hexdigest()
    with conn() as c:
        target=c.execute('SELECT tenant_id FROM members WHERE id=?',(member_id,)).fetchone()
        if not target: raise HTTPException(404,'Member not found')
        cur=c.execute("UPDATE members SET token=?,token_status='ACTIVE',token_created_at=?,token_revoked_at=NULL WHERE id=?",(digest,created,member_id))
        event(c,'member.token.rotated',a['id'],None,{'member_id':member_id},tenant_override=target['tenant_id'])
    return {'member_id':member_id,'token':token,'token_status':'ACTIVE','token_created_at':created}

@app.post('/api/v1/projects')
def create_project(b:ProjectIn,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    pid='prj_'+uuid.uuid4().hex[:12]
    with conn() as c:
        if not c.execute('SELECT 1 FROM tenants WHERE id=?',(b.tenant_id,)).fetchone(): raise HTTPException(422,'Tenant not found')
        c.execute('INSERT INTO projects(id,name,description,created_by,created_at,tenant_id) VALUES(?,?,?,?,?,?)',(pid,b.name,b.description,a['id'],now(),b.tenant_id))
        c.execute('INSERT INTO project_members(project_id,member_id,role,work_function,joined_at) VALUES(?,?,?,?,?)',(pid,a['id'],'owner','other',now()))
    return {'id':pid,'name':b.name,'description':b.description}
@app.get('/api/v1/projects')
def projects(authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        if is_admin(a): rows=c.execute('SELECT * FROM projects ORDER BY created_at DESC')
        else: rows=c.execute('SELECT p.*,pm.role AS project_role,pm.work_function FROM projects p JOIN project_members pm ON pm.project_id=p.id WHERE pm.member_id=? AND p.tenant_id=? ORDER BY p.created_at DESC',(a['id'],a.get('tenant_id','tenant-default')))
        return [dict(x) for x in rows]
@app.post('/api/v1/projects/{pid}/close')
def close_project(pid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization); reason=str(b.get('reason','')).strip()
    if len(reason)<10: raise HTTPException(422,'Closure reason must be at least 10 characters')
    with conn() as c:
        begin_serialized_write(c)
        require_project_access(c,pid,a,write=True)
        project=c.execute('SELECT status FROM projects WHERE id=?',(pid,)).fetchone()
        if project['status']=='CLOSED': raise HTTPException(409,'Project is already closed')
        blockers=[]
        reqs=c.execute("SELECT id,title,status FROM requirements WHERE project_id=? AND status!='ACCEPTED'",(pid,)).fetchall()
        if reqs: blockers.append({'type':'requirements','ids':[x['id'] for x in reqs]})
        tasks=c.execute("""SELECT t.id,t.status FROM tasks t JOIN requirements r ON r.id=t.requirement_id
                           WHERE r.project_id=? AND t.status!='DONE'""",(pid,)).fetchall()
        if tasks: blockers.append({'type':'tasks','ids':[x['id'] for x in tasks]})
        packages=c.execute("SELECT id FROM task_work_packages WHERE project_id=? AND status='ACTIVE'",(pid,)).fetchall()
        if packages: blockers.append({'type':'active_work_packages','ids':[x['id'] for x in packages]})
        attention=c.execute("SELECT id FROM task_work_packages WHERE project_id=? AND status='ACTIVE' AND needs_attention=1",(pid,)).fetchall()
        if attention: blockers.append({'type':'exceptions','ids':[x['id'] for x in attention]})
        delegations=c.execute("SELECT id FROM task_delegations WHERE project_id=? AND status='PENDING'",(pid,)).fetchall()
        if delegations: blockers.append({'type':'pending_delegations','ids':[x['id'] for x in delegations]})
        approvals=c.execute("SELECT id FROM project_approvals WHERE project_id=? AND status='PENDING'",(pid,)).fetchall()
        if approvals: blockers.append({'type':'pending_approvals','ids':[x['id'] for x in approvals]})
        if blockers: raise HTTPException(409,detail={'message':'Project cannot be closed until all delivery obligations are complete','blockers':blockers})
        stamp=now()
        updated=c.execute("UPDATE projects SET status='CLOSED' WHERE id=? AND status='ACTIVE'",(pid,)).rowcount
        if updated != 1: raise HTTPException(409,'Project closure state changed concurrently')
        current=c.execute('SELECT status,tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        if not current or current['status']!='CLOSED': raise HTTPException(409,'Project closure was not persisted')
        event(c,'project.closed',a['id'],None,{'project_id':pid,'reason':reason},tenant_override=current['tenant_id'])
    return {'project_id':pid,'status':'CLOSED','closed_at':stamp,'reason':reason}

@app.post('/api/v1/projects/{pid}/reopen')
def reopen_project(pid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization); reason=str(b.get('reason','')).strip()
    if len(reason)<10: raise HTTPException(422,'Reopen reason must be at least 10 characters')
    action_reset=_lifecycle_action_ctx.set('REOPEN')
    try:
        with conn() as c:
            begin_serialized_write(c)
            require_project_access(c,pid,a)
            role=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not is_admin(a) and (not role or role['role']!='owner'):
                raise HTTPException(403,'Project owner approval required')
            project=c.execute('SELECT status,tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
            if project['status']!='CLOSED': raise HTTPException(409,'Project is not closed')
            stamp=now()
            c.execute("UPDATE projects SET status='ACTIVE' WHERE id=? AND status='CLOSED'",(pid,))
            event(c,'project.reopened',a['id'],None,{'project_id':pid,'reason':reason},tenant_override=project['tenant_id'])
            return {'project_id':pid,'status':'ACTIVE','reopened_at':stamp,'reason':reason}
    finally:
        _lifecycle_action_ctx.reset(action_reset)

@app.get('/api/v1/projects/{pid}/members')
def project_members(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        return [dict(x) for x in c.execute('SELECT m.id,m.name,m.username,m.role AS account_role,pm.role AS project_role,pm.work_function,pm.joined_at FROM project_members pm JOIN members m ON m.id=pm.member_id WHERE pm.project_id=? ORDER BY pm.joined_at',(pid,))]
@app.get('/api/v1/projects/{pid}/member-candidates')
def project_member_candidates(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        if not project: raise HTTPException(404,'Project not found')
        rows=c.execute("""
            SELECT m.id,m.name,m.username,m.role AS account_role,
                   CASE WHEN pm.member_id IS NULL THEN 0 ELSE 1 END AS already_member,
                   pm.role AS project_role,pm.work_function
            FROM members m
            LEFT JOIN project_members pm ON pm.project_id=? AND pm.member_id=m.id
            WHERE m.tenant_id=? AND m.password_status='ACTIVE'
            ORDER BY m.name
        """,(pid,project['tenant_id'])).fetchall()
        return [dict(x) for x in rows]

@app.post('/api/v1/projects/{pid}/members')
def add_project_member(pid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization)
    mid=b.get('member_id') or b.get('member_username'); role=b.get('role','member'); work_function=b.get('work_function','other')
    if role not in ('member','reviewer','manager') and role != 'owner': raise HTTPException(422,'Invalid project role')
    if work_function not in ('developer','tester','product','architect','other'): raise HTTPException(422,'Invalid work function')
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        if role=='manager' and not is_admin(a):
            own=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not own or own['role']!='owner': raise HTTPException(403,'Only project owners may directly grant manager role; use an approval request')
        member_row=c.execute('SELECT tenant_id FROM members WHERE id=?',(mid,)).fetchone()
        project_row=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        if not member_row: raise HTTPException(404,'Member not found')
        if project_row['tenant_id'] != member_row['tenant_id']: raise HTTPException(400,'Member belongs to a different tenant')  # recipient tenant is validated against the project tenant before membership mutation
        c.execute('INSERT INTO project_members(project_id,member_id,role,work_function,joined_at) VALUES(?,?,?,?,?) ON CONFLICT(project_id,member_id) DO UPDATE SET role=excluded.role,work_function=excluded.work_function',(pid,mid,role,work_function,now()))
        event(c,'project.member.role_set',a['id'],None,{'project_id':pid,'member_id':mid,'role':role},tenant_override=project_row['tenant_id'])
        return {'project_id':pid,'member_id':mid,'role':role,'work_function':work_function}
@app.patch('/api/v1/projects/{pid}/members/{member_id}/function')
def update_project_member_function(pid:str,member_id:str,b:ProjectMemberFunctionIn,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        target=c.execute('SELECT role,work_function FROM project_members WHERE project_id=? AND member_id=?',(pid,member_id)).fetchone()
        if not target: raise HTTPException(404,'Target is not a project member')
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        c.execute('UPDATE project_members SET work_function=? WHERE project_id=? AND member_id=?',(b.work_function,pid,member_id))
        event(c,'project.member.work_function_set',a['id'],None,{'project_id':pid,'member_id':member_id,'work_function':b.work_function},tenant_override=project['tenant_id'])
        return {'project_id':pid,'member_id':member_id,'project_role':target['role'],'work_function':b.work_function}

@app.delete('/api/v1/projects/{pid}/members/{member_id}')
def remove_project_member(pid:str,member_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        target=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',
            (pid,member_id)).fetchone()
        if not target:
            raise HTTPException(404,'Target is not a project member')
        if target['role'] in ('owner','manager') and not is_admin(a):
            own=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',
                (pid,a['id'])).fetchone()
            if not own or own['role']!='owner':
                raise HTTPException(403,'Only project owners may remove project owners or managers')
        if target['role']=='owner':
            owner_count=c.execute("SELECT COUNT(*) AS n FROM project_members WHERE project_id=? AND role='owner'",
                (pid,)).fetchone()['n']
            if owner_count<=1:
                raise HTTPException(409,'A project must retain at least one owner')
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        removed_assignments=c.execute("""
            DELETE FROM assignments
            WHERE member_id=? AND task_id IN (
                SELECT t.id FROM tasks t JOIN requirements r ON r.id=t.requirement_id
                WHERE r.project_id=?
            )
        """,(member_id,pid)).rowcount
        c.execute('DELETE FROM project_members WHERE project_id=? AND member_id=?',(pid,member_id))
        event(c,'project.member.removed',a['id'],None,{
            'project_id':pid,'member_id':member_id,'previous_role':target['role'],
            'removed_assignment_count':removed_assignments
        },tenant_override=project['tenant_id'])
        return {'project_id':pid,'member_id':member_id,'removed':True,
            'previous_role':target['role'],'removed_assignment_count':removed_assignments}

@app.post('/api/v1/projects/{pid}/role-change-requests')
def request_project_role_change(pid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization); member_id=str(b.get('member_id','')).strip(); new_role=str(b.get('new_role','')).strip()
    reason=str(b.get('reason','')).strip()
    if not member_id or new_role not in ('member','reviewer','manager') or not reason or len(reason)>1000:
        raise HTTPException(422,'member_id, valid new_role and reason (1-1000 chars) are required')
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        target=c.execute('SELECT tenant_id FROM members WHERE id=?',(member_id,)).fetchone()
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        if not target or target['tenant_id']!=project['tenant_id']: raise HTTPException(404,'Member not found in project tenant')
        if not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(pid,member_id)).fetchone(): raise HTTPException(404,'Target is not a project member')
        current=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,member_id)).fetchone()['role']
        if current==new_role: raise HTTPException(409,'Member already has requested role')
        aid='apr_'+uuid.uuid4().hex
        payload={'member_id':member_id,'previous_role':current,'new_role':new_role,'reason':reason}
        c.execute("INSERT INTO project_approvals(id,project_id,tenant_id,requester_member_id,action,payload,status,created_at) VALUES(?,?,?,?,? ,?,'PENDING',?)",
                  (aid,pid,project['tenant_id'],a['id'],'PROJECT_ROLE_CHANGE',json.dumps(payload),now()))
        event(c,'project.role_change.requested',a['id'],None,{'approval_id':aid,'project_id':pid,**payload},tenant_override=project['tenant_id'])
        return {'approval_id':aid,'status':'PENDING','project_id':pid,'payload':payload}

@app.get('/api/v1/projects/{pid}/approvals')
def list_project_approvals(pid:str,status:str='PENDING',limit:int=100,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,200))
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute('SELECT * FROM project_approvals WHERE project_id=? AND status=? ORDER BY created_at DESC LIMIT ?',(pid,status,limit)).fetchall()
        return {'items':[{'id':x['id'],'action':x['action'],'payload':json.loads(x['payload']),'status':x['status'],'requester_member_id':x['requester_member_id'],'decided_by':x['decided_by'],'decision_reason':x['decision_reason'],'created_at':x['created_at'],'decided_at':x['decided_at']} for x in rows]}

@app.post('/api/v1/projects/{pid}/approvals/{approval_id}/decision')
def decide_project_approval(pid:str,approval_id:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization); decision=str(b.get('decision','')).upper(); reason=str(b.get('reason','')).strip()
    if decision not in ('APPROVE','REJECT') or not reason or len(reason)>1000: raise HTTPException(422,'decision must be APPROVE or REJECT and reason is required')
    with conn() as c:
        require_project_access(c,pid,a)
        if not is_admin(a):
            own=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not own or own['role']!='owner': raise HTTPException(403,'Project owner approval required')
        row=c.execute('SELECT * FROM project_approvals WHERE id=? AND project_id=?',(approval_id,pid)).fetchone()
        if not row: raise HTTPException(404,'Approval not found')
        if row['status']!='PENDING': raise HTTPException(409,'Approval already decided')
        if row['requester_member_id']==a['id']: raise HTTPException(403,'Requester cannot approve their own request')
        payload=json.loads(row['payload'])
        if row['action']!='PROJECT_ROLE_CHANGE': raise HTTPException(409,'Unsupported approval action')
        if decision=='APPROVE':
            current=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,payload['member_id'])).fetchone()
            if not current or current['role']!=payload['previous_role']: raise HTTPException(409,'Target role changed since request; submit a new request')
            c.execute('UPDATE project_members SET role=? WHERE project_id=? AND member_id=?',(payload['new_role'],pid,payload['member_id']))
        stamp=now()
        approval_status='APPROVED' if decision=='APPROVE' else 'REJECTED'
        c.execute('UPDATE project_approvals SET status=?,decided_by=?,decision_reason=?,decided_at=? WHERE id=? AND status=?',(approval_status,a['id'],reason,stamp,approval_id,'PENDING'))
        event(c,'project.role_change.'+('approved' if decision=='APPROVE' else 'rejected'),a['id'],None,{'approval_id':approval_id,'project_id':pid,**payload,'decision_reason':reason},tenant_override=row['tenant_id'])
        return {'approval_id':approval_id,'status':approval_status,'member_id':payload['member_id'],'role':payload['new_role'] if decision=='APPROVE' else payload['previous_role']}

@app.get('/api/v1/requirements/{rid}/acceptance-report')
def requirement_acceptance_report(rid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        req=c.execute('SELECT * FROM requirements WHERE id=?',(rid,)).fetchone()
        if not req: raise HTTPException(404,'Requirement not found')
        require_project_access(c,req['project_id'],a)
        criteria=json.loads(req['acceptance_criteria'] or '[]')
        tasks=c.execute("SELECT t.id,t.title,t.status,t.progress,t.updated_at,(SELECT COUNT(*) FROM artifacts ar WHERE ar.task_id=t.id) AS artifact_count FROM tasks t WHERE t.requirement_id=? ORDER BY t.created_at,t.id",(rid,)).fetchall()
        items=[dict(x) for x in tasks]
        missing=[x['id'] for x in items if x['status']!='DONE' or x['artifact_count']<1]
        return {'requirement_id':rid,'project_id':req['project_id'],'title':req['title'],'status':req['status'],
            'acceptance_criteria':[{'index':i,'text':v} for i,v in enumerate(criteria)],'task_count':len(items),
            'tasks':items,'all_tasks_done':bool(items) and all(x['status']=='DONE' for x in items),
            'missing_delivery_evidence_task_ids':missing,'ready_for_acceptance':bool(items) and not missing and bool(criteria)}

@app.post('/api/v1/requirements/{rid}/acceptance')
def decide_requirement_acceptance(rid:str,b:RequirementAcceptanceIn,authorization:str=Header(None)):
    a=actor(authorization)
    if a.get('actor_type')=='AGENT': raise HTTPException(403,'Agent cannot approve or reject requirement acceptance')
    with conn() as c:
        req=c.execute('SELECT * FROM requirements WHERE id=?',(rid,)).fetchone()
        if not req: raise HTTPException(404,'Requirement not found')
        pid=req['project_id']; require_project_access(c,pid,a)
        if not is_admin(a):
            role=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not role or role['role'] not in ('owner','manager','reviewer'): raise HTTPException(403,'Reviewer role required')
        if req['status']=='ACCEPTED': raise HTTPException(409,'Requirement is already accepted')
        criteria=json.loads(req['acceptance_criteria'] or '[]')
        verified=list(dict.fromkeys(b.verified_criteria))
        if len(verified)!=len(b.verified_criteria): raise HTTPException(422,'verified_criteria must be unique')
        if any(i<0 or i>=len(criteria) for i in verified): raise HTTPException(422,'verified_criteria contains an unknown criterion index')
        tasks=c.execute("SELECT t.id,t.status,(SELECT COUNT(*) FROM artifacts ar WHERE ar.task_id=t.id) AS artifact_count FROM tasks t WHERE t.requirement_id=? ORDER BY t.id",(rid,)).fetchall()
        if b.decision=='APPROVE':
            if not criteria or verified!=list(range(len(criteria))): raise HTTPException(409,'Every acceptance criterion must be explicitly verified')
            pending=[x['id'] for x in tasks if x['status']!='DONE']
            missing=[x['id'] for x in tasks if x['artifact_count']<1]
            if not tasks or pending or missing: raise HTTPException(409,detail={'message':'Requirement cannot be accepted until every task is DONE and has delivery evidence','pending_task_ids':pending,'missing_artifact_task_ids':missing})
            status='ACCEPTED'
        else: status='OPEN'
        stamp=now(); c.execute('UPDATE requirements SET status=? WHERE id=?',(status,rid))
        tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id']
        payload={'project_id':pid,'requirement_id':rid,'decision':b.decision,'status':status,'verified_criteria':verified,
            'acceptance_criteria':criteria,'comment':b.comment,'task_ids':[x['id'] for x in tasks]}
        eid=event(c,'requirement.acceptance.'+b.decision.lower(),a['id'],None,payload,tenant_override=tenant)
        return {'requirement_id':rid,'status':status,'decision':b.decision,'event_id':eid,'decided_at':stamp,'verified_criteria':verified}

@app.post('/api/v1/projects/{pid}/decisions')
def record_project_decision(pid:str,b:ProjectDecisionIn,authorization:str=Header(None)):
    a=actor(authorization); decision_id='dec_'+uuid.uuid4().hex
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        accountable=c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(pid,b.accountable_member_id)).fetchone()
        if not accountable: raise HTTPException(422,'Accountable member must belong to this project')
        task_ids=list(dict.fromkeys(b.related_task_ids))
        if len(task_ids)!=len(b.related_task_ids): raise HTTPException(422,'related_task_ids must be unique')
        for task_id in task_ids:
            if task_project(c,task_id)!=pid: raise HTTPException(422,'Every related task must belong to this project')
        payload={'project_id':pid,'decision_id':decision_id,'title':b.title,'decision':b.decision,
            'rationale':b.rationale,'accountable_member_id':b.accountable_member_id,
            'related_task_ids':task_ids,'due_at':b.due_at,'recorded_by':a['id']}
        event(c,'project.decision.created',a['id'],None,payload)
    return {'id':decision_id,'project_id':pid,'status':'RECORDED','created_at':now(),**payload}

@app.get('/api/v1/projects/{pid}/decisions')
def list_project_decisions(pid:str,limit:int=100,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,500))
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("SELECT e.id,e.actor_member_id,e.payload,e.created_at,m.name AS actor_name FROM events e LEFT JOIN members m ON m.id=e.actor_member_id WHERE e.event_type='project.decision.created' AND e.payload LIKE ? ORDER BY e.created_at DESC LIMIT ?",('%"project_id"%"'+pid+'"%',limit)).fetchall()
        items=[]
        for row in rows:
            payload=json.loads(row['payload'] or '{}')
            if payload.get('project_id')!=pid: continue
            accountable=c.execute('SELECT name FROM members WHERE id=?',(payload.get('accountable_member_id'),)).fetchone()
            items.append({'id':payload.get('decision_id'),'title':payload.get('title'),'decision':payload.get('decision'),
                'rationale':payload.get('rationale',''),'accountable_member_id':payload.get('accountable_member_id'),
                'accountable_member_name':accountable['name'] if accountable else None,'related_task_ids':payload.get('related_task_ids',[]),
                'due_at':payload.get('due_at'),'recorded_by':row['actor_member_id'],'recorded_by_name':row['actor_name'],
                'created_at':row['created_at'],'audit_event_id':row['id']})
        return {'project_id':pid,'items':items,'count':len(items)}

@app.get('/api/v1/projects/{pid}/governance')
def project_governance_snapshot(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT t.id,t.status,t.progress,t.updated_at,a.member_id,m.name AS member_name
            FROM tasks t JOIN requirements r ON r.id=t.requirement_id
            LEFT JOIN assignments a ON a.task_id=t.id LEFT JOIN members m ON m.id=a.member_id
            WHERE r.project_id=? ORDER BY t.id""",(pid,)).fetchall()
        task_ids=set(); task_state={}
        for row in rows:
            task_ids.add(row['id'])
            task_state[row['id']]={'status':row['status'],'progress':row['progress']}
        total=len(task_ids)
        status_counts={}
        for item in task_state.values(): status_counts[item['status']]=status_counts.get(item['status'],0)+1
        responsibility={}
        for row in rows:
            if not row['member_id']: continue
            slot=responsibility.setdefault(row['member_id'],{'member_id':row['member_id'],'member_name':row['member_name'],'assigned_task_ids':[],'done':0,'active':0,'review':0,'blocked':0})
            if row['id'] not in slot['assigned_task_ids']:
                slot['assigned_task_ids'].append(row['id'])
                if row['status']=='DONE': slot['done']+=1
                elif row['status']=='REVIEW': slot['review']+=1
                elif row['status']=='BLOCKED': slot['blocked']+=1
                else: slot['active']+=1
        packages=c.execute("SELECT risk_state,COUNT(*) AS n FROM task_work_packages WHERE project_id=? AND status='ACTIVE' GROUP BY risk_state",(pid,)).fetchall()
        package_risks={x['risk_state']:x['n'] for x in packages}
        pending_reviews=status_counts.get('REVIEW',0)
        delivery_health=project_message_delivery_health(pid,authorization,120,300,500)
        review_rows=c.execute("""SELECT e.payload,e.created_at FROM events e
            WHERE e.event_type='message.delivery.incident.reviewed' AND e.payload LIKE ?
            ORDER BY e.created_at DESC LIMIT 1000""",('%'+pid+'%',)).fetchall()
        latest_reviews={}
        for review_row in review_rows:
            try:
                payload=json.loads(review_row['payload'] or '{}')
                if payload.get('project_id')!=pid: continue
                mid=payload.get('message_id')
                if mid and mid not in latest_reviews:
                    latest_reviews[mid]={'disposition':payload.get('disposition'),'comment':payload.get('comment'),
                                         'reviewed_at':review_row['created_at']}
            except (TypeError,ValueError):
                continue
        reviewed_incidents=[]
        open_incidents=0; resolved_incidents=0; accepted_risk_incidents=0; investigating_incidents=0
        for incident in delivery_health.get('incidents',[]):
            review=latest_reviews.get(incident['message_id'])
            disposition=review.get('disposition') if review else 'UNREVIEWED'
            item=dict(incident)
            item['review_disposition']=disposition
            item['reviewed_at']=review.get('reviewed_at') if review else None
            reviewed_incidents.append(item)
            if disposition=='RESOLVED': resolved_incidents+=1
            elif disposition=='ACCEPTED_RISK': accepted_risk_incidents+=1
            else:
                open_incidents+=1
                if disposition=='INVESTIGATING': investigating_incidents+=1
        daily=c.execute("""SELECT substr(m.created_at,1,10) AS day,COUNT(*) AS created,
            SUM(CASE WHEN m.status IN ('ACKNOWLEDGED','REJECTED') THEN 1 ELSE 0 END) AS terminal_ack
            FROM messages m JOIN tasks t ON t.id=m.task_id JOIN requirements r ON r.id=t.requirement_id
            WHERE r.project_id=? AND m.created_at>=? GROUP BY substr(m.created_at,1,10) ORDER BY day""",
            (pid,datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).isoformat())).fetchall()
        delivery_trend=[{'date':x['day'],'messages_created':x['created'],'terminal_ack':x['terminal_ack'] or 0} for x in daily]
        message_delivery_governance={
            'checked_messages':delivery_health.get('checked_messages',0),
            'dispatch_counts':delivery_health.get('dispatch_counts',{}),
            'ack_counts':delivery_health.get('ack_counts',{}),
            'incident_count':delivery_health.get('incident_count',0),
            'open_incidents':open_incidents,'investigating_incidents':investigating_incidents,
            'resolved_incidents':resolved_incidents,'accepted_risk_incidents':accepted_risk_incidents,
            'incidents':reviewed_incidents,'trend_since_utc_midnight':delivery_trend,
            'sla_policy':delivery_health.get('policy'),
            'truncated':delivery_health.get('truncated',False)
        }
        return {'project_id':pid,'task_total':total,'task_status_counts':status_counts,
            'completed_tasks':status_counts.get('DONE',0),'completion_percent':round(status_counts.get('DONE',0)*100/total) if total else 100,
            'pending_reviews':pending_reviews,'open_tasks':total-status_counts.get('DONE',0),
            'active_work_package_risk_counts':package_risks,
            'at_risk_work_packages':sum(package_risks.get(k,0) for k in ('OVERDUE','BLOCKED_DEPENDENCY','STALLED')),
            'responsibility':list(responsibility.values()),
            'completion_gate':'SATISFIED' if total and status_counts.get('DONE',0)==total else ('EMPTY' if not total else 'OPEN'),
            'message_delivery':message_delivery_governance}

@app.get('/api/v1/projects/{pid}/workflow')
def get_project_workflow(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        row=c.execute('SELECT config,updated_by,updated_at FROM project_workflows WHERE project_id=?',(pid,)).fetchone()
        if row: return {'project_id':pid,'config':json.loads(row['config']),'updated_by':row['updated_by'],'updated_at':row['updated_at']}
        return {'project_id':pid,'config':{'enabled':True,'stages':[{'key':'OPEN','name':'需求进入','order':1,'approval_role':'none','sla_seconds':None},{'key':'IN_PROGRESS','name':'执行','order':2,'approval_role':'none','sla_seconds':172800},{'key':'REVIEW','name':'评审验收','order':3,'approval_role':'reviewer','sla_seconds':86400},{'key':'DONE','name':'完成交付','order':4,'approval_role':'none','sla_seconds':None}]},'source':'system-default'}

@app.put('/api/v1/projects/{pid}/workflow')
def set_project_workflow(pid:str,b:WorkflowConfigIn,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        if not (a['role']=='admin' or project_role(c,pid,a) in ('owner','manager')): raise HTTPException(403,'Project manager or platform administrator required')
        stages=sorted([x.model_dump() for x in b.stages],key=lambda x:x['order'])
        if [x['order'] for x in stages] != list(range(1,len(stages)+1)): raise HTTPException(422,'Stage order must be contiguous from 1')
        if len({x['key'] for x in stages}) != len(stages): raise HTTPException(422,'Stage keys must be unique')
        if not any(x['key']=='REVIEW' for x in stages): raise HTTPException(422,'System governance requires a REVIEW stage')
        cfg={'enabled':b.enabled,'stages':stages}; stamp=now(); tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id']
        c.execute('INSERT INTO project_workflows(project_id,tenant_id,config,updated_by,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET config=excluded.config,updated_by=excluded.updated_by,updated_at=excluded.updated_at',(pid,tenant,json.dumps(cfg),a['id'],stamp))
        event(c,'project.workflow.updated',a['id'],None,{'project_id':pid,'config':cfg},tenant_override=tenant)
        return {'project_id':pid,'config':cfg,'updated_by':a['id'],'updated_at':stamp}

@app.get('/api/v1/projects/{pid}/gates')
def get_project_gates(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute('SELECT gate_key,config,updated_by,updated_at FROM project_gates WHERE project_id=? ORDER BY gate_key',(pid,)).fetchall()
        items={r['gate_key']:{'config':json.loads(r['config']),'updated_by':r['updated_by'],'updated_at':r['updated_at']} for r in rows}
        items.setdefault('REVIEW_REQUIRED',{'config':{'enabled':True,'required_roles':['reviewer'],'required_evidence':True,'required_all_tasks_done':False},'system_locked':True})
        items.setdefault('DELIVERY_EVIDENCE',{'config':{'enabled':True,'required_roles':['owner','manager','reviewer'],'required_evidence':True,'required_all_tasks_done':True},'system_locked':True})
        return {'project_id':pid,'gates':items}

@app.put('/api/v1/projects/{pid}/gates/{gate_key}')
def set_project_gate(pid:str,gate_key:str,b:GateConfigIn,authorization:str=Header(None)):
    a=actor(authorization)
    if gate_key in ('REVIEW_REQUIRED','DELIVERY_EVIDENCE'): raise HTTPException(409,'System governance gate cannot be disabled or weakened')
    if not re.fullmatch(r'[A-Z0-9_]{2,60}',gate_key): raise HTTPException(422,'Invalid gate key')
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        if not (a['role']=='admin' or project_role(c,pid,a) in ('owner','manager')): raise HTTPException(403,'Project manager or platform administrator required')
        cfg=b.model_dump(); cfg['applies_to']=cfg.get('applies_to') or 'DONE'; stamp=now(); tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id']
        c.execute('INSERT INTO project_gates(project_id,gate_key,tenant_id,config,updated_by,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(project_id,gate_key) DO UPDATE SET config=excluded.config,updated_by=excluded.updated_by,updated_at=excluded.updated_at',(pid,gate_key,tenant,json.dumps(cfg),a['id'],stamp))
        event(c,'project.gate.updated',a['id'],None,{'project_id':pid,'gate_key':gate_key,'config':cfg},tenant_override=tenant)
        return {'project_id':pid,'gate_key':gate_key,'config':cfg,'updated_at':stamp}


DEFAULT_PROJECT_WORKFLOW={'enabled':True,'stages':[{'key':'OPEN','name':'需求进入','order':1,'approval_role':'none','sla_seconds':None},{'key':'IN_PROGRESS','name':'执行','order':2,'approval_role':'none','sla_seconds':172800},{'key':'REVIEW','name':'评审验收','order':3,'approval_role':'reviewer','sla_seconds':86400},{'key':'DONE','name':'完成交付','order':4,'approval_role':'none','sla_seconds':None}]}
SYSTEM_GOVERNANCE_GATES={
    'REVIEW_REQUIRED':{'enabled':True,'required_roles':['reviewer'],'required_evidence':True,'required_all_tasks_done':False,'applies_to':'DONE'},
    'DELIVERY_EVIDENCE':{'enabled':True,'required_roles':['owner','manager','reviewer'],'required_evidence':True,'required_all_tasks_done':True,'applies_to':'DONE'}
}
def project_role(c,pid,actor_value):
    row=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,actor_value['id'])).fetchone()
    return row['role'] if row else None
def project_workflow_config(c,pid):
    row=c.execute('SELECT config FROM project_workflows WHERE project_id=?',(pid,)).fetchone()
    return json.loads(row['config']) if row else DEFAULT_PROJECT_WORKFLOW
def project_gate_config(c,pid,gate_key):
    if gate_key in SYSTEM_GOVERNANCE_GATES: return SYSTEM_GOVERNANCE_GATES[gate_key]
    row=c.execute('SELECT config FROM project_gates WHERE project_id=? AND gate_key=?',(pid,gate_key)).fetchone()
    return json.loads(row['config']) if row else None
def enforce_project_gate(c,pid,gate_key,actor_member_id,task_id=None,target_stage='DONE'):
    cfg=project_gate_config(c,pid,gate_key)
    if not cfg or not cfg.get('enabled',True) or cfg.get('applies_to','DONE')!=target_stage: return
    if cfg.get('required_roles'):
        platform=c.execute('SELECT role FROM members WHERE id=?',(actor_member_id,)).fetchone()
        if not platform or platform['role']!='admin':
            member_role=project_role(c,pid,{'id':actor_member_id})
            function_row=c.execute('SELECT work_function FROM project_members WHERE project_id=? AND member_id=?',(pid,actor_member_id)).fetchone()
            work_function=function_row['work_function'] if function_row else None
            if member_role not in cfg['required_roles'] and work_function not in cfg['required_roles']:
                raise HTTPException(403,f'Gate {gate_key} requires one of: {", ".join(cfg["required_roles"])}')
    if task_id and cfg.get('required_evidence'):
        if c.execute('SELECT 1 FROM artifacts WHERE task_id=? LIMIT 1',(task_id,)).fetchone() is None:
            raise HTTPException(409,detail={'message':f'Gate {gate_key} requires delivery evidence','gate_key':gate_key,'task_id':task_id})
    if task_id and cfg.get('required_all_tasks_done'):
        row=c.execute('SELECT requirement_id FROM tasks WHERE id=?',(task_id,)).fetchone()
        if row:
            pending=c.execute("SELECT id FROM tasks WHERE requirement_id=? AND status!='DONE' AND id!=?",(row['requirement_id'],task_id)).fetchall()
            if pending: raise HTTPException(409,detail={'message':f'Gate {gate_key} requires all other requirement tasks to be DONE before this task closes','gate_key':gate_key,'pending_task_ids':[x['id'] for x in pending]})
def enforce_workflow_exit(c,pid,current_stage,actor_member_id):
    cfg=project_workflow_config(c,pid)
    stage=next((x for x in cfg.get('stages',[]) if x.get('key')==current_stage),None)
    if not stage: raise HTTPException(409,detail={'message':'Current task status is not part of the configured workflow','current_stage':current_stage})
    approval_role=stage.get('approval_role','none')
    if approval_role!='none':
        platform=c.execute('SELECT role FROM members WHERE id=?',(actor_member_id,)).fetchone()
        if not platform or platform['role']!='admin':
            role=project_role(c,pid,{'id':actor_member_id})
            if role!=approval_role: raise HTTPException(403,f'Leaving workflow stage {current_stage} requires {approval_role} role')
def enforce_workflow_stage(c,pid,stage_key,actor_member_id,task_id=None):
    cfg=project_workflow_config(c,pid)
    stage=next((x for x in cfg.get('stages',[]) if x.get('key')==stage_key),None)
    if not stage: raise HTTPException(409,detail={'message':'Target workflow stage is not configured','stage_key':stage_key})
    for gate_key in [x['gate_key'] for x in c.execute('SELECT gate_key FROM project_gates WHERE project_id=?',(pid,)).fetchall()]:
        enforce_project_gate(c,pid,gate_key,actor_member_id,task_id,stage_key)
def enforce_task_review_request(c,tid,a):
    """Apply REVIEW-stage gates when progress is used to request human review."""
    pid=task_project(c,tid)
    if not pid: raise HTTPException(404,'Task not found')
    workflow=project_workflow_config(c,pid)
    if not any(x.get('key')=='REVIEW' for x in workflow.get('stages',[])):
        raise HTTPException(409,'REVIEW stage is not configured for this project')
    if a.get('actor_type')=='AGENT':
        gate_rows=c.execute('SELECT gate_key FROM project_gates WHERE project_id=?',(pid,)).fetchall()
        for gate_row in gate_rows:
            gate_key=gate_row['gate_key']
            gate=project_gate_config(c,pid,gate_key)
            if not gate or not gate.get('enabled',True) or gate.get('applies_to','DONE')!='REVIEW':
                continue
            if gate.get('required_roles'):
                raise HTTPException(403,'Agent cannot satisfy human role gates')
            enforce_project_gate(c,pid,gate_key,a['id'],tid,'REVIEW')
        return
    enforce_workflow_stage(c,pid,'REVIEW',a['id'],tid)

def transition_task_workflow(c,tid,target_stage,actor_member_id,comment=''):
    pid=task_project(c,tid)
    if not pid: raise HTTPException(404,'Task not found')
    task=c.execute('SELECT status,progress FROM tasks WHERE id=?',(tid,)).fetchone()
    if not task: raise HTTPException(404,'Task not found')
    enforce_workflow_stage(c,pid,target_stage,actor_member_id,tid)
    progress=100 if target_stage=='DONE' else (100 if target_stage=='REVIEW' else task['progress'])
    c.execute('UPDATE tasks SET status=?,progress=?,updated_at=? WHERE id=?',(target_stage,progress,now(),tid))
    eid=event(c,'task.workflow.transitioned',actor_member_id,tid,{'from_status':task['status'],'to_status':target_stage,'comment':comment})
    return eid

@app.get('/api/v1/projects/{pid}/audit')
def project_audit(pid:str,limit:int=100,before:str='',event_type:str='',authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,500))
    with conn() as c:
        require_project_access(c,pid,a)
        sql="SELECT e.* FROM events e LEFT JOIN tasks t ON t.id=e.task_id LEFT JOIN requirements r ON r.id=t.requirement_id WHERE (r.project_id=? OR (e.task_id IS NULL AND e.payload LIKE ?))"
        args=[pid,'%\"project_id\"%\"'+pid+'\"%']
        if before: sql+=" AND e.created_at<?"; args.append(before)
        if event_type: sql+=" AND e.event_type=?"; args.append(event_type)
        sql+=" ORDER BY e.created_at DESC LIMIT ?"; args.append(limit)
        rows=c.execute(sql,args).fetchall()
        return {'project_id':pid,'items':[{'id':x['id'],'event_type':x['event_type'],'actor_member_id':x['actor_member_id'],'task_id':x['task_id'],'payload':json.loads(x['payload'] or '{}'),'created_at':x['created_at']} for x in rows]}

@app.get('/api/v1/projects/{pid}/audit.csv')
def export_project_audit(pid:str,limit:int=5000,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,10000))
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT e.id,e.event_type,e.actor_member_id,e.task_id,e.payload,e.created_at
            FROM events e LEFT JOIN tasks t ON t.id=e.task_id LEFT JOIN requirements r ON r.id=t.requirement_id
            WHERE (r.project_id=? OR (e.task_id IS NULL AND e.payload LIKE ?)) ORDER BY e.created_at DESC LIMIT ?""",(pid,'%\"project_id\"%\"'+pid+'\"%',limit)).fetchall()
        def q(v): return '"'+str(v if v is not None else '').replace('"','""')+'"'
        lines=['id,event_type,actor_member_id,task_id,created_at,payload']
        for x in rows: lines.append(','.join(q(v) for v in (x['id'],x['event_type'],x['actor_member_id'],x['task_id'],x['created_at'],x['payload'])))
        return Response(content='\n'.join(lines)+'\n',media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="daep-audit-{pid}.csv"'})

@app.get('/api/v1/projects/{pid}/requirements')
def project_requirements(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        return [dict(x) for x in c.execute('SELECT * FROM requirements WHERE project_id=? ORDER BY created_at DESC',(pid,))]
@app.get('/api/v1/projects/{pid}/tasks')
def project_tasks(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute('SELECT t.* FROM tasks t JOIN requirements r ON r.id=t.requirement_id WHERE r.project_id=? ORDER BY t.created_at DESC',(pid,)).fetchall()
        result=[]
        for raw in rows:
            item=dict(raw)
            item['dependencies']=[x['depends_on_task_id'] for x in c.execute('SELECT depends_on_task_id FROM dependencies WHERE task_id=?',(item['id'],))]
            result.append(item)
        return result
@app.post('/api/v1/requirements')
def create_requirement(b:RequirementIn,authorization:str=Header(None)):
    a=actor(authorization); rid='req_'+uuid.uuid4().hex[:12]
    with conn() as c:
        project=c.execute('SELECT status FROM projects WHERE id=?',(b.project_id,)).fetchone()
        if not project: raise HTTPException(404,'Project not found')
        if project['status']=='CLOSED': raise HTTPException(409,'Project is closed')
        require_project_planning_access(c,b.project_id,a)
        c.execute('INSERT INTO requirements VALUES(?,?,?,?,?,?,?)',(rid,b.project_id,b.title,b.description,json.dumps(b.acceptance_criteria),'OPEN',now()))
    return {'id':rid,'project_id':b.project_id,'title':b.title,'status':'OPEN'}
@app.get('/api/v1/requirements/{rid}')
def get_requirement(rid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        r=c.execute('SELECT * FROM requirements WHERE id=?',(rid,)).fetchone()
        if r: require_project_access(c,r['project_id'],a)
        if not r: raise HTTPException(404,'Requirement not found')
        d=dict(r); d['acceptance_criteria']=json.loads(d['acceptance_criteria']); return d
@app.post('/api/v1/tasks')
def create_task(b:TaskIn,authorization:str=Header(None)):
    a=actor(authorization); tid='tsk_'+uuid.uuid4().hex[:12]
    with conn() as c:
        req=c.execute('SELECT * FROM requirements WHERE id=?',(b.requirement_id,)).fetchone()
        if not req: raise HTTPException(404,'Requirement not found')
        require_project_planning_access(c,req['project_id'],a)
        for dep in b.dependencies:
            if dep == tid: raise HTTPException(400,'A task cannot depend on itself')
            if not c.execute('SELECT 1 FROM tasks WHERE id=?',(dep,)).fetchone(): raise HTTPException(400,f'Unknown dependency {dep}')
            require_task_access(c,dep,a)
            if task_project(c,dep) != req['project_id']: raise HTTPException(400,'Dependencies must belong to the same project')
        c.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?)',(tid,b.requirement_id,b.title,b.description,'READY',0,now(),now()))
        for mid in b.assignee_member_ids:
            member_row=c.execute('SELECT tenant_id FROM members WHERE id=?',(mid,)).fetchone()
            if not member_row: raise HTTPException(400,f'Unknown member {mid}')
            project_tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(req['project_id'],)).fetchone()['tenant_id']
            if member_row['tenant_id'] != project_tenant: raise HTTPException(400,'Assignee belongs to a different tenant')
            c.execute('INSERT INTO assignments VALUES(?,?)',(tid,mid))
            c.execute("INSERT OR IGNORE INTO project_members(project_id,member_id,role,work_function,joined_at) VALUES(?,?,?,'other',?)",(req['project_id'],mid,'member',now()))
        for dep in b.dependencies: c.execute('INSERT INTO dependencies VALUES(?,?)',(tid,dep))
        event(c,'task.created',a['id'],tid,{'title':b.title})
    return task_detail(tid,authorization)
def task_detail(tid,authorization):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a)
        r=c.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone()
        if not r: raise HTTPException(404,'Task not found')
        d=dict(r); d['assignees']=[dict(x) for x in c.execute('SELECT m.id,m.name FROM assignments a JOIN members m ON m.id=a.member_id JOIN tasks t ON t.id=a.task_id JOIN requirements rq ON rq.id=t.requirement_id JOIN projects p ON p.id=rq.project_id WHERE a.task_id=? AND m.tenant_id=p.tenant_id',(tid,))]; d['dependencies']=[x['depends_on_task_id'] for x in c.execute('SELECT depends_on_task_id FROM dependencies WHERE task_id=?',(tid,))]; return d
@app.get('/api/v1/tasks/{tid}')
def get_task(tid:str,authorization:str=Header(None)): return task_detail(tid,authorization)
@app.put('/api/v1/tasks/{tid}/dependencies')
def update_task_dependencies(tid:str,b:TaskDependenciesIn,authorization:str=Header(None)):
    a=actor(authorization)
    if len(set(b.dependencies)) != len(b.dependencies): raise HTTPException(400,'Duplicate dependencies are not allowed')
    with conn() as c:
        require_task_access(c,tid,a)
        project_id=task_project(c,tid)
        require_project_access(c,project_id,a,write=True)
        for dep in b.dependencies:
            if dep == tid: raise HTTPException(400,'A task cannot depend on itself')
            if task_project(c,dep) != project_id: raise HTTPException(400,'Dependencies must belong to the same project')
            require_task_access(c,dep,a)
            pending=[dep]; visited=set()
            while pending:
                current=pending.pop()
                if current == tid: raise HTTPException(409,'Dependency would create a cycle')
                if current in visited: continue
                visited.add(current)
                pending.extend(x['depends_on_task_id'] for x in c.execute('SELECT depends_on_task_id FROM dependencies WHERE task_id=?',(current,)).fetchall())
        c.execute('DELETE FROM dependencies WHERE task_id=?',(tid,))
        for dep in b.dependencies: c.execute('INSERT INTO dependencies(task_id,depends_on_task_id) VALUES(?,?)',(tid,dep))
        event(c,'task.dependencies.updated',a['id'],tid,{'dependencies':b.dependencies})
    return task_detail(tid,authorization)

@app.get('/api/v1/me/tasks')
def my_tasks(authorization:str=Header(None)):
    a=actor(authorization)
    if a.get('actor_type')=='AGENT':
        raise HTTPException(403,'Use /api/v1/agents/me/tasks for Agent assignments')
    with conn() as c: return [dict(x) for x in c.execute('SELECT t.* FROM tasks t JOIN assignments s ON s.task_id=t.id JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE s.member_id=? AND p.tenant_id=? ORDER BY t.created_at DESC',(a['id'],a.get('tenant_id','tenant-default')))]

@app.post('/api/v1/tasks/{tid}/progress')
def progress(tid:str,b:ProgressIn,authorization:str=Header(None),idempotency_key:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a,assigned_only=True)
        if b.progress==100:
            enforce_task_review_request(c,tid,a)
        if a.get('actor_type')=='AGENT' and b.progress==100:
            if c.execute('SELECT 1 FROM artifacts WHERE task_id=? LIMIT 1',(tid,)).fetchone() is None:
                raise HTTPException(409,'Agent must submit at least one artifact before requesting review')
        identity=a.get('agent_id') if a.get('actor_type')=='AGENT' else a['id']
        scoped_key=f"{identity}:{tid}:{idempotency_key}" if idempotency_key else None
        if scoped_key:
            prior=c.execute('SELECT id,payload FROM events WHERE idempotency_key=?',(scoped_key,)).fetchone()
            if prior:
                prior_payload=json.loads(prior['payload'] or '{}')
                prior_payload.pop('actor_type',None); prior_payload.pop('agent_id',None)
                if prior_payload != b.model_dump(): raise HTTPException(409,'Idempotency-Key was already used with a different payload')
                return {'event_id':prior['id'],'task_id':tid,'progress':b.progress,'idempotent_replay':True}
        c.execute('UPDATE tasks SET progress=?,status=?,updated_at=? WHERE id=?',(b.progress,'REVIEW' if b.progress==100 else ('IN_PROGRESS' if b.progress>0 else 'READY'),now(),tid))
        eid=event(c,'task.progress.updated',a['id'],tid,b.model_dump(),scoped_key)
    return {'event_id':eid,'task_id':tid,'progress':b.progress}
@app.post('/api/v1/tasks/{tid}/blocked')
def blocked(tid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a,assigned_only=True)
        c.execute("UPDATE tasks SET status='BLOCKED',updated_at=? WHERE id=?",(now(),tid)); eid=event(c,'task.blocked',a['id'],tid,b)
    return {'event_id':eid,'status':'BLOCKED'}
@app.post('/api/v1/tasks/{tid}/work-result')
def report_work_result(tid:str,b:WorkResultIn,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        begin_serialized_write(c)
        require_task_access(c,tid,a,assigned_only=True)
        package_sql='SELECT id,parent_task_id,status,correlation_id FROM task_work_packages WHERE child_task_id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): package_sql += ' FOR UPDATE'
        package=c.execute(package_sql,(tid,)).fetchone()
        if not package: raise HTTPException(404,'Task is not a registered work package')
        identity=a.get('agent_id') if a.get('actor_type')=='AGENT' else a['id']
        key=f"work-result:{identity}:{tid}:{b.idempotency_key}" if b.idempotency_key else None
        payload={'outcome':b.outcome,'summary':b.summary,'work_package_id':package['id'],'correlation_id':package['correlation_id'],'parent_task_id':package['parent_task_id']}
        if key:
            prior=c.execute('SELECT id,payload FROM events WHERE idempotency_key=?',(key,)).fetchone()
            if prior:
                prior_payload=json.loads(prior['payload'] or '{}')
                prior_payload.pop('actor_type',None); prior_payload.pop('agent_id',None)
                if prior_payload!=payload: raise HTTPException(409,'Idempotency key was used with a different result')
                return {'task_id':tid,'status':'REVIEW' if b.outcome=='COMPLETE' else 'BLOCKED','event_id':prior['id'],'idempotent_replay':True}
        if package['status']!='ACTIVE': raise HTTPException(409,'Work package is no longer active')
        if b.outcome=='COMPLETE':
            count=c.execute('SELECT COUNT(*) AS n FROM artifacts WHERE task_id=?',(tid,)).fetchone()['n']
            if count<1: raise HTTPException(409,'Submit at least one artifact before reporting completion')
            status='REVIEW'; progress=100
        else:
            status='BLOCKED'; progress=0
        c.execute('UPDATE tasks SET status=?,progress=?,updated_at=? WHERE id=?',(status,progress,now(),tid))
        eid=event(c,'task.work_package.reported',a['id'],tid,payload,key)
    return {'task_id':tid,'status':status,'event_id':eid,'outcome':b.outcome}


@app.post('/api/v1/tasks/{tid}/workflow-transition')
def transition_task_workflow_endpoint(tid:str,b:dict,authorization:str=Header(None),idempotency_key:str=Header(None)):
    a=actor(authorization); target=str(b.get('target_stage','')).strip().upper(); comment=str(b.get('comment',''))[:4000]
    if not target: raise HTTPException(422,'target_stage is required')
    if target=='BLOCKED': raise HTTPException(409,'BLOCKED is controlled by the task blocked endpoint')
    with conn() as c:
        pid=task_project(c,tid)
        if not pid: raise HTTPException(404,'Task not found')
        cfg=project_workflow_config(c,pid)
        stage=next((x for x in cfg.get('stages',[]) if x.get('key')==target),None)
        if not stage: raise HTTPException(409,'Target workflow stage is not configured')
        if a.get('actor_type')=='AGENT' and (target=='DONE' or stage.get('approval_role','none') not in ('none',None,'')):
            raise HTTPException(403,'Agent cannot enter approval or completion stages; human review is required')
        current=c.execute('SELECT status FROM tasks WHERE id=?',(tid,)).fetchone()['status']
        if is_admin(a): pass
        elif current in ('REVIEW','DONE') or target in ('DONE',):
            require_project_access(c,pid,a,write=True)
        else:
            require_task_access(c,tid,a,assigned_only=True)
        scoped_key=f'workflow:{a["id"]}:{tid}:{idempotency_key}' if idempotency_key else None
        if scoped_key:
            prior=c.execute('SELECT id,payload FROM events WHERE idempotency_key=?',(scoped_key,)).fetchone()
            if prior:
                if prior['payload']!=json.dumps({'target_stage':target,'comment':comment}): raise HTTPException(409,'Idempotency-Key was already used with a different workflow transition')
                return {'task_id':tid,'target_stage':target,'event_id':prior['id'],'idempotent_replay':True}
        enforce_workflow_stage(c,pid,target,a['id'],tid)
        eid=transition_task_workflow(c,tid,target,a['id'],comment)
        if scoped_key:
            # The transition event itself is the idempotent record; attach a unique companion event only when needed.
            c.execute('UPDATE events SET idempotency_key=?,payload=? WHERE id=? AND idempotency_key IS NULL',(scoped_key,json.dumps({'target_stage':target,'comment':comment}),eid))
        return {'task_id':tid,'status':target,'event_id':eid}

@app.post('/api/v1/tasks/{tid}/artifacts')
def artifact(tid:str,b:ArtifactIn,authorization:str=Header(None)):
    a=actor(authorization); aid='art_'+uuid.uuid4().hex[:12]
    with conn() as c:
        require_task_access(c,tid,a,assigned_only=True)
        c.execute('INSERT INTO artifacts(id,task_id,artifact_type,uri,commit_sha,metadata,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',(aid,tid,b.artifact_type,b.uri,b.commit_sha,json.dumps(b.metadata),now(),c.execute('SELECT p.tenant_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE t.id=?',(tid,)).fetchone()['tenant_id'])); wp=c.execute('SELECT correlation_id,id FROM task_work_packages WHERE child_task_id=?',(tid,)).fetchone(); event(c,'artifact.submitted',a['id'],tid,{'artifact_id':aid,'uri':b.uri,'work_package_id':wp['id'] if wp else None,'correlation_id':wp['correlation_id'] if wp else None})
    return {'id':aid,'task_id':tid}
@app.post('/api/v1/tasks/{tid}/review')
def review_task(tid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization); decision=b.get('decision')
    if a.get('actor_type')=='AGENT': raise HTTPException(403,'Agent cannot review or approve tasks')
    if a.get('actor_type')=='AGENT': raise HTTPException(403,'Agent identities cannot review or approve work')
    if decision not in ('APPROVE','REJECT'): raise HTTPException(422,'decision must be APPROVE or REJECT')
    with conn() as c:
        begin_serialized_write(c)
        pid=task_project(c,tid)
        if not pid: raise HTTPException(404,'Task not found')
        if is_admin(a): pass
        else:
            row=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not row or row['role'] not in ('owner','manager','reviewer'): raise HTTPException(403,'Reviewer role required')
        task_sql='SELECT status FROM tasks WHERE id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): task_sql += ' FOR UPDATE'
        task=c.execute(task_sql,(tid,)).fetchone()
        if task['status']!='REVIEW': raise HTTPException(409,'Task is not awaiting review')
        if decision=='APPROVE':
            enforce_workflow_exit(c,pid,task['status'],a['id'])
            enforce_workflow_stage(c,pid,'DONE',a['id'],tid)
            packages=c.execute("SELECT w.child_task_id,t.status FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? AND w.status='ACTIVE'",(tid,)).fetchall()
            pending=[x['child_task_id'] for x in packages if x['status']!='DONE']
            missing=[x['child_task_id'] for x in packages if c.execute('SELECT 1 FROM artifacts WHERE task_id=? LIMIT 1',(x['child_task_id'],)).fetchone() is None]
            if pending or missing:
                raise HTTPException(409,detail={'message':'Parent task cannot be approved until every active work package is approved and has at least one artifact','pending_work_packages':pending,'missing_artifacts':missing})
        status='DONE' if decision=='APPROVE' else 'IN_PROGRESS'
        updated=c.execute('UPDATE tasks SET status=?,progress=?,updated_at=? WHERE id=? AND status=?',(status,100 if decision=='APPROVE' else 90,now(),tid,'REVIEW'))
        if updated.rowcount != 1: raise HTTPException(409,'Task is no longer awaiting review')
        if decision=='APPROVE':
            stamp=now()
            c.execute("UPDATE agent_task_assignments SET status='COMPLETED',updated_at=? WHERE task_id=? AND status='ACCEPTED'",(stamp,tid))
        eid=event(c,'task.reviewed',a['id'],tid,{'decision':decision,'comment':b.get('comment','')})
        return {'task_id':tid,'status':status,'event_id':eid}

@app.post('/api/v1/work-packages/{package_id}/review')
def review_work_package(package_id:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization)
    if a.get('actor_type')=='AGENT': raise HTTPException(403,'Agent cannot review or approve work packages')
    if a.get('actor_type')=='AGENT': raise HTTPException(403,'Agent identities cannot review or approve work packages')
    decision=str(b.get('decision','')).strip().upper()
    comment=str(b.get('comment',''))[:4000]
    if decision not in ('APPROVE','REJECT'): raise HTTPException(422,'decision must be APPROVE or REJECT')
    with conn() as c:
        begin_serialized_write(c)
        package_sql='SELECT w.*,t.status AS task_status,t.progress FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): package_sql += ' FOR UPDATE'
        package=c.execute(package_sql,(package_id,)).fetchone()
        if not package: raise HTTPException(404,'Work package not found')
        pid=package['project_id']
        if is_admin(a): pass
        else:
            row=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not row or row['role'] not in ('owner','manager','reviewer'): raise HTTPException(403,'Reviewer role required')
        if package['status']!='ACTIVE': raise HTTPException(409,'Work package is no longer active')
        if package['task_status']!='REVIEW': raise HTTPException(409,'Work package is not awaiting review')
        stamp=now()
        if decision=='APPROVE':
            enforce_workflow_exit(c,pid,package['task_status'],a['id'])
            enforce_workflow_stage(c,pid,'DONE',a['id'],package['child_task_id'])
            if c.execute('SELECT 1 FROM artifacts WHERE task_id=? LIMIT 1',(package['child_task_id'],)).fetchone() is None:
                raise HTTPException(409,'Work package must have at least one artifact before approval')
            status='DONE'; progress=100
        else:
            status='IN_PROGRESS'; progress=90
        updated=c.execute('UPDATE tasks SET status=?,progress=?,updated_at=? WHERE id=? AND status=?',(status,progress,stamp,package['child_task_id'],'REVIEW'))
        if updated.rowcount != 1: raise HTTPException(409,'Work package task is no longer awaiting review')
        if decision=='APPROVE':
            c.execute("UPDATE agent_task_assignments SET status='COMPLETED',updated_at=? WHERE task_id=? AND status='ACCEPTED'",(stamp,package['child_task_id']))
        eid=event(c,'task.work_package.reviewed',a['id'],package['child_task_id'],{'work_package_id':package_id,'parent_task_id':package['parent_task_id'],'decision':decision,'comment':comment})
        return {'work_package_id':package_id,'task_id':package['child_task_id'],'status':status,'progress':progress,'event_id':eid,'decision':decision}

@app.post('/api/v1/tasks/{parent_id}/work-packages')
def create_work_package(parent_id:str,b:WorkPackageIn,authorization:str=Header(None)):
    a=actor(authorization); child_id='tsk_'+uuid.uuid4().hex[:12]; package_id='wpk_'+uuid.uuid4().hex
    agent_name=b.agent_name.strip()
    if not agent_name: raise HTTPException(422,'agent_name must not be blank')
    with conn() as c:
        require_task_access(c,parent_id,a)
        project_id=task_project(c,parent_id)
        require_project_access(c,project_id,a,write=True)
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(project_id,)).fetchone()
        member=c.execute('SELECT tenant_id FROM members WHERE id=?',(b.assignee_member_id,)).fetchone()
        if not member or member['tenant_id']!=project['tenant_id']: raise HTTPException(404,'Assignee not found in this tenant')
        if not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(project_id,b.assignee_member_id)).fetchone(): raise HTTPException(400,'Assignee is not a project member')
        agent=c.execute('SELECT status,last_seen FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(project_id,b.assignee_member_id,agent_name)).fetchone()
        if not agent: raise HTTPException(404,'Assignee Agent is not registered in this project')
        if agent['status']=='OFFLINE' or agent['last_seen'] < datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat(): raise HTTPException(409,'Assignee Agent presence is offline or stale')
        for dep in b.dependencies:
            if dep==parent_id or not c.execute('SELECT 1 FROM tasks WHERE id=?',(dep,)).fetchone(): raise HTTPException(400,'Invalid dependency')
            require_task_access(c,dep,a)
            if task_project(c,dep)!=project_id: raise HTTPException(400,'Dependencies must belong to the same project')
        req=c.execute('SELECT r.id FROM tasks t JOIN requirements r ON r.id=t.requirement_id WHERE t.id=?',(parent_id,)).fetchone()
        if not req: raise HTTPException(409,'Create a requirement before adding work packages')
        stamp=now()
        c.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?)',(child_id,req['id'],b.title,b.description,'READY',0,stamp,stamp))
        c.execute('INSERT INTO assignments(task_id,member_id) VALUES(?,?)',(child_id,b.assignee_member_id))
        for dep in b.dependencies: c.execute('INSERT INTO dependencies(task_id,depends_on_task_id) VALUES(?,?)',(child_id,dep))
        correlation_id='corr_'+uuid.uuid4().hex
        sla_due_at=datetime.fromtimestamp(datetime.fromisoformat(stamp).timestamp()+b.sla_seconds,timezone.utc).isoformat() if b.sla_seconds else None
        c.execute('INSERT INTO task_work_packages(id,parent_task_id,child_task_id,project_id,tenant_id,assignee_member_id,agent_name,status,created_at,updated_at,correlation_id,sla_due_at,risk_state) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(package_id,parent_id,child_id,project_id,project['tenant_id'],b.assignee_member_id,agent_name,'ACTIVE',stamp,stamp,correlation_id,sla_due_at,'ON_TRACK'))
        mid='msg_'+uuid.uuid4().hex[:12]
        title='Work package assigned: '+b.title
        content=json.dumps({'work_package_id':package_id,'correlation_id':correlation_id,'parent_task_id':parent_id,'task_id':child_id,'agent_name':agent_name,'title':b.title,'sla_due_at':sla_due_at},ensure_ascii=False)
        c.execute('INSERT INTO messages(id,recipient_member_id,tenant_id,task_id,message_type,title,content,priority,status,created_at,acked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(mid,b.assignee_member_id,project['tenant_id'],child_id,'WORK_PACKAGE_ASSIGNED',title,content,'HIGH','PENDING',stamp,None))
        payload={'message_id':mid,'recipient_member_id':b.assignee_member_id,'project_id':project_id,'task_id':child_id,'message_type':'WORK_PACKAGE_ASSIGNED','title':title,'content':content,'priority':'HIGH'}
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',('obx_'+uuid.uuid4().hex,'message.created',json.dumps(payload),'PENDING',0,stamp,stamp,project['tenant_id']))
        event(c,'task.work_package.created',a['id'],parent_id,{'work_package_id':package_id,'correlation_id':correlation_id,'child_task_id':child_id,'assignee_member_id':b.assignee_member_id,'agent_name':agent_name,'sla_due_at':sla_due_at,'sla_seconds':b.sla_seconds})
    return {'id':package_id,'correlation_id':correlation_id,'parent_task_id':parent_id,'task_id':child_id,'assignee_member_id':b.assignee_member_id,'agent_name':agent_name,'status':'ACTIVE','sla_due_at':sla_due_at,'risk_state':'ON_TRACK','message_id':mid}

@app.get('/api/v1/tasks/{parent_id}/work-packages')
def list_work_packages(parent_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,parent_id,a)
        rows=c.execute('SELECT w.*,t.title,t.description,t.status AS task_status,t.progress,t.updated_at AS task_updated_at FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? ORDER BY w.created_at',(parent_id,)).fetchall()
        result=[]
        for raw in rows:
            row=dict(raw)
            row['artifacts']=[dict(x) for x in c.execute('SELECT id,artifact_type,uri,commit_sha,created_at FROM artifacts WHERE task_id=? ORDER BY created_at',(row['child_task_id'],))]
            result.append(row)
        return result

@app.get('/api/v1/tasks/{parent_id}/work-summary')
def work_package_summary(parent_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,parent_id,a)
        rows=c.execute("SELECT t.status,t.progress FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? AND w.status='ACTIVE'",(parent_id,)).fetchall()
        total=len(rows)
        counts={k:sum(1 for x in rows if x['status']==k) for k in ('READY','IN_PROGRESS','BLOCKED','REVIEW','DONE')}
        progress=round(sum(int(x['progress'] or 0) for x in rows)/total) if total else 0
        artifacts=c.execute('SELECT COUNT(*) AS n FROM artifacts a JOIN task_work_packages w ON w.child_task_id=a.task_id WHERE w.parent_task_id=? AND w.status=\'ACTIVE\'',(parent_id,)).fetchone()['n']
        blocked=c.execute("SELECT t.id,t.title,t.status FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? AND w.status='ACTIVE' AND t.status='BLOCKED'",(parent_id,)).fetchall()
        artifact_rows=c.execute('SELECT w.child_task_id,a.id,a.artifact_type,a.uri,a.commit_sha,a.created_at FROM task_work_packages w JOIN artifacts a ON a.task_id=w.child_task_id WHERE w.parent_task_id=? AND w.status=\'ACTIVE\' ORDER BY a.created_at',(parent_id,)).fetchall()
        return {'parent_task_id':parent_id,'work_package_count':total,'progress':progress,'status_counts':counts,'blocked_tasks':[dict(x) for x in blocked],'artifact_count':artifacts,'artifacts':[dict(x) for x in artifact_rows],'all_done':bool(total and counts['DONE']==total)}

@app.get('/api/v1/tasks/{parent_id}/work-timeline')
def work_package_timeline(parent_id:str,limit:int=200,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,500))
    with conn() as c:
        require_task_access(c,parent_id,a)
        packages=c.execute('SELECT w.*,t.title,t.status AS task_status,t.progress FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? ORDER BY w.created_at',(parent_id,)).fetchall()
        items=[]
        task_ids=[parent_id]+[w['child_task_id'] for w in packages]
        for e in c.execute("""SELECT e.*,m.name AS actor_name FROM events e
            LEFT JOIN members m ON m.id=e.actor_member_id WHERE e.task_id=? ORDER BY e.created_at""",(parent_id,)).fetchall():
            p=json.loads(e['payload'] or '{}')
            items.append({'occurred_at':e['created_at'],'kind':'event','event_type':e['event_type'],
                'task_id':parent_id,'event_id':e['id'],'actor_member_id':e['actor_member_id'],
                'actor_name':e['actor_name'],'payload':p})
        # Parent-level coordination messages and delivery bundles are part of
        # the same execution trace as child work-package activity.
        for msg in c.execute('SELECT id,message_type,title,status,created_at,acked_at,content FROM messages WHERE task_id=? ORDER BY created_at',(parent_id,)).fetchall():
            try: body=json.loads(msg['content'] or '{}')
            except Exception: body={'content':msg['content']}
            items.append({'occurred_at':msg['created_at'],'kind':'message','message_id':msg['id'],
                'message_type':msg['message_type'],'title':msg['title'],'status':msg['status'],
                'acked_at':msg['acked_at'],'task_id':parent_id,'correlation_id':body.get('correlation_id'),'payload':body})
        for art in c.execute('SELECT id,artifact_type,uri,commit_sha,created_at FROM artifacts WHERE task_id=? ORDER BY created_at',(parent_id,)).fetchall():
            items.append({'occurred_at':art['created_at'],'kind':'artifact','task_id':parent_id,'correlation_id':None,'artifact':dict(art)})
        for w in packages:
            cid=w['correlation_id'] or w['id']; child=w['child_task_id']
            for e in c.execute("""SELECT e.*,m.name AS actor_name FROM events e
                LEFT JOIN members m ON m.id=e.actor_member_id WHERE e.task_id=? ORDER BY e.created_at""",(child,)).fetchall():
                p=json.loads(e['payload'] or '{}')
                items.append({'occurred_at':e['created_at'],'kind':'event','event_type':e['event_type'],
                    'task_id':child,'event_id':e['id'],'actor_member_id':e['actor_member_id'],
                    'actor_name':e['actor_name'],'correlation_id':cid,'payload':p})
            for msg in c.execute('SELECT id,message_type,title,status,created_at,acked_at,content FROM messages WHERE task_id=? ORDER BY created_at',(child,)).fetchall():
                try: body=json.loads(msg['content'] or '{}')
                except Exception: body={'content':msg['content']}
                items.append({'occurred_at':msg['created_at'],'kind':'message','message_id':msg['id'],
                    'message_type':msg['message_type'],'title':msg['title'],'status':msg['status'],
                    'acked_at':msg['acked_at'],'task_id':child,'correlation_id':body.get('correlation_id',cid),'payload':body})
            for art in c.execute('SELECT id,artifact_type,uri,commit_sha,created_at FROM artifacts WHERE task_id=? ORDER BY created_at',(child,)).fetchall():
                items.append({'occurred_at':art['created_at'],'kind':'artifact','task_id':child,'correlation_id':cid,'artifact':dict(art)})
        marks=','.join('?' for _ in task_ids)
        delegations=c.execute(f"""SELECT d.*,rq.name AS requester_name,rc.name AS recipient_name
            FROM task_delegations d JOIN members rq ON rq.id=d.requester_member_id
            JOIN members rc ON rc.id=d.recipient_member_id
            WHERE d.task_id IN ({marks}) ORDER BY d.created_at""",tuple(task_ids)).fetchall()
        for d in delegations:
            row=dict(d)
            items.append({'occurred_at':row['created_at'],'kind':'delegation','stage':'OFFERED',
                'task_id':row['task_id'],'delegation_id':row['id'],'status':row['status'],
                'requester_member_id':row['requester_member_id'],'requester_name':row['requester_name'],
                'recipient_member_id':row['recipient_member_id'],'recipient_name':row['recipient_name'],
                'agent_name':row['agent_name'],'reason':row['reason'],'expires_at':row['expires_at']})
            if row['status']!='PENDING':
                decision_at=row['responded_at'] or row['updated_at']
                items.append({'occurred_at':decision_at,'kind':'delegation','stage':row['status'],
                    'task_id':row['task_id'],'delegation_id':row['id'],'status':row['status'],
                    'requester_member_id':row['requester_member_id'],'requester_name':row['requester_name'],
                    'recipient_member_id':row['recipient_member_id'],'recipient_name':row['recipient_name'],
                    'agent_name':row['agent_name'],'reason':row['reason'],'expires_at':row['expires_at']})
        dependency_edges=[]
        for tid in task_ids:
            task=c.execute('SELECT title FROM tasks WHERE id=?',(tid,)).fetchone()
            for dep in c.execute("""SELECT d.depends_on_task_id,t.title AS depends_on_title,t.status AS depends_on_status
                FROM dependencies d JOIN tasks t ON t.id=d.depends_on_task_id WHERE d.task_id=?""",(tid,)).fetchall():
                dependency_edges.append({'task_id':tid,'task_title':task['title'] if task else tid,
                    'depends_on_task_id':dep['depends_on_task_id'],'depends_on_title':dep['depends_on_title'],
                    'depends_on_status':dep['depends_on_status'],'blocked':dep['depends_on_status']!='DONE'})
        items.sort(key=lambda x:(x['occurred_at'],x.get('event_id') or x.get('message_id') or x.get('delegation_id') or x.get('artifact',{}).get('id','')))
        items=items[-limit:]
        return {'parent_task_id':parent_id,'count':len(items),'items':items,
            'dependency_edges':dependency_edges,
            'delegations':[{'id':d['id'],'task_id':d['task_id'],'requester_member_id':d['requester_member_id'],
                'requester_name':d['requester_name'],'recipient_member_id':d['recipient_member_id'],
                'recipient_name':d['recipient_name'],'agent_name':d['agent_name'],'reason':d['reason'],
                'status':d['status'],'created_at':d['created_at'],'responded_at':d['responded_at'],
                'expires_at':d['expires_at']} for d in delegations],
            'work_packages':[{'id':w['id'],'correlation_id':w['correlation_id'] or w['id'],
                'child_task_id':w['child_task_id'],'title':w['title'],'status':w['task_status'],
                'progress':w['progress'],'assignee_member_id':w['assignee_member_id'],'agent_name':w['agent_name'],
                'sla_due_at':w['sla_due_at'],'risk_state':w['risk_state'],'needs_attention':bool(w['needs_attention'])}
                for w in packages]}
@app.post('/api/v1/projects/{pid}/work-packages/scan-health')
def scan_project_work_health(pid:str,authorization:str=Header(None)):
    a=actor(authorization); stamp=now()
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        rows=c.execute("""SELECT w.id,w.parent_task_id,w.child_task_id,w.correlation_id,w.sla_due_at,w.risk_state,w.needs_attention,
        t.title,t.status AS task_status FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id
        WHERE w.project_id=? AND w.status='ACTIVE' ORDER BY w.created_at""",(pid,)).fetchall()
        changed=[]; counts={'ON_TRACK':0,'OVERDUE':0,'BLOCKED_DEPENDENCY':0,'STALLED':0,'IN_REVIEW':0,'COMPLETED':0}
        for row in rows:
            blockers=c.execute("""SELECT d.depends_on_task_id,t.title,t.status FROM dependencies d
                JOIN tasks t ON t.id=d.depends_on_task_id WHERE d.task_id=? AND t.status!='DONE'""",(row['child_task_id'],)).fetchall()
            if row['task_status']=='DONE': risk='COMPLETED'
            elif row['task_status']=='REVIEW': risk='IN_REVIEW'
            elif blockers: risk='BLOCKED_DEPENDENCY'
            elif row['needs_attention']: risk='STALLED'
            elif row['sla_due_at'] and row['sla_due_at']<=stamp: risk='OVERDUE'
            else: risk='ON_TRACK'
            if risk!=row['risk_state']:
                c.execute('UPDATE task_work_packages SET risk_state=?,updated_at=? WHERE id=?',(risk,stamp,row['id']))
                detail={'work_package_id':row['id'],'correlation_id':row['correlation_id'],'child_task_id':row['child_task_id'],'previous_risk_state':row['risk_state'],'risk_state':risk,'sla_due_at':row['sla_due_at'],'blocking_dependencies':[dict(x) for x in blockers]}
                event(c,'task.work_package.risk_changed',a['id'],row['parent_task_id'],detail)
                changed.append(detail)
            counts[risk]=counts.get(risk,0)+1
        return {'project_id':pid,'scanned_count':len(rows),'changed_count':len(changed),'risk_counts':counts,'changes':changed}

@app.get('/api/v1/projects/{pid}/work-health')
def project_work_health(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT w.id,w.parent_task_id,w.child_task_id,w.correlation_id,w.assignee_member_id,w.agent_name,
            w.sla_due_at,w.risk_state,w.needs_attention,t.title,t.status AS task_status,t.progress,t.updated_at
            FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id
            WHERE w.project_id=? AND w.status='ACTIVE' ORDER BY w.created_at""",(pid,)).fetchall()
        counts={}
        items=[]
        for row in rows:
            risk=row['risk_state']; counts[risk]=counts.get(risk,0)+1
            blockers=c.execute("""SELECT d.depends_on_task_id,t.title,t.status FROM dependencies d
                JOIN tasks t ON t.id=d.depends_on_task_id WHERE d.task_id=? AND t.status!='DONE'""",(row['child_task_id'],)).fetchall()
            items.append({'work_package_id':row['id'],'parent_task_id':row['parent_task_id'],'child_task_id':row['child_task_id'],
                'correlation_id':row['correlation_id'],'title':row['title'],'task_status':row['task_status'],'progress':row['progress'],
                'assignee_member_id':row['assignee_member_id'],'agent_name':row['agent_name'],'sla_due_at':row['sla_due_at'],
                'risk_state':risk,'needs_attention':bool(row['needs_attention']),'blocking_dependencies':[dict(x) for x in blockers],
                'last_activity_at':row['updated_at']})
        total=len(items); at_risk=sum(counts.get(k,0) for k in ('OVERDUE','BLOCKED_DEPENDENCY','STALLED'))
        return {'project_id':pid,'work_package_count':total,'at_risk_count':at_risk,
            'health_score':round(100*(total-at_risk)/total) if total else 100,
            'risk_counts':counts,'items':items}

@app.get('/api/v1/projects/{pid}/coordination')
def project_coordination_center(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        packages=c.execute("""SELECT w.id AS work_package_id,w.parent_task_id,w.child_task_id,w.assignee_member_id,w.agent_name,
            w.sla_due_at,w.risk_state,w.needs_attention,w.stall_reason,w.stalled_at,t.title,t.status AS task_status,
            t.progress,t.updated_at,m.name AS assignee_name
            FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id
            LEFT JOIN members m ON m.id=w.assignee_member_id
            WHERE w.project_id=? AND w.status='ACTIVE'
            AND (w.needs_attention=1 OR w.risk_state IN ('OVERDUE','BLOCKED_DEPENDENCY','STALLED','IN_REVIEW'))
            ORDER BY CASE w.risk_state WHEN 'OVERDUE' THEN 0 WHEN 'STALLED' THEN 1 WHEN 'BLOCKED_DEPENDENCY' THEN 2 WHEN 'IN_REVIEW' THEN 3 ELSE 4 END,w.updated_at""",(pid,)).fetchall()
        package_items=[]
        for row in packages:
            blockers=c.execute("""SELECT d.depends_on_task_id,t.title,t.status FROM dependencies d
                JOIN tasks t ON t.id=d.depends_on_task_id WHERE d.task_id=? AND t.status!='DONE'""",(row['child_task_id'],)).fetchall()
            agent=c.execute('SELECT status,last_seen FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(pid,row['assignee_member_id'],row['agent_name'])).fetchone()
            package_items.append({**dict(row),'blocking_dependencies':[dict(x) for x in blockers],
                'agent_status':agent['status'] if agent else 'NOT_REGISTERED','agent_last_seen':agent['last_seen'] if agent else None})
        unclaimed=c.execute("""SELECT t.id AS task_id,t.title,t.status,t.progress,t.updated_at
            FROM tasks t JOIN requirements r ON r.id=t.requirement_id
            LEFT JOIN assignments a ON a.task_id=t.id
            WHERE r.project_id=? AND t.status!='DONE' AND a.task_id IS NULL
            AND NOT EXISTS (SELECT 1 FROM task_work_packages w WHERE w.child_task_id=t.id AND w.status='ACTIVE')
            ORDER BY t.updated_at""",(pid,)).fetchall()
        reviews=c.execute("""SELECT t.id AS task_id,t.title,t.progress,t.updated_at,
            (SELECT COUNT(*) FROM artifacts ar WHERE ar.task_id=t.id) AS artifact_count
            FROM tasks t JOIN requirements r ON r.id=t.requirement_id
            WHERE r.project_id=? AND t.status='REVIEW' ORDER BY t.updated_at""",(pid,)).fetchall()
        delegations=c.execute("""SELECT d.id,d.task_id,d.status,d.requester_member_id,d.recipient_member_id,
            d.agent_name,d.reason,d.created_at,d.expires_at,t.title AS task_title,
            rq.name AS requester_name,rc.name AS recipient_name
            FROM task_delegations d JOIN tasks t ON t.id=d.task_id
            JOIN members rq ON rq.id=d.requester_member_id JOIN members rc ON rc.id=d.recipient_member_id
            WHERE d.project_id=? AND d.status='PENDING' ORDER BY d.created_at""",(pid,)).fetchall()
        return {'project_id':pid,'exception_work_packages':[dict(x) for x in package_items],
            'unclaimed_tasks':[dict(x) for x in unclaimed],'pending_reviews':[dict(x) for x in reviews],
            'pending_delegations':[dict(x) for x in delegations],
            'counts':{'exception_work_packages':len(package_items),'unclaimed_tasks':len(unclaimed),
                'pending_reviews':len(reviews),'pending_delegations':len(delegations)}}

@app.post('/api/v1/projects/{pid}/work-packages/scan-stalled')
def scan_stalled_work_packages(pid:str,b:WorkPackageScanIn,authorization:str=Header(None)):
    a=actor(authorization)
    cutoff=datetime.fromtimestamp(time.time()-b.stale_after_seconds,timezone.utc).isoformat()
    stamp=now()
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        rows=c.execute("""SELECT w.id,w.parent_task_id,w.child_task_id,w.assignee_member_id,t.status,t.updated_at,t.title
        FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id
        WHERE w.project_id=? AND w.status='ACTIVE' AND w.needs_attention=0
        AND t.status IN ('READY','IN_PROGRESS','BLOCKED') AND t.updated_at<=?""",(pid,cutoff)).fetchall()
        marked=[]
        for row in rows:
            reason=f"No task activity for at least {b.stale_after_seconds} seconds"
            changed=c.execute('UPDATE task_work_packages SET needs_attention=1,stalled_at=?,stall_reason=?,updated_at=? WHERE id=? AND needs_attention=0',(stamp,reason,stamp,row['id']))
            if changed.rowcount:
                event(c,'task.work_package.stalled',a['id'],row['parent_task_id'],{'work_package_id':row['id'],'correlation_id':c.execute('SELECT correlation_id FROM task_work_packages WHERE id=?',(row['id'],)).fetchone()['correlation_id'],'child_task_id':row['child_task_id'],'assignee_member_id':row['assignee_member_id'],'stalled_at':stamp,'reason':reason})
                marked.append({'work_package_id':row['id'],'child_task_id':row['child_task_id'],'title':row['title'],'task_status':row['status'],'assignee_member_id':row['assignee_member_id'],'stalled_at':stamp,'reason':reason})
    return {'project_id':pid,'stale_after_seconds':b.stale_after_seconds,'marked_count':len(marked),'items':marked}

@app.post('/api/v1/work-packages/{package_id}/reassign')
def reassign_work_package(package_id:str,b:WorkPackageReassignIn,authorization:str=Header(None)):
    a=actor(authorization); agent_name=b.agent_name.strip()
    if not agent_name: raise HTTPException(422,'agent_name must not be blank')
    with conn() as c:
        begin_serialized_write(c)
        package_sql='SELECT * FROM task_work_packages WHERE id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): package_sql += ' FOR UPDATE'
        package=c.execute(package_sql,(package_id,)).fetchone()
        if not package: raise HTTPException(404,'Work package not found')
        require_project_access(c,package['project_id'],a,write=True)
        if package['status']!='ACTIVE': raise HTTPException(409,'Only active work packages can be reassigned')
        if not package['needs_attention']: raise HTTPException(409,'Work package must be marked stalled before reassignment')
        if package['assignee_member_id']==b.assignee_member_id and package['agent_name']==agent_name:
            raise HTTPException(400,'Choose a different assignee or Agent')
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(package['project_id'],)).fetchone()
        member=c.execute('SELECT tenant_id FROM members WHERE id=?',(b.assignee_member_id,)).fetchone()
        if not member or member['tenant_id']!=project['tenant_id']: raise HTTPException(404,'New assignee not found in this tenant')
        if not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(package['project_id'],b.assignee_member_id)).fetchone():
            raise HTTPException(400,'New assignee is not a project member')
        agent=c.execute('SELECT status,last_seen FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(package['project_id'],b.assignee_member_id,agent_name)).fetchone()
        cutoff=datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat()
        if not agent: raise HTTPException(404,'New assignee Agent is not registered in this project')
        if agent['status']=='OFFLINE' or agent['last_seen']<cutoff: raise HTTPException(409,'New assignee Agent presence is offline or stale')
        stamp=now()
        c.execute('DELETE FROM assignments WHERE task_id=? AND member_id=?',(package['child_task_id'],package['assignee_member_id']))
        c.execute('INSERT OR IGNORE INTO assignments(task_id,member_id) VALUES(?,?)',(package['child_task_id'],b.assignee_member_id))
        c.execute('UPDATE task_work_packages SET assignee_member_id=?,agent_name=?,needs_attention=0,stalled_at=NULL,stall_reason=NULL,updated_at=? WHERE id=?',(b.assignee_member_id,agent_name,stamp,package_id))
        c.execute('UPDATE tasks SET updated_at=? WHERE id=?',(stamp,package['child_task_id']))
        mid='msg_'+uuid.uuid4().hex[:12]
        title='Work package reassigned: '+package['child_task_id']
        content=json.dumps({'work_package_id':package_id,'correlation_id':package['correlation_id'],'parent_task_id':package['parent_task_id'],'task_id':package['child_task_id'],'previous_assignee_member_id':package['assignee_member_id'],'assignee_member_id':b.assignee_member_id,'agent_name':agent_name,'reason':b.reason},ensure_ascii=False)
        c.execute('INSERT INTO messages(id,recipient_member_id,tenant_id,task_id,message_type,title,content,priority,status,created_at,acked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(mid,b.assignee_member_id,project['tenant_id'],package['child_task_id'],'WORK_PACKAGE_REASSIGNED',title,content,'HIGH','PENDING',stamp,None))
        payload={'message_id':mid,'recipient_member_id':b.assignee_member_id,'project_id':package['project_id'],'task_id':package['child_task_id'],'message_type':'WORK_PACKAGE_REASSIGNED','title':title,'content':content,'priority':'HIGH'}
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',('obx_'+uuid.uuid4().hex,'message.created',json.dumps(payload),'PENDING',0,stamp,stamp,project['tenant_id']))
        eid=event(c,'task.work_package.reassigned',a['id'],package['parent_task_id'],{'work_package_id':package_id,'correlation_id':package['correlation_id'],'child_task_id':package['child_task_id'],'previous_assignee_member_id':package['assignee_member_id'],'assignee_member_id':b.assignee_member_id,'previous_agent_name':package['agent_name'],'agent_name':agent_name,'reason':b.reason})
    return {'work_package_id':package_id,'task_id':package['child_task_id'],'assignee_member_id':b.assignee_member_id,'agent_name':agent_name,'needs_attention':False,'message_id':mid,'event_id':eid}

@app.post('/api/v1/projects/{pid}/agents/register')
def register_project_agent(pid:str,b:AgentPresenceIn,authorization:str=Header(None)):
    a=actor(authorization)
    agent_name=b.agent_name.strip()
    if not agent_name: raise HTTPException(422,'agent_name must not be blank')
    clean_caps=sorted({str(x).strip().lower() for x in b.capabilities if str(x).strip()})
    clean_protocols=sorted({str(x).strip().lower() for x in b.protocols if str(x).strip()})
    if any(len(x)>80 for x in clean_caps) or any(len(x)>40 for x in clean_protocols):
        raise HTTPException(422,'Capability or protocol identifier is too long')
    if not clean_protocols: raise HTTPException(422,'At least one protocol is required')
    if len(json.dumps(b.metadata))>4000: raise HTTPException(422,'Agent metadata exceeds 4000 bytes')
    with conn() as c:
        require_project_access(c,pid,a)
        tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id']
        existing=c.execute('SELECT id,created_at FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(pid,a['id'],agent_name)).fetchone()
        aid=existing['id'] if existing else 'agt_'+uuid.uuid4().hex
        created=existing['created_at'] if existing else now()
        stamp=now()
        c.execute("""INSERT INTO project_agents(id,project_id,member_id,tenant_id,agent_name,capabilities,protocols,status,metadata,last_seen,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(project_id,member_id,agent_name) DO UPDATE SET capabilities=excluded.capabilities,protocols=excluded.protocols,status=excluded.status,metadata=excluded.metadata,last_seen=excluded.last_seen,updated_at=excluded.updated_at""",
        (aid,pid,a['id'],tenant,agent_name,json.dumps(clean_caps),json.dumps(clean_protocols),b.status,json.dumps(b.metadata),stamp,created,stamp))
        event(c,'agent.presence.updated',a['id'],None,{'project_id':pid,'agent_id':aid,'agent_name':agent_name,'status':b.status},tenant_override=tenant)
    return {'id':aid,'project_id':pid,'member_id':a['id'],'agent_name':b.agent_name.strip(),'status':b.status,'capabilities':clean_caps,'protocols':clean_protocols,'last_seen':stamp}

@app.post('/api/v1/projects/{pid}/agents/heartbeat')
def heartbeat_project_agent(pid:str,body:dict,authorization:str=Header(None)):
    a=actor(authorization); name=str(body.get('agent_name','')).strip()
    if not name or len(name)>120: raise HTTPException(422,'agent_name is required (max 120)')
    status=str(body.get('status','AVAILABLE')).upper()
    if status not in ('AVAILABLE','BUSY','OFFLINE'): raise HTTPException(422,'Invalid agent status')
    with conn() as c:
        require_project_access(c,pid,a)
        previous=c.execute('SELECT id,status FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(pid,a['id'],name)).fetchone()
        if not previous: raise HTTPException(404,'Agent registration not found; register the agent first')
        stamp=now()
        c.execute('UPDATE project_agents SET status=?,last_seen=?,updated_at=? WHERE id=?',(status,stamp,stamp,previous['id']))
        if previous['status'] != status:
            event(c,'agent.presence.changed',a['id'],None,{'project_id':pid,'agent_id':previous['id'],'status':status})
    return {'id':previous['id'],'status':status,'last_seen':stamp}

@app.get('/api/v1/projects/{pid}/agents')
def discover_project_agents(pid:str,authorization:str=Header(None),capability:str='',protocol:str=''):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("SELECT pa.*,m.name AS member_name FROM project_agents pa JOIN members m ON m.id=pa.member_id WHERE pa.project_id=? ORDER BY pa.agent_name,pa.member_id",(pid,)).fetchall()
        cutoff=datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat()
        items=[]
        for raw in rows:
            row=dict(raw)
            caps=json.loads(row['capabilities'] or '[]'); protocols=json.loads(row['protocols'] or '[]')
            live=row['status']!='OFFLINE' and row['last_seen']>=cutoff
            if capability and capability.lower() not in caps: continue
            if protocol and protocol.lower() not in protocols: continue
            items.append({'id':row['id'],'member_id':row['member_id'],'member_name':row['member_name'],'agent_name':row['agent_name'],'capabilities':caps,'protocols':protocols,'status':row['status'] if live else 'OFFLINE','last_seen':row['last_seen'],'metadata':json.loads(row['metadata'] or '{}')})
        return {'items':items,'count':len(items),'presence_ttl_seconds':120}

@app.get('/api/v1/projects/{pid}/agent-matches')
def recommend_project_agents(pid:str,required_capabilities:str='',protocol:str='mcp',authorization:str=Header(None)):
    """Rank project-local Agent registrations without assigning work or invoking a Runtime."""
    a=actor(authorization)
    requested=[x.strip().casefold() for x in required_capabilities.split(',') if x.strip()]
    if len(requested)>50 or any(len(x)>120 for x in requested):
        raise HTTPException(422,'At most 50 required capabilities are allowed; each must be at most 120 characters')
    requested=list(dict.fromkeys(requested))
    requested_protocol=protocol.strip().casefold()
    if not requested_protocol or len(requested_protocol)>40:
        raise HTTPException(422,'protocol must contain 1 to 40 characters')
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT pa.*,m.name AS member_name FROM project_agents pa
            JOIN members m ON m.id=pa.member_id WHERE pa.project_id=?""",(pid,)).fetchall()
        cutoff=datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat()
        items=[]
        for raw in rows:
            row=dict(raw)
            caps=sorted({str(x).strip().casefold() for x in json.loads(row['capabilities'] or '[]') if str(x).strip()})
            protocols=sorted({str(x).strip().casefold() for x in json.loads(row['protocols'] or '[]') if str(x).strip()})
            matched=[x for x in requested if x in caps]
            missing=[x for x in requested if x not in caps]
            live=row['status']!='OFFLINE' and row['last_seen']>=cutoff
            protocol_match=requested_protocol in protocols
            available=live and row['status']=='AVAILABLE'
            items.append({'id':row['id'],'member_id':row['member_id'],'member_name':row['member_name'],
                'agent_name':row['agent_name'],'capabilities':caps,'protocols':protocols,
                'presence_status':row['status'] if live else 'OFFLINE','last_seen':row['last_seen'],
                'matched_capabilities':matched,'missing_capabilities':missing,
                'match_count':len(matched),'required_count':len(requested),
                'protocol_match':protocol_match,'eligible':not missing and protocol_match and available,
                'availability_reason':('AVAILABLE' if available else ('BUSY' if live and row['status']=='BUSY' else 'OFFLINE_OR_STALE')),
                'match_score':round(100*len(matched)/len(requested)) if requested else (100 if protocol_match else 0)})
        items.sort(key=lambda x:(not x['eligible'],bool(x['missing_capabilities']),not x['protocol_match'],
            -x['match_count'],x['availability_reason']!='AVAILABLE',x['member_name'].casefold(),x['agent_name'].casefold()))
        return {'project_id':pid,'required_capabilities':requested,'protocol':requested_protocol,
            'items':items,'count':len(items),'eligible_count':sum(1 for x in items if x['eligible']),
            'recommendation_only':True,'runtime_controlled':False}

@app.post('/api/v1/tasks/{tid}/delegations')
def create_task_delegation(tid:str,b:DelegationIn,authorization:str=Header(None)):
    a=actor(authorization)
    if b.recipient_member_id == a['id']: raise HTTPException(400,'A task cannot be delegated to yourself')
    agent_name=b.agent_name.strip()
    if not agent_name: raise HTTPException(422,'agent_name must not be blank')
    did='dlg_'+uuid.uuid4().hex
    with conn() as c:
        require_task_access(c,tid,a,assigned_only=True)
        pid=task_project(c,tid)
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        recipient=c.execute('SELECT tenant_id FROM members WHERE id=?',(b.recipient_member_id,)).fetchone()
        if not recipient or recipient['tenant_id'] != project['tenant_id']: raise HTTPException(404,'Recipient not found in this tenant')
        if not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(pid,b.recipient_member_id)).fetchone(): raise HTTPException(400,'Recipient is not a project member')
        agent=c.execute("SELECT id,status,last_seen FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?",(pid,b.recipient_member_id,agent_name)).fetchone()
        if not agent: raise HTTPException(404,'Recipient Agent is not registered in this project')
        if agent['status']=='OFFLINE' or agent['last_seen'] < datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat():
            raise HTTPException(409,'Recipient Agent presence is offline or stale')
        stamp=now(); expiry=datetime.fromtimestamp(time.time()+b.expires_in_seconds,timezone.utc).isoformat()
        mid='msg_'+uuid.uuid4().hex[:12]
        title='Task delegation offer: '+tid
        content=json.dumps({'delegation_id':did,'task_id':tid,'agent_name':agent_name,'reason':b.reason,'expires_at':expiry},ensure_ascii=False)
        c.execute("INSERT INTO task_delegations(id,task_id,project_id,tenant_id,requester_member_id,recipient_member_id,agent_name,reason,status,message_id,expires_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(did,tid,pid,project['tenant_id'],a['id'],b.recipient_member_id,agent_name,b.reason,'PENDING',mid,expiry,stamp,stamp))
        c.execute("INSERT INTO messages(id,recipient_member_id,tenant_id,task_id,message_type,title,content,priority,status,created_at,acked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(mid,b.recipient_member_id,project['tenant_id'],tid,'TASK_DELEGATION',title,content,'HIGH','PENDING',stamp,None))
        payload={'message_id':mid,'recipient_member_id':b.recipient_member_id,'project_id':pid,'task_id':tid,'message_type':'TASK_DELEGATION','title':title,'content':content,'priority':'HIGH'}
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',('obx_'+uuid.uuid4().hex,'message.created',json.dumps(payload), 'PENDING',0,stamp,stamp,project['tenant_id']))
        event(c,'task.delegation.offered',a['id'],tid,{'delegation_id':did,'recipient_member_id':b.recipient_member_id,'agent_name':agent_name})
    return {'id':did,'task_id':tid,'recipient_member_id':b.recipient_member_id,'agent_name':agent_name,'status':'PENDING','expires_at':expiry,'message_id':mid}

@app.post('/api/v1/delegations/{did}/respond')
def respond_task_delegation(did:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization); decision=b.get('decision')
    if decision not in ('ACCEPT','REJECT'): raise HTTPException(422,'decision must be ACCEPT or REJECT')
    with conn() as c:
        begin_serialized_write(c)
        if DATABASE_URL.startswith(('postgresql://','postgres://')):
            row=c.execute('SELECT * FROM task_delegations WHERE id=? FOR UPDATE',(did,)).fetchone()
        else:
            row=c.execute('SELECT * FROM task_delegations WHERE id=?',(did,)).fetchone()
        if not row or row['recipient_member_id'] != a['id']: raise HTTPException(404,'Delegation not found')
        # Re-check the live project membership/tenant scope at response time so a
        # stale or legacy delegation cannot grant a cross-project assignment.
        require_project_access(c,row['project_id'],a)
        task_pid=task_project(c,row['task_id'])
        if task_pid != row['project_id']: raise HTTPException(409,'Delegation project scope is invalid')
        if row['status'] != 'PENDING': raise HTTPException(409,'Delegation is no longer pending')
        if row['expires_at'] <= now():
            stamp=now()
            cur=c.execute("UPDATE task_delegations SET status='EXPIRED',updated_at=? WHERE id=? AND status='PENDING'",(stamp,did))
            if cur.rowcount:
                event(c,'task.delegation.expired',a['id'],row['task_id'],{'delegation_id':did})
            return JSONResponse(status_code=410,content={'detail':'Delegation offer has expired','status':'EXPIRED'})
        if decision=='ACCEPT':
            c.execute('INSERT OR IGNORE INTO assignments(task_id,member_id) VALUES(?,?)',(row['task_id'],a['id']))
            c.execute('INSERT OR IGNORE INTO project_members(project_id,member_id,role,joined_at) VALUES(?,?,?,?)',(row['project_id'],a['id'],'member',now()))
            status='ACCEPTED'
        else: status='REJECTED'
        stamp=now()
        cur=c.execute('UPDATE task_delegations SET status=?,responded_at=?,updated_at=? WHERE id=? AND status=\'PENDING\'',(status,stamp,stamp,did))
        if cur.rowcount != 1:
            raise HTTPException(409,'Delegation response raced with another decision')
        event(c,'task.delegation.'+status.lower(),a['id'],row['task_id'],{'delegation_id':did,'agent_name':row['agent_name']})
        return {'id':did,'task_id':row['task_id'],'status':status,'responded_at':stamp}

@app.get('/api/v1/tasks/{tid}/delegations')
def list_task_delegations(tid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a)
        rows=c.execute('SELECT * FROM task_delegations WHERE task_id=? ORDER BY created_at DESC',(tid,)).fetchall()
        result=[]
        for raw in rows:
            row=dict(raw)
            if row['status']=='PENDING' and row['expires_at'] <= now():
                stamp=now()
                cur=c.execute("UPDATE task_delegations SET status='EXPIRED',updated_at=? WHERE id=? AND status='PENDING'",(stamp,row['id']))
                if cur.rowcount:
                    event(c,'task.delegation.expired',a['id'],tid,{'delegation_id':row['id']})
                row['status']='EXPIRED'
            result.append(row)
        return result

@app.get('/api/v1/projects/{pid}/delegations')
def project_delegations(pid:str,limit:int=100,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,500))
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT d.*,rq.name AS requester_name,rc.name AS recipient_name,t.title AS task_title
            FROM task_delegations d
            JOIN members rq ON rq.id=d.requester_member_id
            JOIN members rc ON rc.id=d.recipient_member_id
            JOIN tasks t ON t.id=d.task_id
            WHERE d.project_id=? ORDER BY d.created_at DESC LIMIT ?""",(pid,limit)).fetchall()
        items=[]
        for raw in rows:
            row=dict(raw)
            if row['status']=='PENDING' and row['expires_at'] <= now():
                stamp=now()
                cur=c.execute("UPDATE task_delegations SET status='EXPIRED',updated_at=? WHERE id=? AND status='PENDING'",(stamp,row['id']))
                if cur.rowcount:
                    event(c,'task.delegation.expired',a['id'],row['task_id'],{'delegation_id':row['id']})
                row['status']='EXPIRED'
            items.append(row)
        return {'project_id':pid,'count':len(items),'items':items}

@app.post('/api/v1/messages')
def send_message(b:MessageIn,authorization:str=Header(None)):
    a=actor(authorization); mid='msg_'+uuid.uuid4().hex[:12]
    with conn() as c:
        if not c.execute('SELECT 1 FROM members WHERE id=?',(b.recipient_member_id,)).fetchone(): raise HTTPException(404,'Recipient not found')
        if b.task_id:
            require_task_access(c,b.task_id,a)
            pid=task_project(c,b.task_id)
            if b.project_id and b.project_id != pid: raise HTTPException(400,'project_id does not match task')
        else: pid=b.project_id
        if not pid and not is_admin(a): raise HTTPException(400,'project_id is required for project-scoped messages')
        if pid:
            require_project_access(c,pid,a)
            recipient=c.execute('SELECT tenant_id FROM members WHERE id=?',(b.recipient_member_id,)).fetchone()
            project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
            if recipient and recipient['tenant_id'] != project['tenant_id']: raise HTTPException(400,'Recipient belongs to a different tenant')
            if not is_admin(a) and not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(pid,b.recipient_member_id)).fetchone(): raise HTTPException(400,'Recipient is not a project member')
        created=now()
        message_tenant=(c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id'] if pid else c.execute('SELECT tenant_id FROM members WHERE id=?',(b.recipient_member_id,)).fetchone()['tenant_id'])
        c.execute('INSERT INTO messages(id,recipient_member_id,tenant_id,task_id,message_type,title,content,priority,status,created_at,acked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(mid,b.recipient_member_id,message_tenant,b.task_id,b.message_type,b.title,b.content,b.priority,'PENDING',created,None))
        payload={'message_id':mid,'recipient_member_id':b.recipient_member_id,'project_id':pid,'task_id':b.task_id,'message_type':b.message_type,'title':b.title,'content':b.content,'priority':b.priority}
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',('obx_'+uuid.uuid4().hex,'message.created',json.dumps(payload),'PENDING',0,created,created,message_tenant))
        event(c,'message.created',a['id'],b.task_id,{'message_id':mid,'recipient':b.recipient_member_id},tenant_override=message_tenant)
    return {'id':mid,'status':'PENDING'}
@app.get('/api/v1/me/notifications')
def notifications(authorization:str=Header(None),after:int=0,limit:int=50):
    a=actor(authorization); limit=max(1,min(limit,100))
    with conn() as c:
        rows=[dict(x) for x in c.execute("SELECT * FROM messages WHERE recipient_member_id=? AND status='PENDING' AND seq>? ORDER BY seq LIMIT ?",(a['id'],after,limit))]
        for row in rows: c.execute('UPDATE messages SET attempts=attempts+1,last_attempt_at=? WHERE id=?',(now(),row['id']))
        return {'items':rows,'next_cursor':rows[-1]['seq'] if rows else after,'has_more':len(rows)==limit}
@app.post('/api/v1/messages/{mid}/ack')
def ack(mid:str,b:AckIn,authorization: str=Header(None)):
    a=actor(authorization)
    if b.status not in ('ACKNOWLEDGED','REJECTED'): raise HTTPException(422,'Invalid acknowledgement status')
    with conn() as c:
        existing=c.execute('SELECT status,task_id,tenant_id FROM messages WHERE id=? AND recipient_member_id=?',(mid,a['id'])).fetchone()
        if not existing: raise HTTPException(404,'Message not found for current member')
        if existing['status'] in ('ACKNOWLEDGED','REJECTED'):
            if existing['status'] != b.status: raise HTTPException(409,'Message has already reached a different terminal status')
            return {'id':mid,'status':existing['status'],'idempotent':True}
        stamp=now()
        cur=c.execute("UPDATE messages SET status=?,acked_at=? WHERE id=? AND recipient_member_id=? AND status='PENDING'",(b.status,stamp,mid,a['id']))
        if cur.rowcount==0: raise HTTPException(409,'Message status changed; retry the request')
        event(c,'message.acknowledged',a['id'],existing['task_id'],{'message_id':mid,'status':b.status},tenant_override=existing['tenant_id'])
    return {'id':mid,'status':b.status,'idempotent':False}
@app.get('/api/v1/tasks/{tid}/events')
def task_events(tid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a)
        return [dict(x) for x in c.execute('SELECT * FROM events WHERE task_id=? ORDER BY created_at',(tid,))]
@app.get('/api/v1/tasks/{tid}/artifacts')
def task_artifacts(tid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a)
        return [dict(x) for x in c.execute('SELECT * FROM artifacts WHERE task_id=? ORDER BY created_at',(tid,))]
@app.post('/internal/v1/outbox/claim')
def claim_outbox(body:dict,authorization:str=Header(None)):
    require_worker(authorization)
    worker=str(body.get('worker_id','')).strip()
    if not worker or len(worker)>120: raise HTTPException(422,'worker_id is required (max 120 chars)')
    limit=max(1,min(int(body.get('limit',20)),100)); lease_seconds=max(10,min(int(body.get('lease_seconds',60)),900))
    claimed=[]; timestamp=datetime.now(timezone.utc); stamp=timestamp.isoformat()
    with conn() as c:
        is_pg=DATABASE_URL.startswith(('postgresql://','postgres://'))
        if not is_pg: c.execute('BEGIN IMMEDIATE')
        query="SELECT * FROM outbox WHERE (status='PENDING' AND available_at<=?) OR (status='IN_FLIGHT' AND lease_until<=?) ORDER BY created_at LIMIT ?"
        if is_pg: query += " FOR UPDATE SKIP LOCKED"
        rows=c.execute(query,(stamp,stamp,limit)).fetchall()
        for row in rows:
            lease_until=datetime.fromtimestamp(timestamp.timestamp()+lease_seconds,timezone.utc).isoformat()
            lease_token=secrets.token_urlsafe(32)
            cur=c.execute("UPDATE outbox SET status='IN_FLIGHT',attempts=attempts+1,lease_until=?,lease_owner=?,lease_token=? WHERE id=? AND ((status='PENDING' AND available_at<=?) OR (status='IN_FLIGHT' AND lease_until<=?))",(lease_until,worker,lease_token,row['id'],stamp,stamp))
            if cur.rowcount:
                item=dict(row); item.update(status='IN_FLIGHT',attempts=row['attempts']+1,lease_until=lease_until,lease_owner=worker,lease_token=lease_token,payload=json.loads(row['payload']))
                claimed.append(item)
    return {'items':claimed,'count':len(claimed)}

@app.post('/internal/v1/outbox/{outbox_id}/complete')
def complete_outbox(outbox_id:str,body:dict,authorization:str=Header(None)):
    require_worker(authorization)
    worker=str(body.get('worker_id','')).strip(); lease_token=str(body.get('lease_token',''))
    if not worker or len(worker)>120 or len(lease_token)<32: raise HTTPException(422,'worker_id and lease_token are required')
    with conn() as c:
        stamp=now()
        cur=c.execute("UPDATE outbox SET status='SENT',sent_at=?,lease_until=NULL,lease_owner=NULL,lease_token=NULL,last_error=NULL WHERE id=? AND status='IN_FLIGHT' AND lease_owner=? AND lease_token=? AND lease_until>?",(stamp,outbox_id,worker,lease_token,stamp))
        if not cur.rowcount: raise HTTPException(409,'Outbox lease not owned by worker or item is not in flight')
    return {'id':outbox_id,'status':'SENT'}

@app.post('/internal/v1/outbox/{outbox_id}/fail')
def fail_outbox(outbox_id:str,body:dict,authorization:str=Header(None)):
    require_worker(authorization)
    worker=str(body.get('worker_id','')).strip(); lease_token=str(body.get('lease_token','')); error=str(body.get('error','Delivery failed'))[:2000]
    if not worker or len(worker)>120 or len(lease_token)<32: raise HTTPException(422,'worker_id and lease_token are required')
    with conn() as c:
        stamp=now()
        row=c.execute("SELECT attempts FROM outbox WHERE id=? AND status='IN_FLIGHT' AND lease_owner=? AND lease_token=? AND lease_until>?",(outbox_id,worker,lease_token,stamp)).fetchone()
        if not row: raise HTTPException(409,'Outbox lease not owned, expired, or item is not in flight')
        attempts=row['attempts']; terminal=attempts>=8
        delay=min(3600,5*(2**min(attempts-1,10)))
        available=datetime.fromtimestamp(datetime.now(timezone.utc).timestamp()+delay,timezone.utc).isoformat()
        cur=c.execute("UPDATE outbox SET status=?,available_at=?,lease_until=NULL,lease_owner=NULL,lease_token=NULL,last_error=? WHERE id=? AND status='IN_FLIGHT' AND lease_owner=? AND lease_token=? AND lease_until>?",('DEAD' if terminal else 'PENDING',available,error,outbox_id,worker,lease_token,stamp))
        if not cur.rowcount: raise HTTPException(409,'Outbox lease changed or expired during failure acknowledgement')
    return {'id':outbox_id,'status':'DEAD' if terminal else 'PENDING','retry_after_seconds':None if terminal else delay}

@app.get('/api/v1/admin/outbox/dead')
def list_dead_outbox(limit:int=50,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    limit=max(1,min(limit,200))
    with conn() as c:
        rows=c.execute("SELECT id,event_type,status,attempts,available_at,last_error,created_at,tenant_id FROM outbox WHERE status='DEAD' ORDER BY created_at LIMIT ?",(limit,)).fetchall()
        return {'items':[dict(x) for x in rows],'count':len(rows)}

@app.post('/api/v1/admin/messages/{message_id}/restore-outbox')
def restore_missing_message_outbox(message_id:str,body:dict,authorization:str=Header(None)):
    """Explicitly restore one missing message dispatch record; never duplicates an existing dispatch."""
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    reason=str(body.get('reason','')).strip()
    if not reason or len(reason)>1000: raise HTTPException(422,'A recovery reason (1-1000 characters) is required')
    with conn() as c:
        begin_serialized_write(c)
        query='SELECT * FROM messages WHERE id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): query += ' FOR UPDATE'
        message=c.execute(query,(message_id,)).fetchone()
        if not message: raise HTTPException(404,'Message not found')
        existing_rows=c.execute("SELECT id,payload FROM outbox WHERE event_type='message.created'").fetchall()
        matching=[]
        for item in existing_rows:
            try:
                if json.loads(item['payload']).get('message_id')==message_id: matching.append(item['id'])
            except (TypeError,ValueError):
                continue
        if matching:
            raise HTTPException(409,'A message.created outbox record already exists; refusing duplicate recovery')
        project_id=None
        if message['task_id']:
            project=c.execute('SELECT r.project_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id WHERE t.id=?',(message['task_id'],)).fetchone()
            if project: project_id=project['project_id']
        payload={'message_id':message_id,'recipient_member_id':message['recipient_member_id'],
                 'project_id':project_id,'task_id':message['task_id'],'message_type':message['message_type'],
                 'title':message['title'],'content':message['content'],'priority':message['priority']}
        stamp=now(); outbox_id='obx_'+uuid.uuid4().hex
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',
                  (outbox_id,'message.created',json.dumps(payload),'PENDING',0,stamp,stamp,message['tenant_id']))
        event(c,'message.outbox.restored',a['id'],message['task_id'],
              {'message_id':message_id,'outbox_id':outbox_id,'reason':reason},tenant_override=message['tenant_id'])
    return {'message_id':message_id,'outbox_id':outbox_id,'status':'PENDING','restored':True}

@app.get('/api/v1/projects/{project_id}/message-delivery-health')
def project_message_delivery_health(project_id:str,authorization:str=Header(None),
                                    dispatch_sla_seconds:int=120,ack_sla_seconds:int=300,
                                    limit:int=100):
    """Project-scoped delivery SLA health; broker dispatch and recipient ACK clocks are separate."""
    a=actor(authorization)
    dispatch_sla_seconds=max(10,min(dispatch_sla_seconds,86400))
    ack_sla_seconds=max(10,min(ack_sla_seconds,604800))
    limit=max(1,min(limit,500))
    stamp=datetime.now(timezone.utc)
    incidents=[]
    with conn() as c:
        require_project_access(c,project_id,a)
        messages=c.execute("""SELECT m.id,m.recipient_member_id,m.tenant_id,m.task_id,m.status,m.created_at,m.acked_at
            FROM messages m JOIN tasks t ON t.id=m.task_id
            JOIN requirements r ON r.id=t.requirement_id
            WHERE r.project_id=? ORDER BY m.seq DESC LIMIT ?""",(project_id,limit)).fetchall()
        outbox=c.execute("SELECT id,payload,status,attempts,available_at,lease_until,lease_owner,last_error,created_at,sent_at FROM outbox WHERE event_type='message.created'").fetchall()
    by_message={}
    malformed=0
    for row in outbox:
        try:
            mid=json.loads(row['payload']).get('message_id')
            if isinstance(mid,str) and mid: by_message.setdefault(mid,[]).append(row)
            else: malformed+=1
        except (TypeError,ValueError):
            malformed+=1
    dispatch_counts={k:0 for k in ('HEALTHY','MISSING','DUPLICATE','DEAD','DISPATCH_OVERDUE')}
    ack_counts={k:0 for k in ('NOT_DUE','ACK_OVERDUE','ACKNOWLEDGED','REJECTED')}
    def parse_stamp(value):
        if not value: return None
        try:
            parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError,ValueError):
            return None
    for message in messages:
        records=by_message.get(message['id'],[])
        dispatch='HEALTHY'; ack='NOT_DUE'; detail=None
        if not records:
            dispatch='MISSING'; detail='No message.created outbox record'
        elif len(records)>1:
            dispatch='DUPLICATE'; detail='Multiple message.created outbox records'
        elif records[0]['status']=='DEAD':
            dispatch='DEAD'; detail=records[0]['last_error'] or 'Outbox entered DEAD state'
        elif records[0]['status'] in ('PENDING','IN_FLIGHT'):
            created=parse_stamp(records[0]['created_at'])
            if created and (stamp-created).total_seconds()>dispatch_sla_seconds:
                dispatch='DISPATCH_OVERDUE'; detail='Broker dispatch exceeded SLA'
        elif records[0]['status']!='SENT':
            dispatch='HEALTHY'; detail='Unrecognized outbox state: '+str(records[0]['status'])
        if dispatch in dispatch_counts: dispatch_counts[dispatch]+=1
        if message['status'] in ('ACKNOWLEDGED','REJECTED'):
            ack=message['status']
        elif records and len(records)==1 and records[0]['status']=='SENT':
            sent=parse_stamp(records[0]['sent_at'])
            if sent and (stamp-sent).total_seconds()>ack_sla_seconds:
                ack='ACK_OVERDUE'
        if ack in ack_counts: ack_counts[ack]+=1
        if dispatch!='HEALTHY':
            incidents.append({'message_id':message['id'],'task_id':message['task_id'],
                'category':'DISPATCH_'+dispatch,'dispatch_status':dispatch,'ack_status':ack,
                'age_seconds':max(0,int((stamp-(parse_stamp(message['created_at']) or stamp)).total_seconds())),
                'detail':detail})
        if ack=='ACK_OVERDUE':
            incidents.append({'message_id':message['id'],'task_id':message['task_id'],
                'category':'ACK_OVERDUE','dispatch_status':dispatch,'ack_status':ack,
                'age_seconds':max(0,int((stamp-(parse_stamp(records[0]['sent_at']) or stamp)).total_seconds())),
                'detail':'Broker dispatch completed but recipient ACK exceeded SLA'})
    return {'project_id':project_id,'generated_at':stamp.isoformat(),
        'policy':{'dispatch_sla_seconds':dispatch_sla_seconds,'ack_sla_seconds':ack_sla_seconds},
        'checked_messages':len(messages),'truncated':len(messages)==limit,
        'dispatch_counts':dispatch_counts,'ack_counts':ack_counts,
        'incident_count':len(incidents),'incidents':incidents[:limit],
        'malformed_outbox_records_seen':malformed,
        'semantics':'ACK SLA starts at outbox sent_at only. SENT is broker dispatch completion, not recipient ACK.'}

@app.post('/api/v1/projects/{project_id}/message-delivery-incidents/{message_id}/review')
def review_message_delivery_incident(project_id:str,message_id:str,body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    disposition=str(body.get('disposition','')).strip().upper()
    comment=str(body.get('comment','')).strip()
    if disposition not in ('INVESTIGATING','RESOLVED','ACCEPTED_RISK'):
        raise HTTPException(422,'disposition must be INVESTIGATING, RESOLVED, or ACCEPTED_RISK')
    if not comment or len(comment)>2000:
        raise HTTPException(422,'A review comment (1-2000 characters) is required')
    with conn() as c:
        require_project_access(c,project_id,a,write=True)
        row=c.execute("""SELECT m.task_id,m.tenant_id FROM messages m JOIN tasks t ON t.id=m.task_id
            JOIN requirements r ON r.id=t.requirement_id WHERE m.id=? AND r.project_id=?""",
            (message_id,project_id)).fetchone()
        if not row: raise HTTPException(404,'Project message not found')
        event(c,'message.delivery.incident.reviewed',a['id'],row['task_id'],
              {'project_id':project_id,'message_id':message_id,'disposition':disposition,'comment':comment},
              tenant_override=row['tenant_id'])
    return {'project_id':project_id,'message_id':message_id,'disposition':disposition,'recorded':True}


@app.get('/api/v1/admin/message-delivery')
def message_delivery_overview(authorization:str=Header(None),limit:int=200,offset:int=0,
                              dispatch_status:str=None,ack_status:str=None):
    """Admin operational view separating broker dispatch from recipient acknowledgement."""
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    limit=max(1,min(limit,500)); offset=max(0,offset)
    allowed_dispatch={'NO_OUTBOX','DUPLICATE','PENDING','IN_FLIGHT','SENT','DEAD'}
    allowed_ack={'PENDING','ACKNOWLEDGED','REJECTED'}
    if dispatch_status and dispatch_status not in allowed_dispatch:
        raise HTTPException(422,'Invalid dispatch_status filter')
    if ack_status and ack_status not in allowed_ack:
        raise HTTPException(422,'Invalid ack_status filter')
    with conn() as c:
        messages=c.execute('SELECT id,recipient_member_id,tenant_id,task_id,message_type,priority,status,created_at,acked_at FROM messages ORDER BY seq DESC LIMIT ? OFFSET ?',(limit,offset)).fetchall()
        outbox=c.execute("SELECT id,event_type,payload,status,attempts,available_at,lease_until,lease_owner,last_error,created_at,sent_at,tenant_id FROM outbox WHERE event_type='message.created' ORDER BY created_at").fetchall()
    by_message={}
    malformed_count=0
    for item in outbox:
        try:
            mid=json.loads(item['payload']).get('message_id')
            if not isinstance(mid,str) or not mid: malformed_count+=1; continue
        except (TypeError,ValueError):
            malformed_count+=1; continue
        by_message.setdefault(mid,[]).append(item)
    items=[]
    counts={key:0 for key in ('NO_OUTBOX','DUPLICATE','PENDING','IN_FLIGHT','SENT','DEAD')}
    ack_counts={key:0 for key in ('PENDING','ACKNOWLEDGED','REJECTED')}
    for message in messages:
        records=by_message.get(message['id'],[])
        state='NO_OUTBOX' if not records else ('DUPLICATE' if len(records)>1 else records[0]['status'])
        if state not in counts: state='UNKNOWN'
        if state in counts: counts[state]+=1
        ack=message['status']
        if ack in ack_counts: ack_counts[ack]+=1
        if dispatch_status and state!=dispatch_status: continue
        if ack_status and ack!=ack_status: continue
        items.append({
            'message_id':message['id'],'recipient_member_id':message['recipient_member_id'],
            'tenant_id':message['tenant_id'],'task_id':message['task_id'],
            'message_type':message['message_type'],'priority':message['priority'],
            'ack_status':ack,'created_at':message['created_at'],'acked_at':message['acked_at'],
            'dispatch_status':state,'dispatch_records':[{
                'outbox_id':row['id'],'status':row['status'],'attempts':row['attempts'],
                'available_at':row['available_at'],'lease_until':row['lease_until'],
                'lease_owner':row['lease_owner'],'last_error':row['last_error'],
                'created_at':row['created_at'],'sent_at':row['sent_at']
            } for row in records]
        })
    return {'items':items,'count':len(items),'limit':limit,'offset':offset,
            'dispatch_counts':counts,'ack_counts':ack_counts,
            'malformed_outbox_records_seen':malformed_count,
            'semantics':{'SENT':'Broker dispatch completed; recipient acknowledgement is tracked separately in ack_status.',
                         'ACKNOWLEDGED':'Recipient explicitly acknowledged the message.',
                         'REJECTED':'Recipient explicitly rejected the message.'}}

@app.get('/api/v1/admin/message-delivery-integrity')
def message_delivery_integrity(authorization:str=Header(None),limit:int=5000):
    """Read-only reconciliation of durable messages and their outbox dispatch records."""
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    limit=max(1,min(limit,10000))
    with conn() as c:
        messages=c.execute('SELECT id,recipient_member_id,tenant_id,task_id FROM messages ORDER BY seq LIMIT ?',(limit+1,)).fetchall()
        outbox=c.execute("SELECT id,event_type,payload,tenant_id,status FROM outbox WHERE event_type='message.created' ORDER BY created_at LIMIT ?",(limit+1,)).fetchall()
    truncated=len(messages)>limit or len(outbox)>limit
    messages=messages[:limit]; outbox=outbox[:limit]
    by_message={}
    malformed=[]; orphaned=[]; tenant_mismatch=[]; recipient_mismatch=[]; task_mismatch=[]
    known={row['id']:row for row in messages}
    for item in outbox:
        try:
            payload=json.loads(item['payload'])
            message_id=payload.get('message_id')
            if not isinstance(message_id,str) or not message_id:
                malformed.append(item['id']); continue
        except (TypeError,ValueError):
            malformed.append(item['id']); continue
        by_message.setdefault(message_id,[]).append(item)
        message=known.get(message_id)
        if not message:
            orphaned.append(item['id']); continue
        if item['tenant_id'] != message['tenant_id']:
            tenant_mismatch.append(item['id'])
        if payload.get('recipient_member_id') != message['recipient_member_id']:
            recipient_mismatch.append(item['id'])
        if payload.get('task_id') != message['task_id']:
            task_mismatch.append(item['id'])
    missing=[mid for mid in known if mid not in by_message]
    duplicates={mid:[x['id'] for x in rows] for mid,rows in by_message.items() if len(rows)>1}
    issues={
        'messages_without_outbox':missing,
        'duplicate_outbox_by_message':duplicates,
        'orphaned_outbox':orphaned,
        'malformed_outbox':malformed,
        'tenant_mismatch_outbox':tenant_mismatch,
        'recipient_mismatch_outbox':recipient_mismatch,
        'task_mismatch_outbox':task_mismatch,
    }
    counts={key:(len(value) if isinstance(value,list) else len(value)) for key,value in issues.items()}
    return {'checked_messages':len(messages),'checked_message_outbox':len(outbox),'truncated':truncated,
            'healthy':not any(counts.values()) and not truncated,'issue_counts':counts,'issues':issues,
            'semantics':'Read-only structural reconciliation; SENT means broker dispatch completed, not recipient ACK.'}

@app.post('/api/v1/admin/outbox/{outbox_id}/replay')
def replay_dead_outbox(outbox_id:str,body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    reason=str(body.get('reason','')).strip()
    if not reason or len(reason)>1000: raise HTTPException(422,'A replay reason (1-1000 characters) is required')
    with conn() as c:
        row=c.execute("SELECT tenant_id,status FROM outbox WHERE id=?",(outbox_id,)).fetchone()
        if not row: raise HTTPException(404,'Outbox item not found')
        if row['status']!='DEAD': raise HTTPException(409,'Only DEAD outbox items can be replayed')
        stamp=now()
        cur=c.execute("UPDATE outbox SET status='PENDING',attempts=0,available_at=?,lease_until=NULL,lease_owner=NULL,lease_token=NULL,last_error=NULL,sent_at=NULL WHERE id=? AND status='DEAD'",(stamp,outbox_id))
        if not cur.rowcount: raise HTTPException(409,'Outbox item changed; refresh and retry')
        event(c,'outbox.dead.replayed',a['id'],None,{'outbox_id':outbox_id,'reason':reason},tenant_override=row['tenant_id'])
    return {'id':outbox_id,'status':'PENDING','replayed':True}

@app.websocket('/ws/v1')
async def websocket_endpoint(ws:WebSocket,token:str='',after:int=0):
    # Best-effort online notification channel. The durable inbox remains the source of truth.
    lookup_reset=_auth_lookup_ctx.set(True)
    try:
        with conn() as c: member=(c.execute("SELECT id,tenant_id,role FROM daep_authenticate_member(?,?)",(hashlib.sha256(token.encode()).hexdigest(),now())).fetchone() if DATABASE_URL.startswith(('postgresql://','postgres://')) else c.execute("SELECT id,tenant_id,role FROM members WHERE token=? AND token_status='ACTIVE' AND (token_expires_at IS NULL OR token_expires_at>?)",(hashlib.sha256(token.encode()).hexdigest(),now())).fetchone())
    finally:
        _auth_lookup_ctx.reset(lookup_reset)
    if not member: await ws.close(code=1008); return
    cursor=max(0,after)
    _tenant_ctx.set(member['tenant_id']); _admin_ctx.set(member['role']=='admin' and member['tenant_id']=='tenant-default')
    await ws.accept()
    try:
        await ws.send_json({'type':'connected','at':now(),'cursor':cursor,'delivery':'best-effort; reconnect with after=<last processed seq> or recover via inbox'})
        while True:
            with conn() as c:
                rows=[dict(r) for r in c.execute("SELECT * FROM messages WHERE recipient_member_id=? AND status='PENDING' AND seq>? ORDER BY seq LIMIT 100",(member['id'],cursor))]
                if rows:
                    for r in rows:
                        await ws.send_json({'type':'notification','message':r})
                        cursor=max(cursor,r['seq'])
                        c.execute('UPDATE messages SET attempts=attempts+1,last_attempt_at=? WHERE id=?',(now(),r['id']))
            try: await asyncio.wait_for(ws.receive_text(),timeout=3.0)
            except asyncio.TimeoutError: pass
    except WebSocketDisconnect: pass
def require_worker(authorization):
    expected=os.getenv('DAEP_WORKER_TOKEN','')
    if len(expected)<32: raise HTTPException(503,'Dedicated DAEP_WORKER_TOKEN is not configured')
    if secrets.compare_digest(hashlib.sha256(expected.encode()).digest(),hashlib.sha256(ADMIN_TOKEN.encode()).digest()): raise HTTPException(503,'Worker credential must be different from DAEP_ADMIN_TOKEN')
    if not authorization or not authorization.startswith('Bearer '): raise HTTPException(401,'Worker bearer token required')
    supplied=authorization[7:]
    expected_digest=hashlib.sha256(expected.encode()).digest()
    supplied_digest=hashlib.sha256(supplied.encode()).digest()
    if not secrets.compare_digest(supplied_digest,expected_digest): raise HTTPException(401,'Invalid worker credential')
    _service_ctx.set(True)
def require_project_access(c, project_id, a, write=False):
    project=c.execute('SELECT tenant_id,status FROM projects WHERE id=?',(project_id,)).fetchone()
    if not project: raise HTTPException(404,'Project not found')
    if project['tenant_id'] != a.get('tenant_id','tenant-default') and not is_admin(a):
        raise HTTPException(403,'Tenant isolation violation')
    if write and project['status']=='CLOSED': raise HTTPException(409,'Project is closed')
    if is_admin(a): return
    if a.get('actor_type')=='AGENT':
        binding=c.execute("SELECT 1 FROM agent_project_bindings WHERE project_id=? AND agent_id=? AND status='ACTIVE'",
            (project_id,a['agent_id'])).fetchone()
        if not binding: raise HTTPException(403,'Agent project binding required')
        if write: raise HTTPException(403,'Agent cannot perform project-level governance or administration')
        return
    row=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(project_id,a['id'])).fetchone()
    if not row: raise HTTPException(403,'Project membership required')
    if write and row['role'] not in ('owner','manager'): raise HTTPException(403,'Project manager role required')
def task_project(c, tid):
    r=c.execute('SELECT r.project_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id WHERE t.id=?',(tid,)).fetchone()
    return r['project_id'] if r else None
def require_task_access(c, tid, a, assigned_only=False):
    pid=task_project(c,tid)
    if not pid: raise HTTPException(404,'Task not found')
    project=c.execute('SELECT status FROM projects WHERE id=?',(pid,)).fetchone()
    closed=bool(project and project['status']=='CLOSED')
    if is_admin(a):
        if assigned_only and closed: raise HTTPException(409,'Project is closed')
        return
    if a.get('actor_type')=='AGENT':
        require_project_access(c,pid,a)
        if assigned_only and closed:
            raise HTTPException(409,'Project is closed')
        assignment=c.execute("""SELECT 1 FROM agent_task_assignments
            WHERE task_id=? AND project_id=? AND agent_id=? AND status='ACCEPTED'""",
            (tid,pid,a['agent_id'])).fetchone()
        if not assignment:
            raise HTTPException(403,'Accepted Agent task assignment required')
        return
    if assigned_only:
        if closed: raise HTTPException(409,'Project is closed')
        ok=c.execute('SELECT 1 FROM assignments WHERE task_id=? AND member_id=?',(tid,a['id'])).fetchone()
        if not ok: raise HTTPException(403,'Task assignment required')
    else: require_project_access(c,pid,a)

def event(c,typ,member,task,payload,key=None,tenant_override=None):
    eid='evt_'+uuid.uuid4().hex
    tenant=tenant_override or 'tenant-default'
    if tenant_override:
        pass
    elif task:
        rr=c.execute('SELECT p.tenant_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE t.id=?',(task,)).fetchone()
        if rr: tenant=rr['tenant_id']
    elif member:
        rr=c.execute('SELECT tenant_id FROM members WHERE id=?',(member,)).fetchone()
        if rr: tenant=rr['tenant_id']
    audit_payload=dict(payload or {})
    audit_payload.setdefault('actor_type','AGENT' if _agent_ctx.get() else 'MEMBER')
    if _agent_ctx.get(): audit_payload.setdefault('agent_id',_agent_ctx.get())
    # Agent actions are attributed to the Agent identity, never to its owner's member row.
    actor_member_id=None if _agent_ctx.get() else member
    payload_json=json.dumps(audit_payload)
    if key:
        c.execute('INSERT INTO events(id,event_type,actor_member_id,task_id,payload,created_at,idempotency_key,tenant_id) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(idempotency_key) DO NOTHING',(eid,typ,actor_member_id,task,payload_json,now(),key,tenant))
        prior=c.execute('SELECT id,payload FROM events WHERE idempotency_key=?',(key,)).fetchone()
        if prior:
            if prior['payload'] != payload_json:
                raise HTTPException(409,'Idempotency key was used with a different payload')
            return prior['id']
    else:
        c.execute('INSERT INTO events(id,event_type,actor_member_id,task_id,payload,created_at,idempotency_key,tenant_id) VALUES(?,?,?,?,?,?,?,?)',(eid,typ,actor_member_id,task,payload_json,now(),key,tenant))
    return eid

@app.get('/',include_in_schema=False)
def dashboard(): return FileResponse(os.path.join(os.path.dirname(os.path.dirname(__file__)),'web','index.html'))
def _oidc_discovery():
    issuer=os.getenv('DAEP_OIDC_ISSUER','').rstrip('/')
    if not issuer: raise HTTPException(503,'OIDC is not configured')
    try:
        with urllib.request.urlopen(issuer+'/.well-known/openid-configuration',timeout=10) as r: return json.loads(r.read())
    except Exception as exc: raise HTTPException(503,f'OIDC discovery failed: {exc}')

def _oidc_state_record():
    """Create one-time server-side OIDC state, nonce and PKCE verifier."""
    state=secrets.token_urlsafe(32)
    nonce=secrets.token_urlsafe(32)
    verifier=secrets.token_urlsafe(64)
    expires=datetime.fromtimestamp(time.time()+600,timezone.utc).isoformat()
    with conn() as c:
        c.execute('DELETE FROM oidc_states WHERE expires_at<=?',(now(),))
        c.execute('INSERT INTO oidc_states(state_hash,nonce,code_verifier,expires_at,created_at) VALUES(?,?,?,?,?)',
                  (hashlib.sha256(state.encode()).hexdigest(),nonce,verifier,expires,now()))
    return state,nonce,verifier

def _verify_oidc_browser_state(state,cookie_state):
    if not cookie_state or not secrets.compare_digest(hashlib.sha256(cookie_state.encode()).digest(),hashlib.sha256(state.encode()).digest()):
        raise HTTPException(400,'OIDC browser state cookie mismatch')

def _consume_oidc_state(state):
    if not state or len(state)>512: raise HTTPException(400,'Invalid OIDC state')
    digest=hashlib.sha256(state.encode()).hexdigest()
    with conn() as c:
        row=c.execute('SELECT nonce,code_verifier,expires_at FROM oidc_states WHERE state_hash=?',(digest,)).fetchone()
        if not row: raise HTTPException(400,'Invalid or already used OIDC state')
        c.execute('DELETE FROM oidc_states WHERE state_hash=?',(digest,))
    if row['expires_at'] <= now(): raise HTTPException(400,'Expired OIDC state')
    return row['nonce'],row['code_verifier']

@app.get('/api/v1/auth/oidc/login')
def oidc_login():
    if not (os.getenv('DAEP_OIDC_CLIENT_ID') and os.getenv('DAEP_OIDC_REDIRECT_URI')): raise HTTPException(503,'OIDC is not configured')
    d=_oidc_discovery(); state,nonce,verifier=_oidc_state_record()
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    params={'client_id':os.getenv('DAEP_OIDC_CLIENT_ID'),'response_type':'code','redirect_uri':os.getenv('DAEP_OIDC_REDIRECT_URI'),'scope':os.getenv('DAEP_OIDC_SCOPES','openid profile email'),'state':state,'nonce':nonce,'code_challenge':challenge,'code_challenge_method':'S256'}
    if os.getenv('DAEP_OIDC_AUDIENCE'): params['audience']=os.getenv('DAEP_OIDC_AUDIENCE')
    response=RedirectResponse(d['authorization_endpoint']+'?'+urllib.parse.urlencode(params),status_code=302)
    response.set_cookie('daep_oidc_state',state,max_age=600,httponly=True,secure=os.getenv('DAEP_OIDC_REDIRECT_URI','').startswith('https://'),samesite='lax',path='/api/v1/auth/oidc/callback')
    return response

@app.get('/api/v1/auth/oidc/callback')
def oidc_callback(code:str,state:str,daep_oidc_state:Optional[str]=Cookie(None)):
    client_id=os.getenv('DAEP_OIDC_CLIENT_ID',''); client_secret=os.getenv('DAEP_OIDC_CLIENT_SECRET','')
    redirect_uri=os.getenv('DAEP_OIDC_REDIRECT_URI','')
    if not client_id or not client_secret or not redirect_uri: raise HTTPException(503,'OIDC client is not configured')
    _verify_oidc_browser_state(state,daep_oidc_state)
    nonce,code_verifier=_consume_oidc_state(state); d=_oidc_discovery()
    form=urllib.parse.urlencode({'grant_type':'authorization_code','code':code,'redirect_uri':redirect_uri,'client_id':client_id,'client_secret':client_secret,'code_verifier':code_verifier}).encode()
    req=urllib.request.Request(d['token_endpoint'],data=form,method='POST',headers={'Content-Type':'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req,timeout=15) as r: tokens=json.loads(r.read())
    except Exception: raise HTTPException(502,'OIDC token exchange failed')
    id_token=tokens.get('id_token')
    if not id_token: raise HTTPException(502,'OIDC provider did not return an id_token')
    try:
        import jwt
        jwks_client=jwt.PyJWKClient(d['jwks_uri'],timeout=10)
        signing_key=jwks_client.get_signing_key_from_jwt(id_token).key
        claims=jwt.decode(id_token,signing_key,algorithms=['RS256','RS384','RS512','PS256','ES256'],audience=client_id,issuer=os.getenv('DAEP_OIDC_ISSUER').rstrip('/'),options={'require':['exp','iat','sub','iss','aud']})
        if not secrets.compare_digest(str(claims.get('nonce','')),nonce): raise ValueError('OIDC nonce mismatch')
        audiences=claims.get('aud',[])
        if isinstance(audiences,list) and len(audiences)>1 and claims.get('azp')!=client_id: raise ValueError('OIDC authorized party mismatch')
    except Exception: raise HTTPException(401,'OIDC ID token validation failed')
    subject=str(claims.get('sub','')); email=str(claims.get('email',''))
    if not subject: raise HTTPException(401,'OIDC subject is missing')
    created=now(); raw=uuid.uuid4().hex+uuid.uuid4().hex; digest=hashlib.sha256(raw.encode()).hexdigest()
    service_reset=_service_ctx.set(True)
    try:
        with conn() as c:
            row=c.execute('SELECT id FROM members WHERE oidc_subject=?',(subject,)).fetchone()
            if row:
                c.execute("UPDATE members SET token=?,token_status='ACTIVE',token_created_at=?,token_revoked_at=NULL,oidc_email=? WHERE id=?",(digest,created,email,row['id']))
                member_id=row['id']
            else:
                if os.getenv('DAEP_OIDC_AUTO_PROVISION','false').lower()!='true': raise HTTPException(403,'OIDC identity is not provisioned')
                member_id='mem_'+uuid.uuid4().hex[:12]; tenant_id=os.getenv('DAEP_OIDC_DEFAULT_TENANT','tenant-default'); name=str(claims.get('name') or email or subject)
                if not c.execute("SELECT 1 FROM tenants WHERE id=? AND status='ACTIVE'",(tenant_id,)).fetchone(): raise HTTPException(403,'OIDC default tenant is unavailable')
                oidc_role=os.getenv('DAEP_OIDC_DEFAULT_ROLE','developer')
                if oidc_role not in ('developer','manager','reviewer'): oidc_role='developer'
                c.execute("INSERT INTO members(id,name,role,token,created_at,tenant_id,token_status,token_created_at,oidc_subject,oidc_email) VALUES(?,?,?,?,?,?,?,?,?,?)",(member_id,name,oidc_role,digest,created,tenant_id,'ACTIVE',created,subject,email))
    finally:
        _service_ctx.reset(service_reset)
    response=JSONResponse({'member_id':member_id,'token':raw,'token_expires_at':None,'message':'OIDC authentication succeeded; store this API token securely. It is returned only once.'})
    response.delete_cookie('daep_oidc_state',path='/api/v1/auth/oidc/callback')
    return response

@app.get('/api/v1/auth/oidc/config')
def oidc_config():
    enabled=bool(os.getenv('DAEP_OIDC_ISSUER') and os.getenv('DAEP_OIDC_CLIENT_ID') and os.getenv('DAEP_OIDC_REDIRECT_URI'))
    return {'enabled':enabled,'issuer':os.getenv('DAEP_OIDC_ISSUER',''),'client_id':os.getenv('DAEP_OIDC_CLIENT_ID',''),'redirect_uri':os.getenv('DAEP_OIDC_REDIRECT_URI',''),'scopes':os.getenv('DAEP_OIDC_SCOPES','openid profile email')}

@app.post('/api/v1/integrations/git/webhook')
async def git_webhook(request:Request, body:dict, x_daep_webhook_secret:str=Header('',alias='X-DAEP-Webhook-Secret'), x_daep_tenant_id:str=Header('',alias='X-DAEP-Tenant-ID'), x_daep_provider:str=Header('',alias='X-DAEP-Provider'), x_github_event:str=Header('',alias='X-GitHub-Event'), x_github_delivery:str=Header('',alias='X-GitHub-Delivery'), x_hub_signature_256:str=Header('',alias='X-Hub-Signature-256'), x_gitlab_event:str=Header('',alias='X-Gitlab-Event'), x_gitlab_event_uuid:str=Header('',alias='X-Gitlab-Event-UUID'), x_gitlab_token:str=Header('',alias='X-Gitlab-Token')):
    raw=await request.body()
    provider=(x_daep_provider or ('github' if x_github_event or x_hub_signature_256 else 'gitlab' if x_gitlab_event or x_gitlab_token else 'generic')).lower()
    if provider not in ('github','gitlab','generic'): raise HTTPException(422,'Unsupported Git provider')
    if provider=='github':
        expected=os.getenv('DAEP_GITHUB_WEBHOOK_SECRET') or os.getenv('DAEP_GIT_WEBHOOK_SECRET','')
        if not expected or not x_hub_signature_256 or not x_hub_signature_256.startswith('sha256='): raise HTTPException(401,'GitHub webhook signature is required')
        supplied=x_hub_signature_256.split('=',1)[1]
        actual=hmac.new(expected.encode(),raw,hashlib.sha256).hexdigest()
        if not hmac.compare_digest(actual,supplied): raise HTTPException(401,'Invalid GitHub webhook signature')
        delivery=x_github_delivery
    elif provider=='gitlab':
        expected=os.getenv('DAEP_GITLAB_WEBHOOK_SECRET') or os.getenv('DAEP_GIT_WEBHOOK_SECRET','')
        if not expected or not x_gitlab_token or not secrets.compare_digest(hashlib.sha256(x_gitlab_token.encode()).digest(),hashlib.sha256(expected.encode()).digest()): raise HTTPException(401,'Invalid GitLab webhook token')
        delivery=x_gitlab_event_uuid
    else:
        expected=os.getenv('DAEP_GIT_WEBHOOK_SECRET','')
        if not expected or not x_daep_webhook_secret or not secrets.compare_digest(hashlib.sha256(x_daep_webhook_secret.encode()).digest(),hashlib.sha256(expected.encode()).digest()): raise HTTPException(401,'Invalid webhook secret')
        delivery=request.headers.get('X-DAEP-Delivery','')
    if delivery and len(delivery)>200: raise HTTPException(422,'Webhook delivery id is too long')
    event_type=str(body.get('event_type') or body.get('action') or x_github_event or x_gitlab_event or 'push')[:80]
    task_id=body.get('task_id'); commit=body.get('after') or body.get('commit_sha')
    service_reset=_service_ctx.set(True)
    try:
        with conn() as c:
            if task_id:
                row=c.execute('SELECT p.tenant_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE t.id=?',(task_id,)).fetchone()
                if not row: raise HTTPException(404,'Task not found')
                tenant_id=row['tenant_id']
            else:
                tenant_id=str(x_daep_tenant_id or body.get('tenant_id') or '').strip()
                if not tenant_id: raise HTTPException(422,'X-DAEP-Tenant-ID is required when task_id is absent')
                if not c.execute("SELECT 1 FROM tenants WHERE id=? AND status='ACTIVE'",(tenant_id,)).fetchone(): raise HTTPException(404,'Tenant not found or inactive')
        _tenant_ctx.set(tenant_id); _admin_ctx.set(False)
        _service_ctx.reset(service_reset); service_reset=_service_ctx.set(False)
        with conn() as c:
            eid=event(c,'git.webhook.received',None,task_id,{'provider':provider,'delivery_id':delivery,'event_type':event_type,'commit_sha':commit,'payload':body},key=(f'git:{provider}:{delivery}' if delivery else None),tenant_override=tenant_id)
        return {'accepted':True,'event_id':eid,'event_type':event_type,'commit_sha':commit,'tenant_id':tenant_id,'provider':provider,'delivery_id':delivery}
    finally:
        _service_ctx.reset(service_reset)

@app.get('/health')
def health():
    service_reset=_service_ctx.set(True)
    try:
        with conn() as c:
            pending=c.execute("SELECT COUNT(*) n FROM outbox WHERE status IN ('PENDING','IN_FLIGHT')").fetchone()['n']
        return {'status':'ok','service':'daep-api','version':'1.0.0-rc9','outbox_pending':pending}
    finally:
        _service_ctx.reset(service_reset)

@app.get('/readyz')
def readiness():
    service_reset=_service_ctx.set(True)
    try:
        with conn() as c:
            c.execute('SELECT 1').fetchone()
            if DATABASE_URL.startswith(('postgresql://','postgres://')):
                c.execute("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='members'").fetchone()
        return {'status':'ready','service':'daep-api','version':'1.0.0-rc9'}
    except Exception:
        raise HTTPException(503,'DAEP database readiness check failed')
    finally:
        _service_ctx.reset(service_reset)
@app.get('/api/v1/me')
def me(authorization:str=Header(None)):
    a=actor(authorization); return {k:a[k] for k in ('id','name','role')}
@app.post('/api/v1/tenants')
def create_tenant(body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    name=str(body.get('name','')).strip()
    if not name or len(name)>160: raise HTTPException(422,'Tenant name is required')
    tid='ten_'+uuid.uuid4().hex[:12]
    with conn() as c: c.execute('INSERT INTO tenants(id,name,status,created_at) VALUES(?,?,?,?)',(tid,name,'ACTIVE',now()))
    return {'id':tid,'name':name,'status':'ACTIVE'}

@app.get('/api/v1/tenants')
def list_tenants(authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    with conn() as c: return [dict(x) for x in c.execute('SELECT * FROM tenants ORDER BY created_at')]

@app.post('/api/v1/members')
def create_member(body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    if not isinstance(body.get('name'),str) or not body['name'].strip(): raise HTTPException(422,'Member name is required')
    if body.get('role','developer') not in ('manager','developer','reviewer'): raise HTTPException(422,'Only the bootstrap identity can hold the platform administrator role')
    mid='mem_'+uuid.uuid4().hex[:12]; token=uuid.uuid4().hex+uuid.uuid4().hex; created=now()
    tenant_id=str(body.get('tenant_id') or a.get('tenant_id') or 'tenant-default')
    with conn() as c:
        if not c.execute("SELECT 1 FROM tenants WHERE id=? AND status='ACTIVE'",(tenant_id,)).fetchone(): raise HTTPException(404,'Tenant not found or inactive')
        c.execute('INSERT INTO members(id,name,role,token,created_at,tenant_id,token_status,token_created_at,token_revoked_at,token_expires_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(mid,body['name'],body.get('role','developer'),hashlib.sha256(token.encode()).hexdigest(),created,tenant_id,'ACTIVE',created,None,body.get('token_expires_at')))
    return {'id':mid,'name':body['name'],'role':body.get('role','developer'),'tenant_id':tenant_id,'token':token}
@app.get('/api/v1/members')
def members(authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    with conn() as c: return [dict(x) for x in c.execute('SELECT id,name,role,tenant_id,token_status,token_created_at,token_revoked_at,token_expires_at,created_at FROM members ORDER BY created_at')]
@app.post('/api/v1/members/{member_id}/revoke-token')
def revoke_member_token(member_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    with conn() as c:
        target=c.execute('SELECT tenant_id FROM members WHERE id=?',(member_id,)).fetchone()
        if not target: raise HTTPException(404,'Member not found')
        cur=c.execute("UPDATE members SET token_status='REVOKED',token_revoked_at=? WHERE id=?" ,(now(),member_id))
        event(c,'member.token.revoked',a['id'],None,{'member_id':member_id},tenant_override=target['tenant_id'])
    return {'member_id':member_id,'token_status':'REVOKED'}

@app.post('/api/v1/members/{member_id}/rotate-token')
def rotate_member_token(member_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    token=uuid.uuid4().hex+uuid.uuid4().hex; created=now(); digest=hashlib.sha256(token.encode()).hexdigest()
    with conn() as c:
        target=c.execute('SELECT tenant_id FROM members WHERE id=?',(member_id,)).fetchone()
        if not target: raise HTTPException(404,'Member not found')
        cur=c.execute("UPDATE members SET token=?,token_status='ACTIVE',token_created_at=?,token_revoked_at=NULL WHERE id=?",(digest,created,member_id))
        event(c,'member.token.rotated',a['id'],None,{'member_id':member_id},tenant_override=target['tenant_id'])
    return {'member_id':member_id,'token':token,'token_status':'ACTIVE','token_created_at':created}

@app.post('/api/v1/projects')
def create_project(b:ProjectIn,authorization:str=Header(None)):
    a=actor(authorization); pid='prj_'+uuid.uuid4().hex[:12]
    with conn() as c:
        c.execute('INSERT INTO projects(id,name,description,created_by,created_at,tenant_id) VALUES(?,?,?,?,?,?)',(pid,b.name,b.description,a['id'],now(),a.get('tenant_id','tenant-default')))
        c.execute('INSERT INTO project_members(project_id,member_id,role,work_function,joined_at) VALUES(?,?,?,?,?)',(pid,a['id'],'owner','other',now()))
    return {'id':pid,'name':b.name,'description':b.description}
@app.get('/api/v1/projects')
def projects(authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        if is_admin(a): rows=c.execute('SELECT * FROM projects ORDER BY created_at DESC')
        else: rows=c.execute('SELECT p.*,pm.role AS project_role,pm.work_function FROM projects p JOIN project_members pm ON pm.project_id=p.id WHERE pm.member_id=? AND p.tenant_id=? ORDER BY p.created_at DESC',(a['id'],a.get('tenant_id','tenant-default')))
        return [dict(x) for x in rows]
@app.get('/api/v1/projects/{pid}/members')
def project_members(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        return [dict(x) for x in c.execute('SELECT m.id,m.name,m.role AS account_role,pm.role AS project_role,pm.work_function,pm.joined_at FROM project_members pm JOIN members m ON m.id=pm.member_id WHERE pm.project_id=? ORDER BY pm.joined_at',(pid,))]
@app.post('/api/v1/projects/{pid}/members')
def add_project_member(pid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization)
    mid=b.get('member_id'); role=b.get('role','member'); work_function=b.get('work_function','other')
    if role not in ('member','reviewer','manager'): raise HTTPException(422,'Invalid project role')
    if work_function not in ('developer','tester','product','architect','other'): raise HTTPException(422,'Invalid work function')
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        if role=='manager' and not is_admin(a):
            own=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not own or own['role']!='owner': raise HTTPException(403,'Only project owners may directly grant manager role; use an approval request')
        member_row=c.execute('SELECT tenant_id FROM members WHERE id=?',(mid,)).fetchone()
        project_row=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        if not member_row: raise HTTPException(404,'Member not found')
        if project_row['tenant_id'] != member_row['tenant_id']: raise HTTPException(400,'Member belongs to a different tenant')
        c.execute('INSERT INTO project_members(project_id,member_id,role,work_function,joined_at) VALUES(?,?,?,?,?) ON CONFLICT(project_id,member_id) DO UPDATE SET role=excluded.role,work_function=excluded.work_function',(pid,mid,role,work_function,now()))
        event(c,'project.member.role_set',a['id'],None,{'project_id':pid,'member_id':mid,'role':role},tenant_override=project_row['tenant_id'])
        return {'project_id':pid,'member_id':mid,'role':role,'work_function':work_function}
@app.patch('/api/v1/projects/{pid}/members/{member_id}/function')
def update_project_member_function(pid:str,member_id:str,b:ProjectMemberFunctionIn,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        target=c.execute('SELECT role,work_function FROM project_members WHERE project_id=? AND member_id=?',(pid,member_id)).fetchone()
        if not target: raise HTTPException(404,'Target is not a project member')
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        c.execute('UPDATE project_members SET work_function=? WHERE project_id=? AND member_id=?',(b.work_function,pid,member_id))
        event(c,'project.member.work_function_set',a['id'],None,{'project_id':pid,'member_id':member_id,'work_function':b.work_function},tenant_override=project['tenant_id'])
        return {'project_id':pid,'member_id':member_id,'project_role':target['role'],'work_function':b.work_function}

@app.post('/api/v1/projects/{pid}/role-change-requests')
def request_project_role_change(pid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization); member_id=str(b.get('member_id','')).strip(); new_role=str(b.get('new_role','')).strip()
    reason=str(b.get('reason','')).strip()
    if not member_id or new_role not in ('member','reviewer','manager') or not reason or len(reason)>1000:
        raise HTTPException(422,'member_id, valid new_role and reason (1-1000 chars) are required')
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        target=c.execute('SELECT tenant_id FROM members WHERE id=?',(member_id,)).fetchone()
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        if not target or target['tenant_id']!=project['tenant_id']: raise HTTPException(404,'Member not found in project tenant')
        if not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(pid,member_id)).fetchone(): raise HTTPException(404,'Target is not a project member')
        current=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,member_id)).fetchone()['role']
        if current==new_role: raise HTTPException(409,'Member already has requested role')
        aid='apr_'+uuid.uuid4().hex
        payload={'member_id':member_id,'previous_role':current,'new_role':new_role,'reason':reason}
        c.execute("INSERT INTO project_approvals(id,project_id,tenant_id,requester_member_id,action,payload,status,created_at) VALUES(?,?,?,?,? ,?,'PENDING',?)",
                  (aid,pid,project['tenant_id'],a['id'],'PROJECT_ROLE_CHANGE',json.dumps(payload),now()))
        event(c,'project.role_change.requested',a['id'],None,{'approval_id':aid,'project_id':pid,**payload},tenant_override=project['tenant_id'])
        return {'approval_id':aid,'status':'PENDING','project_id':pid,'payload':payload}

@app.get('/api/v1/projects/{pid}/approvals')
def list_project_approvals(pid:str,status:str='PENDING',limit:int=100,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,200))
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute('SELECT * FROM project_approvals WHERE project_id=? AND status=? ORDER BY created_at DESC LIMIT ?',(pid,status,limit)).fetchall()
        return {'items':[{'id':x['id'],'action':x['action'],'payload':json.loads(x['payload']),'status':x['status'],'requester_member_id':x['requester_member_id'],'decided_by':x['decided_by'],'decision_reason':x['decision_reason'],'created_at':x['created_at'],'decided_at':x['decided_at']} for x in rows]}

@app.post('/api/v1/projects/{pid}/approvals/{approval_id}/decision')
def decide_project_approval(pid:str,approval_id:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization); decision=str(b.get('decision','')).upper(); reason=str(b.get('reason','')).strip()
    if decision not in ('APPROVE','REJECT') or not reason or len(reason)>1000: raise HTTPException(422,'decision must be APPROVE or REJECT and reason is required')
    with conn() as c:
        require_project_access(c,pid,a)
        if not is_admin(a):
            own=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not own or own['role']!='owner': raise HTTPException(403,'Project owner approval required')
        row=c.execute('SELECT * FROM project_approvals WHERE id=? AND project_id=?',(approval_id,pid)).fetchone()
        if not row: raise HTTPException(404,'Approval not found')
        if row['status']!='PENDING': raise HTTPException(409,'Approval already decided')
        if row['requester_member_id']==a['id']: raise HTTPException(403,'Requester cannot approve their own request')
        payload=json.loads(row['payload'])
        if row['action']!='PROJECT_ROLE_CHANGE': raise HTTPException(409,'Unsupported approval action')
        if decision=='APPROVE':
            current=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,payload['member_id'])).fetchone()
            if not current or current['role']!=payload['previous_role']: raise HTTPException(409,'Target role changed since request; submit a new request')
            c.execute('UPDATE project_members SET role=? WHERE project_id=? AND member_id=?',(payload['new_role'],pid,payload['member_id']))
        stamp=now()
        approval_status='APPROVED' if decision=='APPROVE' else 'REJECTED'
        c.execute('UPDATE project_approvals SET status=?,decided_by=?,decision_reason=?,decided_at=? WHERE id=? AND status=?',(approval_status,a['id'],reason,stamp,approval_id,'PENDING'))
        event(c,'project.role_change.'+('approved' if decision=='APPROVE' else 'rejected'),a['id'],None,{'approval_id':approval_id,'project_id':pid,**payload,'decision_reason':reason},tenant_override=row['tenant_id'])
        return {'approval_id':approval_id,'status':approval_status,'member_id':payload['member_id'],'role':payload['new_role'] if decision=='APPROVE' else payload['previous_role']}

@app.get('/api/v1/requirements/{rid}/acceptance-report')
def requirement_acceptance_report(rid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        req=c.execute('SELECT * FROM requirements WHERE id=?',(rid,)).fetchone()
        if not req: raise HTTPException(404,'Requirement not found')
        require_project_access(c,req['project_id'],a)
        criteria=json.loads(req['acceptance_criteria'] or '[]')
        tasks=c.execute("SELECT t.id,t.title,t.status,t.progress,t.updated_at,(SELECT COUNT(*) FROM artifacts ar WHERE ar.task_id=t.id) AS artifact_count FROM tasks t WHERE t.requirement_id=? ORDER BY t.created_at,t.id",(rid,)).fetchall()
        items=[dict(x) for x in tasks]
        missing=[x['id'] for x in items if x['status']!='DONE' or x['artifact_count']<1]
        return {'requirement_id':rid,'project_id':req['project_id'],'title':req['title'],'status':req['status'],
            'acceptance_criteria':[{'index':i,'text':v} for i,v in enumerate(criteria)],'task_count':len(items),
            'tasks':items,'all_tasks_done':bool(items) and all(x['status']=='DONE' for x in items),
            'missing_delivery_evidence_task_ids':missing,'ready_for_acceptance':bool(items) and not missing and bool(criteria)}

@app.post('/api/v1/requirements/{rid}/acceptance')
def decide_requirement_acceptance(rid:str,b:RequirementAcceptanceIn,authorization:str=Header(None)):
    a=actor(authorization)
    if a.get('actor_type')=='AGENT': raise HTTPException(403,'Agent cannot approve or reject requirement acceptance')
    with conn() as c:
        req=c.execute('SELECT * FROM requirements WHERE id=?',(rid,)).fetchone()
        if not req: raise HTTPException(404,'Requirement not found')
        pid=req['project_id']; require_project_access(c,pid,a)
        if not is_admin(a):
            role=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not role or role['role'] not in ('owner','manager','reviewer'): raise HTTPException(403,'Reviewer role required')
        if req['status']=='ACCEPTED': raise HTTPException(409,'Requirement is already accepted')
        criteria=json.loads(req['acceptance_criteria'] or '[]')
        verified=list(dict.fromkeys(b.verified_criteria))
        if len(verified)!=len(b.verified_criteria): raise HTTPException(422,'verified_criteria must be unique')
        if any(i<0 or i>=len(criteria) for i in verified): raise HTTPException(422,'verified_criteria contains an unknown criterion index')
        tasks=c.execute("SELECT t.id,t.status,(SELECT COUNT(*) FROM artifacts ar WHERE ar.task_id=t.id) AS artifact_count FROM tasks t WHERE t.requirement_id=? ORDER BY t.id",(rid,)).fetchall()
        if b.decision=='APPROVE':
            if not criteria or verified!=list(range(len(criteria))): raise HTTPException(409,'Every acceptance criterion must be explicitly verified')
            pending=[x['id'] for x in tasks if x['status']!='DONE']
            missing=[x['id'] for x in tasks if x['artifact_count']<1]
            if not tasks or pending or missing: raise HTTPException(409,detail={'message':'Requirement cannot be accepted until every task is DONE and has delivery evidence','pending_task_ids':pending,'missing_artifact_task_ids':missing})
            status='ACCEPTED'
        else: status='OPEN'
        stamp=now(); c.execute('UPDATE requirements SET status=? WHERE id=?',(status,rid))
        tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id']
        payload={'project_id':pid,'requirement_id':rid,'decision':b.decision,'status':status,'verified_criteria':verified,
            'acceptance_criteria':criteria,'comment':b.comment,'task_ids':[x['id'] for x in tasks]}
        eid=event(c,'requirement.acceptance.'+b.decision.lower(),a['id'],None,payload,tenant_override=tenant)
        return {'requirement_id':rid,'status':status,'decision':b.decision,'event_id':eid,'decided_at':stamp,'verified_criteria':verified}

@app.post('/api/v1/projects/{pid}/decisions')
def record_project_decision(pid:str,b:ProjectDecisionIn,authorization:str=Header(None)):
    a=actor(authorization); decision_id='dec_'+uuid.uuid4().hex
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        accountable=c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(pid,b.accountable_member_id)).fetchone()
        if not accountable: raise HTTPException(422,'Accountable member must belong to this project')
        task_ids=list(dict.fromkeys(b.related_task_ids))
        if len(task_ids)!=len(b.related_task_ids): raise HTTPException(422,'related_task_ids must be unique')
        for task_id in task_ids:
            if task_project(c,task_id)!=pid: raise HTTPException(422,'Every related task must belong to this project')
        payload={'project_id':pid,'decision_id':decision_id,'title':b.title,'decision':b.decision,
            'rationale':b.rationale,'accountable_member_id':b.accountable_member_id,
            'related_task_ids':task_ids,'due_at':b.due_at,'recorded_by':a['id']}
        event(c,'project.decision.created',a['id'],None,payload)
    return {'id':decision_id,'project_id':pid,'status':'RECORDED','created_at':now(),**payload}

@app.get('/api/v1/projects/{pid}/decisions')
def list_project_decisions(pid:str,limit:int=100,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,500))
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("SELECT e.id,e.actor_member_id,e.payload,e.created_at,m.name AS actor_name FROM events e LEFT JOIN members m ON m.id=e.actor_member_id WHERE e.event_type='project.decision.created' AND e.payload LIKE ? ORDER BY e.created_at DESC LIMIT ?",('%"project_id"%"'+pid+'"%',limit)).fetchall()
        items=[]
        for row in rows:
            payload=json.loads(row['payload'] or '{}')
            if payload.get('project_id')!=pid: continue
            accountable=c.execute('SELECT name FROM members WHERE id=?',(payload.get('accountable_member_id'),)).fetchone()
            items.append({'id':payload.get('decision_id'),'title':payload.get('title'),'decision':payload.get('decision'),
                'rationale':payload.get('rationale',''),'accountable_member_id':payload.get('accountable_member_id'),
                'accountable_member_name':accountable['name'] if accountable else None,'related_task_ids':payload.get('related_task_ids',[]),
                'due_at':payload.get('due_at'),'recorded_by':row['actor_member_id'],'recorded_by_name':row['actor_name'],
                'created_at':row['created_at'],'audit_event_id':row['id']})
        return {'project_id':pid,'items':items,'count':len(items)}

@app.get('/api/v1/projects/{pid}/governance')
def project_governance_snapshot(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT t.id,t.status,t.progress,t.updated_at,a.member_id,m.name AS member_name
            FROM tasks t JOIN requirements r ON r.id=t.requirement_id
            LEFT JOIN assignments a ON a.task_id=t.id LEFT JOIN members m ON m.id=a.member_id
            WHERE r.project_id=? ORDER BY t.id""",(pid,)).fetchall()
        task_ids=set(); task_state={}
        for row in rows:
            task_ids.add(row['id'])
            task_state[row['id']]={'status':row['status'],'progress':row['progress']}
        total=len(task_ids)
        status_counts={}
        for item in task_state.values(): status_counts[item['status']]=status_counts.get(item['status'],0)+1
        responsibility={}
        for row in rows:
            if not row['member_id']: continue
            slot=responsibility.setdefault(row['member_id'],{'member_id':row['member_id'],'member_name':row['member_name'],'assigned_task_ids':[],'done':0,'active':0,'review':0,'blocked':0})
            if row['id'] not in slot['assigned_task_ids']:
                slot['assigned_task_ids'].append(row['id'])
                if row['status']=='DONE': slot['done']+=1
                elif row['status']=='REVIEW': slot['review']+=1
                elif row['status']=='BLOCKED': slot['blocked']+=1
                else: slot['active']+=1
        packages=c.execute("SELECT risk_state,COUNT(*) AS n FROM task_work_packages WHERE project_id=? AND status='ACTIVE' GROUP BY risk_state",(pid,)).fetchall()
        package_risks={x['risk_state']:x['n'] for x in packages}
        pending_reviews=status_counts.get('REVIEW',0)
        delivery_health=project_message_delivery_health(pid,authorization,120,300,500)
        review_rows=c.execute("""SELECT e.payload,e.created_at FROM events e
            WHERE e.event_type='message.delivery.incident.reviewed' AND e.payload LIKE ?
            ORDER BY e.created_at DESC LIMIT 1000""",('%'+pid+'%',)).fetchall()
        latest_reviews={}
        for review_row in review_rows:
            try:
                payload=json.loads(review_row['payload'] or '{}')
                if payload.get('project_id')!=pid: continue
                mid=payload.get('message_id')
                if mid and mid not in latest_reviews:
                    latest_reviews[mid]={'disposition':payload.get('disposition'),'comment':payload.get('comment'),
                                         'reviewed_at':review_row['created_at']}
            except (TypeError,ValueError):
                continue
        reviewed_incidents=[]
        open_incidents=0; resolved_incidents=0; accepted_risk_incidents=0; investigating_incidents=0
        for incident in delivery_health.get('incidents',[]):
            review=latest_reviews.get(incident['message_id'])
            disposition=review.get('disposition') if review else 'UNREVIEWED'
            item=dict(incident)
            item['review_disposition']=disposition
            item['reviewed_at']=review.get('reviewed_at') if review else None
            reviewed_incidents.append(item)
            if disposition=='RESOLVED': resolved_incidents+=1
            elif disposition=='ACCEPTED_RISK': accepted_risk_incidents+=1
            else:
                open_incidents+=1
                if disposition=='INVESTIGATING': investigating_incidents+=1
        daily=c.execute("""SELECT substr(m.created_at,1,10) AS day,COUNT(*) AS created,
            SUM(CASE WHEN m.status IN ('ACKNOWLEDGED','REJECTED') THEN 1 ELSE 0 END) AS terminal_ack
            FROM messages m JOIN tasks t ON t.id=m.task_id JOIN requirements r ON r.id=t.requirement_id
            WHERE r.project_id=? AND m.created_at>=? GROUP BY substr(m.created_at,1,10) ORDER BY day""",
            (pid,datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).isoformat())).fetchall()
        delivery_trend=[{'date':x['day'],'messages_created':x['created'],'terminal_ack':x['terminal_ack'] or 0} for x in daily]
        message_delivery_governance={
            'checked_messages':delivery_health.get('checked_messages',0),
            'dispatch_counts':delivery_health.get('dispatch_counts',{}),
            'ack_counts':delivery_health.get('ack_counts',{}),
            'incident_count':delivery_health.get('incident_count',0),
            'open_incidents':open_incidents,'investigating_incidents':investigating_incidents,
            'resolved_incidents':resolved_incidents,'accepted_risk_incidents':accepted_risk_incidents,
            'incidents':reviewed_incidents,'trend_since_utc_midnight':delivery_trend,
            'sla_policy':delivery_health.get('policy'),
            'truncated':delivery_health.get('truncated',False)
        }
        return {'project_id':pid,'task_total':total,'task_status_counts':status_counts,
            'completed_tasks':status_counts.get('DONE',0),'completion_percent':round(status_counts.get('DONE',0)*100/total) if total else 100,
            'pending_reviews':pending_reviews,'open_tasks':total-status_counts.get('DONE',0),
            'active_work_package_risk_counts':package_risks,
            'at_risk_work_packages':sum(package_risks.get(k,0) for k in ('OVERDUE','BLOCKED_DEPENDENCY','STALLED')),
            'responsibility':list(responsibility.values()),
            'completion_gate':'SATISFIED' if total and status_counts.get('DONE',0)==total else ('EMPTY' if not total else 'OPEN'),
            'message_delivery':message_delivery_governance}

@app.get('/api/v1/projects/{pid}/workflow')
def get_project_workflow(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        row=c.execute('SELECT config,updated_by,updated_at FROM project_workflows WHERE project_id=?',(pid,)).fetchone()
        if row: return {'project_id':pid,'config':json.loads(row['config']),'updated_by':row['updated_by'],'updated_at':row['updated_at']}
        return {'project_id':pid,'config':{'enabled':True,'stages':[{'key':'OPEN','name':'需求进入','order':1,'approval_role':'none','sla_seconds':None},{'key':'IN_PROGRESS','name':'执行','order':2,'approval_role':'none','sla_seconds':172800},{'key':'REVIEW','name':'评审验收','order':3,'approval_role':'reviewer','sla_seconds':86400},{'key':'DONE','name':'完成交付','order':4,'approval_role':'none','sla_seconds':None}]},'source':'system-default'}

@app.put('/api/v1/projects/{pid}/workflow')
def set_project_workflow(pid:str,b:WorkflowConfigIn,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        if not (a['role']=='admin' or project_role(c,pid,a) in ('owner','manager')): raise HTTPException(403,'Project manager or platform administrator required')
        stages=sorted([x.model_dump() for x in b.stages],key=lambda x:x['order'])
        if [x['order'] for x in stages] != list(range(1,len(stages)+1)): raise HTTPException(422,'Stage order must be contiguous from 1')
        if len({x['key'] for x in stages}) != len(stages): raise HTTPException(422,'Stage keys must be unique')
        if not any(x['key']=='REVIEW' for x in stages): raise HTTPException(422,'System governance requires a REVIEW stage')
        cfg={'enabled':b.enabled,'stages':stages}; stamp=now(); tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id']
        c.execute('INSERT INTO project_workflows(project_id,tenant_id,config,updated_by,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET config=excluded.config,updated_by=excluded.updated_by,updated_at=excluded.updated_at',(pid,tenant,json.dumps(cfg),a['id'],stamp))
        event(c,'project.workflow.updated',a['id'],None,{'project_id':pid,'config':cfg},tenant_override=tenant)
        return {'project_id':pid,'config':cfg,'updated_by':a['id'],'updated_at':stamp}

@app.get('/api/v1/projects/{pid}/gates')
def get_project_gates(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute('SELECT gate_key,config,updated_by,updated_at FROM project_gates WHERE project_id=? ORDER BY gate_key',(pid,)).fetchall()
        items={r['gate_key']:{'config':json.loads(r['config']),'updated_by':r['updated_by'],'updated_at':r['updated_at']} for r in rows}
        items.setdefault('REVIEW_REQUIRED',{'config':{'enabled':True,'required_roles':['reviewer'],'required_evidence':True,'required_all_tasks_done':False},'system_locked':True})
        items.setdefault('DELIVERY_EVIDENCE',{'config':{'enabled':True,'required_roles':['owner','manager','reviewer'],'required_evidence':True,'required_all_tasks_done':True},'system_locked':True})
        return {'project_id':pid,'gates':items}

@app.put('/api/v1/projects/{pid}/gates/{gate_key}')
def set_project_gate(pid:str,gate_key:str,b:GateConfigIn,authorization:str=Header(None)):
    a=actor(authorization)
    if gate_key in ('REVIEW_REQUIRED','DELIVERY_EVIDENCE'): raise HTTPException(409,'System governance gate cannot be disabled or weakened')
    if not re.fullmatch(r'[A-Z0-9_]{2,60}',gate_key): raise HTTPException(422,'Invalid gate key')
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        if not (a['role']=='admin' or project_role(c,pid,a) in ('owner','manager')): raise HTTPException(403,'Project manager or platform administrator required')
        cfg=b.model_dump(); cfg['applies_to']=cfg.get('applies_to') or 'DONE'; stamp=now(); tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id']
        c.execute('INSERT INTO project_gates(project_id,gate_key,tenant_id,config,updated_by,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(project_id,gate_key) DO UPDATE SET config=excluded.config,updated_by=excluded.updated_by,updated_at=excluded.updated_at',(pid,gate_key,tenant,json.dumps(cfg),a['id'],stamp))
        event(c,'project.gate.updated',a['id'],None,{'project_id':pid,'gate_key':gate_key,'config':cfg},tenant_override=tenant)
        return {'project_id':pid,'gate_key':gate_key,'config':cfg,'updated_at':stamp}


DEFAULT_PROJECT_WORKFLOW={'enabled':True,'stages':[{'key':'OPEN','name':'需求进入','order':1,'approval_role':'none','sla_seconds':None},{'key':'IN_PROGRESS','name':'执行','order':2,'approval_role':'none','sla_seconds':172800},{'key':'REVIEW','name':'评审验收','order':3,'approval_role':'reviewer','sla_seconds':86400},{'key':'DONE','name':'完成交付','order':4,'approval_role':'none','sla_seconds':None}]}
SYSTEM_GOVERNANCE_GATES={
    'REVIEW_REQUIRED':{'enabled':True,'required_roles':['reviewer'],'required_evidence':True,'required_all_tasks_done':False,'applies_to':'DONE'},
    'DELIVERY_EVIDENCE':{'enabled':True,'required_roles':['owner','manager','reviewer'],'required_evidence':True,'required_all_tasks_done':True,'applies_to':'DONE'}
}
def project_role(c,pid,actor_value):
    row=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,actor_value['id'])).fetchone()
    return row['role'] if row else None
def project_workflow_config(c,pid):
    row=c.execute('SELECT config FROM project_workflows WHERE project_id=?',(pid,)).fetchone()
    return json.loads(row['config']) if row else DEFAULT_PROJECT_WORKFLOW
def project_gate_config(c,pid,gate_key):
    if gate_key in SYSTEM_GOVERNANCE_GATES: return SYSTEM_GOVERNANCE_GATES[gate_key]
    row=c.execute('SELECT config FROM project_gates WHERE project_id=? AND gate_key=?',(pid,gate_key)).fetchone()
    return json.loads(row['config']) if row else None
def enforce_project_gate(c,pid,gate_key,actor_member_id,task_id=None,target_stage='DONE'):
    cfg=project_gate_config(c,pid,gate_key)
    if not cfg or not cfg.get('enabled',True) or cfg.get('applies_to','DONE')!=target_stage: return
    if cfg.get('required_roles'):
        platform=c.execute('SELECT role FROM members WHERE id=?',(actor_member_id,)).fetchone()
        if not platform or platform['role']!='admin':
            member_role=project_role(c,pid,{'id':actor_member_id})
            function_row=c.execute('SELECT work_function FROM project_members WHERE project_id=? AND member_id=?',(pid,actor_member_id)).fetchone()
            work_function=function_row['work_function'] if function_row else None
            if member_role not in cfg['required_roles'] and work_function not in cfg['required_roles']:
                raise HTTPException(403,f'Gate {gate_key} requires one of: {", ".join(cfg["required_roles"])}')
    if task_id and cfg.get('required_evidence'):
        if c.execute('SELECT 1 FROM artifacts WHERE task_id=? LIMIT 1',(task_id,)).fetchone() is None:
            raise HTTPException(409,detail={'message':f'Gate {gate_key} requires delivery evidence','gate_key':gate_key,'task_id':task_id})
    if task_id and cfg.get('required_all_tasks_done'):
        row=c.execute('SELECT requirement_id FROM tasks WHERE id=?',(task_id,)).fetchone()
        if row:
            pending=c.execute("SELECT id FROM tasks WHERE requirement_id=? AND status!='DONE' AND id!=?",(row['requirement_id'],task_id)).fetchall()
            if pending: raise HTTPException(409,detail={'message':f'Gate {gate_key} requires all other requirement tasks to be DONE before this task closes','gate_key':gate_key,'pending_task_ids':[x['id'] for x in pending]})
def enforce_workflow_exit(c,pid,current_stage,actor_member_id):
    cfg=project_workflow_config(c,pid)
    stage=next((x for x in cfg.get('stages',[]) if x.get('key')==current_stage),None)
    if not stage: raise HTTPException(409,detail={'message':'Current task status is not part of the configured workflow','current_stage':current_stage})
    approval_role=stage.get('approval_role','none')
    if approval_role!='none':
        platform=c.execute('SELECT role FROM members WHERE id=?',(actor_member_id,)).fetchone()
        if not platform or platform['role']!='admin':
            role=project_role(c,pid,{'id':actor_member_id})
            if role!=approval_role: raise HTTPException(403,f'Leaving workflow stage {current_stage} requires {approval_role} role')
def enforce_workflow_stage(c,pid,stage_key,actor_member_id,task_id=None):
    cfg=project_workflow_config(c,pid)
    stage=next((x for x in cfg.get('stages',[]) if x.get('key')==stage_key),None)
    if not stage: raise HTTPException(409,detail={'message':'Target workflow stage is not configured','stage_key':stage_key})
    for gate_key in [x['gate_key'] for x in c.execute('SELECT gate_key FROM project_gates WHERE project_id=?',(pid,)).fetchall()]:
        enforce_project_gate(c,pid,gate_key,actor_member_id,task_id,stage_key)
def transition_task_workflow(c,tid,target_stage,actor_member_id,comment=''):
    pid=task_project(c,tid)
    if not pid: raise HTTPException(404,'Task not found')
    task=c.execute('SELECT status,progress FROM tasks WHERE id=?',(tid,)).fetchone()
    if not task: raise HTTPException(404,'Task not found')
    enforce_workflow_stage(c,pid,target_stage,actor_member_id,tid)
    progress=100 if target_stage=='DONE' else (100 if target_stage=='REVIEW' else task['progress'])
    c.execute('UPDATE tasks SET status=?,progress=?,updated_at=? WHERE id=?',(target_stage,progress,now(),tid))
    eid=event(c,'task.workflow.transitioned',actor_member_id,tid,{'from_status':task['status'],'to_status':target_stage,'comment':comment})
    return eid

@app.get('/api/v1/projects/{pid}/audit')
def project_audit(pid:str,limit:int=100,before:str='',event_type:str='',authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,500))
    with conn() as c:
        require_project_access(c,pid,a)
        sql="SELECT e.* FROM events e LEFT JOIN tasks t ON t.id=e.task_id LEFT JOIN requirements r ON r.id=t.requirement_id WHERE (r.project_id=? OR (e.task_id IS NULL AND e.payload LIKE ?))"
        args=[pid,'%\"project_id\"%\"'+pid+'\"%']
        if before: sql+=" AND e.created_at<?"; args.append(before)
        if event_type: sql+=" AND e.event_type=?"; args.append(event_type)
        sql+=" ORDER BY e.created_at DESC LIMIT ?"; args.append(limit)
        rows=c.execute(sql,args).fetchall()
        return {'project_id':pid,'items':[{'id':x['id'],'event_type':x['event_type'],'actor_member_id':x['actor_member_id'],'task_id':x['task_id'],'payload':json.loads(x['payload'] or '{}'),'created_at':x['created_at']} for x in rows]}

@app.get('/api/v1/projects/{pid}/audit.csv')
def export_project_audit(pid:str,limit:int=5000,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,10000))
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT e.id,e.event_type,e.actor_member_id,e.task_id,e.payload,e.created_at
            FROM events e LEFT JOIN tasks t ON t.id=e.task_id LEFT JOIN requirements r ON r.id=t.requirement_id
            WHERE (r.project_id=? OR (e.task_id IS NULL AND e.payload LIKE ?)) ORDER BY e.created_at DESC LIMIT ?""",(pid,'%\"project_id\"%\"'+pid+'\"%',limit)).fetchall()
        def q(v): return '"'+str(v if v is not None else '').replace('"','""')+'"'
        lines=['id,event_type,actor_member_id,task_id,created_at,payload']
        for x in rows: lines.append(','.join(q(v) for v in (x['id'],x['event_type'],x['actor_member_id'],x['task_id'],x['created_at'],x['payload'])))
        return Response(content='\n'.join(lines)+'\n',media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="daep-audit-{pid}.csv"'})

@app.get('/api/v1/projects/{pid}/requirements')
def project_requirements(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        return [dict(x) for x in c.execute('SELECT * FROM requirements WHERE project_id=? ORDER BY created_at DESC',(pid,))]
@app.get('/api/v1/projects/{pid}/tasks')
def project_tasks(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute('SELECT t.* FROM tasks t JOIN requirements r ON r.id=t.requirement_id WHERE r.project_id=? ORDER BY t.created_at DESC',(pid,)).fetchall()
        result=[]
        for raw in rows:
            item=dict(raw)
            item['dependencies']=[x['depends_on_task_id'] for x in c.execute('SELECT depends_on_task_id FROM dependencies WHERE task_id=?',(item['id'],))]
            result.append(item)
        return result
@app.post('/api/v1/requirements')
def create_requirement(b:RequirementIn,authorization:str=Header(None)):
    a=actor(authorization); rid='req_'+uuid.uuid4().hex[:12]
    with conn() as c:
        if not c.execute('SELECT 1 FROM projects WHERE id=?',(b.project_id,)).fetchone(): raise HTTPException(404,'Project not found')
        require_project_access(c,b.project_id,a,write=True)
        c.execute('INSERT INTO requirements VALUES(?,?,?,?,?,?,?)',(rid,b.project_id,b.title,b.description,json.dumps(b.acceptance_criteria),'OPEN',now()))
    return {'id':rid,'project_id':b.project_id,'title':b.title,'status':'OPEN'}
@app.get('/api/v1/requirements/{rid}')
def get_requirement(rid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        r=c.execute('SELECT * FROM requirements WHERE id=?',(rid,)).fetchone()
        if r: require_project_access(c,r['project_id'],a)
        if not r: raise HTTPException(404,'Requirement not found')
        d=dict(r); d['acceptance_criteria']=json.loads(d['acceptance_criteria']); return d
@app.post('/api/v1/tasks')
def create_task(b:TaskIn,authorization:str=Header(None)):
    a=actor(authorization); tid='tsk_'+uuid.uuid4().hex[:12]
    with conn() as c:
        req=c.execute('SELECT * FROM requirements WHERE id=?',(b.requirement_id,)).fetchone()
        if not req: raise HTTPException(404,'Requirement not found')
        require_project_access(c,req['project_id'],a,write=True)
        for dep in b.dependencies:
            if dep == tid: raise HTTPException(400,'A task cannot depend on itself')
            if not c.execute('SELECT 1 FROM tasks WHERE id=?',(dep,)).fetchone(): raise HTTPException(400,f'Unknown dependency {dep}')
            require_task_access(c,dep,a)
            if task_project(c,dep) != req['project_id']: raise HTTPException(400,'Dependencies must belong to the same project')
        c.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?)',(tid,b.requirement_id,b.title,b.description,'READY',0,now(),now()))
        for mid in b.assignee_member_ids:
            member_row=c.execute('SELECT tenant_id FROM members WHERE id=?',(mid,)).fetchone()
            if not member_row: raise HTTPException(400,f'Unknown member {mid}')
            project_tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(req['project_id'],)).fetchone()['tenant_id']
            if member_row['tenant_id'] != project_tenant: raise HTTPException(400,'Assignee belongs to a different tenant')
            c.execute('INSERT INTO assignments VALUES(?,?)',(tid,mid))
            c.execute("INSERT OR IGNORE INTO project_members(project_id,member_id,role,work_function,joined_at) VALUES(?,?,?,'other',?)",(req['project_id'],mid,'member',now()))
        for dep in b.dependencies: c.execute('INSERT INTO dependencies VALUES(?,?)',(tid,dep))
        event(c,'task.created',a['id'],tid,{'title':b.title})
    return task_detail(tid,authorization)
def task_detail(tid,authorization):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a)
        r=c.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone()
        if not r: raise HTTPException(404,'Task not found')
        d=dict(r); d['assignees']=[dict(x) for x in c.execute('SELECT m.id,m.name FROM assignments a JOIN members m ON m.id=a.member_id JOIN tasks t ON t.id=a.task_id JOIN requirements rq ON rq.id=t.requirement_id JOIN projects p ON p.id=rq.project_id WHERE a.task_id=? AND m.tenant_id=p.tenant_id',(tid,))]; d['dependencies']=[x['depends_on_task_id'] for x in c.execute('SELECT depends_on_task_id FROM dependencies WHERE task_id=?',(tid,))]; return d
@app.get('/api/v1/tasks/{tid}')
def get_task(tid:str,authorization:str=Header(None)): return task_detail(tid,authorization)
@app.put('/api/v1/tasks/{tid}/dependencies')
def update_task_dependencies(tid:str,b:TaskDependenciesIn,authorization:str=Header(None)):
    a=actor(authorization)
    if len(set(b.dependencies)) != len(b.dependencies): raise HTTPException(400,'Duplicate dependencies are not allowed')
    with conn() as c:
        require_task_access(c,tid,a)
        project_id=task_project(c,tid)
        require_project_access(c,project_id,a,write=True)
        for dep in b.dependencies:
            if dep == tid: raise HTTPException(400,'A task cannot depend on itself')
            if task_project(c,dep) != project_id: raise HTTPException(400,'Dependencies must belong to the same project')
            require_task_access(c,dep,a)
            pending=[dep]; visited=set()
            while pending:
                current=pending.pop()
                if current == tid: raise HTTPException(409,'Dependency would create a cycle')
                if current in visited: continue
                visited.add(current)
                pending.extend(x['depends_on_task_id'] for x in c.execute('SELECT depends_on_task_id FROM dependencies WHERE task_id=?',(current,)).fetchall())
        c.execute('DELETE FROM dependencies WHERE task_id=?',(tid,))
        for dep in b.dependencies: c.execute('INSERT INTO dependencies(task_id,depends_on_task_id) VALUES(?,?)',(tid,dep))
        event(c,'task.dependencies.updated',a['id'],tid,{'dependencies':b.dependencies})
    return task_detail(tid,authorization)

@app.get('/api/v1/me/tasks')
def my_tasks(authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c: return [dict(x) for x in c.execute('SELECT t.* FROM tasks t JOIN assignments s ON s.task_id=t.id JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE s.member_id=? AND p.tenant_id=? ORDER BY t.created_at DESC',(a['id'],a.get('tenant_id','tenant-default')))]
@app.post('/api/v1/tasks/{tid}/progress')
def progress(tid:str,b:ProgressIn,authorization:str=Header(None),idempotency_key:str=Header(None)):
    a=actor(authorization)
    if a.get('actor_type')=='AGENT' and b.progress>=100:
        raise HTTPException(409,'Agent must submit delivery evidence and report work result; a human reviewer closes the task')
    with conn() as c:
        require_task_access(c,tid,a,assigned_only=True)
        if b.progress==100:
            enforce_task_review_request(c,tid,a)
        identity=a.get('agent_id') if a.get('actor_type')=='AGENT' else a['id']
        scoped_key=f"{identity}:{tid}:{idempotency_key}" if idempotency_key else None
        if scoped_key:
            prior=c.execute('SELECT id,payload FROM events WHERE idempotency_key=?',(scoped_key,)).fetchone()
            if prior:
                prior_payload=json.loads(prior['payload'] or '{}')
                prior_payload.pop('actor_type',None); prior_payload.pop('agent_id',None)
                if prior_payload != b.model_dump(): raise HTTPException(409,'Idempotency-Key was already used with a different payload')
                return {'event_id':prior['id'],'task_id':tid,'progress':b.progress,'idempotent_replay':True}
        c.execute('UPDATE tasks SET progress=?,status=?,updated_at=? WHERE id=?',(b.progress,'REVIEW' if b.progress==100 else ('IN_PROGRESS' if b.progress>0 else 'READY'),now(),tid))
        eid=event(c,'task.progress.updated',a['id'],tid,b.model_dump(),scoped_key)
    return {'event_id':eid,'task_id':tid,'progress':b.progress}
@app.post('/api/v1/tasks/{tid}/blocked')
def blocked(tid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a,assigned_only=True)
        c.execute("UPDATE tasks SET status='BLOCKED',updated_at=? WHERE id=?",(now(),tid)); eid=event(c,'task.blocked',a['id'],tid,b)
    return {'event_id':eid,'status':'BLOCKED'}
@app.post('/api/v1/tasks/{tid}/work-result')
def report_work_result(tid:str,b:WorkResultIn,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        begin_serialized_write(c)
        require_task_access(c,tid,a,assigned_only=True)
        package_sql='SELECT id,parent_task_id,status,correlation_id FROM task_work_packages WHERE child_task_id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): package_sql += ' FOR UPDATE'
        package=c.execute(package_sql,(tid,)).fetchone()
        if not package: raise HTTPException(404,'Task is not a registered work package')
        identity=a.get('agent_id') if a.get('actor_type')=='AGENT' else a['id']
        key=f"work-result:{identity}:{tid}:{b.idempotency_key}" if b.idempotency_key else None
        payload={'outcome':b.outcome,'summary':b.summary,'work_package_id':package['id'],'correlation_id':package['correlation_id'],'parent_task_id':package['parent_task_id']}
        if key:
            prior=c.execute('SELECT id,payload FROM events WHERE idempotency_key=?',(key,)).fetchone()
            if prior:
                prior_payload=json.loads(prior['payload'] or '{}')
                prior_payload.pop('actor_type',None); prior_payload.pop('agent_id',None)
                if prior_payload!=payload: raise HTTPException(409,'Idempotency key was used with a different result')
                return {'task_id':tid,'status':'REVIEW' if b.outcome=='COMPLETE' else 'BLOCKED','event_id':prior['id'],'idempotent_replay':True}
        if package['status']!='ACTIVE': raise HTTPException(409,'Work package is no longer active')
        if b.outcome=='COMPLETE':
            count=c.execute('SELECT COUNT(*) AS n FROM artifacts WHERE task_id=?',(tid,)).fetchone()['n']
            if count<1: raise HTTPException(409,'Submit at least one artifact before reporting completion')
            status='REVIEW'; progress=100
        else:
            status='BLOCKED'; progress=0
        c.execute('UPDATE tasks SET status=?,progress=?,updated_at=? WHERE id=?',(status,progress,now(),tid))
        eid=event(c,'task.work_package.reported',a['id'],tid,payload,key)
    return {'task_id':tid,'status':status,'event_id':eid,'outcome':b.outcome}


@app.post('/api/v1/tasks/{tid}/workflow-transition')
def transition_task_workflow_endpoint(tid:str,b:dict,authorization:str=Header(None),idempotency_key:str=Header(None)):
    a=actor(authorization); target=str(b.get('target_stage','')).strip().upper(); comment=str(b.get('comment',''))[:4000]
    if not target: raise HTTPException(422,'target_stage is required')
    if target=='BLOCKED': raise HTTPException(409,'BLOCKED is controlled by the task blocked endpoint')
    with conn() as c:
        pid=task_project(c,tid)
        if not pid: raise HTTPException(404,'Task not found')
        cfg=project_workflow_config(c,pid)
        stage=next((x for x in cfg.get('stages',[]) if x.get('key')==target),None)
        if not stage: raise HTTPException(409,'Target workflow stage is not configured')
        current=c.execute('SELECT status FROM tasks WHERE id=?',(tid,)).fetchone()['status']
        if is_admin(a): pass
        elif current in ('REVIEW','DONE') or target in ('DONE',):
            require_project_access(c,pid,a,write=True)
        else:
            require_task_access(c,tid,a,assigned_only=True)
        scoped_key=f'workflow:{a["id"]}:{tid}:{idempotency_key}' if idempotency_key else None
        if scoped_key:
            prior=c.execute('SELECT id,payload FROM events WHERE idempotency_key=?',(scoped_key,)).fetchone()
            if prior:
                if prior['payload']!=json.dumps({'target_stage':target,'comment':comment}): raise HTTPException(409,'Idempotency-Key was already used with a different workflow transition')
                return {'task_id':tid,'target_stage':target,'event_id':prior['id'],'idempotent_replay':True}
        enforce_workflow_stage(c,pid,target,a['id'],tid)
        eid=transition_task_workflow(c,tid,target,a['id'],comment)
        if scoped_key:
            # The transition event itself is the idempotent record; attach a unique companion event only when needed.
            c.execute('UPDATE events SET idempotency_key=?,payload=? WHERE id=? AND idempotency_key IS NULL',(scoped_key,json.dumps({'target_stage':target,'comment':comment}),eid))
        return {'task_id':tid,'status':target,'event_id':eid}

@app.post('/api/v1/tasks/{tid}/artifacts')
def artifact(tid:str,b:ArtifactIn,authorization:str=Header(None)):
    a=actor(authorization); aid='art_'+uuid.uuid4().hex[:12]
    with conn() as c:
        require_task_access(c,tid,a,assigned_only=True)
        c.execute('INSERT INTO artifacts(id,task_id,artifact_type,uri,commit_sha,metadata,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',(aid,tid,b.artifact_type,b.uri,b.commit_sha,json.dumps(b.metadata),now(),c.execute('SELECT p.tenant_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE t.id=?',(tid,)).fetchone()['tenant_id'])); wp=c.execute('SELECT correlation_id,id FROM task_work_packages WHERE child_task_id=?',(tid,)).fetchone(); event(c,'artifact.submitted',a['id'],tid,{'artifact_id':aid,'uri':b.uri,'work_package_id':wp['id'] if wp else None,'correlation_id':wp['correlation_id'] if wp else None})
    return {'id':aid,'task_id':tid}
@app.post('/api/v1/tasks/{tid}/review')
def review_task(tid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization); decision=b.get('decision')
    if a.get('actor_type')=='AGENT': raise HTTPException(403,'Agent cannot review or approve tasks')
    if decision not in ('APPROVE','REJECT'): raise HTTPException(422,'decision must be APPROVE or REJECT')
    with conn() as c:
        begin_serialized_write(c)
        pid=task_project(c,tid)
        if not pid: raise HTTPException(404,'Task not found')
        if is_admin(a): pass
        else:
            row=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not row or row['role'] not in ('owner','manager','reviewer'): raise HTTPException(403,'Reviewer role required')
        task_sql='SELECT status FROM tasks WHERE id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): task_sql += ' FOR UPDATE'
        task=c.execute(task_sql,(tid,)).fetchone()
        if task['status']!='REVIEW': raise HTTPException(409,'Task is not awaiting review')
        if decision=='APPROVE':
            enforce_workflow_exit(c,pid,task['status'],a['id'])
            enforce_workflow_stage(c,pid,'DONE',a['id'],tid)
            packages=c.execute("SELECT w.child_task_id,t.status FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? AND w.status='ACTIVE'",(tid,)).fetchall()
            pending=[x['child_task_id'] for x in packages if x['status']!='DONE']
            missing=[x['child_task_id'] for x in packages if c.execute('SELECT 1 FROM artifacts WHERE task_id=? LIMIT 1',(x['child_task_id'],)).fetchone() is None]
            if pending or missing:
                raise HTTPException(409,detail={'message':'Parent task cannot be approved until every active work package is approved and has at least one artifact','pending_work_packages':pending,'missing_artifacts':missing})
        status='DONE' if decision=='APPROVE' else 'IN_PROGRESS'
        updated=c.execute('UPDATE tasks SET status=?,progress=?,updated_at=? WHERE id=? AND status=?',(status,100 if decision=='APPROVE' else 90,now(),tid,'REVIEW'))
        if updated.rowcount != 1: raise HTTPException(409,'Task is no longer awaiting review')
        eid=event(c,'task.reviewed',a['id'],tid,{'decision':decision,'comment':b.get('comment','')})
        return {'task_id':tid,'status':status,'event_id':eid}

@app.post('/api/v1/work-packages/{package_id}/review')
def review_work_package(package_id:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization)
    if a.get('actor_type')=='AGENT': raise HTTPException(403,'Agent cannot review or approve work packages')
    decision=str(b.get('decision','')).strip().upper()
    comment=str(b.get('comment',''))[:4000]
    if decision not in ('APPROVE','REJECT'): raise HTTPException(422,'decision must be APPROVE or REJECT')
    with conn() as c:
        begin_serialized_write(c)
        package_sql='SELECT w.*,t.status AS task_status,t.progress FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): package_sql += ' FOR UPDATE'
        package=c.execute(package_sql,(package_id,)).fetchone()
        if not package: raise HTTPException(404,'Work package not found')
        pid=package['project_id']
        if is_admin(a): pass
        else:
            row=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not row or row['role'] not in ('owner','manager','reviewer'): raise HTTPException(403,'Reviewer role required')
        if package['status']!='ACTIVE': raise HTTPException(409,'Work package is no longer active')
        if package['task_status']!='REVIEW': raise HTTPException(409,'Work package is not awaiting review')
        stamp=now()
        if decision=='APPROVE':
            enforce_workflow_exit(c,pid,package['task_status'],a['id'])
            enforce_workflow_stage(c,pid,'DONE',a['id'],package['child_task_id'])
            if c.execute('SELECT 1 FROM artifacts WHERE task_id=? LIMIT 1',(package['child_task_id'],)).fetchone() is None:
                raise HTTPException(409,'Work package must have at least one artifact before approval')
            status='DONE'; progress=100
        else:
            status='IN_PROGRESS'; progress=90
        updated=c.execute('UPDATE tasks SET status=?,progress=?,updated_at=? WHERE id=? AND status=?',(status,progress,stamp,package['child_task_id'],'REVIEW'))
        if updated.rowcount != 1: raise HTTPException(409,'Work package task is no longer awaiting review')
        eid=event(c,'task.work_package.reviewed',a['id'],package['child_task_id'],{'work_package_id':package_id,'parent_task_id':package['parent_task_id'],'decision':decision,'comment':comment})
        return {'work_package_id':package_id,'task_id':package['child_task_id'],'status':status,'progress':progress,'event_id':eid,'decision':decision}

@app.post('/api/v1/tasks/{parent_id}/work-packages')
def create_work_package(parent_id:str,b:WorkPackageIn,authorization:str=Header(None)):
    a=actor(authorization); child_id='tsk_'+uuid.uuid4().hex[:12]; package_id='wpk_'+uuid.uuid4().hex
    agent_name=b.agent_name.strip()
    if not agent_name: raise HTTPException(422,'agent_name must not be blank')
    with conn() as c:
        require_task_access(c,parent_id,a)
        project_id=task_project(c,parent_id)
        require_project_access(c,project_id,a,write=True)
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(project_id,)).fetchone()
        member=c.execute('SELECT tenant_id FROM members WHERE id=?',(b.assignee_member_id,)).fetchone()
        if not member or member['tenant_id']!=project['tenant_id']: raise HTTPException(404,'Assignee not found in this tenant')
        if not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(project_id,b.assignee_member_id)).fetchone(): raise HTTPException(400,'Assignee is not a project member')
        agent=c.execute('SELECT status,last_seen FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(project_id,b.assignee_member_id,agent_name)).fetchone()
        if not agent: raise HTTPException(404,'Assignee Agent is not registered in this project')
        if agent['status']=='OFFLINE' or agent['last_seen'] < datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat(): raise HTTPException(409,'Assignee Agent presence is offline or stale')
        for dep in b.dependencies:
            if dep==parent_id or not c.execute('SELECT 1 FROM tasks WHERE id=?',(dep,)).fetchone(): raise HTTPException(400,'Invalid dependency')
            require_task_access(c,dep,a)
            if task_project(c,dep)!=project_id: raise HTTPException(400,'Dependencies must belong to the same project')
        req=c.execute('SELECT r.id FROM tasks t JOIN requirements r ON r.id=t.requirement_id WHERE t.id=?',(parent_id,)).fetchone()
        if not req: raise HTTPException(409,'Create a requirement before adding work packages')
        stamp=now()
        c.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?)',(child_id,req['id'],b.title,b.description,'READY',0,stamp,stamp))
        c.execute('INSERT INTO assignments(task_id,member_id) VALUES(?,?)',(child_id,b.assignee_member_id))
        for dep in b.dependencies: c.execute('INSERT INTO dependencies(task_id,depends_on_task_id) VALUES(?,?)',(child_id,dep))
        correlation_id='corr_'+uuid.uuid4().hex
        sla_due_at=datetime.fromtimestamp(datetime.fromisoformat(stamp).timestamp()+b.sla_seconds,timezone.utc).isoformat() if b.sla_seconds else None
        c.execute('INSERT INTO task_work_packages(id,parent_task_id,child_task_id,project_id,tenant_id,assignee_member_id,agent_name,status,created_at,updated_at,correlation_id,sla_due_at,risk_state) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(package_id,parent_id,child_id,project_id,project['tenant_id'],b.assignee_member_id,agent_name,'ACTIVE',stamp,stamp,correlation_id,sla_due_at,'ON_TRACK'))
        mid='msg_'+uuid.uuid4().hex[:12]
        title='Work package assigned: '+b.title
        content=json.dumps({'work_package_id':package_id,'correlation_id':correlation_id,'parent_task_id':parent_id,'task_id':child_id,'agent_name':agent_name,'title':b.title,'sla_due_at':sla_due_at},ensure_ascii=False)
        c.execute('INSERT INTO messages(id,recipient_member_id,tenant_id,task_id,message_type,title,content,priority,status,created_at,acked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(mid,b.assignee_member_id,project['tenant_id'],child_id,'WORK_PACKAGE_ASSIGNED',title,content,'HIGH','PENDING',stamp,None))
        payload={'message_id':mid,'recipient_member_id':b.assignee_member_id,'project_id':project_id,'task_id':child_id,'message_type':'WORK_PACKAGE_ASSIGNED','title':title,'content':content,'priority':'HIGH'}
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',('obx_'+uuid.uuid4().hex,'message.created',json.dumps(payload),'PENDING',0,stamp,stamp,project['tenant_id']))
        event(c,'task.work_package.created',a['id'],parent_id,{'work_package_id':package_id,'correlation_id':correlation_id,'child_task_id':child_id,'assignee_member_id':b.assignee_member_id,'agent_name':agent_name,'sla_due_at':sla_due_at,'sla_seconds':b.sla_seconds})
    return {'id':package_id,'correlation_id':correlation_id,'parent_task_id':parent_id,'task_id':child_id,'assignee_member_id':b.assignee_member_id,'agent_name':agent_name,'status':'ACTIVE','sla_due_at':sla_due_at,'risk_state':'ON_TRACK','message_id':mid}

@app.get('/api/v1/tasks/{parent_id}/work-packages')
def list_work_packages(parent_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,parent_id,a)
        rows=c.execute('SELECT w.*,t.title,t.description,t.status AS task_status,t.progress,t.updated_at AS task_updated_at FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? ORDER BY w.created_at',(parent_id,)).fetchall()
        result=[]
        for raw in rows:
            row=dict(raw)
            row['artifacts']=[dict(x) for x in c.execute('SELECT id,artifact_type,uri,commit_sha,created_at FROM artifacts WHERE task_id=? ORDER BY created_at',(row['child_task_id'],))]
            result.append(row)
        return result

@app.get('/api/v1/tasks/{parent_id}/work-summary')
def work_package_summary(parent_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,parent_id,a)
        rows=c.execute("SELECT t.status,t.progress FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? AND w.status='ACTIVE'",(parent_id,)).fetchall()
        total=len(rows)
        counts={k:sum(1 for x in rows if x['status']==k) for k in ('READY','IN_PROGRESS','BLOCKED','REVIEW','DONE')}
        progress=round(sum(int(x['progress'] or 0) for x in rows)/total) if total else 0
        artifacts=c.execute('SELECT COUNT(*) AS n FROM artifacts a JOIN task_work_packages w ON w.child_task_id=a.task_id WHERE w.parent_task_id=? AND w.status=\'ACTIVE\'',(parent_id,)).fetchone()['n']
        blocked=c.execute("SELECT t.id,t.title,t.status FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? AND w.status='ACTIVE' AND t.status='BLOCKED'",(parent_id,)).fetchall()
        artifact_rows=c.execute('SELECT w.child_task_id,a.id,a.artifact_type,a.uri,a.commit_sha,a.created_at FROM task_work_packages w JOIN artifacts a ON a.task_id=w.child_task_id WHERE w.parent_task_id=? AND w.status=\'ACTIVE\' ORDER BY a.created_at',(parent_id,)).fetchall()
        return {'parent_task_id':parent_id,'work_package_count':total,'progress':progress,'status_counts':counts,'blocked_tasks':[dict(x) for x in blocked],'artifact_count':artifacts,'artifacts':[dict(x) for x in artifact_rows],'all_done':bool(total and counts['DONE']==total)}

@app.get('/api/v1/tasks/{parent_id}/work-timeline')
def work_package_timeline(parent_id:str,limit:int=200,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,500))
    with conn() as c:
        require_task_access(c,parent_id,a)
        packages=c.execute('SELECT w.*,t.title,t.status AS task_status,t.progress FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? ORDER BY w.created_at',(parent_id,)).fetchall()
        items=[]
        task_ids=[parent_id]+[w['child_task_id'] for w in packages]
        for e in c.execute("""SELECT e.*,m.name AS actor_name FROM events e
            LEFT JOIN members m ON m.id=e.actor_member_id WHERE e.task_id=? ORDER BY e.created_at""",(parent_id,)).fetchall():
            p=json.loads(e['payload'] or '{}')
            items.append({'occurred_at':e['created_at'],'kind':'event','event_type':e['event_type'],
                'task_id':parent_id,'event_id':e['id'],'actor_member_id':e['actor_member_id'],
                'actor_name':e['actor_name'],'payload':p})
        for w in packages:
            cid=w['correlation_id'] or w['id']; child=w['child_task_id']
            for e in c.execute("""SELECT e.*,m.name AS actor_name FROM events e
                LEFT JOIN members m ON m.id=e.actor_member_id WHERE e.task_id=? ORDER BY e.created_at""",(child,)).fetchall():
                p=json.loads(e['payload'] or '{}')
                items.append({'occurred_at':e['created_at'],'kind':'event','event_type':e['event_type'],
                    'task_id':child,'event_id':e['id'],'actor_member_id':e['actor_member_id'],
                    'actor_name':e['actor_name'],'correlation_id':cid,'payload':p})
            for msg in c.execute('SELECT id,message_type,title,status,created_at,acked_at,content FROM messages WHERE task_id=? ORDER BY created_at',(child,)).fetchall():
                try: body=json.loads(msg['content'] or '{}')
                except Exception: body={'content':msg['content']}
                items.append({'occurred_at':msg['created_at'],'kind':'message','message_id':msg['id'],
                    'message_type':msg['message_type'],'title':msg['title'],'status':msg['status'],
                    'acked_at':msg['acked_at'],'task_id':child,'correlation_id':body.get('correlation_id',cid),'payload':body})
            for art in c.execute('SELECT id,artifact_type,uri,commit_sha,created_at FROM artifacts WHERE task_id=? ORDER BY created_at',(child,)).fetchall():
                items.append({'occurred_at':art['created_at'],'kind':'artifact','task_id':child,'correlation_id':cid,'artifact':dict(art)})
        marks=','.join('?' for _ in task_ids)
        delegations=c.execute(f"""SELECT d.*,rq.name AS requester_name,rc.name AS recipient_name
            FROM task_delegations d JOIN members rq ON rq.id=d.requester_member_id
            JOIN members rc ON rc.id=d.recipient_member_id
            WHERE d.task_id IN ({marks}) ORDER BY d.created_at""",tuple(task_ids)).fetchall()
        for d in delegations:
            row=dict(d)
            items.append({'occurred_at':row['created_at'],'kind':'delegation','stage':'OFFERED',
                'task_id':row['task_id'],'delegation_id':row['id'],'status':row['status'],
                'requester_member_id':row['requester_member_id'],'requester_name':row['requester_name'],
                'recipient_member_id':row['recipient_member_id'],'recipient_name':row['recipient_name'],
                'agent_name':row['agent_name'],'reason':row['reason'],'expires_at':row['expires_at']})
            if row['status']!='PENDING':
                decision_at=row['responded_at'] or row['updated_at']
                items.append({'occurred_at':decision_at,'kind':'delegation','stage':row['status'],
                    'task_id':row['task_id'],'delegation_id':row['id'],'status':row['status'],
                    'requester_member_id':row['requester_member_id'],'requester_name':row['requester_name'],
                    'recipient_member_id':row['recipient_member_id'],'recipient_name':row['recipient_name'],
                    'agent_name':row['agent_name'],'reason':row['reason'],'expires_at':row['expires_at']})
        dependency_edges=[]
        for tid in task_ids:
            task=c.execute('SELECT title FROM tasks WHERE id=?',(tid,)).fetchone()
            for dep in c.execute("""SELECT d.depends_on_task_id,t.title AS depends_on_title,t.status AS depends_on_status
                FROM dependencies d JOIN tasks t ON t.id=d.depends_on_task_id WHERE d.task_id=?""",(tid,)).fetchall():
                dependency_edges.append({'task_id':tid,'task_title':task['title'] if task else tid,
                    'depends_on_task_id':dep['depends_on_task_id'],'depends_on_title':dep['depends_on_title'],
                    'depends_on_status':dep['depends_on_status'],'blocked':dep['depends_on_status']!='DONE'})
        items.sort(key=lambda x:(x['occurred_at'],x.get('event_id') or x.get('message_id') or x.get('delegation_id') or x.get('artifact',{}).get('id','')))
        items=items[-limit:]
        return {'parent_task_id':parent_id,'count':len(items),'items':items,
            'dependency_edges':dependency_edges,
            'delegations':[{'id':d['id'],'task_id':d['task_id'],'requester_member_id':d['requester_member_id'],
                'requester_name':d['requester_name'],'recipient_member_id':d['recipient_member_id'],
                'recipient_name':d['recipient_name'],'agent_name':d['agent_name'],'reason':d['reason'],
                'status':d['status'],'created_at':d['created_at'],'responded_at':d['responded_at'],
                'expires_at':d['expires_at']} for d in delegations],
            'work_packages':[{'id':w['id'],'correlation_id':w['correlation_id'] or w['id'],
                'child_task_id':w['child_task_id'],'title':w['title'],'status':w['task_status'],
                'progress':w['progress'],'assignee_member_id':w['assignee_member_id'],'agent_name':w['agent_name'],
                'sla_due_at':w['sla_due_at'],'risk_state':w['risk_state'],'needs_attention':bool(w['needs_attention'])}
                for w in packages]}
@app.post('/api/v1/projects/{pid}/work-packages/scan-health')
def scan_project_work_health(pid:str,authorization:str=Header(None)):
    a=actor(authorization); stamp=now()
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        rows=c.execute("""SELECT w.id,w.parent_task_id,w.child_task_id,w.correlation_id,w.sla_due_at,w.risk_state,w.needs_attention,
        t.title,t.status AS task_status FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id
        WHERE w.project_id=? AND w.status='ACTIVE' ORDER BY w.created_at""",(pid,)).fetchall()
        changed=[]; counts={'ON_TRACK':0,'OVERDUE':0,'BLOCKED_DEPENDENCY':0,'STALLED':0,'IN_REVIEW':0,'COMPLETED':0}
        for row in rows:
            blockers=c.execute("""SELECT d.depends_on_task_id,t.title,t.status FROM dependencies d
                JOIN tasks t ON t.id=d.depends_on_task_id WHERE d.task_id=? AND t.status!='DONE'""",(row['child_task_id'],)).fetchall()
            if row['task_status']=='DONE': risk='COMPLETED'
            elif row['task_status']=='REVIEW': risk='IN_REVIEW'
            elif blockers: risk='BLOCKED_DEPENDENCY'
            elif row['needs_attention']: risk='STALLED'
            elif row['sla_due_at'] and row['sla_due_at']<=stamp: risk='OVERDUE'
            else: risk='ON_TRACK'
            if risk!=row['risk_state']:
                c.execute('UPDATE task_work_packages SET risk_state=?,updated_at=? WHERE id=?',(risk,stamp,row['id']))
                detail={'work_package_id':row['id'],'correlation_id':row['correlation_id'],'child_task_id':row['child_task_id'],'previous_risk_state':row['risk_state'],'risk_state':risk,'sla_due_at':row['sla_due_at'],'blocking_dependencies':[dict(x) for x in blockers]}
                event(c,'task.work_package.risk_changed',a['id'],row['parent_task_id'],detail)
                changed.append(detail)
            counts[risk]=counts.get(risk,0)+1
        return {'project_id':pid,'scanned_count':len(rows),'changed_count':len(changed),'risk_counts':counts,'changes':changed}

@app.get('/api/v1/projects/{pid}/work-health')
def project_work_health(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT w.id,w.parent_task_id,w.child_task_id,w.correlation_id,w.assignee_member_id,w.agent_name,
            w.sla_due_at,w.risk_state,w.needs_attention,t.title,t.status AS task_status,t.progress,t.updated_at
            FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id
            WHERE w.project_id=? AND w.status='ACTIVE' ORDER BY w.created_at""",(pid,)).fetchall()
        counts={}
        items=[]
        for row in rows:
            risk=row['risk_state']; counts[risk]=counts.get(risk,0)+1
            blockers=c.execute("""SELECT d.depends_on_task_id,t.title,t.status FROM dependencies d
                JOIN tasks t ON t.id=d.depends_on_task_id WHERE d.task_id=? AND t.status!='DONE'""",(row['child_task_id'],)).fetchall()
            items.append({'work_package_id':row['id'],'parent_task_id':row['parent_task_id'],'child_task_id':row['child_task_id'],
                'correlation_id':row['correlation_id'],'title':row['title'],'task_status':row['task_status'],'progress':row['progress'],
                'assignee_member_id':row['assignee_member_id'],'agent_name':row['agent_name'],'sla_due_at':row['sla_due_at'],
                'risk_state':risk,'needs_attention':bool(row['needs_attention']),'blocking_dependencies':[dict(x) for x in blockers],
                'last_activity_at':row['updated_at']})
        total=len(items); at_risk=sum(counts.get(k,0) for k in ('OVERDUE','BLOCKED_DEPENDENCY','STALLED'))
        return {'project_id':pid,'work_package_count':total,'at_risk_count':at_risk,
            'health_score':round(100*(total-at_risk)/total) if total else 100,
            'risk_counts':counts,'items':items}

@app.get('/api/v1/projects/{pid}/coordination')
def project_coordination_center(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        packages=c.execute("""SELECT w.id AS work_package_id,w.parent_task_id,w.child_task_id,w.assignee_member_id,w.agent_name,
            w.sla_due_at,w.risk_state,w.needs_attention,w.stall_reason,w.stalled_at,t.title,t.status AS task_status,
            t.progress,t.updated_at,m.name AS assignee_name
            FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id
            LEFT JOIN members m ON m.id=w.assignee_member_id
            WHERE w.project_id=? AND w.status='ACTIVE'
            AND (w.needs_attention=1 OR w.risk_state IN ('OVERDUE','BLOCKED_DEPENDENCY','STALLED','IN_REVIEW'))
            ORDER BY CASE w.risk_state WHEN 'OVERDUE' THEN 0 WHEN 'STALLED' THEN 1 WHEN 'BLOCKED_DEPENDENCY' THEN 2 WHEN 'IN_REVIEW' THEN 3 ELSE 4 END,w.updated_at""",(pid,)).fetchall()
        package_items=[]
        for row in packages:
            blockers=c.execute("""SELECT d.depends_on_task_id,t.title,t.status FROM dependencies d
                JOIN tasks t ON t.id=d.depends_on_task_id WHERE d.task_id=? AND t.status!='DONE'""",(row['child_task_id'],)).fetchall()
            agent=c.execute('SELECT status,last_seen FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(pid,row['assignee_member_id'],row['agent_name'])).fetchone()
            package_items.append({**dict(row),'blocking_dependencies':[dict(x) for x in blockers],
                'agent_status':agent['status'] if agent else 'NOT_REGISTERED','agent_last_seen':agent['last_seen'] if agent else None})
        unclaimed=c.execute("""SELECT t.id AS task_id,t.title,t.status,t.progress,t.updated_at
            FROM tasks t JOIN requirements r ON r.id=t.requirement_id
            LEFT JOIN assignments a ON a.task_id=t.id
            WHERE r.project_id=? AND t.status!='DONE' AND a.task_id IS NULL
            AND NOT EXISTS (SELECT 1 FROM task_work_packages w WHERE w.child_task_id=t.id AND w.status='ACTIVE')
            ORDER BY t.updated_at""",(pid,)).fetchall()
        reviews=c.execute("""SELECT t.id AS task_id,t.title,t.progress,t.updated_at,
            (SELECT COUNT(*) FROM artifacts ar WHERE ar.task_id=t.id) AS artifact_count
            FROM tasks t JOIN requirements r ON r.id=t.requirement_id
            WHERE r.project_id=? AND t.status='REVIEW' ORDER BY t.updated_at""",(pid,)).fetchall()
        delegations=c.execute("""SELECT d.id,d.task_id,d.status,d.requester_member_id,d.recipient_member_id,
            d.agent_name,d.reason,d.created_at,d.expires_at,t.title AS task_title,
            rq.name AS requester_name,rc.name AS recipient_name
            FROM task_delegations d JOIN tasks t ON t.id=d.task_id
            JOIN members rq ON rq.id=d.requester_member_id JOIN members rc ON rc.id=d.recipient_member_id
            WHERE d.project_id=? AND d.status='PENDING' ORDER BY d.created_at""",(pid,)).fetchall()
        return {'project_id':pid,'exception_work_packages':[dict(x) for x in package_items],
            'unclaimed_tasks':[dict(x) for x in unclaimed],'pending_reviews':[dict(x) for x in reviews],
            'pending_delegations':[dict(x) for x in delegations],
            'counts':{'exception_work_packages':len(package_items),'unclaimed_tasks':len(unclaimed),
                'pending_reviews':len(reviews),'pending_delegations':len(delegations)}}

@app.post('/api/v1/projects/{pid}/work-packages/scan-stalled')
def scan_stalled_work_packages(pid:str,b:WorkPackageScanIn,authorization:str=Header(None)):
    a=actor(authorization)
    cutoff=datetime.fromtimestamp(time.time()-b.stale_after_seconds,timezone.utc).isoformat()
    stamp=now()
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        rows=c.execute("""SELECT w.id,w.parent_task_id,w.child_task_id,w.assignee_member_id,t.status,t.updated_at,t.title
        FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id
        WHERE w.project_id=? AND w.status='ACTIVE' AND w.needs_attention=0
        AND t.status IN ('READY','IN_PROGRESS','BLOCKED') AND t.updated_at<=?""",(pid,cutoff)).fetchall()
        marked=[]
        for row in rows:
            reason=f"No task activity for at least {b.stale_after_seconds} seconds"
            changed=c.execute('UPDATE task_work_packages SET needs_attention=1,stalled_at=?,stall_reason=?,updated_at=? WHERE id=? AND needs_attention=0',(stamp,reason,stamp,row['id']))
            if changed.rowcount:
                event(c,'task.work_package.stalled',a['id'],row['parent_task_id'],{'work_package_id':row['id'],'correlation_id':c.execute('SELECT correlation_id FROM task_work_packages WHERE id=?',(row['id'],)).fetchone()['correlation_id'],'child_task_id':row['child_task_id'],'assignee_member_id':row['assignee_member_id'],'stalled_at':stamp,'reason':reason})
                marked.append({'work_package_id':row['id'],'child_task_id':row['child_task_id'],'title':row['title'],'task_status':row['status'],'assignee_member_id':row['assignee_member_id'],'stalled_at':stamp,'reason':reason})
    return {'project_id':pid,'stale_after_seconds':b.stale_after_seconds,'marked_count':len(marked),'items':marked}

@app.post('/api/v1/work-packages/{package_id}/reassign')
def reassign_work_package(package_id:str,b:WorkPackageReassignIn,authorization:str=Header(None)):
    a=actor(authorization); agent_name=b.agent_name.strip()
    if not agent_name: raise HTTPException(422,'agent_name must not be blank')
    with conn() as c:
        begin_serialized_write(c)
        package_sql='SELECT * FROM task_work_packages WHERE id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): package_sql += ' FOR UPDATE'
        package=c.execute(package_sql,(package_id,)).fetchone()
        if not package: raise HTTPException(404,'Work package not found')
        require_project_access(c,package['project_id'],a,write=True)
        if package['status']!='ACTIVE': raise HTTPException(409,'Only active work packages can be reassigned')
        if not package['needs_attention']: raise HTTPException(409,'Work package must be marked stalled before reassignment')
        if package['assignee_member_id']==b.assignee_member_id and package['agent_name']==agent_name:
            raise HTTPException(400,'Choose a different assignee or Agent')
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(package['project_id'],)).fetchone()
        member=c.execute('SELECT tenant_id FROM members WHERE id=?',(b.assignee_member_id,)).fetchone()
        if not member or member['tenant_id']!=project['tenant_id']: raise HTTPException(404,'New assignee not found in this tenant')
        if not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(package['project_id'],b.assignee_member_id)).fetchone():
            raise HTTPException(400,'New assignee is not a project member')
        agent=c.execute('SELECT status,last_seen FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(package['project_id'],b.assignee_member_id,agent_name)).fetchone()
        cutoff=datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat()
        if not agent: raise HTTPException(404,'New assignee Agent is not registered in this project')
        if agent['status']=='OFFLINE' or agent['last_seen']<cutoff: raise HTTPException(409,'New assignee Agent presence is offline or stale')
        stamp=now()
        c.execute('DELETE FROM assignments WHERE task_id=? AND member_id=?',(package['child_task_id'],package['assignee_member_id']))
        c.execute('INSERT OR IGNORE INTO assignments(task_id,member_id) VALUES(?,?)',(package['child_task_id'],b.assignee_member_id))
        c.execute('UPDATE task_work_packages SET assignee_member_id=?,agent_name=?,needs_attention=0,stalled_at=NULL,stall_reason=NULL,updated_at=? WHERE id=?',(b.assignee_member_id,agent_name,stamp,package_id))
        c.execute('UPDATE tasks SET updated_at=? WHERE id=?',(stamp,package['child_task_id']))
        mid='msg_'+uuid.uuid4().hex[:12]
        title='Work package reassigned: '+package['child_task_id']
        content=json.dumps({'work_package_id':package_id,'correlation_id':package['correlation_id'],'parent_task_id':package['parent_task_id'],'task_id':package['child_task_id'],'previous_assignee_member_id':package['assignee_member_id'],'assignee_member_id':b.assignee_member_id,'agent_name':agent_name,'reason':b.reason},ensure_ascii=False)
        c.execute('INSERT INTO messages(id,recipient_member_id,tenant_id,task_id,message_type,title,content,priority,status,created_at,acked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(mid,b.assignee_member_id,project['tenant_id'],package['child_task_id'],'WORK_PACKAGE_REASSIGNED',title,content,'HIGH','PENDING',stamp,None))
        payload={'message_id':mid,'recipient_member_id':b.assignee_member_id,'project_id':package['project_id'],'task_id':package['child_task_id'],'message_type':'WORK_PACKAGE_REASSIGNED','title':title,'content':content,'priority':'HIGH'}
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',('obx_'+uuid.uuid4().hex,'message.created',json.dumps(payload),'PENDING',0,stamp,stamp,project['tenant_id']))
        eid=event(c,'task.work_package.reassigned',a['id'],package['parent_task_id'],{'work_package_id':package_id,'correlation_id':package['correlation_id'],'child_task_id':package['child_task_id'],'previous_assignee_member_id':package['assignee_member_id'],'assignee_member_id':b.assignee_member_id,'previous_agent_name':package['agent_name'],'agent_name':agent_name,'reason':b.reason})
    return {'work_package_id':package_id,'task_id':package['child_task_id'],'assignee_member_id':b.assignee_member_id,'agent_name':agent_name,'needs_attention':False,'message_id':mid,'event_id':eid}

@app.post('/api/v1/projects/{pid}/agents/register')
def register_project_agent(pid:str,b:AgentPresenceIn,authorization:str=Header(None)):
    a=actor(authorization)
    agent_name=b.agent_name.strip()
    if not agent_name: raise HTTPException(422,'agent_name must not be blank')
    clean_caps=sorted({str(x).strip().lower() for x in b.capabilities if str(x).strip()})
    clean_protocols=sorted({str(x).strip().lower() for x in b.protocols if str(x).strip()})
    if any(len(x)>80 for x in clean_caps) or any(len(x)>40 for x in clean_protocols):
        raise HTTPException(422,'Capability or protocol identifier is too long')
    if not clean_protocols: raise HTTPException(422,'At least one protocol is required')
    if len(json.dumps(b.metadata))>4000: raise HTTPException(422,'Agent metadata exceeds 4000 bytes')
    with conn() as c:
        require_project_access(c,pid,a)
        tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id']
        existing=c.execute('SELECT id,created_at FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(pid,a['id'],agent_name)).fetchone()
        aid=existing['id'] if existing else 'agt_'+uuid.uuid4().hex
        created=existing['created_at'] if existing else now()
        stamp=now()
        c.execute("""INSERT INTO project_agents(id,project_id,member_id,tenant_id,agent_name,capabilities,protocols,status,metadata,last_seen,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(project_id,member_id,agent_name) DO UPDATE SET capabilities=excluded.capabilities,protocols=excluded.protocols,status=excluded.status,metadata=excluded.metadata,last_seen=excluded.last_seen,updated_at=excluded.updated_at""",
        (aid,pid,a['id'],tenant,agent_name,json.dumps(clean_caps),json.dumps(clean_protocols),b.status,json.dumps(b.metadata),stamp,created,stamp))
        event(c,'agent.presence.updated',a['id'],None,{'project_id':pid,'agent_id':aid,'agent_name':agent_name,'status':b.status},tenant_override=tenant)
    return {'id':aid,'project_id':pid,'member_id':a['id'],'agent_name':b.agent_name.strip(),'status':b.status,'capabilities':clean_caps,'protocols':clean_protocols,'last_seen':stamp}

@app.post('/api/v1/projects/{pid}/agents/heartbeat')
def heartbeat_project_agent(pid:str,body:dict,authorization:str=Header(None)):
    a=actor(authorization); name=str(body.get('agent_name','')).strip()
    if not name or len(name)>120: raise HTTPException(422,'agent_name is required (max 120)')
    status=str(body.get('status','AVAILABLE')).upper()
    if status not in ('AVAILABLE','BUSY','OFFLINE'): raise HTTPException(422,'Invalid agent status')
    with conn() as c:
        require_project_access(c,pid,a)
        previous=c.execute('SELECT id,status FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(pid,a['id'],name)).fetchone()
        if not previous: raise HTTPException(404,'Agent registration not found; register the agent first')
        stamp=now()
        c.execute('UPDATE project_agents SET status=?,last_seen=?,updated_at=? WHERE id=?',(status,stamp,stamp,previous['id']))
        if previous['status'] != status:
            event(c,'agent.presence.changed',a['id'],None,{'project_id':pid,'agent_id':previous['id'],'status':status})
    return {'id':previous['id'],'status':status,'last_seen':stamp}

@app.get('/api/v1/projects/{pid}/agents')
def discover_project_agents(pid:str,authorization:str=Header(None),capability:str='',protocol:str=''):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("SELECT pa.*,m.name AS member_name FROM project_agents pa JOIN members m ON m.id=pa.member_id WHERE pa.project_id=? ORDER BY pa.agent_name,pa.member_id",(pid,)).fetchall()
        cutoff=datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat()
        items=[]
        for raw in rows:
            row=dict(raw)
            caps=json.loads(row['capabilities'] or '[]'); protocols=json.loads(row['protocols'] or '[]')
            live=row['status']!='OFFLINE' and row['last_seen']>=cutoff
            if capability and capability.lower() not in caps: continue
            if protocol and protocol.lower() not in protocols: continue
            items.append({'id':row['id'],'member_id':row['member_id'],'member_name':row['member_name'],'agent_name':row['agent_name'],'capabilities':caps,'protocols':protocols,'status':row['status'] if live else 'OFFLINE','last_seen':row['last_seen'],'metadata':json.loads(row['metadata'] or '{}')})
        return {'items':items,'count':len(items),'presence_ttl_seconds':120}

@app.get('/api/v1/projects/{pid}/agent-matches')
def recommend_project_agents(pid:str,required_capabilities:str='',protocol:str='mcp',authorization:str=Header(None)):
    """Rank project-local Agent registrations without assigning work or invoking a Runtime."""
    a=actor(authorization)
    requested=[x.strip().casefold() for x in required_capabilities.split(',') if x.strip()]
    if len(requested)>50 or any(len(x)>120 for x in requested):
        raise HTTPException(422,'At most 50 required capabilities are allowed; each must be at most 120 characters')
    requested=list(dict.fromkeys(requested))
    requested_protocol=protocol.strip().casefold()
    if not requested_protocol or len(requested_protocol)>40:
        raise HTTPException(422,'protocol must contain 1 to 40 characters')
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT pa.*,m.name AS member_name FROM project_agents pa
            JOIN members m ON m.id=pa.member_id WHERE pa.project_id=?""",(pid,)).fetchall()
        cutoff=datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat()
        items=[]
        for raw in rows:
            row=dict(raw)
            caps=sorted({str(x).strip().casefold() for x in json.loads(row['capabilities'] or '[]') if str(x).strip()})
            protocols=sorted({str(x).strip().casefold() for x in json.loads(row['protocols'] or '[]') if str(x).strip()})
            matched=[x for x in requested if x in caps]
            missing=[x for x in requested if x not in caps]
            live=row['status']!='OFFLINE' and row['last_seen']>=cutoff
            protocol_match=requested_protocol in protocols
            available=live and row['status']=='AVAILABLE'
            items.append({'id':row['id'],'member_id':row['member_id'],'member_name':row['member_name'],
                'agent_name':row['agent_name'],'capabilities':caps,'protocols':protocols,
                'presence_status':row['status'] if live else 'OFFLINE','last_seen':row['last_seen'],
                'matched_capabilities':matched,'missing_capabilities':missing,
                'match_count':len(matched),'required_count':len(requested),
                'protocol_match':protocol_match,'eligible':not missing and protocol_match and available,
                'availability_reason':('AVAILABLE' if available else ('BUSY' if live and row['status']=='BUSY' else 'OFFLINE_OR_STALE')),
                'match_score':round(100*len(matched)/len(requested)) if requested else (100 if protocol_match else 0)})
        items.sort(key=lambda x:(not x['eligible'],bool(x['missing_capabilities']),not x['protocol_match'],
            -x['match_count'],x['availability_reason']!='AVAILABLE',x['member_name'].casefold(),x['agent_name'].casefold()))
        return {'project_id':pid,'required_capabilities':requested,'protocol':requested_protocol,
            'items':items,'count':len(items),'eligible_count':sum(1 for x in items if x['eligible']),
            'recommendation_only':True,'runtime_controlled':False}

@app.post('/api/v1/tasks/{tid}/delegations')
def create_task_delegation(tid:str,b:DelegationIn,authorization:str=Header(None)):
    a=actor(authorization)
    if b.recipient_member_id == a['id']: raise HTTPException(400,'A task cannot be delegated to yourself')
    agent_name=b.agent_name.strip()
    if not agent_name: raise HTTPException(422,'agent_name must not be blank')
    did='dlg_'+uuid.uuid4().hex
    with conn() as c:
        require_task_access(c,tid,a,assigned_only=True)
        pid=task_project(c,tid)
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        recipient=c.execute('SELECT tenant_id FROM members WHERE id=?',(b.recipient_member_id,)).fetchone()
        if not recipient or recipient['tenant_id'] != project['tenant_id']: raise HTTPException(404,'Recipient not found in this tenant')
        if not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(pid,b.recipient_member_id)).fetchone(): raise HTTPException(400,'Recipient is not a project member')
        agent=c.execute("SELECT id,status,last_seen FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?",(pid,b.recipient_member_id,agent_name)).fetchone()
        if not agent: raise HTTPException(404,'Recipient Agent is not registered in this project')
        if agent['status']=='OFFLINE' or agent['last_seen'] < datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat():
            raise HTTPException(409,'Recipient Agent presence is offline or stale')
        stamp=now(); expiry=datetime.fromtimestamp(time.time()+b.expires_in_seconds,timezone.utc).isoformat()
        mid='msg_'+uuid.uuid4().hex[:12]
        title='Task delegation offer: '+tid
        content=json.dumps({'delegation_id':did,'task_id':tid,'agent_name':agent_name,'reason':b.reason,'expires_at':expiry},ensure_ascii=False)
        c.execute("INSERT INTO task_delegations(id,task_id,project_id,tenant_id,requester_member_id,recipient_member_id,agent_name,reason,status,message_id,expires_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(did,tid,pid,project['tenant_id'],a['id'],b.recipient_member_id,agent_name,b.reason,'PENDING',mid,expiry,stamp,stamp))
        c.execute("INSERT INTO messages(id,recipient_member_id,tenant_id,task_id,message_type,title,content,priority,status,created_at,acked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(mid,b.recipient_member_id,project['tenant_id'],tid,'TASK_DELEGATION',title,content,'HIGH','PENDING',stamp,None))
        payload={'message_id':mid,'recipient_member_id':b.recipient_member_id,'project_id':pid,'task_id':tid,'message_type':'TASK_DELEGATION','title':title,'content':content,'priority':'HIGH'}
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',('obx_'+uuid.uuid4().hex,'message.created',json.dumps(payload), 'PENDING',0,stamp,stamp,project['tenant_id']))
        event(c,'task.delegation.offered',a['id'],tid,{'delegation_id':did,'recipient_member_id':b.recipient_member_id,'agent_name':agent_name})
    return {'id':did,'task_id':tid,'recipient_member_id':b.recipient_member_id,'agent_name':agent_name,'status':'PENDING','expires_at':expiry,'message_id':mid}

@app.post('/api/v1/delegations/{did}/respond')
def respond_task_delegation(did:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization); decision=b.get('decision')
    if decision not in ('ACCEPT','REJECT'): raise HTTPException(422,'decision must be ACCEPT or REJECT')
    with conn() as c:
        begin_serialized_write(c)
        if DATABASE_URL.startswith(('postgresql://','postgres://')):
            row=c.execute('SELECT * FROM task_delegations WHERE id=? FOR UPDATE',(did,)).fetchone()
        else:
            row=c.execute('SELECT * FROM task_delegations WHERE id=?',(did,)).fetchone()
        if not row or row['recipient_member_id'] != a['id']: raise HTTPException(404,'Delegation not found')
        if row['status'] != 'PENDING': raise HTTPException(409,'Delegation is no longer pending')
        if row['expires_at'] <= now():
            stamp=now()
            cur=c.execute("UPDATE task_delegations SET status='EXPIRED',updated_at=? WHERE id=? AND status='PENDING'",(stamp,did))
            if cur.rowcount:
                event(c,'task.delegation.expired',a['id'],row['task_id'],{'delegation_id':did})
            return JSONResponse(status_code=410,content={'detail':'Delegation offer has expired','status':'EXPIRED'})
        if decision=='ACCEPT':
            c.execute('INSERT OR IGNORE INTO assignments(task_id,member_id) VALUES(?,?)',(row['task_id'],a['id']))
            c.execute('INSERT OR IGNORE INTO project_members(project_id,member_id,role,joined_at) VALUES(?,?,?,?)',(row['project_id'],a['id'],'member',now()))
            status='ACCEPTED'
        else: status='REJECTED'
        stamp=now()
        cur=c.execute('UPDATE task_delegations SET status=?,responded_at=?,updated_at=? WHERE id=? AND status=\'PENDING\'',(status,stamp,stamp,did))
        if cur.rowcount != 1:
            raise HTTPException(409,'Delegation response raced with another decision')
        event(c,'task.delegation.'+status.lower(),a['id'],row['task_id'],{'delegation_id':did,'agent_name':row['agent_name']})
        return {'id':did,'task_id':row['task_id'],'status':status,'responded_at':stamp}

@app.get('/api/v1/tasks/{tid}/delegations')
def list_task_delegations(tid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a)
        rows=c.execute('SELECT * FROM task_delegations WHERE task_id=? ORDER BY created_at DESC',(tid,)).fetchall()
        result=[]
        for raw in rows:
            row=dict(raw)
            if row['status']=='PENDING' and row['expires_at'] <= now():
                stamp=now()
                cur=c.execute("UPDATE task_delegations SET status='EXPIRED',updated_at=? WHERE id=? AND status='PENDING'",(stamp,row['id']))
                if cur.rowcount:
                    event(c,'task.delegation.expired',a['id'],tid,{'delegation_id':row['id']})
                row['status']='EXPIRED'
            result.append(row)
        return result

@app.get('/api/v1/projects/{pid}/delegations')
def project_delegations(pid:str,limit:int=100,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,500))
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT d.*,rq.name AS requester_name,rc.name AS recipient_name,t.title AS task_title
            FROM task_delegations d
            JOIN members rq ON rq.id=d.requester_member_id
            JOIN members rc ON rc.id=d.recipient_member_id
            JOIN tasks t ON t.id=d.task_id
            WHERE d.project_id=? ORDER BY d.created_at DESC LIMIT ?""",(pid,limit)).fetchall()
        items=[]
        for raw in rows:
            row=dict(raw)
            if row['status']=='PENDING' and row['expires_at'] <= now():
                stamp=now()
                cur=c.execute("UPDATE task_delegations SET status='EXPIRED',updated_at=? WHERE id=? AND status='PENDING'",(stamp,row['id']))
                if cur.rowcount:
                    event(c,'task.delegation.expired',a['id'],row['task_id'],{'delegation_id':row['id']})
                row['status']='EXPIRED'
            items.append(row)
        return {'project_id':pid,'count':len(items),'items':items}

@app.post('/api/v1/messages')
def send_message(b:MessageIn,authorization:str=Header(None)):
    a=actor(authorization); mid='msg_'+uuid.uuid4().hex[:12]
    with conn() as c:
        if not c.execute('SELECT 1 FROM members WHERE id=?',(b.recipient_member_id,)).fetchone(): raise HTTPException(404,'Recipient not found')
        if b.task_id:
            require_task_access(c,b.task_id,a)
            pid=task_project(c,b.task_id)
            if b.project_id and b.project_id != pid: raise HTTPException(400,'project_id does not match task')
        else: pid=b.project_id
        if not pid and not is_admin(a): raise HTTPException(400,'project_id is required for project-scoped messages')
        if pid:
            require_project_access(c,pid,a)
            recipient=c.execute('SELECT tenant_id FROM members WHERE id=?',(b.recipient_member_id,)).fetchone()
            project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
            if recipient and recipient['tenant_id'] != project['tenant_id']: raise HTTPException(400,'Recipient belongs to a different tenant')
            if not is_admin(a) and not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(pid,b.recipient_member_id)).fetchone(): raise HTTPException(400,'Recipient is not a project member')
        created=now()
        message_tenant=(c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id'] if pid else c.execute('SELECT tenant_id FROM members WHERE id=?',(b.recipient_member_id,)).fetchone()['tenant_id'])
        c.execute('INSERT INTO messages(id,recipient_member_id,tenant_id,task_id,message_type,title,content,priority,status,created_at,acked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(mid,b.recipient_member_id,message_tenant,b.task_id,b.message_type,b.title,b.content,b.priority,'PENDING',created,None))
        payload={'message_id':mid,'recipient_member_id':b.recipient_member_id,'project_id':pid,'task_id':b.task_id,'message_type':b.message_type,'title':b.title,'content':b.content,'priority':b.priority}
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',('obx_'+uuid.uuid4().hex,'message.created',json.dumps(payload),'PENDING',0,created,created,message_tenant))
        event(c,'message.created',a['id'],b.task_id,{'message_id':mid,'recipient':b.recipient_member_id},tenant_override=message_tenant)
    return {'id':mid,'status':'PENDING'}
@app.get('/api/v1/me/notifications')
def notifications(authorization:str=Header(None),after:int=0,limit:int=50):
    a=actor(authorization); limit=max(1,min(limit,100))
    with conn() as c:
        rows=[dict(x) for x in c.execute("SELECT * FROM messages WHERE recipient_member_id=? AND status='PENDING' AND seq>? ORDER BY seq LIMIT ?",(a['id'],after,limit))]
        for row in rows: c.execute('UPDATE messages SET attempts=attempts+1,last_attempt_at=? WHERE id=?',(now(),row['id']))
        return {'items':rows,'next_cursor':rows[-1]['seq'] if rows else after,'has_more':len(rows)==limit}
@app.post('/api/v1/messages/{mid}/ack')
def ack(mid:str,b:AckIn,authorization: str=Header(None)):
    a=actor(authorization)
    if b.status not in ('ACKNOWLEDGED','REJECTED'): raise HTTPException(422,'Invalid acknowledgement status')
    with conn() as c:
        existing=c.execute('SELECT status,task_id,tenant_id FROM messages WHERE id=? AND recipient_member_id=?',(mid,a['id'])).fetchone()
        if not existing: raise HTTPException(404,'Message not found for current member')
        if existing['status'] in ('ACKNOWLEDGED','REJECTED'):
            if existing['status'] != b.status: raise HTTPException(409,'Message has already reached a different terminal status')
            return {'id':mid,'status':existing['status'],'idempotent':True}
        stamp=now()
        cur=c.execute("UPDATE messages SET status=?,acked_at=? WHERE id=? AND recipient_member_id=? AND status='PENDING'",(b.status,stamp,mid,a['id']))
        if cur.rowcount==0: raise HTTPException(409,'Message status changed; retry the request')
        event(c,'message.acknowledged',a['id'],existing['task_id'],{'message_id':mid,'status':b.status},tenant_override=existing['tenant_id'])
    return {'id':mid,'status':b.status,'idempotent':False}
@app.get('/api/v1/tasks/{tid}/events')
def task_events(tid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a)
        return [dict(x) for x in c.execute('SELECT * FROM events WHERE task_id=? ORDER BY created_at',(tid,))]
@app.get('/api/v1/tasks/{tid}/artifacts')
def task_artifacts(tid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a)
        return [dict(x) for x in c.execute('SELECT * FROM artifacts WHERE task_id=? ORDER BY created_at',(tid,))]
@app.post('/internal/v1/outbox/claim')
def claim_outbox(body:dict,authorization:str=Header(None)):
    require_worker(authorization)
    worker=str(body.get('worker_id','')).strip()
    if not worker or len(worker)>120: raise HTTPException(422,'worker_id is required (max 120 chars)')
    limit=max(1,min(int(body.get('limit',20)),100)); lease_seconds=max(10,min(int(body.get('lease_seconds',60)),900))
    claimed=[]; timestamp=datetime.now(timezone.utc); stamp=timestamp.isoformat()
    with conn() as c:
        is_pg=DATABASE_URL.startswith(('postgresql://','postgres://'))
        if not is_pg: c.execute('BEGIN IMMEDIATE')
        query="SELECT * FROM outbox WHERE (status='PENDING' AND available_at<=?) OR (status='IN_FLIGHT' AND lease_until<=?) ORDER BY created_at LIMIT ?"
        if is_pg: query += " FOR UPDATE SKIP LOCKED"
        rows=c.execute(query,(stamp,stamp,limit)).fetchall()
        for row in rows:
            lease_until=datetime.fromtimestamp(timestamp.timestamp()+lease_seconds,timezone.utc).isoformat()
            lease_token=secrets.token_urlsafe(32)
            cur=c.execute("UPDATE outbox SET status='IN_FLIGHT',attempts=attempts+1,lease_until=?,lease_owner=?,lease_token=? WHERE id=? AND ((status='PENDING' AND available_at<=?) OR (status='IN_FLIGHT' AND lease_until<=?))",(lease_until,worker,lease_token,row['id'],stamp,stamp))
            if cur.rowcount:
                item=dict(row); item.update(status='IN_FLIGHT',attempts=row['attempts']+1,lease_until=lease_until,lease_owner=worker,lease_token=lease_token,payload=json.loads(row['payload']))
                claimed.append(item)
    return {'items':claimed,'count':len(claimed)}

@app.post('/internal/v1/outbox/{outbox_id}/complete')
def complete_outbox(outbox_id:str,body:dict,authorization:str=Header(None)):
    require_worker(authorization)
    worker=str(body.get('worker_id','')).strip(); lease_token=str(body.get('lease_token',''))
    if not worker or len(worker)>120 or len(lease_token)<32: raise HTTPException(422,'worker_id and lease_token are required')
    with conn() as c:
        stamp=now()
        cur=c.execute("UPDATE outbox SET status='SENT',sent_at=?,lease_until=NULL,lease_owner=NULL,lease_token=NULL,last_error=NULL WHERE id=? AND status='IN_FLIGHT' AND lease_owner=? AND lease_token=? AND lease_until>?",(stamp,outbox_id,worker,lease_token,stamp))
        if not cur.rowcount: raise HTTPException(409,'Outbox lease not owned by worker or item is not in flight')
    return {'id':outbox_id,'status':'SENT'}

@app.post('/internal/v1/outbox/{outbox_id}/fail')
def fail_outbox(outbox_id:str,body:dict,authorization:str=Header(None)):
    require_worker(authorization)
    worker=str(body.get('worker_id','')).strip(); lease_token=str(body.get('lease_token','')); error=str(body.get('error','Delivery failed'))[:2000]
    if not worker or len(worker)>120 or len(lease_token)<32: raise HTTPException(422,'worker_id and lease_token are required')
    with conn() as c:
        stamp=now()
        row=c.execute("SELECT attempts FROM outbox WHERE id=? AND status='IN_FLIGHT' AND lease_owner=? AND lease_token=? AND lease_until>?",(outbox_id,worker,lease_token,stamp)).fetchone()
        if not row: raise HTTPException(409,'Outbox lease not owned, expired, or item is not in flight')
        attempts=row['attempts']; terminal=attempts>=8
        delay=min(3600,5*(2**min(attempts-1,10)))
        available=datetime.fromtimestamp(datetime.now(timezone.utc).timestamp()+delay,timezone.utc).isoformat()
        cur=c.execute("UPDATE outbox SET status=?,available_at=?,lease_until=NULL,lease_owner=NULL,lease_token=NULL,last_error=? WHERE id=? AND status='IN_FLIGHT' AND lease_owner=? AND lease_token=? AND lease_until>?",('DEAD' if terminal else 'PENDING',available,error,outbox_id,worker,lease_token,stamp))
        if not cur.rowcount: raise HTTPException(409,'Outbox lease changed or expired during failure acknowledgement')
    return {'id':outbox_id,'status':'DEAD' if terminal else 'PENDING','retry_after_seconds':None if terminal else delay}

@app.get('/api/v1/admin/outbox/dead')
def list_dead_outbox(limit:int=50,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    limit=max(1,min(limit,200))
    with conn() as c:
        rows=c.execute("SELECT id,event_type,status,attempts,available_at,last_error,created_at,tenant_id FROM outbox WHERE status='DEAD' ORDER BY created_at LIMIT ?",(limit,)).fetchall()
        return {'items':[dict(x) for x in rows],'count':len(rows)}

@app.post('/api/v1/admin/messages/{message_id}/restore-outbox')
def restore_missing_message_outbox(message_id:str,body:dict,authorization:str=Header(None)):
    """Explicitly restore one missing message dispatch record; never duplicates an existing dispatch."""
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    reason=str(body.get('reason','')).strip()
    if not reason or len(reason)>1000: raise HTTPException(422,'A recovery reason (1-1000 characters) is required')
    with conn() as c:
        begin_serialized_write(c)
        query='SELECT * FROM messages WHERE id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): query += ' FOR UPDATE'
        message=c.execute(query,(message_id,)).fetchone()
        if not message: raise HTTPException(404,'Message not found')
        existing_rows=c.execute("SELECT id,payload FROM outbox WHERE event_type='message.created'").fetchall()
        matching=[]
        for item in existing_rows:
            try:
                if json.loads(item['payload']).get('message_id')==message_id: matching.append(item['id'])
            except (TypeError,ValueError):
                continue
        if matching:
            raise HTTPException(409,'A message.created outbox record already exists; refusing duplicate recovery')
        project_id=None
        if message['task_id']:
            project=c.execute('SELECT r.project_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id WHERE t.id=?',(message['task_id'],)).fetchone()
            if project: project_id=project['project_id']
        payload={'message_id':message_id,'recipient_member_id':message['recipient_member_id'],
                 'project_id':project_id,'task_id':message['task_id'],'message_type':message['message_type'],
                 'title':message['title'],'content':message['content'],'priority':message['priority']}
        stamp=now(); outbox_id='obx_'+uuid.uuid4().hex
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',
                  (outbox_id,'message.created',json.dumps(payload),'PENDING',0,stamp,stamp,message['tenant_id']))
        event(c,'message.outbox.restored',a['id'],message['task_id'],
              {'message_id':message_id,'outbox_id':outbox_id,'reason':reason},tenant_override=message['tenant_id'])
    return {'message_id':message_id,'outbox_id':outbox_id,'status':'PENDING','restored':True}

@app.get('/api/v1/projects/{project_id}/message-delivery-health')
def project_message_delivery_health(project_id:str,authorization:str=Header(None),
                                    dispatch_sla_seconds:int=120,ack_sla_seconds:int=300,
                                    limit:int=100):
    """Project-scoped delivery SLA health; broker dispatch and recipient ACK clocks are separate."""
    a=actor(authorization)
    dispatch_sla_seconds=max(10,min(dispatch_sla_seconds,86400))
    ack_sla_seconds=max(10,min(ack_sla_seconds,604800))
    limit=max(1,min(limit,500))
    stamp=datetime.now(timezone.utc)
    incidents=[]
    with conn() as c:
        require_project_access(c,project_id,a)
        messages=c.execute("""SELECT m.id,m.recipient_member_id,m.tenant_id,m.task_id,m.status,m.created_at,m.acked_at
            FROM messages m JOIN tasks t ON t.id=m.task_id
            JOIN requirements r ON r.id=t.requirement_id
            WHERE r.project_id=? ORDER BY m.seq DESC LIMIT ?""",(project_id,limit)).fetchall()
        outbox=c.execute("SELECT id,payload,status,attempts,available_at,lease_until,lease_owner,last_error,created_at,sent_at FROM outbox WHERE event_type='message.created'").fetchall()
    by_message={}
    malformed=0
    for row in outbox:
        try:
            mid=json.loads(row['payload']).get('message_id')
            if isinstance(mid,str) and mid: by_message.setdefault(mid,[]).append(row)
            else: malformed+=1
        except (TypeError,ValueError):
            malformed+=1
    dispatch_counts={k:0 for k in ('HEALTHY','MISSING','DUPLICATE','DEAD','DISPATCH_OVERDUE')}
    ack_counts={k:0 for k in ('NOT_DUE','ACK_OVERDUE','ACKNOWLEDGED','REJECTED')}
    def parse_stamp(value):
        if not value: return None
        try:
            parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError,ValueError):
            return None
    for message in messages:
        records=by_message.get(message['id'],[])
        dispatch='HEALTHY'; ack='NOT_DUE'; detail=None
        if not records:
            dispatch='MISSING'; detail='No message.created outbox record'
        elif len(records)>1:
            dispatch='DUPLICATE'; detail='Multiple message.created outbox records'
        elif records[0]['status']=='DEAD':
            dispatch='DEAD'; detail=records[0]['last_error'] or 'Outbox entered DEAD state'
        elif records[0]['status'] in ('PENDING','IN_FLIGHT'):
            created=parse_stamp(records[0]['created_at'])
            if created and (stamp-created).total_seconds()>dispatch_sla_seconds:
                dispatch='DISPATCH_OVERDUE'; detail='Broker dispatch exceeded SLA'
        elif records[0]['status']!='SENT':
            dispatch='HEALTHY'; detail='Unrecognized outbox state: '+str(records[0]['status'])
        if dispatch in dispatch_counts: dispatch_counts[dispatch]+=1
        if message['status'] in ('ACKNOWLEDGED','REJECTED'):
            ack=message['status']
        elif records and len(records)==1 and records[0]['status']=='SENT':
            sent=parse_stamp(records[0]['sent_at'])
            if sent and (stamp-sent).total_seconds()>ack_sla_seconds:
                ack='ACK_OVERDUE'
        if ack in ack_counts: ack_counts[ack]+=1
        if dispatch!='HEALTHY':
            incidents.append({'message_id':message['id'],'task_id':message['task_id'],
                'category':'DISPATCH_'+dispatch,'dispatch_status':dispatch,'ack_status':ack,
                'age_seconds':max(0,int((stamp-(parse_stamp(message['created_at']) or stamp)).total_seconds())),
                'detail':detail})
        if ack=='ACK_OVERDUE':
            incidents.append({'message_id':message['id'],'task_id':message['task_id'],
                'category':'ACK_OVERDUE','dispatch_status':dispatch,'ack_status':ack,
                'age_seconds':max(0,int((stamp-(parse_stamp(records[0]['sent_at']) or stamp)).total_seconds())),
                'detail':'Broker dispatch completed but recipient ACK exceeded SLA'})
    return {'project_id':project_id,'generated_at':stamp.isoformat(),
        'policy':{'dispatch_sla_seconds':dispatch_sla_seconds,'ack_sla_seconds':ack_sla_seconds},
        'checked_messages':len(messages),'truncated':len(messages)==limit,
        'dispatch_counts':dispatch_counts,'ack_counts':ack_counts,
        'incident_count':len(incidents),'incidents':incidents[:limit],
        'malformed_outbox_records_seen':malformed,
        'semantics':'ACK SLA starts at outbox sent_at only. SENT is broker dispatch completion, not recipient ACK.'}

@app.post('/api/v1/projects/{project_id}/message-delivery-incidents/{message_id}/review')
def review_message_delivery_incident(project_id:str,message_id:str,body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    disposition=str(body.get('disposition','')).strip().upper()
    comment=str(body.get('comment','')).strip()
    if disposition not in ('INVESTIGATING','RESOLVED','ACCEPTED_RISK'):
        raise HTTPException(422,'disposition must be INVESTIGATING, RESOLVED, or ACCEPTED_RISK')
    if not comment or len(comment)>2000:
        raise HTTPException(422,'A review comment (1-2000 characters) is required')
    with conn() as c:
        require_project_access(c,project_id,a,write=True)
        row=c.execute("""SELECT m.task_id,m.tenant_id FROM messages m JOIN tasks t ON t.id=m.task_id
            JOIN requirements r ON r.id=t.requirement_id WHERE m.id=? AND r.project_id=?""",
            (message_id,project_id)).fetchone()
        if not row: raise HTTPException(404,'Project message not found')
        event(c,'message.delivery.incident.reviewed',a['id'],row['task_id'],
              {'project_id':project_id,'message_id':message_id,'disposition':disposition,'comment':comment},
              tenant_override=row['tenant_id'])
    return {'project_id':project_id,'message_id':message_id,'disposition':disposition,'recorded':True}


@app.get('/api/v1/admin/message-delivery')
def message_delivery_overview(authorization:str=Header(None),limit:int=200,offset:int=0,
                              dispatch_status:str=None,ack_status:str=None):
    """Admin operational view separating broker dispatch from recipient acknowledgement."""
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    limit=max(1,min(limit,500)); offset=max(0,offset)
    allowed_dispatch={'NO_OUTBOX','DUPLICATE','PENDING','IN_FLIGHT','SENT','DEAD'}
    allowed_ack={'PENDING','ACKNOWLEDGED','REJECTED'}
    if dispatch_status and dispatch_status not in allowed_dispatch:
        raise HTTPException(422,'Invalid dispatch_status filter')
    if ack_status and ack_status not in allowed_ack:
        raise HTTPException(422,'Invalid ack_status filter')
    with conn() as c:
        messages=c.execute('SELECT id,recipient_member_id,tenant_id,task_id,message_type,priority,status,created_at,acked_at FROM messages ORDER BY seq DESC LIMIT ? OFFSET ?',(limit,offset)).fetchall()
        outbox=c.execute("SELECT id,event_type,payload,status,attempts,available_at,lease_until,lease_owner,last_error,created_at,sent_at,tenant_id FROM outbox WHERE event_type='message.created' ORDER BY created_at").fetchall()
    by_message={}
    malformed_count=0
    for item in outbox:
        try:
            mid=json.loads(item['payload']).get('message_id')
            if not isinstance(mid,str) or not mid: malformed_count+=1; continue
        except (TypeError,ValueError):
            malformed_count+=1; continue
        by_message.setdefault(mid,[]).append(item)
    items=[]
    counts={key:0 for key in ('NO_OUTBOX','DUPLICATE','PENDING','IN_FLIGHT','SENT','DEAD')}
    ack_counts={key:0 for key in ('PENDING','ACKNOWLEDGED','REJECTED')}
    for message in messages:
        records=by_message.get(message['id'],[])
        state='NO_OUTBOX' if not records else ('DUPLICATE' if len(records)>1 else records[0]['status'])
        if state not in counts: state='UNKNOWN'
        if state in counts: counts[state]+=1
        ack=message['status']
        if ack in ack_counts: ack_counts[ack]+=1
        if dispatch_status and state!=dispatch_status: continue
        if ack_status and ack!=ack_status: continue
        items.append({
            'message_id':message['id'],'recipient_member_id':message['recipient_member_id'],
            'tenant_id':message['tenant_id'],'task_id':message['task_id'],
            'message_type':message['message_type'],'priority':message['priority'],
            'ack_status':ack,'created_at':message['created_at'],'acked_at':message['acked_at'],
            'dispatch_status':state,'dispatch_records':[{
                'outbox_id':row['id'],'status':row['status'],'attempts':row['attempts'],
                'available_at':row['available_at'],'lease_until':row['lease_until'],
                'lease_owner':row['lease_owner'],'last_error':row['last_error'],
                'created_at':row['created_at'],'sent_at':row['sent_at']
            } for row in records]
        })
    return {'items':items,'count':len(items),'limit':limit,'offset':offset,
            'dispatch_counts':counts,'ack_counts':ack_counts,
            'malformed_outbox_records_seen':malformed_count,
            'semantics':{'SENT':'Broker dispatch completed; recipient acknowledgement is tracked separately in ack_status.',
                         'ACKNOWLEDGED':'Recipient explicitly acknowledged the message.',
                         'REJECTED':'Recipient explicitly rejected the message.'}}

@app.get('/api/v1/admin/message-delivery-integrity')
def message_delivery_integrity(authorization:str=Header(None),limit:int=5000):
    """Read-only reconciliation of durable messages and their outbox dispatch records."""
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    limit=max(1,min(limit,10000))
    with conn() as c:
        messages=c.execute('SELECT id,recipient_member_id,tenant_id,task_id FROM messages ORDER BY seq LIMIT ?',(limit+1,)).fetchall()
        outbox=c.execute("SELECT id,event_type,payload,tenant_id,status FROM outbox WHERE event_type='message.created' ORDER BY created_at LIMIT ?",(limit+1,)).fetchall()
    truncated=len(messages)>limit or len(outbox)>limit
    messages=messages[:limit]; outbox=outbox[:limit]
    by_message={}
    malformed=[]; orphaned=[]; tenant_mismatch=[]; recipient_mismatch=[]; task_mismatch=[]
    known={row['id']:row for row in messages}
    for item in outbox:
        try:
            payload=json.loads(item['payload'])
            message_id=payload.get('message_id')
            if not isinstance(message_id,str) or not message_id:
                malformed.append(item['id']); continue
        except (TypeError,ValueError):
            malformed.append(item['id']); continue
        by_message.setdefault(message_id,[]).append(item)
        message=known.get(message_id)
        if not message:
            orphaned.append(item['id']); continue
        if item['tenant_id'] != message['tenant_id']:
            tenant_mismatch.append(item['id'])
        if payload.get('recipient_member_id') != message['recipient_member_id']:
            recipient_mismatch.append(item['id'])
        if payload.get('task_id') != message['task_id']:
            task_mismatch.append(item['id'])
    missing=[mid for mid in known if mid not in by_message]
    duplicates={mid:[x['id'] for x in rows] for mid,rows in by_message.items() if len(rows)>1}
    issues={
        'messages_without_outbox':missing,
        'duplicate_outbox_by_message':duplicates,
        'orphaned_outbox':orphaned,
        'malformed_outbox':malformed,
        'tenant_mismatch_outbox':tenant_mismatch,
        'recipient_mismatch_outbox':recipient_mismatch,
        'task_mismatch_outbox':task_mismatch,
    }
    counts={key:(len(value) if isinstance(value,list) else len(value)) for key,value in issues.items()}
    return {'checked_messages':len(messages),'checked_message_outbox':len(outbox),'truncated':truncated,
            'healthy':not any(counts.values()) and not truncated,'issue_counts':counts,'issues':issues,
            'semantics':'Read-only structural reconciliation; SENT means broker dispatch completed, not recipient ACK.'}

@app.post('/api/v1/admin/outbox/{outbox_id}/replay')
def replay_dead_outbox(outbox_id:str,body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    reason=str(body.get('reason','')).strip()
    if not reason or len(reason)>1000: raise HTTPException(422,'A replay reason (1-1000 characters) is required')
    with conn() as c:
        row=c.execute("SELECT tenant_id,status FROM outbox WHERE id=?",(outbox_id,)).fetchone()
        if not row: raise HTTPException(404,'Outbox item not found')
        if row['status']!='DEAD': raise HTTPException(409,'Only DEAD outbox items can be replayed')
        stamp=now()
        cur=c.execute("UPDATE outbox SET status='PENDING',attempts=0,available_at=?,lease_until=NULL,lease_owner=NULL,lease_token=NULL,last_error=NULL,sent_at=NULL WHERE id=? AND status='DEAD'",(stamp,outbox_id))
        if not cur.rowcount: raise HTTPException(409,'Outbox item changed; refresh and retry')
        event(c,'outbox.dead.replayed',a['id'],None,{'outbox_id':outbox_id,'reason':reason},tenant_override=row['tenant_id'])
    return {'id':outbox_id,'status':'PENDING','replayed':True}

@app.websocket('/ws/v1')
async def websocket_endpoint(ws:WebSocket,token:str='',after:int=0):
    # Best-effort online notification channel. The durable inbox remains the source of truth.
    lookup_reset=_auth_lookup_ctx.set(True)
    try:
        with conn() as c: member=(c.execute("SELECT id,tenant_id,role FROM daep_authenticate_member(?,?)",(hashlib.sha256(token.encode()).hexdigest(),now())).fetchone() if DATABASE_URL.startswith(('postgresql://','postgres://')) else c.execute("SELECT id,tenant_id,role FROM members WHERE token=? AND token_status='ACTIVE' AND (token_expires_at IS NULL OR token_expires_at>?)",(hashlib.sha256(token.encode()).hexdigest(),now())).fetchone())
    finally:
        _auth_lookup_ctx.reset(lookup_reset)
    if not member: await ws.close(code=1008); return
    cursor=max(0,after)
    _tenant_ctx.set(member['tenant_id']); _admin_ctx.set(member['role']=='admin' and member['tenant_id']=='tenant-default')
    await ws.accept()
    try:
        await ws.send_json({'type':'connected','at':now(),'cursor':cursor,'delivery':'best-effort; reconnect with after=<last processed seq> or recover via inbox'})
        while True:
            with conn() as c:
                rows=[dict(r) for r in c.execute("SELECT * FROM messages WHERE recipient_member_id=? AND status='PENDING' AND seq>? ORDER BY seq LIMIT 100",(member['id'],cursor))]
                if rows:
                    for r in rows:
                        await ws.send_json({'type':'notification','message':r})
                        cursor=max(cursor,r['seq'])
                        c.execute('UPDATE messages SET attempts=attempts+1,last_attempt_at=? WHERE id=?',(now(),r['id']))
            try: await asyncio.wait_for(ws.receive_text(),timeout=3.0)
            except asyncio.TimeoutError: pass
    except WebSocketDisconnect: pass

def require_worker(authorization):
    expected=os.getenv('DAEP_WORKER_TOKEN','')
    if len(expected)<32: raise HTTPException(503,'Dedicated DAEP_WORKER_TOKEN is not configured')
    if secrets.compare_digest(hashlib.sha256(expected.encode()).digest(),hashlib.sha256(ADMIN_TOKEN.encode()).digest()): raise HTTPException(503,'Worker credential must be different from DAEP_ADMIN_TOKEN')
    if not authorization or not authorization.startswith('Bearer '): raise HTTPException(401,'Worker bearer token required')
    supplied=authorization[7:]
    expected_digest=hashlib.sha256(expected.encode()).digest()
    supplied_digest=hashlib.sha256(supplied.encode()).digest()
    if not secrets.compare_digest(supplied_digest,expected_digest): raise HTTPException(401,'Invalid worker credential')
    _service_ctx.set(True)
def require_project_access(c, project_id, a, write=False):
    project=c.execute('SELECT tenant_id,status FROM projects WHERE id=?',(project_id,)).fetchone()
    if not project: raise HTTPException(404,'Project not found')
    if project['tenant_id'] != a.get('tenant_id','tenant-default') and not is_admin(a):
        raise HTTPException(403,'Tenant isolation violation')
    if write and project['status']=='CLOSED': raise HTTPException(409,'Project is closed')
    if is_admin(a): return
    if a.get('actor_type')=='AGENT':
        binding=c.execute("SELECT 1 FROM agent_project_bindings WHERE project_id=? AND agent_id=? AND status='ACTIVE'",
            (project_id,a['agent_id'])).fetchone()
        if not binding: raise HTTPException(403,'Agent project binding required')
        if write: raise HTTPException(403,'Agent cannot perform project-level governance or administration')
        return
    row=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(project_id,a['id'])).fetchone()
    if not row: raise HTTPException(403,'Project membership required')
    if write and row['role'] not in ('owner','manager'): raise HTTPException(403,'Project manager role required')
def task_project(c, tid):
    r=c.execute('SELECT r.project_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id WHERE t.id=?',(tid,)).fetchone()
    return r['project_id'] if r else None
def require_task_access(c, tid, a, assigned_only=False):
    pid=task_project(c,tid)
    if not pid: raise HTTPException(404,'Task not found')
    project=c.execute('SELECT status FROM projects WHERE id=?',(pid,)).fetchone()
    closed=bool(project and project['status']=='CLOSED')
    if is_admin(a):
        if assigned_only and closed: raise HTTPException(409,'Project is closed')
        return
    if a.get('actor_type')=='AGENT':
        require_project_access(c,pid,a)
        if assigned_only and closed:
            raise HTTPException(409,'Project is closed')
        assignment=c.execute("""SELECT 1 FROM agent_task_assignments
            WHERE task_id=? AND project_id=? AND agent_id=? AND status='ACCEPTED'""",
            (tid,pid,a['agent_id'])).fetchone()
        if not assignment:
            raise HTTPException(403,'Accepted Agent task assignment required')
        return
    if assigned_only:
        if closed: raise HTTPException(409,'Project is closed')
        ok=c.execute('SELECT 1 FROM assignments WHERE task_id=? AND member_id=?',(tid,a['id'])).fetchone()
        if not ok: raise HTTPException(403,'Task assignment required')
    else: require_project_access(c,pid,a)

def event(c,typ,member,task,payload,key=None,tenant_override=None):
    eid='evt_'+uuid.uuid4().hex
    tenant=tenant_override or 'tenant-default'
    if tenant_override:
        pass
    elif task:
        rr=c.execute('SELECT p.tenant_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE t.id=?',(task,)).fetchone()
        if rr: tenant=rr['tenant_id']
    elif member:
        rr=c.execute('SELECT tenant_id FROM members WHERE id=?',(member,)).fetchone()
        if rr: tenant=rr['tenant_id']
    audit_payload=dict(payload or {})
    audit_payload.setdefault('actor_type','AGENT' if _agent_ctx.get() else 'MEMBER')
    if _agent_ctx.get(): audit_payload.setdefault('agent_id',_agent_ctx.get())
    # Agent actions are attributed to the Agent identity, never to its owner's member row.
    actor_member_id=None if _agent_ctx.get() else member
    payload_json=json.dumps(audit_payload)
    if key:
        c.execute('INSERT INTO events(id,event_type,actor_member_id,task_id,payload,created_at,idempotency_key,tenant_id) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(idempotency_key) DO NOTHING',(eid,typ,actor_member_id,task,payload_json,now(),key,tenant))
        prior=c.execute('SELECT id,payload FROM events WHERE idempotency_key=?',(key,)).fetchone()
        if prior:
            if prior['payload'] != payload_json:
                raise HTTPException(409,'Idempotency key was used with a different payload')
            return prior['id']
    else:
        c.execute('INSERT INTO events(id,event_type,actor_member_id,task_id,payload,created_at,idempotency_key,tenant_id) VALUES(?,?,?,?,?,?,?,?)',(eid,typ,actor_member_id,task,payload_json,now(),key,tenant))
    return eid

@app.get('/',include_in_schema=False)
def dashboard(): return FileResponse(os.path.join(os.path.dirname(os.path.dirname(__file__)),'web','index.html'))
def _oidc_discovery():
    issuer=os.getenv('DAEP_OIDC_ISSUER','').rstrip('/')
    if not issuer: raise HTTPException(503,'OIDC is not configured')
    try:
        with urllib.request.urlopen(issuer+'/.well-known/openid-configuration',timeout=10) as r: return json.loads(r.read())
    except Exception as exc: raise HTTPException(503,f'OIDC discovery failed: {exc}')

def _oidc_state_record():
    """Create one-time server-side OIDC state, nonce and PKCE verifier."""
    state=secrets.token_urlsafe(32)
    nonce=secrets.token_urlsafe(32)
    verifier=secrets.token_urlsafe(64)
    expires=datetime.fromtimestamp(time.time()+600,timezone.utc).isoformat()
    with conn() as c:
        c.execute('DELETE FROM oidc_states WHERE expires_at<=?',(now(),))
        c.execute('INSERT INTO oidc_states(state_hash,nonce,code_verifier,expires_at,created_at) VALUES(?,?,?,?,?)',
                  (hashlib.sha256(state.encode()).hexdigest(),nonce,verifier,expires,now()))
    return state,nonce,verifier

def _verify_oidc_browser_state(state,cookie_state):
    if not cookie_state or not secrets.compare_digest(hashlib.sha256(cookie_state.encode()).digest(),hashlib.sha256(state.encode()).digest()):
        raise HTTPException(400,'OIDC browser state cookie mismatch')

def _consume_oidc_state(state):
    if not state or len(state)>512: raise HTTPException(400,'Invalid OIDC state')
    digest=hashlib.sha256(state.encode()).hexdigest()
    with conn() as c:
        row=c.execute('SELECT nonce,code_verifier,expires_at FROM oidc_states WHERE state_hash=?',(digest,)).fetchone()
        if not row: raise HTTPException(400,'Invalid or already used OIDC state')
        c.execute('DELETE FROM oidc_states WHERE state_hash=?',(digest,))
    if row['expires_at'] <= now(): raise HTTPException(400,'Expired OIDC state')
    return row['nonce'],row['code_verifier']

@app.get('/api/v1/auth/oidc/login')
def oidc_login():
    if not (os.getenv('DAEP_OIDC_CLIENT_ID') and os.getenv('DAEP_OIDC_REDIRECT_URI')): raise HTTPException(503,'OIDC is not configured')
    d=_oidc_discovery(); state,nonce,verifier=_oidc_state_record()
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    params={'client_id':os.getenv('DAEP_OIDC_CLIENT_ID'),'response_type':'code','redirect_uri':os.getenv('DAEP_OIDC_REDIRECT_URI'),'scope':os.getenv('DAEP_OIDC_SCOPES','openid profile email'),'state':state,'nonce':nonce,'code_challenge':challenge,'code_challenge_method':'S256'}
    if os.getenv('DAEP_OIDC_AUDIENCE'): params['audience']=os.getenv('DAEP_OIDC_AUDIENCE')
    response=RedirectResponse(d['authorization_endpoint']+'?'+urllib.parse.urlencode(params),status_code=302)
    response.set_cookie('daep_oidc_state',state,max_age=600,httponly=True,secure=os.getenv('DAEP_OIDC_REDIRECT_URI','').startswith('https://'),samesite='lax',path='/api/v1/auth/oidc/callback')
    return response

@app.get('/api/v1/auth/oidc/callback')
def oidc_callback(code:str,state:str,daep_oidc_state:Optional[str]=Cookie(None)):
    client_id=os.getenv('DAEP_OIDC_CLIENT_ID',''); client_secret=os.getenv('DAEP_OIDC_CLIENT_SECRET','')
    redirect_uri=os.getenv('DAEP_OIDC_REDIRECT_URI','')
    if not client_id or not client_secret or not redirect_uri: raise HTTPException(503,'OIDC client is not configured')
    _verify_oidc_browser_state(state,daep_oidc_state)
    nonce,code_verifier=_consume_oidc_state(state); d=_oidc_discovery()
    form=urllib.parse.urlencode({'grant_type':'authorization_code','code':code,'redirect_uri':redirect_uri,'client_id':client_id,'client_secret':client_secret,'code_verifier':code_verifier}).encode()
    req=urllib.request.Request(d['token_endpoint'],data=form,method='POST',headers={'Content-Type':'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req,timeout=15) as r: tokens=json.loads(r.read())
    except Exception: raise HTTPException(502,'OIDC token exchange failed')
    id_token=tokens.get('id_token')
    if not id_token: raise HTTPException(502,'OIDC provider did not return an id_token')
    try:
        import jwt
        jwks_client=jwt.PyJWKClient(d['jwks_uri'],timeout=10)
        signing_key=jwks_client.get_signing_key_from_jwt(id_token).key
        claims=jwt.decode(id_token,signing_key,algorithms=['RS256','RS384','RS512','PS256','ES256'],audience=client_id,issuer=os.getenv('DAEP_OIDC_ISSUER').rstrip('/'),options={'require':['exp','iat','sub','iss','aud']})
        if not secrets.compare_digest(str(claims.get('nonce','')),nonce): raise ValueError('OIDC nonce mismatch')
        audiences=claims.get('aud',[])
        if isinstance(audiences,list) and len(audiences)>1 and claims.get('azp')!=client_id: raise ValueError('OIDC authorized party mismatch')
    except Exception: raise HTTPException(401,'OIDC ID token validation failed')
    subject=str(claims.get('sub','')); email=str(claims.get('email',''))
    if not subject: raise HTTPException(401,'OIDC subject is missing')
    created=now(); raw=uuid.uuid4().hex+uuid.uuid4().hex; digest=hashlib.sha256(raw.encode()).hexdigest()
    service_reset=_service_ctx.set(True)
    try:
        with conn() as c:
            row=c.execute('SELECT id FROM members WHERE oidc_subject=?',(subject,)).fetchone()
            if row:
                c.execute("UPDATE members SET token=?,token_status='ACTIVE',token_created_at=?,token_revoked_at=NULL,oidc_email=? WHERE id=?",(digest,created,email,row['id']))
                member_id=row['id']
            else:
                if os.getenv('DAEP_OIDC_AUTO_PROVISION','false').lower()!='true': raise HTTPException(403,'OIDC identity is not provisioned')
                member_id='mem_'+uuid.uuid4().hex[:12]; tenant_id=os.getenv('DAEP_OIDC_DEFAULT_TENANT','tenant-default'); name=str(claims.get('name') or email or subject)
                if not c.execute("SELECT 1 FROM tenants WHERE id=? AND status='ACTIVE'",(tenant_id,)).fetchone(): raise HTTPException(403,'OIDC default tenant is unavailable')
                oidc_role=os.getenv('DAEP_OIDC_DEFAULT_ROLE','developer')
                if oidc_role not in ('developer','manager','reviewer'): oidc_role='developer'
                c.execute("INSERT INTO members(id,name,role,token,created_at,tenant_id,token_status,token_created_at,oidc_subject,oidc_email) VALUES(?,?,?,?,?,?,?,?,?,?)",(member_id,name,oidc_role,digest,created,tenant_id,'ACTIVE',created,subject,email))
    finally:
        _service_ctx.reset(service_reset)
    response=JSONResponse({'member_id':member_id,'token':raw,'token_expires_at':None,'message':'OIDC authentication succeeded; store this API token securely. It is returned only once.'})
    response.delete_cookie('daep_oidc_state',path='/api/v1/auth/oidc/callback')
    return response

@app.get('/api/v1/auth/oidc/config')
def oidc_config():
    enabled=bool(os.getenv('DAEP_OIDC_ISSUER') and os.getenv('DAEP_OIDC_CLIENT_ID') and os.getenv('DAEP_OIDC_REDIRECT_URI'))
    return {'enabled':enabled,'issuer':os.getenv('DAEP_OIDC_ISSUER',''),'client_id':os.getenv('DAEP_OIDC_CLIENT_ID',''),'redirect_uri':os.getenv('DAEP_OIDC_REDIRECT_URI',''),'scopes':os.getenv('DAEP_OIDC_SCOPES','openid profile email')}

@app.post('/api/v1/integrations/git/webhook')
async def git_webhook(request:Request, body:dict, x_daep_webhook_secret:str=Header('',alias='X-DAEP-Webhook-Secret'), x_daep_tenant_id:str=Header('',alias='X-DAEP-Tenant-ID'), x_daep_provider:str=Header('',alias='X-DAEP-Provider'), x_github_event:str=Header('',alias='X-GitHub-Event'), x_github_delivery:str=Header('',alias='X-GitHub-Delivery'), x_hub_signature_256:str=Header('',alias='X-Hub-Signature-256'), x_gitlab_event:str=Header('',alias='X-Gitlab-Event'), x_gitlab_event_uuid:str=Header('',alias='X-Gitlab-Event-UUID'), x_gitlab_token:str=Header('',alias='X-Gitlab-Token')):
    raw=await request.body()
    provider=(x_daep_provider or ('github' if x_github_event or x_hub_signature_256 else 'gitlab' if x_gitlab_event or x_gitlab_token else 'generic')).lower()
    if provider not in ('github','gitlab','generic'): raise HTTPException(422,'Unsupported Git provider')
    if provider=='github':
        expected=os.getenv('DAEP_GITHUB_WEBHOOK_SECRET') or os.getenv('DAEP_GIT_WEBHOOK_SECRET','')
        if not expected or not x_hub_signature_256 or not x_hub_signature_256.startswith('sha256='): raise HTTPException(401,'GitHub webhook signature is required')
        supplied=x_hub_signature_256.split('=',1)[1]
        actual=hmac.new(expected.encode(),raw,hashlib.sha256).hexdigest()
        if not hmac.compare_digest(actual,supplied): raise HTTPException(401,'Invalid GitHub webhook signature')
        delivery=x_github_delivery
    elif provider=='gitlab':
        expected=os.getenv('DAEP_GITLAB_WEBHOOK_SECRET') or os.getenv('DAEP_GIT_WEBHOOK_SECRET','')
        if not expected or not x_gitlab_token or not secrets.compare_digest(hashlib.sha256(x_gitlab_token.encode()).digest(),hashlib.sha256(expected.encode()).digest()): raise HTTPException(401,'Invalid GitLab webhook token')
        delivery=x_gitlab_event_uuid
    else:
        expected=os.getenv('DAEP_GIT_WEBHOOK_SECRET','')
        if not expected or not x_daep_webhook_secret or not secrets.compare_digest(hashlib.sha256(x_daep_webhook_secret.encode()).digest(),hashlib.sha256(expected.encode()).digest()): raise HTTPException(401,'Invalid webhook secret')
        delivery=request.headers.get('X-DAEP-Delivery','')
    if delivery and len(delivery)>200: raise HTTPException(422,'Webhook delivery id is too long')
    event_type=str(body.get('event_type') or body.get('action') or x_github_event or x_gitlab_event or 'push')[:80]
    task_id=body.get('task_id'); commit=body.get('after') or body.get('commit_sha')
    service_reset=_service_ctx.set(True)
    try:
        with conn() as c:
            if task_id:
                row=c.execute('SELECT p.tenant_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE t.id=?',(task_id,)).fetchone()
                if not row: raise HTTPException(404,'Task not found')
                tenant_id=row['tenant_id']
            else:
                tenant_id=str(x_daep_tenant_id or body.get('tenant_id') or '').strip()
                if not tenant_id: raise HTTPException(422,'X-DAEP-Tenant-ID is required when task_id is absent')
                if not c.execute("SELECT 1 FROM tenants WHERE id=? AND status='ACTIVE'",(tenant_id,)).fetchone(): raise HTTPException(404,'Tenant not found or inactive')
        _tenant_ctx.set(tenant_id); _admin_ctx.set(False)
        _service_ctx.reset(service_reset); service_reset=_service_ctx.set(False)
        with conn() as c:
            eid=event(c,'git.webhook.received',None,task_id,{'provider':provider,'delivery_id':delivery,'event_type':event_type,'commit_sha':commit,'payload':body},key=(f'git:{provider}:{delivery}' if delivery else None),tenant_override=tenant_id)
        return {'accepted':True,'event_id':eid,'event_type':event_type,'commit_sha':commit,'tenant_id':tenant_id,'provider':provider,'delivery_id':delivery}
    finally:
        _service_ctx.reset(service_reset)

@app.get('/health')
def health():
    service_reset=_service_ctx.set(True)
    try:
        with conn() as c:
            pending=c.execute("SELECT COUNT(*) n FROM outbox WHERE status IN ('PENDING','IN_FLIGHT')").fetchone()['n']
        return {'status':'ok','service':'daep-api','version':'1.0.0-rc9','outbox_pending':pending}
    finally:
        _service_ctx.reset(service_reset)

@app.get('/readyz')
def readiness():
    service_reset=_service_ctx.set(True)
    try:
        with conn() as c:
            c.execute('SELECT 1').fetchone()
            if DATABASE_URL.startswith(('postgresql://','postgres://')):
                c.execute("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='members'").fetchone()
        return {'status':'ready','service':'daep-api','version':'1.0.0-rc9'}
    except Exception:
        raise HTTPException(503,'DAEP database readiness check failed')
    finally:
        _service_ctx.reset(service_reset)
@app.get('/api/v1/me')
def me(authorization:str=Header(None)):
    a=actor(authorization); return {k:a[k] for k in ('id','name','role')}
@app.post('/api/v1/tenants')
def create_tenant(body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    name=str(body.get('name','')).strip()
    if not name or len(name)>160: raise HTTPException(422,'Tenant name is required')
    tid='ten_'+uuid.uuid4().hex[:12]
    with conn() as c: c.execute('INSERT INTO tenants(id,name,status,created_at) VALUES(?,?,?,?)',(tid,name,'ACTIVE',now()))
    return {'id':tid,'name':name,'status':'ACTIVE'}

@app.get('/api/v1/tenants')
def list_tenants(authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    with conn() as c: return [dict(x) for x in c.execute('SELECT * FROM tenants ORDER BY created_at')]

@app.post('/api/v1/members')
def create_member(body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    if not isinstance(body.get('name'),str) or not body['name'].strip(): raise HTTPException(422,'Member name is required')
    if body.get('role','developer') not in ('manager','developer','reviewer'): raise HTTPException(422,'Only the bootstrap identity can hold the platform administrator role')
    mid='mem_'+uuid.uuid4().hex[:12]; token=uuid.uuid4().hex+uuid.uuid4().hex; created=now()
    tenant_id=str(body.get('tenant_id') or a.get('tenant_id') or 'tenant-default')
    with conn() as c:
        if not c.execute("SELECT 1 FROM tenants WHERE id=? AND status='ACTIVE'",(tenant_id,)).fetchone(): raise HTTPException(404,'Tenant not found or inactive')
        c.execute('INSERT INTO members(id,name,role,token,created_at,tenant_id,token_status,token_created_at,token_revoked_at,token_expires_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(mid,body['name'],body.get('role','developer'),hashlib.sha256(token.encode()).hexdigest(),created,tenant_id,'ACTIVE',created,None,body.get('token_expires_at')))
    return {'id':mid,'name':body['name'],'role':body.get('role','developer'),'tenant_id':tenant_id,'token':token}
@app.get('/api/v1/members')
def members(authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    with conn() as c: return [dict(x) for x in c.execute('SELECT id,name,role,tenant_id,token_status,token_created_at,token_revoked_at,token_expires_at,created_at FROM members ORDER BY created_at')]
@app.post('/api/v1/members/{member_id}/revoke-token')
def revoke_member_token(member_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    with conn() as c:
        target=c.execute('SELECT tenant_id FROM members WHERE id=?',(member_id,)).fetchone()
        if not target: raise HTTPException(404,'Member not found')
        cur=c.execute("UPDATE members SET token_status='REVOKED',token_revoked_at=? WHERE id=?" ,(now(),member_id))
        event(c,'member.token.revoked',a['id'],None,{'member_id':member_id},tenant_override=target['tenant_id'])
    return {'member_id':member_id,'token_status':'REVOKED'}

@app.post('/api/v1/members/{member_id}/rotate-token')
def rotate_member_token(member_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    token=uuid.uuid4().hex+uuid.uuid4().hex; created=now(); digest=hashlib.sha256(token.encode()).hexdigest()
    with conn() as c:
        target=c.execute('SELECT tenant_id FROM members WHERE id=?',(member_id,)).fetchone()
        if not target: raise HTTPException(404,'Member not found')
        cur=c.execute("UPDATE members SET token=?,token_status='ACTIVE',token_created_at=?,token_revoked_at=NULL WHERE id=?",(digest,created,member_id))
        event(c,'member.token.rotated',a['id'],None,{'member_id':member_id},tenant_override=target['tenant_id'])
    return {'member_id':member_id,'token':token,'token_status':'ACTIVE','token_created_at':created}

@app.post('/api/v1/projects')
def create_project(b:ProjectIn,authorization:str=Header(None)):
    a=actor(authorization); pid='prj_'+uuid.uuid4().hex[:12]
    with conn() as c:
        c.execute('INSERT INTO projects(id,name,description,created_by,created_at,tenant_id) VALUES(?,?,?,?,?,?)',(pid,b.name,b.description,a['id'],now(),a.get('tenant_id','tenant-default')))
        c.execute('INSERT INTO project_members(project_id,member_id,role,work_function,joined_at) VALUES(?,?,?,?,?)',(pid,a['id'],'owner','other',now()))
    return {'id':pid,'name':b.name,'description':b.description}
@app.get('/api/v1/projects')
def projects(authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        if is_admin(a): rows=c.execute('SELECT * FROM projects ORDER BY created_at DESC')
        else: rows=c.execute('SELECT p.*,pm.role AS project_role,pm.work_function FROM projects p JOIN project_members pm ON pm.project_id=p.id WHERE pm.member_id=? AND p.tenant_id=? ORDER BY p.created_at DESC',(a['id'],a.get('tenant_id','tenant-default')))
        return [dict(x) for x in rows]
@app.get('/api/v1/projects/{pid}/members')
def project_members(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        return [dict(x) for x in c.execute('SELECT m.id,m.name,m.role AS account_role,pm.role AS project_role,pm.work_function,pm.joined_at FROM project_members pm JOIN members m ON m.id=pm.member_id WHERE pm.project_id=? ORDER BY pm.joined_at',(pid,))]
@app.post('/api/v1/projects/{pid}/members')
def add_project_member(pid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization)
    mid=b.get('member_id'); role=b.get('role','member'); work_function=b.get('work_function','other')
    if role not in ('member','reviewer','manager'): raise HTTPException(422,'Invalid project role')
    if work_function not in ('developer','tester','product','architect','other'): raise HTTPException(422,'Invalid work function')
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        if role=='manager' and not is_admin(a):
            own=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not own or own['role']!='owner': raise HTTPException(403,'Only project owners may directly grant manager role; use an approval request')
        member_row=c.execute('SELECT tenant_id FROM members WHERE id=?',(mid,)).fetchone()
        project_row=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        if not member_row: raise HTTPException(404,'Member not found')
        if project_row['tenant_id'] != member_row['tenant_id']: raise HTTPException(400,'Member belongs to a different tenant')
        c.execute('INSERT INTO project_members(project_id,member_id,role,work_function,joined_at) VALUES(?,?,?,?,?) ON CONFLICT(project_id,member_id) DO UPDATE SET role=excluded.role,work_function=excluded.work_function',(pid,mid,role,work_function,now()))
        event(c,'project.member.role_set',a['id'],None,{'project_id':pid,'member_id':mid,'role':role},tenant_override=project_row['tenant_id'])
        return {'project_id':pid,'member_id':mid,'role':role,'work_function':work_function}
@app.patch('/api/v1/projects/{pid}/members/{member_id}/function')
def update_project_member_function(pid:str,member_id:str,b:ProjectMemberFunctionIn,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        target=c.execute('SELECT role,work_function FROM project_members WHERE project_id=? AND member_id=?',(pid,member_id)).fetchone()
        if not target: raise HTTPException(404,'Target is not a project member')
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        c.execute('UPDATE project_members SET work_function=? WHERE project_id=? AND member_id=?',(b.work_function,pid,member_id))
        event(c,'project.member.work_function_set',a['id'],None,{'project_id':pid,'member_id':member_id,'work_function':b.work_function},tenant_override=project['tenant_id'])
        return {'project_id':pid,'member_id':member_id,'project_role':target['role'],'work_function':b.work_function}

@app.post('/api/v1/projects/{pid}/role-change-requests')
def request_project_role_change(pid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization); member_id=str(b.get('member_id','')).strip(); new_role=str(b.get('new_role','')).strip()
    reason=str(b.get('reason','')).strip()
    if not member_id or new_role not in ('member','reviewer','manager') or not reason or len(reason)>1000:
        raise HTTPException(422,'member_id, valid new_role and reason (1-1000 chars) are required')
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        target=c.execute('SELECT tenant_id FROM members WHERE id=?',(member_id,)).fetchone()
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        if not target or target['tenant_id']!=project['tenant_id']: raise HTTPException(404,'Member not found in project tenant')
        if not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(pid,member_id)).fetchone(): raise HTTPException(404,'Target is not a project member')
        current=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,member_id)).fetchone()['role']
        if current==new_role: raise HTTPException(409,'Member already has requested role')
        aid='apr_'+uuid.uuid4().hex
        payload={'member_id':member_id,'previous_role':current,'new_role':new_role,'reason':reason}
        c.execute("INSERT INTO project_approvals(id,project_id,tenant_id,requester_member_id,action,payload,status,created_at) VALUES(?,?,?,?,? ,?,'PENDING',?)",
                  (aid,pid,project['tenant_id'],a['id'],'PROJECT_ROLE_CHANGE',json.dumps(payload),now()))
        event(c,'project.role_change.requested',a['id'],None,{'approval_id':aid,'project_id':pid,**payload},tenant_override=project['tenant_id'])
        return {'approval_id':aid,'status':'PENDING','project_id':pid,'payload':payload}

@app.get('/api/v1/projects/{pid}/approvals')
def list_project_approvals(pid:str,status:str='PENDING',limit:int=100,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,200))
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute('SELECT * FROM project_approvals WHERE project_id=? AND status=? ORDER BY created_at DESC LIMIT ?',(pid,status,limit)).fetchall()
        return {'items':[{'id':x['id'],'action':x['action'],'payload':json.loads(x['payload']),'status':x['status'],'requester_member_id':x['requester_member_id'],'decided_by':x['decided_by'],'decision_reason':x['decision_reason'],'created_at':x['created_at'],'decided_at':x['decided_at']} for x in rows]}

@app.post('/api/v1/projects/{pid}/approvals/{approval_id}/decision')
def decide_project_approval(pid:str,approval_id:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization); decision=str(b.get('decision','')).upper(); reason=str(b.get('reason','')).strip()
    if decision not in ('APPROVE','REJECT') or not reason or len(reason)>1000: raise HTTPException(422,'decision must be APPROVE or REJECT and reason is required')
    with conn() as c:
        require_project_access(c,pid,a)
        if not is_admin(a):
            own=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not own or own['role']!='owner': raise HTTPException(403,'Project owner approval required')
        row=c.execute('SELECT * FROM project_approvals WHERE id=? AND project_id=?',(approval_id,pid)).fetchone()
        if not row: raise HTTPException(404,'Approval not found')
        if row['status']!='PENDING': raise HTTPException(409,'Approval already decided')
        if row['requester_member_id']==a['id']: raise HTTPException(403,'Requester cannot approve their own request')
        payload=json.loads(row['payload'])
        if row['action']!='PROJECT_ROLE_CHANGE': raise HTTPException(409,'Unsupported approval action')
        if decision=='APPROVE':
            current=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,payload['member_id'])).fetchone()
            if not current or current['role']!=payload['previous_role']: raise HTTPException(409,'Target role changed since request; submit a new request')
            c.execute('UPDATE project_members SET role=? WHERE project_id=? AND member_id=?',(payload['new_role'],pid,payload['member_id']))
        stamp=now()
        approval_status='APPROVED' if decision=='APPROVE' else 'REJECTED'
        c.execute('UPDATE project_approvals SET status=?,decided_by=?,decision_reason=?,decided_at=? WHERE id=? AND status=?',(approval_status,a['id'],reason,stamp,approval_id,'PENDING'))
        event(c,'project.role_change.'+('approved' if decision=='APPROVE' else 'rejected'),a['id'],None,{'approval_id':approval_id,'project_id':pid,**payload,'decision_reason':reason},tenant_override=row['tenant_id'])
        return {'approval_id':approval_id,'status':approval_status,'member_id':payload['member_id'],'role':payload['new_role'] if decision=='APPROVE' else payload['previous_role']}

@app.get('/api/v1/requirements/{rid}/acceptance-report')
def requirement_acceptance_report(rid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        req=c.execute('SELECT * FROM requirements WHERE id=?',(rid,)).fetchone()
        if not req: raise HTTPException(404,'Requirement not found')
        require_project_access(c,req['project_id'],a)
        criteria=json.loads(req['acceptance_criteria'] or '[]')
        tasks=c.execute("SELECT t.id,t.title,t.status,t.progress,t.updated_at,(SELECT COUNT(*) FROM artifacts ar WHERE ar.task_id=t.id) AS artifact_count FROM tasks t WHERE t.requirement_id=? ORDER BY t.created_at,t.id",(rid,)).fetchall()
        items=[dict(x) for x in tasks]
        missing=[x['id'] for x in items if x['status']!='DONE' or x['artifact_count']<1]
        return {'requirement_id':rid,'project_id':req['project_id'],'title':req['title'],'status':req['status'],
            'acceptance_criteria':[{'index':i,'text':v} for i,v in enumerate(criteria)],'task_count':len(items),
            'tasks':items,'all_tasks_done':bool(items) and all(x['status']=='DONE' for x in items),
            'missing_delivery_evidence_task_ids':missing,'ready_for_acceptance':bool(items) and not missing and bool(criteria)}

@app.post('/api/v1/requirements/{rid}/acceptance')
def decide_requirement_acceptance(rid:str,b:RequirementAcceptanceIn,authorization:str=Header(None)):
    a=actor(authorization)
    if a.get('actor_type')=='AGENT': raise HTTPException(403,'Agent cannot approve or reject requirement acceptance')
    with conn() as c:
        req=c.execute('SELECT * FROM requirements WHERE id=?',(rid,)).fetchone()
        if not req: raise HTTPException(404,'Requirement not found')
        pid=req['project_id']; require_project_access(c,pid,a)
        if not is_admin(a):
            role=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not role or role['role'] not in ('owner','manager','reviewer'): raise HTTPException(403,'Reviewer role required')
        if req['status']=='ACCEPTED': raise HTTPException(409,'Requirement is already accepted')
        criteria=json.loads(req['acceptance_criteria'] or '[]')
        verified=list(dict.fromkeys(b.verified_criteria))
        if len(verified)!=len(b.verified_criteria): raise HTTPException(422,'verified_criteria must be unique')
        if any(i<0 or i>=len(criteria) for i in verified): raise HTTPException(422,'verified_criteria contains an unknown criterion index')
        tasks=c.execute("SELECT t.id,t.status,(SELECT COUNT(*) FROM artifacts ar WHERE ar.task_id=t.id) AS artifact_count FROM tasks t WHERE t.requirement_id=? ORDER BY t.id",(rid,)).fetchall()
        if b.decision=='APPROVE':
            if not criteria or verified!=list(range(len(criteria))): raise HTTPException(409,'Every acceptance criterion must be explicitly verified')
            pending=[x['id'] for x in tasks if x['status']!='DONE']
            missing=[x['id'] for x in tasks if x['artifact_count']<1]
            if not tasks or pending or missing: raise HTTPException(409,detail={'message':'Requirement cannot be accepted until every task is DONE and has delivery evidence','pending_task_ids':pending,'missing_artifact_task_ids':missing})
            status='ACCEPTED'
        else: status='OPEN'
        stamp=now(); c.execute('UPDATE requirements SET status=? WHERE id=?',(status,rid))
        tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id']
        payload={'project_id':pid,'requirement_id':rid,'decision':b.decision,'status':status,'verified_criteria':verified,
            'acceptance_criteria':criteria,'comment':b.comment,'task_ids':[x['id'] for x in tasks]}
        eid=event(c,'requirement.acceptance.'+b.decision.lower(),a['id'],None,payload,tenant_override=tenant)
        return {'requirement_id':rid,'status':status,'decision':b.decision,'event_id':eid,'decided_at':stamp,'verified_criteria':verified}

@app.post('/api/v1/projects/{pid}/decisions')
def record_project_decision(pid:str,b:ProjectDecisionIn,authorization:str=Header(None)):
    a=actor(authorization); decision_id='dec_'+uuid.uuid4().hex
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        accountable=c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(pid,b.accountable_member_id)).fetchone()
        if not accountable: raise HTTPException(422,'Accountable member must belong to this project')
        task_ids=list(dict.fromkeys(b.related_task_ids))
        if len(task_ids)!=len(b.related_task_ids): raise HTTPException(422,'related_task_ids must be unique')
        for task_id in task_ids:
            if task_project(c,task_id)!=pid: raise HTTPException(422,'Every related task must belong to this project')
        payload={'project_id':pid,'decision_id':decision_id,'title':b.title,'decision':b.decision,
            'rationale':b.rationale,'accountable_member_id':b.accountable_member_id,
            'related_task_ids':task_ids,'due_at':b.due_at,'recorded_by':a['id']}
        event(c,'project.decision.created',a['id'],None,payload)
    return {'id':decision_id,'project_id':pid,'status':'RECORDED','created_at':now(),**payload}

@app.get('/api/v1/projects/{pid}/decisions')
def list_project_decisions(pid:str,limit:int=100,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,500))
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("SELECT e.id,e.actor_member_id,e.payload,e.created_at,m.name AS actor_name FROM events e LEFT JOIN members m ON m.id=e.actor_member_id WHERE e.event_type='project.decision.created' AND e.payload LIKE ? ORDER BY e.created_at DESC LIMIT ?",('%"project_id"%"'+pid+'"%',limit)).fetchall()
        items=[]
        for row in rows:
            payload=json.loads(row['payload'] or '{}')
            if payload.get('project_id')!=pid: continue
            accountable=c.execute('SELECT name FROM members WHERE id=?',(payload.get('accountable_member_id'),)).fetchone()
            items.append({'id':payload.get('decision_id'),'title':payload.get('title'),'decision':payload.get('decision'),
                'rationale':payload.get('rationale',''),'accountable_member_id':payload.get('accountable_member_id'),
                'accountable_member_name':accountable['name'] if accountable else None,'related_task_ids':payload.get('related_task_ids',[]),
                'due_at':payload.get('due_at'),'recorded_by':row['actor_member_id'],'recorded_by_name':row['actor_name'],
                'created_at':row['created_at'],'audit_event_id':row['id']})
        return {'project_id':pid,'items':items,'count':len(items)}

@app.get('/api/v1/projects/{pid}/governance')
def project_governance_snapshot(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT t.id,t.status,t.progress,t.updated_at,a.member_id,m.name AS member_name
            FROM tasks t JOIN requirements r ON r.id=t.requirement_id
            LEFT JOIN assignments a ON a.task_id=t.id LEFT JOIN members m ON m.id=a.member_id
            WHERE r.project_id=? ORDER BY t.id""",(pid,)).fetchall()
        task_ids=set(); task_state={}
        for row in rows:
            task_ids.add(row['id'])
            task_state[row['id']]={'status':row['status'],'progress':row['progress']}
        total=len(task_ids)
        status_counts={}
        for item in task_state.values(): status_counts[item['status']]=status_counts.get(item['status'],0)+1
        responsibility={}
        for row in rows:
            if not row['member_id']: continue
            slot=responsibility.setdefault(row['member_id'],{'member_id':row['member_id'],'member_name':row['member_name'],'assigned_task_ids':[],'done':0,'active':0,'review':0,'blocked':0})
            if row['id'] not in slot['assigned_task_ids']:
                slot['assigned_task_ids'].append(row['id'])
                if row['status']=='DONE': slot['done']+=1
                elif row['status']=='REVIEW': slot['review']+=1
                elif row['status']=='BLOCKED': slot['blocked']+=1
                else: slot['active']+=1
        packages=c.execute("SELECT risk_state,COUNT(*) AS n FROM task_work_packages WHERE project_id=? AND status='ACTIVE' GROUP BY risk_state",(pid,)).fetchall()
        package_risks={x['risk_state']:x['n'] for x in packages}
        pending_reviews=status_counts.get('REVIEW',0)
        delivery_health=project_message_delivery_health(pid,authorization,120,300,500)
        review_rows=c.execute("""SELECT e.payload,e.created_at FROM events e
            WHERE e.event_type='message.delivery.incident.reviewed' AND e.payload LIKE ?
            ORDER BY e.created_at DESC LIMIT 1000""",('%'+pid+'%',)).fetchall()
        latest_reviews={}
        for review_row in review_rows:
            try:
                payload=json.loads(review_row['payload'] or '{}')
                if payload.get('project_id')!=pid: continue
                mid=payload.get('message_id')
                if mid and mid not in latest_reviews:
                    latest_reviews[mid]={'disposition':payload.get('disposition'),'comment':payload.get('comment'),
                                         'reviewed_at':review_row['created_at']}
            except (TypeError,ValueError):
                continue
        reviewed_incidents=[]
        open_incidents=0; resolved_incidents=0; accepted_risk_incidents=0; investigating_incidents=0
        for incident in delivery_health.get('incidents',[]):
            review=latest_reviews.get(incident['message_id'])
            disposition=review.get('disposition') if review else 'UNREVIEWED'
            item=dict(incident)
            item['review_disposition']=disposition
            item['reviewed_at']=review.get('reviewed_at') if review else None
            reviewed_incidents.append(item)
            if disposition=='RESOLVED': resolved_incidents+=1
            elif disposition=='ACCEPTED_RISK': accepted_risk_incidents+=1
            else:
                open_incidents+=1
                if disposition=='INVESTIGATING': investigating_incidents+=1
        daily=c.execute("""SELECT substr(m.created_at,1,10) AS day,COUNT(*) AS created,
            SUM(CASE WHEN m.status IN ('ACKNOWLEDGED','REJECTED') THEN 1 ELSE 0 END) AS terminal_ack
            FROM messages m JOIN tasks t ON t.id=m.task_id JOIN requirements r ON r.id=t.requirement_id
            WHERE r.project_id=? AND m.created_at>=? GROUP BY substr(m.created_at,1,10) ORDER BY day""",
            (pid,datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).isoformat())).fetchall()
        delivery_trend=[{'date':x['day'],'messages_created':x['created'],'terminal_ack':x['terminal_ack'] or 0} for x in daily]
        message_delivery_governance={
            'checked_messages':delivery_health.get('checked_messages',0),
            'dispatch_counts':delivery_health.get('dispatch_counts',{}),
            'ack_counts':delivery_health.get('ack_counts',{}),
            'incident_count':delivery_health.get('incident_count',0),
            'open_incidents':open_incidents,'investigating_incidents':investigating_incidents,
            'resolved_incidents':resolved_incidents,'accepted_risk_incidents':accepted_risk_incidents,
            'incidents':reviewed_incidents,'trend_since_utc_midnight':delivery_trend,
            'sla_policy':delivery_health.get('policy'),
            'truncated':delivery_health.get('truncated',False)
        }
        return {'project_id':pid,'task_total':total,'task_status_counts':status_counts,
            'completed_tasks':status_counts.get('DONE',0),'completion_percent':round(status_counts.get('DONE',0)*100/total) if total else 100,
            'pending_reviews':pending_reviews,'open_tasks':total-status_counts.get('DONE',0),
            'active_work_package_risk_counts':package_risks,
            'at_risk_work_packages':sum(package_risks.get(k,0) for k in ('OVERDUE','BLOCKED_DEPENDENCY','STALLED')),
            'responsibility':list(responsibility.values()),
            'completion_gate':'SATISFIED' if total and status_counts.get('DONE',0)==total else ('EMPTY' if not total else 'OPEN'),
            'message_delivery':message_delivery_governance}

@app.get('/api/v1/projects/{pid}/workflow')
def get_project_workflow(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        row=c.execute('SELECT config,updated_by,updated_at FROM project_workflows WHERE project_id=?',(pid,)).fetchone()
        if row: return {'project_id':pid,'config':json.loads(row['config']),'updated_by':row['updated_by'],'updated_at':row['updated_at']}
        return {'project_id':pid,'config':{'enabled':True,'stages':[{'key':'OPEN','name':'需求进入','order':1,'approval_role':'none','sla_seconds':None},{'key':'IN_PROGRESS','name':'执行','order':2,'approval_role':'none','sla_seconds':172800},{'key':'REVIEW','name':'评审验收','order':3,'approval_role':'reviewer','sla_seconds':86400},{'key':'DONE','name':'完成交付','order':4,'approval_role':'none','sla_seconds':None}]},'source':'system-default'}

@app.put('/api/v1/projects/{pid}/workflow')
def set_project_workflow(pid:str,b:WorkflowConfigIn,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        if not (a['role']=='admin' or project_role(c,pid,a) in ('owner','manager')): raise HTTPException(403,'Project manager or platform administrator required')
        stages=sorted([x.model_dump() for x in b.stages],key=lambda x:x['order'])
        if [x['order'] for x in stages] != list(range(1,len(stages)+1)): raise HTTPException(422,'Stage order must be contiguous from 1')
        if len({x['key'] for x in stages}) != len(stages): raise HTTPException(422,'Stage keys must be unique')
        if not any(x['key']=='REVIEW' for x in stages): raise HTTPException(422,'System governance requires a REVIEW stage')
        cfg={'enabled':b.enabled,'stages':stages}; stamp=now(); tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id']
        c.execute('INSERT INTO project_workflows(project_id,tenant_id,config,updated_by,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET config=excluded.config,updated_by=excluded.updated_by,updated_at=excluded.updated_at',(pid,tenant,json.dumps(cfg),a['id'],stamp))
        event(c,'project.workflow.updated',a['id'],None,{'project_id':pid,'config':cfg},tenant_override=tenant)
        return {'project_id':pid,'config':cfg,'updated_by':a['id'],'updated_at':stamp}

@app.get('/api/v1/projects/{pid}/gates')
def get_project_gates(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute('SELECT gate_key,config,updated_by,updated_at FROM project_gates WHERE project_id=? ORDER BY gate_key',(pid,)).fetchall()
        items={r['gate_key']:{'config':json.loads(r['config']),'updated_by':r['updated_by'],'updated_at':r['updated_at']} for r in rows}
        items.setdefault('REVIEW_REQUIRED',{'config':{'enabled':True,'required_roles':['reviewer'],'required_evidence':True,'required_all_tasks_done':False},'system_locked':True})
        items.setdefault('DELIVERY_EVIDENCE',{'config':{'enabled':True,'required_roles':['owner','manager','reviewer'],'required_evidence':True,'required_all_tasks_done':True},'system_locked':True})
        return {'project_id':pid,'gates':items}

@app.put('/api/v1/projects/{pid}/gates/{gate_key}')
def set_project_gate(pid:str,gate_key:str,b:GateConfigIn,authorization:str=Header(None)):
    a=actor(authorization)
    if gate_key in ('REVIEW_REQUIRED','DELIVERY_EVIDENCE'): raise HTTPException(409,'System governance gate cannot be disabled or weakened')
    if not re.fullmatch(r'[A-Z0-9_]{2,60}',gate_key): raise HTTPException(422,'Invalid gate key')
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        if not (a['role']=='admin' or project_role(c,pid,a) in ('owner','manager')): raise HTTPException(403,'Project manager or platform administrator required')
        cfg=b.model_dump(); cfg['applies_to']=cfg.get('applies_to') or 'DONE'; stamp=now(); tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id']
        c.execute('INSERT INTO project_gates(project_id,gate_key,tenant_id,config,updated_by,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(project_id,gate_key) DO UPDATE SET config=excluded.config,updated_by=excluded.updated_by,updated_at=excluded.updated_at',(pid,gate_key,tenant,json.dumps(cfg),a['id'],stamp))
        event(c,'project.gate.updated',a['id'],None,{'project_id':pid,'gate_key':gate_key,'config':cfg},tenant_override=tenant)
        return {'project_id':pid,'gate_key':gate_key,'config':cfg,'updated_at':stamp}


DEFAULT_PROJECT_WORKFLOW={'enabled':True,'stages':[{'key':'OPEN','name':'需求进入','order':1,'approval_role':'none','sla_seconds':None},{'key':'IN_PROGRESS','name':'执行','order':2,'approval_role':'none','sla_seconds':172800},{'key':'REVIEW','name':'评审验收','order':3,'approval_role':'reviewer','sla_seconds':86400},{'key':'DONE','name':'完成交付','order':4,'approval_role':'none','sla_seconds':None}]}
SYSTEM_GOVERNANCE_GATES={
    'REVIEW_REQUIRED':{'enabled':True,'required_roles':['reviewer'],'required_evidence':True,'required_all_tasks_done':False,'applies_to':'DONE'},
    'DELIVERY_EVIDENCE':{'enabled':True,'required_roles':['owner','manager','reviewer'],'required_evidence':True,'required_all_tasks_done':True,'applies_to':'DONE'}
}
def project_role(c,pid,actor_value):
    row=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,actor_value['id'])).fetchone()
    return row['role'] if row else None
def project_workflow_config(c,pid):
    row=c.execute('SELECT config FROM project_workflows WHERE project_id=?',(pid,)).fetchone()
    return json.loads(row['config']) if row else DEFAULT_PROJECT_WORKFLOW
def project_gate_config(c,pid,gate_key):
    if gate_key in SYSTEM_GOVERNANCE_GATES: return SYSTEM_GOVERNANCE_GATES[gate_key]
    row=c.execute('SELECT config FROM project_gates WHERE project_id=? AND gate_key=?',(pid,gate_key)).fetchone()
    return json.loads(row['config']) if row else None
def enforce_project_gate(c,pid,gate_key,actor_member_id,task_id=None,target_stage='DONE'):
    cfg=project_gate_config(c,pid,gate_key)
    if not cfg or not cfg.get('enabled',True) or cfg.get('applies_to','DONE')!=target_stage: return
    if cfg.get('required_roles'):
        platform=c.execute('SELECT role FROM members WHERE id=?',(actor_member_id,)).fetchone()
        if not platform or platform['role']!='admin':
            member_role=project_role(c,pid,{'id':actor_member_id})
            function_row=c.execute('SELECT work_function FROM project_members WHERE project_id=? AND member_id=?',(pid,actor_member_id)).fetchone()
            work_function=function_row['work_function'] if function_row else None
            if member_role not in cfg['required_roles'] and work_function not in cfg['required_roles']:
                raise HTTPException(403,f'Gate {gate_key} requires one of: {", ".join(cfg["required_roles"])}')
    if task_id and cfg.get('required_evidence'):
        if c.execute('SELECT 1 FROM artifacts WHERE task_id=? LIMIT 1',(task_id,)).fetchone() is None:
            raise HTTPException(409,detail={'message':f'Gate {gate_key} requires delivery evidence','gate_key':gate_key,'task_id':task_id})
    if task_id and cfg.get('required_all_tasks_done'):
        row=c.execute('SELECT requirement_id FROM tasks WHERE id=?',(task_id,)).fetchone()
        if row:
            pending=c.execute("SELECT id FROM tasks WHERE requirement_id=? AND status!='DONE' AND id!=?",(row['requirement_id'],task_id)).fetchall()
            if pending: raise HTTPException(409,detail={'message':f'Gate {gate_key} requires all other requirement tasks to be DONE before this task closes','gate_key':gate_key,'pending_task_ids':[x['id'] for x in pending]})
def enforce_workflow_exit(c,pid,current_stage,actor_member_id):
    cfg=project_workflow_config(c,pid)
    stage=next((x for x in cfg.get('stages',[]) if x.get('key')==current_stage),None)
    if not stage: raise HTTPException(409,detail={'message':'Current task status is not part of the configured workflow','current_stage':current_stage})
    approval_role=stage.get('approval_role','none')
    if approval_role!='none':
        platform=c.execute('SELECT role FROM members WHERE id=?',(actor_member_id,)).fetchone()
        if not platform or platform['role']!='admin':
            role=project_role(c,pid,{'id':actor_member_id})
            if role!=approval_role: raise HTTPException(403,f'Leaving workflow stage {current_stage} requires {approval_role} role')
def enforce_workflow_stage(c,pid,stage_key,actor_member_id,task_id=None):
    cfg=project_workflow_config(c,pid)
    stage=next((x for x in cfg.get('stages',[]) if x.get('key')==stage_key),None)
    if not stage: raise HTTPException(409,detail={'message':'Target workflow stage is not configured','stage_key':stage_key})
    for gate_key in [x['gate_key'] for x in c.execute('SELECT gate_key FROM project_gates WHERE project_id=?',(pid,)).fetchall()]:
        enforce_project_gate(c,pid,gate_key,actor_member_id,task_id,stage_key)
def transition_task_workflow(c,tid,target_stage,actor_member_id,comment=''):
    pid=task_project(c,tid)
    if not pid: raise HTTPException(404,'Task not found')
    task=c.execute('SELECT status,progress FROM tasks WHERE id=?',(tid,)).fetchone()
    if not task: raise HTTPException(404,'Task not found')
    enforce_workflow_stage(c,pid,target_stage,actor_member_id,tid)
    progress=100 if target_stage=='DONE' else (100 if target_stage=='REVIEW' else task['progress'])
    c.execute('UPDATE tasks SET status=?,progress=?,updated_at=? WHERE id=?',(target_stage,progress,now(),tid))
    eid=event(c,'task.workflow.transitioned',actor_member_id,tid,{'from_status':task['status'],'to_status':target_stage,'comment':comment})
    return eid

@app.get('/api/v1/projects/{pid}/audit')
def project_audit(pid:str,limit:int=100,before:str='',event_type:str='',authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,500))
    with conn() as c:
        require_project_access(c,pid,a)
        sql="SELECT e.* FROM events e LEFT JOIN tasks t ON t.id=e.task_id LEFT JOIN requirements r ON r.id=t.requirement_id WHERE (r.project_id=? OR (e.task_id IS NULL AND e.payload LIKE ?))"
        args=[pid,'%\"project_id\"%\"'+pid+'\"%']
        if before: sql+=" AND e.created_at<?"; args.append(before)
        if event_type: sql+=" AND e.event_type=?"; args.append(event_type)
        sql+=" ORDER BY e.created_at DESC LIMIT ?"; args.append(limit)
        rows=c.execute(sql,args).fetchall()
        return {'project_id':pid,'items':[{'id':x['id'],'event_type':x['event_type'],'actor_member_id':x['actor_member_id'],'task_id':x['task_id'],'payload':json.loads(x['payload'] or '{}'),'created_at':x['created_at']} for x in rows]}

@app.get('/api/v1/projects/{pid}/audit.csv')
def export_project_audit(pid:str,limit:int=5000,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,10000))
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT e.id,e.event_type,e.actor_member_id,e.task_id,e.payload,e.created_at
            FROM events e LEFT JOIN tasks t ON t.id=e.task_id LEFT JOIN requirements r ON r.id=t.requirement_id
            WHERE (r.project_id=? OR (e.task_id IS NULL AND e.payload LIKE ?)) ORDER BY e.created_at DESC LIMIT ?""",(pid,'%\"project_id\"%\"'+pid+'\"%',limit)).fetchall()
        def q(v): return '"'+str(v if v is not None else '').replace('"','""')+'"'
        lines=['id,event_type,actor_member_id,task_id,created_at,payload']
        for x in rows: lines.append(','.join(q(v) for v in (x['id'],x['event_type'],x['actor_member_id'],x['task_id'],x['created_at'],x['payload'])))
        return Response(content='\n'.join(lines)+'\n',media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="daep-audit-{pid}.csv"'})

@app.get('/api/v1/projects/{pid}/requirements')
def project_requirements(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        return [dict(x) for x in c.execute('SELECT * FROM requirements WHERE project_id=? ORDER BY created_at DESC',(pid,))]
@app.get('/api/v1/projects/{pid}/tasks')
def project_tasks(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute('SELECT t.* FROM tasks t JOIN requirements r ON r.id=t.requirement_id WHERE r.project_id=? ORDER BY t.created_at DESC',(pid,)).fetchall()
        result=[]
        for raw in rows:
            item=dict(raw)
            item['dependencies']=[x['depends_on_task_id'] for x in c.execute('SELECT depends_on_task_id FROM dependencies WHERE task_id=?',(item['id'],))]
            result.append(item)
        return result
@app.post('/api/v1/requirements')
def create_requirement(b:RequirementIn,authorization:str=Header(None)):
    a=actor(authorization); rid='req_'+uuid.uuid4().hex[:12]
    with conn() as c:
        if not c.execute('SELECT 1 FROM projects WHERE id=?',(b.project_id,)).fetchone(): raise HTTPException(404,'Project not found')
        require_project_access(c,b.project_id,a,write=True)
        c.execute('INSERT INTO requirements VALUES(?,?,?,?,?,?,?)',(rid,b.project_id,b.title,b.description,json.dumps(b.acceptance_criteria),'OPEN',now()))
    return {'id':rid,'project_id':b.project_id,'title':b.title,'status':'OPEN'}
@app.get('/api/v1/requirements/{rid}')
def get_requirement(rid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        r=c.execute('SELECT * FROM requirements WHERE id=?',(rid,)).fetchone()
        if r: require_project_access(c,r['project_id'],a)
        if not r: raise HTTPException(404,'Requirement not found')
        d=dict(r); d['acceptance_criteria']=json.loads(d['acceptance_criteria']); return d
@app.post('/api/v1/tasks')
def create_task(b:TaskIn,authorization:str=Header(None)):
    a=actor(authorization); tid='tsk_'+uuid.uuid4().hex[:12]
    with conn() as c:
        req=c.execute('SELECT * FROM requirements WHERE id=?',(b.requirement_id,)).fetchone()
        if not req: raise HTTPException(404,'Requirement not found')
        require_project_access(c,req['project_id'],a,write=True)
        for dep in b.dependencies:
            if dep == tid: raise HTTPException(400,'A task cannot depend on itself')
            if not c.execute('SELECT 1 FROM tasks WHERE id=?',(dep,)).fetchone(): raise HTTPException(400,f'Unknown dependency {dep}')
            require_task_access(c,dep,a)
            if task_project(c,dep) != req['project_id']: raise HTTPException(400,'Dependencies must belong to the same project')
        c.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?)',(tid,b.requirement_id,b.title,b.description,'READY',0,now(),now()))
        for mid in b.assignee_member_ids:
            member_row=c.execute('SELECT tenant_id FROM members WHERE id=?',(mid,)).fetchone()
            if not member_row: raise HTTPException(400,f'Unknown member {mid}')
            project_tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(req['project_id'],)).fetchone()['tenant_id']
            if member_row['tenant_id'] != project_tenant: raise HTTPException(400,'Assignee belongs to a different tenant')
            c.execute('INSERT INTO assignments VALUES(?,?)',(tid,mid))
            c.execute("INSERT OR IGNORE INTO project_members(project_id,member_id,role,work_function,joined_at) VALUES(?,?,?,'other',?)",(req['project_id'],mid,'member',now()))
        for dep in b.dependencies: c.execute('INSERT INTO dependencies VALUES(?,?)',(tid,dep))
        event(c,'task.created',a['id'],tid,{'title':b.title})
    return task_detail(tid,authorization)
def task_detail(tid,authorization):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a)
        r=c.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone()
        if not r: raise HTTPException(404,'Task not found')
        d=dict(r); d['assignees']=[dict(x) for x in c.execute('SELECT m.id,m.name FROM assignments a JOIN members m ON m.id=a.member_id JOIN tasks t ON t.id=a.task_id JOIN requirements rq ON rq.id=t.requirement_id JOIN projects p ON p.id=rq.project_id WHERE a.task_id=? AND m.tenant_id=p.tenant_id',(tid,))]; d['dependencies']=[x['depends_on_task_id'] for x in c.execute('SELECT depends_on_task_id FROM dependencies WHERE task_id=?',(tid,))]; return d
@app.get('/api/v1/tasks/{tid}')
def get_task(tid:str,authorization:str=Header(None)): return task_detail(tid,authorization)
@app.put('/api/v1/tasks/{tid}/dependencies')
def update_task_dependencies(tid:str,b:TaskDependenciesIn,authorization:str=Header(None)):
    a=actor(authorization)
    if len(set(b.dependencies)) != len(b.dependencies): raise HTTPException(400,'Duplicate dependencies are not allowed')
    with conn() as c:
        require_task_access(c,tid,a)
        project_id=task_project(c,tid)
        require_project_access(c,project_id,a,write=True)
        for dep in b.dependencies:
            if dep == tid: raise HTTPException(400,'A task cannot depend on itself')
            if task_project(c,dep) != project_id: raise HTTPException(400,'Dependencies must belong to the same project')
            require_task_access(c,dep,a)
            pending=[dep]; visited=set()
            while pending:
                current=pending.pop()
                if current == tid: raise HTTPException(409,'Dependency would create a cycle')
                if current in visited: continue
                visited.add(current)
                pending.extend(x['depends_on_task_id'] for x in c.execute('SELECT depends_on_task_id FROM dependencies WHERE task_id=?',(current,)).fetchall())
        c.execute('DELETE FROM dependencies WHERE task_id=?',(tid,))
        for dep in b.dependencies: c.execute('INSERT INTO dependencies(task_id,depends_on_task_id) VALUES(?,?)',(tid,dep))
        event(c,'task.dependencies.updated',a['id'],tid,{'dependencies':b.dependencies})
    return task_detail(tid,authorization)

@app.get('/api/v1/me/tasks')
def my_tasks(authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c: return [dict(x) for x in c.execute('SELECT t.* FROM tasks t JOIN assignments s ON s.task_id=t.id JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE s.member_id=? AND p.tenant_id=? ORDER BY t.created_at DESC',(a['id'],a.get('tenant_id','tenant-default')))]
@app.post('/api/v1/tasks/{tid}/progress')
def progress(tid:str,b:ProgressIn,authorization:str=Header(None),idempotency_key:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a,assigned_only=True)
        if b.progress==100:
            enforce_task_review_request(c,tid,a)
        identity=a.get('agent_id') if a.get('actor_type')=='AGENT' else a['id']
        scoped_key=f"{identity}:{tid}:{idempotency_key}" if idempotency_key else None
        if scoped_key:
            prior=c.execute('SELECT id,payload FROM events WHERE idempotency_key=?',(scoped_key,)).fetchone()
            if prior:
                prior_payload=json.loads(prior['payload'] or '{}')
                prior_payload.pop('actor_type',None); prior_payload.pop('agent_id',None)
                if prior_payload != b.model_dump(): raise HTTPException(409,'Idempotency-Key was already used with a different payload')
                return {'event_id':prior['id'],'task_id':tid,'progress':b.progress,'idempotent_replay':True}
        c.execute('UPDATE tasks SET progress=?,status=?,updated_at=? WHERE id=?',(b.progress,'REVIEW' if b.progress==100 else ('IN_PROGRESS' if b.progress>0 else 'READY'),now(),tid))
        eid=event(c,'task.progress.updated',a['id'],tid,b.model_dump(),scoped_key)
    return {'event_id':eid,'task_id':tid,'progress':b.progress}
@app.post('/api/v1/tasks/{tid}/blocked')
def blocked(tid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a,assigned_only=True)
        c.execute("UPDATE tasks SET status='BLOCKED',updated_at=? WHERE id=?",(now(),tid)); eid=event(c,'task.blocked',a['id'],tid,b)
    return {'event_id':eid,'status':'BLOCKED'}
@app.post('/api/v1/tasks/{tid}/work-result')
def report_work_result(tid:str,b:WorkResultIn,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        begin_serialized_write(c)
        require_task_access(c,tid,a,assigned_only=True)
        package_sql='SELECT id,parent_task_id,status,correlation_id FROM task_work_packages WHERE child_task_id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): package_sql += ' FOR UPDATE'
        package=c.execute(package_sql,(tid,)).fetchone()
        if not package: raise HTTPException(404,'Task is not a registered work package')
        identity=a.get('agent_id') if a.get('actor_type')=='AGENT' else a['id']
        key=f"work-result:{identity}:{tid}:{b.idempotency_key}" if b.idempotency_key else None
        payload={'outcome':b.outcome,'summary':b.summary,'work_package_id':package['id'],'correlation_id':package['correlation_id'],'parent_task_id':package['parent_task_id']}
        if key:
            prior=c.execute('SELECT id,payload FROM events WHERE idempotency_key=?',(key,)).fetchone()
            if prior:
                prior_payload=json.loads(prior['payload'] or '{}')
                prior_payload.pop('actor_type',None); prior_payload.pop('agent_id',None)
                if prior_payload!=payload: raise HTTPException(409,'Idempotency key was used with a different result')
                return {'task_id':tid,'status':'REVIEW' if b.outcome=='COMPLETE' else 'BLOCKED','event_id':prior['id'],'idempotent_replay':True}
        if package['status']!='ACTIVE': raise HTTPException(409,'Work package is no longer active')
        if b.outcome=='COMPLETE':
            count=c.execute('SELECT COUNT(*) AS n FROM artifacts WHERE task_id=?',(tid,)).fetchone()['n']
            if count<1: raise HTTPException(409,'Submit at least one artifact before reporting completion')
            status='REVIEW'; progress=100
        else:
            status='BLOCKED'; progress=0
        c.execute('UPDATE tasks SET status=?,progress=?,updated_at=? WHERE id=?',(status,progress,now(),tid))
        eid=event(c,'task.work_package.reported',a['id'],tid,payload,key)
    return {'task_id':tid,'status':status,'event_id':eid,'outcome':b.outcome}


@app.post('/api/v1/tasks/{tid}/workflow-transition')
def transition_task_workflow_endpoint(tid:str,b:dict,authorization:str=Header(None),idempotency_key:str=Header(None)):
    a=actor(authorization); target=str(b.get('target_stage','')).strip().upper(); comment=str(b.get('comment',''))[:4000]
    if not target: raise HTTPException(422,'target_stage is required')
    if target=='BLOCKED': raise HTTPException(409,'BLOCKED is controlled by the task blocked endpoint')
    with conn() as c:
        pid=task_project(c,tid)
        if not pid: raise HTTPException(404,'Task not found')
        cfg=project_workflow_config(c,pid)
        stage=next((x for x in cfg.get('stages',[]) if x.get('key')==target),None)
        if not stage: raise HTTPException(409,'Target workflow stage is not configured')
        current=c.execute('SELECT status FROM tasks WHERE id=?',(tid,)).fetchone()['status']
        if is_admin(a): pass
        elif current in ('REVIEW','DONE') or target in ('DONE',):
            require_project_access(c,pid,a,write=True)
        else:
            require_task_access(c,tid,a,assigned_only=True)
        scoped_key=f'workflow:{a["id"]}:{tid}:{idempotency_key}' if idempotency_key else None
        if scoped_key:
            prior=c.execute('SELECT id,payload FROM events WHERE idempotency_key=?',(scoped_key,)).fetchone()
            if prior:
                if prior['payload']!=json.dumps({'target_stage':target,'comment':comment}): raise HTTPException(409,'Idempotency-Key was already used with a different workflow transition')
                return {'task_id':tid,'target_stage':target,'event_id':prior['id'],'idempotent_replay':True}
        enforce_workflow_stage(c,pid,target,a['id'],tid)
        eid=transition_task_workflow(c,tid,target,a['id'],comment)
        if scoped_key:
            # The transition event itself is the idempotent record; attach a unique companion event only when needed.
            c.execute('UPDATE events SET idempotency_key=?,payload=? WHERE id=? AND idempotency_key IS NULL',(scoped_key,json.dumps({'target_stage':target,'comment':comment}),eid))
        return {'task_id':tid,'status':target,'event_id':eid}

@app.post('/api/v1/tasks/{tid}/artifacts')
def artifact(tid:str,b:ArtifactIn,authorization:str=Header(None)):
    a=actor(authorization); aid='art_'+uuid.uuid4().hex[:12]
    with conn() as c:
        require_task_access(c,tid,a,assigned_only=True)
        c.execute('INSERT INTO artifacts(id,task_id,artifact_type,uri,commit_sha,metadata,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',(aid,tid,b.artifact_type,b.uri,b.commit_sha,json.dumps(b.metadata),now(),c.execute('SELECT p.tenant_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE t.id=?',(tid,)).fetchone()['tenant_id'])); wp=c.execute('SELECT correlation_id,id FROM task_work_packages WHERE child_task_id=?',(tid,)).fetchone(); event(c,'artifact.submitted',a['id'],tid,{'artifact_id':aid,'uri':b.uri,'work_package_id':wp['id'] if wp else None,'correlation_id':wp['correlation_id'] if wp else None})
    return {'id':aid,'task_id':tid}
@app.post('/api/v1/tasks/{tid}/review')
def review_task(tid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization); decision=b.get('decision')
    if a.get('actor_type')=='AGENT': raise HTTPException(403,'Agent cannot review or approve tasks')
    if decision not in ('APPROVE','REJECT'): raise HTTPException(422,'decision must be APPROVE or REJECT')
    with conn() as c:
        begin_serialized_write(c)
        pid=task_project(c,tid)
        if not pid: raise HTTPException(404,'Task not found')
        if is_admin(a): pass
        else:
            row=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not row or row['role'] not in ('owner','manager','reviewer'): raise HTTPException(403,'Reviewer role required')
        task_sql='SELECT status FROM tasks WHERE id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): task_sql += ' FOR UPDATE'
        task=c.execute(task_sql,(tid,)).fetchone()
        if task['status']!='REVIEW': raise HTTPException(409,'Task is not awaiting review')
        if decision=='APPROVE':
            enforce_workflow_exit(c,pid,task['status'],a['id'])
            enforce_workflow_stage(c,pid,'DONE',a['id'],tid)
            packages=c.execute("SELECT w.child_task_id,t.status FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? AND w.status='ACTIVE'",(tid,)).fetchall()
            pending=[x['child_task_id'] for x in packages if x['status']!='DONE']
            missing=[x['child_task_id'] for x in packages if c.execute('SELECT 1 FROM artifacts WHERE task_id=? LIMIT 1',(x['child_task_id'],)).fetchone() is None]
            if pending or missing:
                raise HTTPException(409,detail={'message':'Parent task cannot be approved until every active work package is approved and has at least one artifact','pending_work_packages':pending,'missing_artifacts':missing})
        status='DONE' if decision=='APPROVE' else 'IN_PROGRESS'
        updated=c.execute('UPDATE tasks SET status=?,progress=?,updated_at=? WHERE id=? AND status=?',(status,100 if decision=='APPROVE' else 90,now(),tid,'REVIEW'))
        if updated.rowcount != 1: raise HTTPException(409,'Task is no longer awaiting review')
        eid=event(c,'task.reviewed',a['id'],tid,{'decision':decision,'comment':b.get('comment','')})
        return {'task_id':tid,'status':status,'event_id':eid}

@app.post('/api/v1/work-packages/{package_id}/review')
def review_work_package(package_id:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization)
    if a.get('actor_type')=='AGENT': raise HTTPException(403,'Agent cannot review or approve work packages')
    decision=str(b.get('decision','')).strip().upper()
    comment=str(b.get('comment',''))[:4000]
    if decision not in ('APPROVE','REJECT'): raise HTTPException(422,'decision must be APPROVE or REJECT')
    with conn() as c:
        begin_serialized_write(c)
        package_sql='SELECT w.*,t.status AS task_status,t.progress FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): package_sql += ' FOR UPDATE'
        package=c.execute(package_sql,(package_id,)).fetchone()
        if not package: raise HTTPException(404,'Work package not found')
        pid=package['project_id']
        if is_admin(a): pass
        else:
            row=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not row or row['role'] not in ('owner','manager','reviewer'): raise HTTPException(403,'Reviewer role required')
        if package['status']!='ACTIVE': raise HTTPException(409,'Work package is no longer active')
        if package['task_status']!='REVIEW': raise HTTPException(409,'Work package is not awaiting review')
        stamp=now()
        if decision=='APPROVE':
            enforce_workflow_exit(c,pid,package['task_status'],a['id'])
            enforce_workflow_stage(c,pid,'DONE',a['id'],package['child_task_id'])
            if c.execute('SELECT 1 FROM artifacts WHERE task_id=? LIMIT 1',(package['child_task_id'],)).fetchone() is None:
                raise HTTPException(409,'Work package must have at least one artifact before approval')
            status='DONE'; progress=100
        else:
            status='IN_PROGRESS'; progress=90
        updated=c.execute('UPDATE tasks SET status=?,progress=?,updated_at=? WHERE id=? AND status=?',(status,progress,stamp,package['child_task_id'],'REVIEW'))
        if updated.rowcount != 1: raise HTTPException(409,'Work package task is no longer awaiting review')
        eid=event(c,'task.work_package.reviewed',a['id'],package['child_task_id'],{'work_package_id':package_id,'parent_task_id':package['parent_task_id'],'decision':decision,'comment':comment})
        return {'work_package_id':package_id,'task_id':package['child_task_id'],'status':status,'progress':progress,'event_id':eid,'decision':decision}

@app.post('/api/v1/tasks/{parent_id}/work-packages')
def create_work_package(parent_id:str,b:WorkPackageIn,authorization:str=Header(None)):
    a=actor(authorization); child_id='tsk_'+uuid.uuid4().hex[:12]; package_id='wpk_'+uuid.uuid4().hex
    agent_name=b.agent_name.strip()
    if not agent_name: raise HTTPException(422,'agent_name must not be blank')
    with conn() as c:
        require_task_access(c,parent_id,a)
        project_id=task_project(c,parent_id)
        require_project_access(c,project_id,a,write=True)
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(project_id,)).fetchone()
        member=c.execute('SELECT tenant_id FROM members WHERE id=?',(b.assignee_member_id,)).fetchone()
        if not member or member['tenant_id']!=project['tenant_id']: raise HTTPException(404,'Assignee not found in this tenant')
        if not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(project_id,b.assignee_member_id)).fetchone(): raise HTTPException(400,'Assignee is not a project member')
        agent=c.execute('SELECT status,last_seen FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(project_id,b.assignee_member_id,agent_name)).fetchone()
        if not agent: raise HTTPException(404,'Assignee Agent is not registered in this project')
        if agent['status']=='OFFLINE' or agent['last_seen'] < datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat(): raise HTTPException(409,'Assignee Agent presence is offline or stale')
        for dep in b.dependencies:
            if dep==parent_id or not c.execute('SELECT 1 FROM tasks WHERE id=?',(dep,)).fetchone(): raise HTTPException(400,'Invalid dependency')
            require_task_access(c,dep,a)
            if task_project(c,dep)!=project_id: raise HTTPException(400,'Dependencies must belong to the same project')
        req=c.execute('SELECT r.id FROM tasks t JOIN requirements r ON r.id=t.requirement_id WHERE t.id=?',(parent_id,)).fetchone()
        if not req: raise HTTPException(409,'Create a requirement before adding work packages')
        stamp=now()
        c.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?)',(child_id,req['id'],b.title,b.description,'READY',0,stamp,stamp))
        c.execute('INSERT INTO assignments(task_id,member_id) VALUES(?,?)',(child_id,b.assignee_member_id))
        for dep in b.dependencies: c.execute('INSERT INTO dependencies(task_id,depends_on_task_id) VALUES(?,?)',(child_id,dep))
        correlation_id='corr_'+uuid.uuid4().hex
        sla_due_at=datetime.fromtimestamp(datetime.fromisoformat(stamp).timestamp()+b.sla_seconds,timezone.utc).isoformat() if b.sla_seconds else None
        c.execute('INSERT INTO task_work_packages(id,parent_task_id,child_task_id,project_id,tenant_id,assignee_member_id,agent_name,status,created_at,updated_at,correlation_id,sla_due_at,risk_state) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(package_id,parent_id,child_id,project_id,project['tenant_id'],b.assignee_member_id,agent_name,'ACTIVE',stamp,stamp,correlation_id,sla_due_at,'ON_TRACK'))
        mid='msg_'+uuid.uuid4().hex[:12]
        title='Work package assigned: '+b.title
        content=json.dumps({'work_package_id':package_id,'correlation_id':correlation_id,'parent_task_id':parent_id,'task_id':child_id,'agent_name':agent_name,'title':b.title,'sla_due_at':sla_due_at},ensure_ascii=False)
        c.execute('INSERT INTO messages(id,recipient_member_id,tenant_id,task_id,message_type,title,content,priority,status,created_at,acked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(mid,b.assignee_member_id,project['tenant_id'],child_id,'WORK_PACKAGE_ASSIGNED',title,content,'HIGH','PENDING',stamp,None))
        payload={'message_id':mid,'recipient_member_id':b.assignee_member_id,'project_id':project_id,'task_id':child_id,'message_type':'WORK_PACKAGE_ASSIGNED','title':title,'content':content,'priority':'HIGH'}
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',('obx_'+uuid.uuid4().hex,'message.created',json.dumps(payload),'PENDING',0,stamp,stamp,project['tenant_id']))
        event(c,'task.work_package.created',a['id'],parent_id,{'work_package_id':package_id,'correlation_id':correlation_id,'child_task_id':child_id,'assignee_member_id':b.assignee_member_id,'agent_name':agent_name,'sla_due_at':sla_due_at,'sla_seconds':b.sla_seconds})
    return {'id':package_id,'correlation_id':correlation_id,'parent_task_id':parent_id,'task_id':child_id,'assignee_member_id':b.assignee_member_id,'agent_name':agent_name,'status':'ACTIVE','sla_due_at':sla_due_at,'risk_state':'ON_TRACK','message_id':mid}

@app.get('/api/v1/tasks/{parent_id}/work-packages')
def list_work_packages(parent_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,parent_id,a)
        rows=c.execute('SELECT w.*,t.title,t.description,t.status AS task_status,t.progress,t.updated_at AS task_updated_at FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? ORDER BY w.created_at',(parent_id,)).fetchall()
        result=[]
        for raw in rows:
            row=dict(raw)
            row['artifacts']=[dict(x) for x in c.execute('SELECT id,artifact_type,uri,commit_sha,created_at FROM artifacts WHERE task_id=? ORDER BY created_at',(row['child_task_id'],))]
            result.append(row)
        return result

@app.get('/api/v1/tasks/{parent_id}/work-summary')
def work_package_summary(parent_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,parent_id,a)
        rows=c.execute("SELECT t.status,t.progress FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? AND w.status='ACTIVE'",(parent_id,)).fetchall()
        total=len(rows)
        counts={k:sum(1 for x in rows if x['status']==k) for k in ('READY','IN_PROGRESS','BLOCKED','REVIEW','DONE')}
        progress=round(sum(int(x['progress'] or 0) for x in rows)/total) if total else 0
        artifacts=c.execute('SELECT COUNT(*) AS n FROM artifacts a JOIN task_work_packages w ON w.child_task_id=a.task_id WHERE w.parent_task_id=? AND w.status=\'ACTIVE\'',(parent_id,)).fetchone()['n']
        blocked=c.execute("SELECT t.id,t.title,t.status FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? AND w.status='ACTIVE' AND t.status='BLOCKED'",(parent_id,)).fetchall()
        artifact_rows=c.execute('SELECT w.child_task_id,a.id,a.artifact_type,a.uri,a.commit_sha,a.created_at FROM task_work_packages w JOIN artifacts a ON a.task_id=w.child_task_id WHERE w.parent_task_id=? AND w.status=\'ACTIVE\' ORDER BY a.created_at',(parent_id,)).fetchall()
        return {'parent_task_id':parent_id,'work_package_count':total,'progress':progress,'status_counts':counts,'blocked_tasks':[dict(x) for x in blocked],'artifact_count':artifacts,'artifacts':[dict(x) for x in artifact_rows],'all_done':bool(total and counts['DONE']==total)}

@app.get('/api/v1/tasks/{parent_id}/work-timeline')
def work_package_timeline(parent_id:str,limit:int=200,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,500))
    with conn() as c:
        require_task_access(c,parent_id,a)
        packages=c.execute('SELECT w.*,t.title,t.status AS task_status,t.progress FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? ORDER BY w.created_at',(parent_id,)).fetchall()
        items=[]
        task_ids=[parent_id]+[w['child_task_id'] for w in packages]
        for e in c.execute("""SELECT e.*,m.name AS actor_name FROM events e
            LEFT JOIN members m ON m.id=e.actor_member_id WHERE e.task_id=? ORDER BY e.created_at""",(parent_id,)).fetchall():
            p=json.loads(e['payload'] or '{}')
            items.append({'occurred_at':e['created_at'],'kind':'event','event_type':e['event_type'],
                'task_id':parent_id,'event_id':e['id'],'actor_member_id':e['actor_member_id'],
                'actor_name':e['actor_name'],'payload':p})
        for w in packages:
            cid=w['correlation_id'] or w['id']; child=w['child_task_id']
            for e in c.execute("""SELECT e.*,m.name AS actor_name FROM events e
                LEFT JOIN members m ON m.id=e.actor_member_id WHERE e.task_id=? ORDER BY e.created_at""",(child,)).fetchall():
                p=json.loads(e['payload'] or '{}')
                items.append({'occurred_at':e['created_at'],'kind':'event','event_type':e['event_type'],
                    'task_id':child,'event_id':e['id'],'actor_member_id':e['actor_member_id'],
                    'actor_name':e['actor_name'],'correlation_id':cid,'payload':p})
            for msg in c.execute('SELECT id,message_type,title,status,created_at,acked_at,content FROM messages WHERE task_id=? ORDER BY created_at',(child,)).fetchall():
                try: body=json.loads(msg['content'] or '{}')
                except Exception: body={'content':msg['content']}
                items.append({'occurred_at':msg['created_at'],'kind':'message','message_id':msg['id'],
                    'message_type':msg['message_type'],'title':msg['title'],'status':msg['status'],
                    'acked_at':msg['acked_at'],'task_id':child,'correlation_id':body.get('correlation_id',cid),'payload':body})
            for art in c.execute('SELECT id,artifact_type,uri,commit_sha,created_at FROM artifacts WHERE task_id=? ORDER BY created_at',(child,)).fetchall():
                items.append({'occurred_at':art['created_at'],'kind':'artifact','task_id':child,'correlation_id':cid,'artifact':dict(art)})
        marks=','.join('?' for _ in task_ids)
        delegations=c.execute(f"""SELECT d.*,rq.name AS requester_name,rc.name AS recipient_name
            FROM task_delegations d JOIN members rq ON rq.id=d.requester_member_id
            JOIN members rc ON rc.id=d.recipient_member_id
            WHERE d.task_id IN ({marks}) ORDER BY d.created_at""",tuple(task_ids)).fetchall()
        for d in delegations:
            row=dict(d)
            items.append({'occurred_at':row['created_at'],'kind':'delegation','stage':'OFFERED',
                'task_id':row['task_id'],'delegation_id':row['id'],'status':row['status'],
                'requester_member_id':row['requester_member_id'],'requester_name':row['requester_name'],
                'recipient_member_id':row['recipient_member_id'],'recipient_name':row['recipient_name'],
                'agent_name':row['agent_name'],'reason':row['reason'],'expires_at':row['expires_at']})
            if row['status']!='PENDING':
                decision_at=row['responded_at'] or row['updated_at']
                items.append({'occurred_at':decision_at,'kind':'delegation','stage':row['status'],
                    'task_id':row['task_id'],'delegation_id':row['id'],'status':row['status'],
                    'requester_member_id':row['requester_member_id'],'requester_name':row['requester_name'],
                    'recipient_member_id':row['recipient_member_id'],'recipient_name':row['recipient_name'],
                    'agent_name':row['agent_name'],'reason':row['reason'],'expires_at':row['expires_at']})
        dependency_edges=[]
        for tid in task_ids:
            task=c.execute('SELECT title FROM tasks WHERE id=?',(tid,)).fetchone()
            for dep in c.execute("""SELECT d.depends_on_task_id,t.title AS depends_on_title,t.status AS depends_on_status
                FROM dependencies d JOIN tasks t ON t.id=d.depends_on_task_id WHERE d.task_id=?""",(tid,)).fetchall():
                dependency_edges.append({'task_id':tid,'task_title':task['title'] if task else tid,
                    'depends_on_task_id':dep['depends_on_task_id'],'depends_on_title':dep['depends_on_title'],
                    'depends_on_status':dep['depends_on_status'],'blocked':dep['depends_on_status']!='DONE'})
        items.sort(key=lambda x:(x['occurred_at'],x.get('event_id') or x.get('message_id') or x.get('delegation_id') or x.get('artifact',{}).get('id','')))
        items=items[-limit:]
        return {'parent_task_id':parent_id,'count':len(items),'items':items,
            'dependency_edges':dependency_edges,
            'delegations':[{'id':d['id'],'task_id':d['task_id'],'requester_member_id':d['requester_member_id'],
                'requester_name':d['requester_name'],'recipient_member_id':d['recipient_member_id'],
                'recipient_name':d['recipient_name'],'agent_name':d['agent_name'],'reason':d['reason'],
                'status':d['status'],'created_at':d['created_at'],'responded_at':d['responded_at'],
                'expires_at':d['expires_at']} for d in delegations],
            'work_packages':[{'id':w['id'],'correlation_id':w['correlation_id'] or w['id'],
                'child_task_id':w['child_task_id'],'title':w['title'],'status':w['task_status'],
                'progress':w['progress'],'assignee_member_id':w['assignee_member_id'],'agent_name':w['agent_name'],
                'sla_due_at':w['sla_due_at'],'risk_state':w['risk_state'],'needs_attention':bool(w['needs_attention'])}
                for w in packages]}
@app.post('/api/v1/projects/{pid}/work-packages/scan-health')
def scan_project_work_health(pid:str,authorization:str=Header(None)):
    a=actor(authorization); stamp=now()
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        rows=c.execute("""SELECT w.id,w.parent_task_id,w.child_task_id,w.correlation_id,w.sla_due_at,w.risk_state,w.needs_attention,
        t.title,t.status AS task_status FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id
        WHERE w.project_id=? AND w.status='ACTIVE' ORDER BY w.created_at""",(pid,)).fetchall()
        changed=[]; counts={'ON_TRACK':0,'OVERDUE':0,'BLOCKED_DEPENDENCY':0,'STALLED':0,'IN_REVIEW':0,'COMPLETED':0}
        for row in rows:
            blockers=c.execute("""SELECT d.depends_on_task_id,t.title,t.status FROM dependencies d
                JOIN tasks t ON t.id=d.depends_on_task_id WHERE d.task_id=? AND t.status!='DONE'""",(row['child_task_id'],)).fetchall()
            if row['task_status']=='DONE': risk='COMPLETED'
            elif row['task_status']=='REVIEW': risk='IN_REVIEW'
            elif blockers: risk='BLOCKED_DEPENDENCY'
            elif row['needs_attention']: risk='STALLED'
            elif row['sla_due_at'] and row['sla_due_at']<=stamp: risk='OVERDUE'
            else: risk='ON_TRACK'
            if risk!=row['risk_state']:
                c.execute('UPDATE task_work_packages SET risk_state=?,updated_at=? WHERE id=?',(risk,stamp,row['id']))
                detail={'work_package_id':row['id'],'correlation_id':row['correlation_id'],'child_task_id':row['child_task_id'],'previous_risk_state':row['risk_state'],'risk_state':risk,'sla_due_at':row['sla_due_at'],'blocking_dependencies':[dict(x) for x in blockers]}
                event(c,'task.work_package.risk_changed',a['id'],row['parent_task_id'],detail)
                changed.append(detail)
            counts[risk]=counts.get(risk,0)+1
        return {'project_id':pid,'scanned_count':len(rows),'changed_count':len(changed),'risk_counts':counts,'changes':changed}

@app.get('/api/v1/projects/{pid}/work-health')
def project_work_health(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT w.id,w.parent_task_id,w.child_task_id,w.correlation_id,w.assignee_member_id,w.agent_name,
            w.sla_due_at,w.risk_state,w.needs_attention,t.title,t.status AS task_status,t.progress,t.updated_at
            FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id
            WHERE w.project_id=? AND w.status='ACTIVE' ORDER BY w.created_at""",(pid,)).fetchall()
        counts={}
        items=[]
        for row in rows:
            risk=row['risk_state']; counts[risk]=counts.get(risk,0)+1
            blockers=c.execute("""SELECT d.depends_on_task_id,t.title,t.status FROM dependencies d
                JOIN tasks t ON t.id=d.depends_on_task_id WHERE d.task_id=? AND t.status!='DONE'""",(row['child_task_id'],)).fetchall()
            items.append({'work_package_id':row['id'],'parent_task_id':row['parent_task_id'],'child_task_id':row['child_task_id'],
                'correlation_id':row['correlation_id'],'title':row['title'],'task_status':row['task_status'],'progress':row['progress'],
                'assignee_member_id':row['assignee_member_id'],'agent_name':row['agent_name'],'sla_due_at':row['sla_due_at'],
                'risk_state':risk,'needs_attention':bool(row['needs_attention']),'blocking_dependencies':[dict(x) for x in blockers],
                'last_activity_at':row['updated_at']})
        total=len(items); at_risk=sum(counts.get(k,0) for k in ('OVERDUE','BLOCKED_DEPENDENCY','STALLED'))
        return {'project_id':pid,'work_package_count':total,'at_risk_count':at_risk,
            'health_score':round(100*(total-at_risk)/total) if total else 100,
            'risk_counts':counts,'items':items}

@app.get('/api/v1/projects/{pid}/coordination')
def project_coordination_center(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        packages=c.execute("""SELECT w.id AS work_package_id,w.parent_task_id,w.child_task_id,w.assignee_member_id,w.agent_name,
            w.sla_due_at,w.risk_state,w.needs_attention,w.stall_reason,w.stalled_at,t.title,t.status AS task_status,
            t.progress,t.updated_at,m.name AS assignee_name
            FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id
            LEFT JOIN members m ON m.id=w.assignee_member_id
            WHERE w.project_id=? AND w.status='ACTIVE'
            AND (w.needs_attention=1 OR w.risk_state IN ('OVERDUE','BLOCKED_DEPENDENCY','STALLED','IN_REVIEW'))
            ORDER BY CASE w.risk_state WHEN 'OVERDUE' THEN 0 WHEN 'STALLED' THEN 1 WHEN 'BLOCKED_DEPENDENCY' THEN 2 WHEN 'IN_REVIEW' THEN 3 ELSE 4 END,w.updated_at""",(pid,)).fetchall()
        package_items=[]
        for row in packages:
            blockers=c.execute("""SELECT d.depends_on_task_id,t.title,t.status FROM dependencies d
                JOIN tasks t ON t.id=d.depends_on_task_id WHERE d.task_id=? AND t.status!='DONE'""",(row['child_task_id'],)).fetchall()
            agent=c.execute('SELECT status,last_seen FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(pid,row['assignee_member_id'],row['agent_name'])).fetchone()
            package_items.append({**dict(row),'blocking_dependencies':[dict(x) for x in blockers],
                'agent_status':agent['status'] if agent else 'NOT_REGISTERED','agent_last_seen':agent['last_seen'] if agent else None})
        unclaimed=c.execute("""SELECT t.id AS task_id,t.title,t.status,t.progress,t.updated_at
            FROM tasks t JOIN requirements r ON r.id=t.requirement_id
            LEFT JOIN assignments a ON a.task_id=t.id
            WHERE r.project_id=? AND t.status!='DONE' AND a.task_id IS NULL
            AND NOT EXISTS (SELECT 1 FROM task_work_packages w WHERE w.child_task_id=t.id AND w.status='ACTIVE')
            ORDER BY t.updated_at""",(pid,)).fetchall()
        reviews=c.execute("""SELECT t.id AS task_id,t.title,t.progress,t.updated_at,
            (SELECT COUNT(*) FROM artifacts ar WHERE ar.task_id=t.id) AS artifact_count
            FROM tasks t JOIN requirements r ON r.id=t.requirement_id
            WHERE r.project_id=? AND t.status='REVIEW' ORDER BY t.updated_at""",(pid,)).fetchall()
        delegations=c.execute("""SELECT d.id,d.task_id,d.status,d.requester_member_id,d.recipient_member_id,
            d.agent_name,d.reason,d.created_at,d.expires_at,t.title AS task_title,
            rq.name AS requester_name,rc.name AS recipient_name
            FROM task_delegations d JOIN tasks t ON t.id=d.task_id
            JOIN members rq ON rq.id=d.requester_member_id JOIN members rc ON rc.id=d.recipient_member_id
            WHERE d.project_id=? AND d.status='PENDING' ORDER BY d.created_at""",(pid,)).fetchall()
        return {'project_id':pid,'exception_work_packages':[dict(x) for x in package_items],
            'unclaimed_tasks':[dict(x) for x in unclaimed],'pending_reviews':[dict(x) for x in reviews],
            'pending_delegations':[dict(x) for x in delegations],
            'counts':{'exception_work_packages':len(package_items),'unclaimed_tasks':len(unclaimed),
                'pending_reviews':len(reviews),'pending_delegations':len(delegations)}}

@app.post('/api/v1/projects/{pid}/work-packages/scan-stalled')
def scan_stalled_work_packages(pid:str,b:WorkPackageScanIn,authorization:str=Header(None)):
    a=actor(authorization)
    cutoff=datetime.fromtimestamp(time.time()-b.stale_after_seconds,timezone.utc).isoformat()
    stamp=now()
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        rows=c.execute("""SELECT w.id,w.parent_task_id,w.child_task_id,w.assignee_member_id,t.status,t.updated_at,t.title
        FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id
        WHERE w.project_id=? AND w.status='ACTIVE' AND w.needs_attention=0
        AND t.status IN ('READY','IN_PROGRESS','BLOCKED') AND t.updated_at<=?""",(pid,cutoff)).fetchall()
        marked=[]
        for row in rows:
            reason=f"No task activity for at least {b.stale_after_seconds} seconds"
            changed=c.execute('UPDATE task_work_packages SET needs_attention=1,stalled_at=?,stall_reason=?,updated_at=? WHERE id=? AND needs_attention=0',(stamp,reason,stamp,row['id']))
            if changed.rowcount:
                event(c,'task.work_package.stalled',a['id'],row['parent_task_id'],{'work_package_id':row['id'],'correlation_id':c.execute('SELECT correlation_id FROM task_work_packages WHERE id=?',(row['id'],)).fetchone()['correlation_id'],'child_task_id':row['child_task_id'],'assignee_member_id':row['assignee_member_id'],'stalled_at':stamp,'reason':reason})
                marked.append({'work_package_id':row['id'],'child_task_id':row['child_task_id'],'title':row['title'],'task_status':row['status'],'assignee_member_id':row['assignee_member_id'],'stalled_at':stamp,'reason':reason})
    return {'project_id':pid,'stale_after_seconds':b.stale_after_seconds,'marked_count':len(marked),'items':marked}

@app.post('/api/v1/work-packages/{package_id}/reassign')
def reassign_work_package(package_id:str,b:WorkPackageReassignIn,authorization:str=Header(None)):
    a=actor(authorization); agent_name=b.agent_name.strip()
    if not agent_name: raise HTTPException(422,'agent_name must not be blank')
    with conn() as c:
        begin_serialized_write(c)
        package_sql='SELECT * FROM task_work_packages WHERE id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): package_sql += ' FOR UPDATE'
        package=c.execute(package_sql,(package_id,)).fetchone()
        if not package: raise HTTPException(404,'Work package not found')
        require_project_access(c,package['project_id'],a,write=True)
        if package['status']!='ACTIVE': raise HTTPException(409,'Only active work packages can be reassigned')
        if not package['needs_attention']: raise HTTPException(409,'Work package must be marked stalled before reassignment')
        if package['assignee_member_id']==b.assignee_member_id and package['agent_name']==agent_name:
            raise HTTPException(400,'Choose a different assignee or Agent')
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(package['project_id'],)).fetchone()
        member=c.execute('SELECT tenant_id FROM members WHERE id=?',(b.assignee_member_id,)).fetchone()
        if not member or member['tenant_id']!=project['tenant_id']: raise HTTPException(404,'New assignee not found in this tenant')
        if not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(package['project_id'],b.assignee_member_id)).fetchone():
            raise HTTPException(400,'New assignee is not a project member')
        agent=c.execute('SELECT status,last_seen FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(package['project_id'],b.assignee_member_id,agent_name)).fetchone()
        cutoff=datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat()
        if not agent: raise HTTPException(404,'New assignee Agent is not registered in this project')
        if agent['status']=='OFFLINE' or agent['last_seen']<cutoff: raise HTTPException(409,'New assignee Agent presence is offline or stale')
        stamp=now()
        c.execute('DELETE FROM assignments WHERE task_id=? AND member_id=?',(package['child_task_id'],package['assignee_member_id']))
        c.execute('INSERT OR IGNORE INTO assignments(task_id,member_id) VALUES(?,?)',(package['child_task_id'],b.assignee_member_id))
        c.execute('UPDATE task_work_packages SET assignee_member_id=?,agent_name=?,needs_attention=0,stalled_at=NULL,stall_reason=NULL,updated_at=? WHERE id=?',(b.assignee_member_id,agent_name,stamp,package_id))
        c.execute('UPDATE tasks SET updated_at=? WHERE id=?',(stamp,package['child_task_id']))
        mid='msg_'+uuid.uuid4().hex[:12]
        title='Work package reassigned: '+package['child_task_id']
        content=json.dumps({'work_package_id':package_id,'correlation_id':package['correlation_id'],'parent_task_id':package['parent_task_id'],'task_id':package['child_task_id'],'previous_assignee_member_id':package['assignee_member_id'],'assignee_member_id':b.assignee_member_id,'agent_name':agent_name,'reason':b.reason},ensure_ascii=False)
        c.execute('INSERT INTO messages(id,recipient_member_id,tenant_id,task_id,message_type,title,content,priority,status,created_at,acked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(mid,b.assignee_member_id,project['tenant_id'],package['child_task_id'],'WORK_PACKAGE_REASSIGNED',title,content,'HIGH','PENDING',stamp,None))
        payload={'message_id':mid,'recipient_member_id':b.assignee_member_id,'project_id':package['project_id'],'task_id':package['child_task_id'],'message_type':'WORK_PACKAGE_REASSIGNED','title':title,'content':content,'priority':'HIGH'}
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',('obx_'+uuid.uuid4().hex,'message.created',json.dumps(payload),'PENDING',0,stamp,stamp,project['tenant_id']))
        eid=event(c,'task.work_package.reassigned',a['id'],package['parent_task_id'],{'work_package_id':package_id,'correlation_id':package['correlation_id'],'child_task_id':package['child_task_id'],'previous_assignee_member_id':package['assignee_member_id'],'assignee_member_id':b.assignee_member_id,'previous_agent_name':package['agent_name'],'agent_name':agent_name,'reason':b.reason})
    return {'work_package_id':package_id,'task_id':package['child_task_id'],'assignee_member_id':b.assignee_member_id,'agent_name':agent_name,'needs_attention':False,'message_id':mid,'event_id':eid}

@app.post('/api/v1/projects/{pid}/agents/register')
def register_project_agent(pid:str,b:AgentPresenceIn,authorization:str=Header(None)):
    a=actor(authorization)
    agent_name=b.agent_name.strip()
    if not agent_name: raise HTTPException(422,'agent_name must not be blank')
    clean_caps=sorted({str(x).strip().lower() for x in b.capabilities if str(x).strip()})
    clean_protocols=sorted({str(x).strip().lower() for x in b.protocols if str(x).strip()})
    if any(len(x)>80 for x in clean_caps) or any(len(x)>40 for x in clean_protocols):
        raise HTTPException(422,'Capability or protocol identifier is too long')
    if not clean_protocols: raise HTTPException(422,'At least one protocol is required')
    if len(json.dumps(b.metadata))>4000: raise HTTPException(422,'Agent metadata exceeds 4000 bytes')
    with conn() as c:
        require_project_access(c,pid,a)
        tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id']
        existing=c.execute('SELECT id,created_at FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(pid,a['id'],agent_name)).fetchone()
        aid=existing['id'] if existing else 'agt_'+uuid.uuid4().hex
        created=existing['created_at'] if existing else now()
        stamp=now()
        c.execute("""INSERT INTO project_agents(id,project_id,member_id,tenant_id,agent_name,capabilities,protocols,status,metadata,last_seen,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(project_id,member_id,agent_name) DO UPDATE SET capabilities=excluded.capabilities,protocols=excluded.protocols,status=excluded.status,metadata=excluded.metadata,last_seen=excluded.last_seen,updated_at=excluded.updated_at""",
        (aid,pid,a['id'],tenant,agent_name,json.dumps(clean_caps),json.dumps(clean_protocols),b.status,json.dumps(b.metadata),stamp,created,stamp))
        event(c,'agent.presence.updated',a['id'],None,{'project_id':pid,'agent_id':aid,'agent_name':agent_name,'status':b.status},tenant_override=tenant)
    return {'id':aid,'project_id':pid,'member_id':a['id'],'agent_name':b.agent_name.strip(),'status':b.status,'capabilities':clean_caps,'protocols':clean_protocols,'last_seen':stamp}

@app.post('/api/v1/projects/{pid}/agents/heartbeat')
def heartbeat_project_agent(pid:str,body:dict,authorization:str=Header(None)):
    a=actor(authorization); name=str(body.get('agent_name','')).strip()
    if not name or len(name)>120: raise HTTPException(422,'agent_name is required (max 120)')
    status=str(body.get('status','AVAILABLE')).upper()
    if status not in ('AVAILABLE','BUSY','OFFLINE'): raise HTTPException(422,'Invalid agent status')
    with conn() as c:
        require_project_access(c,pid,a)
        previous=c.execute('SELECT id,status FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(pid,a['id'],name)).fetchone()
        if not previous: raise HTTPException(404,'Agent registration not found; register the agent first')
        stamp=now()
        c.execute('UPDATE project_agents SET status=?,last_seen=?,updated_at=? WHERE id=?',(status,stamp,stamp,previous['id']))
        if previous['status'] != status:
            event(c,'agent.presence.changed',a['id'],None,{'project_id':pid,'agent_id':previous['id'],'status':status})
    return {'id':previous['id'],'status':status,'last_seen':stamp}

@app.get('/api/v1/projects/{pid}/agents')
def discover_project_agents(pid:str,authorization:str=Header(None),capability:str='',protocol:str=''):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("SELECT pa.*,m.name AS member_name FROM project_agents pa JOIN members m ON m.id=pa.member_id WHERE pa.project_id=? ORDER BY pa.agent_name,pa.member_id",(pid,)).fetchall()
        cutoff=datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat()
        items=[]
        for raw in rows:
            row=dict(raw)
            caps=json.loads(row['capabilities'] or '[]'); protocols=json.loads(row['protocols'] or '[]')
            live=row['status']!='OFFLINE' and row['last_seen']>=cutoff
            if capability and capability.lower() not in caps: continue
            if protocol and protocol.lower() not in protocols: continue
            items.append({'id':row['id'],'member_id':row['member_id'],'member_name':row['member_name'],'agent_name':row['agent_name'],'capabilities':caps,'protocols':protocols,'status':row['status'] if live else 'OFFLINE','last_seen':row['last_seen'],'metadata':json.loads(row['metadata'] or '{}')})
        return {'items':items,'count':len(items),'presence_ttl_seconds':120}

@app.get('/api/v1/projects/{pid}/agent-matches')
def recommend_project_agents(pid:str,required_capabilities:str='',protocol:str='mcp',authorization:str=Header(None)):
    """Rank project-local Agent registrations without assigning work or invoking a Runtime."""
    a=actor(authorization)
    requested=[x.strip().casefold() for x in required_capabilities.split(',') if x.strip()]
    if len(requested)>50 or any(len(x)>120 for x in requested):
        raise HTTPException(422,'At most 50 required capabilities are allowed; each must be at most 120 characters')
    requested=list(dict.fromkeys(requested))
    requested_protocol=protocol.strip().casefold()
    if not requested_protocol or len(requested_protocol)>40:
        raise HTTPException(422,'protocol must contain 1 to 40 characters')
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT pa.*,m.name AS member_name FROM project_agents pa
            JOIN members m ON m.id=pa.member_id WHERE pa.project_id=?""",(pid,)).fetchall()
        cutoff=datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat()
        items=[]
        for raw in rows:
            row=dict(raw)
            caps=sorted({str(x).strip().casefold() for x in json.loads(row['capabilities'] or '[]') if str(x).strip()})
            protocols=sorted({str(x).strip().casefold() for x in json.loads(row['protocols'] or '[]') if str(x).strip()})
            matched=[x for x in requested if x in caps]
            missing=[x for x in requested if x not in caps]
            live=row['status']!='OFFLINE' and row['last_seen']>=cutoff
            protocol_match=requested_protocol in protocols
            available=live and row['status']=='AVAILABLE'
            items.append({'id':row['id'],'member_id':row['member_id'],'member_name':row['member_name'],
                'agent_name':row['agent_name'],'capabilities':caps,'protocols':protocols,
                'presence_status':row['status'] if live else 'OFFLINE','last_seen':row['last_seen'],
                'matched_capabilities':matched,'missing_capabilities':missing,
                'match_count':len(matched),'required_count':len(requested),
                'protocol_match':protocol_match,'eligible':not missing and protocol_match and available,
                'availability_reason':('AVAILABLE' if available else ('BUSY' if live and row['status']=='BUSY' else 'OFFLINE_OR_STALE')),
                'match_score':round(100*len(matched)/len(requested)) if requested else (100 if protocol_match else 0)})
        items.sort(key=lambda x:(not x['eligible'],bool(x['missing_capabilities']),not x['protocol_match'],
            -x['match_count'],x['availability_reason']!='AVAILABLE',x['member_name'].casefold(),x['agent_name'].casefold()))
        return {'project_id':pid,'required_capabilities':requested,'protocol':requested_protocol,
            'items':items,'count':len(items),'eligible_count':sum(1 for x in items if x['eligible']),
            'recommendation_only':True,'runtime_controlled':False}

@app.post('/api/v1/tasks/{tid}/delegations')
def create_task_delegation(tid:str,b:DelegationIn,authorization:str=Header(None)):
    a=actor(authorization)
    if b.recipient_member_id == a['id']: raise HTTPException(400,'A task cannot be delegated to yourself')
    agent_name=b.agent_name.strip()
    if not agent_name: raise HTTPException(422,'agent_name must not be blank')
    did='dlg_'+uuid.uuid4().hex
    with conn() as c:
        require_task_access(c,tid,a,assigned_only=True)
        pid=task_project(c,tid)
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        recipient=c.execute('SELECT tenant_id FROM members WHERE id=?',(b.recipient_member_id,)).fetchone()
        if not recipient or recipient['tenant_id'] != project['tenant_id']: raise HTTPException(404,'Recipient not found in this tenant')
        if not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(pid,b.recipient_member_id)).fetchone(): raise HTTPException(400,'Recipient is not a project member')
        agent=c.execute("SELECT id,status,last_seen FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?",(pid,b.recipient_member_id,agent_name)).fetchone()
        if not agent: raise HTTPException(404,'Recipient Agent is not registered in this project')
        if agent['status']=='OFFLINE' or agent['last_seen'] < datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat():
            raise HTTPException(409,'Recipient Agent presence is offline or stale')
        stamp=now(); expiry=datetime.fromtimestamp(time.time()+b.expires_in_seconds,timezone.utc).isoformat()
        mid='msg_'+uuid.uuid4().hex[:12]
        title='Task delegation offer: '+tid
        content=json.dumps({'delegation_id':did,'task_id':tid,'agent_name':agent_name,'reason':b.reason,'expires_at':expiry},ensure_ascii=False)
        c.execute("INSERT INTO task_delegations(id,task_id,project_id,tenant_id,requester_member_id,recipient_member_id,agent_name,reason,status,message_id,expires_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(did,tid,pid,project['tenant_id'],a['id'],b.recipient_member_id,agent_name,b.reason,'PENDING',mid,expiry,stamp,stamp))
        c.execute("INSERT INTO messages(id,recipient_member_id,tenant_id,task_id,message_type,title,content,priority,status,created_at,acked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(mid,b.recipient_member_id,project['tenant_id'],tid,'TASK_DELEGATION',title,content,'HIGH','PENDING',stamp,None))
        payload={'message_id':mid,'recipient_member_id':b.recipient_member_id,'project_id':pid,'task_id':tid,'message_type':'TASK_DELEGATION','title':title,'content':content,'priority':'HIGH'}
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',('obx_'+uuid.uuid4().hex,'message.created',json.dumps(payload), 'PENDING',0,stamp,stamp,project['tenant_id']))
        event(c,'task.delegation.offered',a['id'],tid,{'delegation_id':did,'recipient_member_id':b.recipient_member_id,'agent_name':agent_name})
    return {'id':did,'task_id':tid,'recipient_member_id':b.recipient_member_id,'agent_name':agent_name,'status':'PENDING','expires_at':expiry,'message_id':mid}

@app.post('/api/v1/delegations/{did}/respond')
def respond_task_delegation(did:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization); decision=b.get('decision')
    if decision not in ('ACCEPT','REJECT'): raise HTTPException(422,'decision must be ACCEPT or REJECT')
    with conn() as c:
        begin_serialized_write(c)
        if DATABASE_URL.startswith(('postgresql://','postgres://')):
            row=c.execute('SELECT * FROM task_delegations WHERE id=? FOR UPDATE',(did,)).fetchone()
        else:
            row=c.execute('SELECT * FROM task_delegations WHERE id=?',(did,)).fetchone()
        if not row or row['recipient_member_id'] != a['id']: raise HTTPException(404,'Delegation not found')
        if row['status'] != 'PENDING': raise HTTPException(409,'Delegation is no longer pending')
        if row['expires_at'] <= now():
            stamp=now()
            cur=c.execute("UPDATE task_delegations SET status='EXPIRED',updated_at=? WHERE id=? AND status='PENDING'",(stamp,did))
            if cur.rowcount:
                event(c,'task.delegation.expired',a['id'],row['task_id'],{'delegation_id':did})
            return JSONResponse(status_code=410,content={'detail':'Delegation offer has expired','status':'EXPIRED'})
        if decision=='ACCEPT':
            c.execute('INSERT OR IGNORE INTO assignments(task_id,member_id) VALUES(?,?)',(row['task_id'],a['id']))
            c.execute('INSERT OR IGNORE INTO project_members(project_id,member_id,role,joined_at) VALUES(?,?,?,?)',(row['project_id'],a['id'],'member',now()))
            status='ACCEPTED'
        else: status='REJECTED'
        stamp=now()
        cur=c.execute('UPDATE task_delegations SET status=?,responded_at=?,updated_at=? WHERE id=? AND status=\'PENDING\'',(status,stamp,stamp,did))
        if cur.rowcount != 1:
            raise HTTPException(409,'Delegation response raced with another decision')
        event(c,'task.delegation.'+status.lower(),a['id'],row['task_id'],{'delegation_id':did,'agent_name':row['agent_name']})
        return {'id':did,'task_id':row['task_id'],'status':status,'responded_at':stamp}

@app.get('/api/v1/tasks/{tid}/delegations')
def list_task_delegations(tid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a)
        rows=c.execute('SELECT * FROM task_delegations WHERE task_id=? ORDER BY created_at DESC',(tid,)).fetchall()
        result=[]
        for raw in rows:
            row=dict(raw)
            if row['status']=='PENDING' and row['expires_at'] <= now():
                stamp=now()
                cur=c.execute("UPDATE task_delegations SET status='EXPIRED',updated_at=? WHERE id=? AND status='PENDING'",(stamp,row['id']))
                if cur.rowcount:
                    event(c,'task.delegation.expired',a['id'],tid,{'delegation_id':row['id']})
                row['status']='EXPIRED'
            result.append(row)
        return result

@app.get('/api/v1/projects/{pid}/delegations')
def project_delegations(pid:str,limit:int=100,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,500))
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT d.*,rq.name AS requester_name,rc.name AS recipient_name,t.title AS task_title
            FROM task_delegations d
            JOIN members rq ON rq.id=d.requester_member_id
            JOIN members rc ON rc.id=d.recipient_member_id
            JOIN tasks t ON t.id=d.task_id
            WHERE d.project_id=? ORDER BY d.created_at DESC LIMIT ?""",(pid,limit)).fetchall()
        items=[]
        for raw in rows:
            row=dict(raw)
            if row['status']=='PENDING' and row['expires_at'] <= now():
                stamp=now()
                cur=c.execute("UPDATE task_delegations SET status='EXPIRED',updated_at=? WHERE id=? AND status='PENDING'",(stamp,row['id']))
                if cur.rowcount:
                    event(c,'task.delegation.expired',a['id'],row['task_id'],{'delegation_id':row['id']})
                row['status']='EXPIRED'
            items.append(row)
        return {'project_id':pid,'count':len(items),'items':items}

@app.post('/api/v1/messages')
def send_message(b:MessageIn,authorization:str=Header(None)):
    a=actor(authorization); mid='msg_'+uuid.uuid4().hex[:12]
    with conn() as c:
        if not c.execute('SELECT 1 FROM members WHERE id=?',(b.recipient_member_id,)).fetchone(): raise HTTPException(404,'Recipient not found')
        if b.task_id:
            require_task_access(c,b.task_id,a)
            pid=task_project(c,b.task_id)
            if b.project_id and b.project_id != pid: raise HTTPException(400,'project_id does not match task')
        else: pid=b.project_id
        if not pid and not is_admin(a): raise HTTPException(400,'project_id is required for project-scoped messages')
        if pid:
            require_project_access(c,pid,a)
            recipient=c.execute('SELECT tenant_id FROM members WHERE id=?',(b.recipient_member_id,)).fetchone()
            project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
            if recipient and recipient['tenant_id'] != project['tenant_id']: raise HTTPException(400,'Recipient belongs to a different tenant')
            if not is_admin(a) and not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(pid,b.recipient_member_id)).fetchone(): raise HTTPException(400,'Recipient is not a project member')
        created=now()
        message_tenant=(c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id'] if pid else c.execute('SELECT tenant_id FROM members WHERE id=?',(b.recipient_member_id,)).fetchone()['tenant_id'])
        c.execute('INSERT INTO messages(id,recipient_member_id,tenant_id,task_id,message_type,title,content,priority,status,created_at,acked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(mid,b.recipient_member_id,message_tenant,b.task_id,b.message_type,b.title,b.content,b.priority,'PENDING',created,None))
        payload={'message_id':mid,'recipient_member_id':b.recipient_member_id,'project_id':pid,'task_id':b.task_id,'message_type':b.message_type,'title':b.title,'content':b.content,'priority':b.priority}
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',('obx_'+uuid.uuid4().hex,'message.created',json.dumps(payload),'PENDING',0,created,created,message_tenant))
        event(c,'message.created',a['id'],b.task_id,{'message_id':mid,'recipient':b.recipient_member_id},tenant_override=message_tenant)
    return {'id':mid,'status':'PENDING'}
@app.get('/api/v1/me/notifications')
def notifications(authorization:str=Header(None),after:int=0,limit:int=50):
    a=actor(authorization); limit=max(1,min(limit,100))
    with conn() as c:
        rows=[dict(x) for x in c.execute("SELECT * FROM messages WHERE recipient_member_id=? AND status='PENDING' AND seq>? ORDER BY seq LIMIT ?",(a['id'],after,limit))]
        for row in rows: c.execute('UPDATE messages SET attempts=attempts+1,last_attempt_at=? WHERE id=?',(now(),row['id']))
        return {'items':rows,'next_cursor':rows[-1]['seq'] if rows else after,'has_more':len(rows)==limit}
@app.post('/api/v1/messages/{mid}/ack')
def ack(mid:str,b:AckIn,authorization: str=Header(None)):
    a=actor(authorization)
    if b.status not in ('ACKNOWLEDGED','REJECTED'): raise HTTPException(422,'Invalid acknowledgement status')
    with conn() as c:
        existing=c.execute('SELECT status,task_id,tenant_id FROM messages WHERE id=? AND recipient_member_id=?',(mid,a['id'])).fetchone()
        if not existing: raise HTTPException(404,'Message not found for current member')
        if existing['status'] in ('ACKNOWLEDGED','REJECTED'):
            if existing['status'] != b.status: raise HTTPException(409,'Message has already reached a different terminal status')
            return {'id':mid,'status':existing['status'],'idempotent':True}
        stamp=now()
        cur=c.execute("UPDATE messages SET status=?,acked_at=? WHERE id=? AND recipient_member_id=? AND status='PENDING'",(b.status,stamp,mid,a['id']))
        if cur.rowcount==0: raise HTTPException(409,'Message status changed; retry the request')
        event(c,'message.acknowledged',a['id'],existing['task_id'],{'message_id':mid,'status':b.status},tenant_override=existing['tenant_id'])
    return {'id':mid,'status':b.status,'idempotent':False}
@app.get('/api/v1/tasks/{tid}/events')
def task_events(tid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a)
        return [dict(x) for x in c.execute('SELECT * FROM events WHERE task_id=? ORDER BY created_at',(tid,))]
@app.get('/api/v1/tasks/{tid}/artifacts')
def task_artifacts(tid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a)
        return [dict(x) for x in c.execute('SELECT * FROM artifacts WHERE task_id=? ORDER BY created_at',(tid,))]
@app.post('/internal/v1/outbox/claim')
def claim_outbox(body:dict,authorization:str=Header(None)):
    require_worker(authorization)
    worker=str(body.get('worker_id','')).strip()
    if not worker or len(worker)>120: raise HTTPException(422,'worker_id is required (max 120 chars)')
    limit=max(1,min(int(body.get('limit',20)),100)); lease_seconds=max(10,min(int(body.get('lease_seconds',60)),900))
    claimed=[]; timestamp=datetime.now(timezone.utc); stamp=timestamp.isoformat()
    with conn() as c:
        is_pg=DATABASE_URL.startswith(('postgresql://','postgres://'))
        if not is_pg: c.execute('BEGIN IMMEDIATE')
        query="SELECT * FROM outbox WHERE (status='PENDING' AND available_at<=?) OR (status='IN_FLIGHT' AND lease_until<=?) ORDER BY created_at LIMIT ?"
        if is_pg: query += " FOR UPDATE SKIP LOCKED"
        rows=c.execute(query,(stamp,stamp,limit)).fetchall()
        for row in rows:
            lease_until=datetime.fromtimestamp(timestamp.timestamp()+lease_seconds,timezone.utc).isoformat()
            lease_token=secrets.token_urlsafe(32)
            cur=c.execute("UPDATE outbox SET status='IN_FLIGHT',attempts=attempts+1,lease_until=?,lease_owner=?,lease_token=? WHERE id=? AND ((status='PENDING' AND available_at<=?) OR (status='IN_FLIGHT' AND lease_until<=?))",(lease_until,worker,lease_token,row['id'],stamp,stamp))
            if cur.rowcount:
                item=dict(row); item.update(status='IN_FLIGHT',attempts=row['attempts']+1,lease_until=lease_until,lease_owner=worker,lease_token=lease_token,payload=json.loads(row['payload']))
                claimed.append(item)
    return {'items':claimed,'count':len(claimed)}

@app.post('/internal/v1/outbox/{outbox_id}/complete')
def complete_outbox(outbox_id:str,body:dict,authorization:str=Header(None)):
    require_worker(authorization)
    worker=str(body.get('worker_id','')).strip(); lease_token=str(body.get('lease_token',''))
    if not worker or len(worker)>120 or len(lease_token)<32: raise HTTPException(422,'worker_id and lease_token are required')
    with conn() as c:
        stamp=now()
        cur=c.execute("UPDATE outbox SET status='SENT',sent_at=?,lease_until=NULL,lease_owner=NULL,lease_token=NULL,last_error=NULL WHERE id=? AND status='IN_FLIGHT' AND lease_owner=? AND lease_token=? AND lease_until>?",(stamp,outbox_id,worker,lease_token,stamp))
        if not cur.rowcount: raise HTTPException(409,'Outbox lease not owned by worker or item is not in flight')
    return {'id':outbox_id,'status':'SENT'}

@app.post('/internal/v1/outbox/{outbox_id}/fail')
def fail_outbox(outbox_id:str,body:dict,authorization:str=Header(None)):
    require_worker(authorization)
    worker=str(body.get('worker_id','')).strip(); lease_token=str(body.get('lease_token','')); error=str(body.get('error','Delivery failed'))[:2000]
    if not worker or len(worker)>120 or len(lease_token)<32: raise HTTPException(422,'worker_id and lease_token are required')
    with conn() as c:
        stamp=now()
        row=c.execute("SELECT attempts FROM outbox WHERE id=? AND status='IN_FLIGHT' AND lease_owner=? AND lease_token=? AND lease_until>?",(outbox_id,worker,lease_token,stamp)).fetchone()
        if not row: raise HTTPException(409,'Outbox lease not owned, expired, or item is not in flight')
        attempts=row['attempts']; terminal=attempts>=8
        delay=min(3600,5*(2**min(attempts-1,10)))
        available=datetime.fromtimestamp(datetime.now(timezone.utc).timestamp()+delay,timezone.utc).isoformat()
        cur=c.execute("UPDATE outbox SET status=?,available_at=?,lease_until=NULL,lease_owner=NULL,lease_token=NULL,last_error=? WHERE id=? AND status='IN_FLIGHT' AND lease_owner=? AND lease_token=? AND lease_until>?",('DEAD' if terminal else 'PENDING',available,error,outbox_id,worker,lease_token,stamp))
        if not cur.rowcount: raise HTTPException(409,'Outbox lease changed or expired during failure acknowledgement')
    return {'id':outbox_id,'status':'DEAD' if terminal else 'PENDING','retry_after_seconds':None if terminal else delay}

@app.get('/api/v1/admin/outbox/dead')
def list_dead_outbox(limit:int=50,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    limit=max(1,min(limit,200))
    with conn() as c:
        rows=c.execute("SELECT id,event_type,status,attempts,available_at,last_error,created_at,tenant_id FROM outbox WHERE status='DEAD' ORDER BY created_at LIMIT ?",(limit,)).fetchall()
        return {'items':[dict(x) for x in rows],'count':len(rows)}

@app.post('/api/v1/admin/messages/{message_id}/restore-outbox')
def restore_missing_message_outbox(message_id:str,body:dict,authorization:str=Header(None)):
    """Explicitly restore one missing message dispatch record; never duplicates an existing dispatch."""
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    reason=str(body.get('reason','')).strip()
    if not reason or len(reason)>1000: raise HTTPException(422,'A recovery reason (1-1000 characters) is required')
    with conn() as c:
        begin_serialized_write(c)
        query='SELECT * FROM messages WHERE id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): query += ' FOR UPDATE'
        message=c.execute(query,(message_id,)).fetchone()
        if not message: raise HTTPException(404,'Message not found')
        existing_rows=c.execute("SELECT id,payload FROM outbox WHERE event_type='message.created'").fetchall()
        matching=[]
        for item in existing_rows:
            try:
                if json.loads(item['payload']).get('message_id')==message_id: matching.append(item['id'])
            except (TypeError,ValueError):
                continue
        if matching:
            raise HTTPException(409,'A message.created outbox record already exists; refusing duplicate recovery')
        project_id=None
        if message['task_id']:
            project=c.execute('SELECT r.project_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id WHERE t.id=?',(message['task_id'],)).fetchone()
            if project: project_id=project['project_id']
        payload={'message_id':message_id,'recipient_member_id':message['recipient_member_id'],
                 'project_id':project_id,'task_id':message['task_id'],'message_type':message['message_type'],
                 'title':message['title'],'content':message['content'],'priority':message['priority']}
        stamp=now(); outbox_id='obx_'+uuid.uuid4().hex
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',
                  (outbox_id,'message.created',json.dumps(payload),'PENDING',0,stamp,stamp,message['tenant_id']))
        event(c,'message.outbox.restored',a['id'],message['task_id'],
              {'message_id':message_id,'outbox_id':outbox_id,'reason':reason},tenant_override=message['tenant_id'])
    return {'message_id':message_id,'outbox_id':outbox_id,'status':'PENDING','restored':True}

@app.get('/api/v1/projects/{project_id}/message-delivery-health')
def project_message_delivery_health(project_id:str,authorization:str=Header(None),
                                    dispatch_sla_seconds:int=120,ack_sla_seconds:int=300,
                                    limit:int=100):
    """Project-scoped delivery SLA health; broker dispatch and recipient ACK clocks are separate."""
    a=actor(authorization)
    dispatch_sla_seconds=max(10,min(dispatch_sla_seconds,86400))
    ack_sla_seconds=max(10,min(ack_sla_seconds,604800))
    limit=max(1,min(limit,500))
    stamp=datetime.now(timezone.utc)
    incidents=[]
    with conn() as c:
        require_project_access(c,project_id,a)
        messages=c.execute("""SELECT m.id,m.recipient_member_id,m.tenant_id,m.task_id,m.status,m.created_at,m.acked_at
            FROM messages m JOIN tasks t ON t.id=m.task_id
            JOIN requirements r ON r.id=t.requirement_id
            WHERE r.project_id=? ORDER BY m.seq DESC LIMIT ?""",(project_id,limit)).fetchall()
        outbox=c.execute("SELECT id,payload,status,attempts,available_at,lease_until,lease_owner,last_error,created_at,sent_at FROM outbox WHERE event_type='message.created'").fetchall()
    by_message={}
    malformed=0
    for row in outbox:
        try:
            mid=json.loads(row['payload']).get('message_id')
            if isinstance(mid,str) and mid: by_message.setdefault(mid,[]).append(row)
            else: malformed+=1
        except (TypeError,ValueError):
            malformed+=1
    dispatch_counts={k:0 for k in ('HEALTHY','MISSING','DUPLICATE','DEAD','DISPATCH_OVERDUE')}
    ack_counts={k:0 for k in ('NOT_DUE','ACK_OVERDUE','ACKNOWLEDGED','REJECTED')}
    def parse_stamp(value):
        if not value: return None
        try:
            parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError,ValueError):
            return None
    for message in messages:
        records=by_message.get(message['id'],[])
        dispatch='HEALTHY'; ack='NOT_DUE'; detail=None
        if not records:
            dispatch='MISSING'; detail='No message.created outbox record'
        elif len(records)>1:
            dispatch='DUPLICATE'; detail='Multiple message.created outbox records'
        elif records[0]['status']=='DEAD':
            dispatch='DEAD'; detail=records[0]['last_error'] or 'Outbox entered DEAD state'
        elif records[0]['status'] in ('PENDING','IN_FLIGHT'):
            created=parse_stamp(records[0]['created_at'])
            if created and (stamp-created).total_seconds()>dispatch_sla_seconds:
                dispatch='DISPATCH_OVERDUE'; detail='Broker dispatch exceeded SLA'
        elif records[0]['status']!='SENT':
            dispatch='HEALTHY'; detail='Unrecognized outbox state: '+str(records[0]['status'])
        if dispatch in dispatch_counts: dispatch_counts[dispatch]+=1
        if message['status'] in ('ACKNOWLEDGED','REJECTED'):
            ack=message['status']
        elif records and len(records)==1 and records[0]['status']=='SENT':
            sent=parse_stamp(records[0]['sent_at'])
            if sent and (stamp-sent).total_seconds()>ack_sla_seconds:
                ack='ACK_OVERDUE'
        if ack in ack_counts: ack_counts[ack]+=1
        if dispatch!='HEALTHY':
            incidents.append({'message_id':message['id'],'task_id':message['task_id'],
                'category':'DISPATCH_'+dispatch,'dispatch_status':dispatch,'ack_status':ack,
                'age_seconds':max(0,int((stamp-(parse_stamp(message['created_at']) or stamp)).total_seconds())),
                'detail':detail})
        if ack=='ACK_OVERDUE':
            incidents.append({'message_id':message['id'],'task_id':message['task_id'],
                'category':'ACK_OVERDUE','dispatch_status':dispatch,'ack_status':ack,
                'age_seconds':max(0,int((stamp-(parse_stamp(records[0]['sent_at']) or stamp)).total_seconds())),
                'detail':'Broker dispatch completed but recipient ACK exceeded SLA'})
    return {'project_id':project_id,'generated_at':stamp.isoformat(),
        'policy':{'dispatch_sla_seconds':dispatch_sla_seconds,'ack_sla_seconds':ack_sla_seconds},
        'checked_messages':len(messages),'truncated':len(messages)==limit,
        'dispatch_counts':dispatch_counts,'ack_counts':ack_counts,
        'incident_count':len(incidents),'incidents':incidents[:limit],
        'malformed_outbox_records_seen':malformed,
        'semantics':'ACK SLA starts at outbox sent_at only. SENT is broker dispatch completion, not recipient ACK.'}

@app.post('/api/v1/projects/{project_id}/message-delivery-incidents/{message_id}/review')
def review_message_delivery_incident(project_id:str,message_id:str,body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    disposition=str(body.get('disposition','')).strip().upper()
    comment=str(body.get('comment','')).strip()
    if disposition not in ('INVESTIGATING','RESOLVED','ACCEPTED_RISK'):
        raise HTTPException(422,'disposition must be INVESTIGATING, RESOLVED, or ACCEPTED_RISK')
    if not comment or len(comment)>2000:
        raise HTTPException(422,'A review comment (1-2000 characters) is required')
    with conn() as c:
        require_project_access(c,project_id,a,write=True)
        row=c.execute("""SELECT m.task_id,m.tenant_id FROM messages m JOIN tasks t ON t.id=m.task_id
            JOIN requirements r ON r.id=t.requirement_id WHERE m.id=? AND r.project_id=?""",
            (message_id,project_id)).fetchone()
        if not row: raise HTTPException(404,'Project message not found')
        event(c,'message.delivery.incident.reviewed',a['id'],row['task_id'],
              {'project_id':project_id,'message_id':message_id,'disposition':disposition,'comment':comment},
              tenant_override=row['tenant_id'])
    return {'project_id':project_id,'message_id':message_id,'disposition':disposition,'recorded':True}


@app.get('/api/v1/admin/message-delivery')
def message_delivery_overview(authorization:str=Header(None),limit:int=200,offset:int=0,
                              dispatch_status:str=None,ack_status:str=None):
    """Admin operational view separating broker dispatch from recipient acknowledgement."""
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    limit=max(1,min(limit,500)); offset=max(0,offset)
    allowed_dispatch={'NO_OUTBOX','DUPLICATE','PENDING','IN_FLIGHT','SENT','DEAD'}
    allowed_ack={'PENDING','ACKNOWLEDGED','REJECTED'}
    if dispatch_status and dispatch_status not in allowed_dispatch:
        raise HTTPException(422,'Invalid dispatch_status filter')
    if ack_status and ack_status not in allowed_ack:
        raise HTTPException(422,'Invalid ack_status filter')
    with conn() as c:
        messages=c.execute('SELECT id,recipient_member_id,tenant_id,task_id,message_type,priority,status,created_at,acked_at FROM messages ORDER BY seq DESC LIMIT ? OFFSET ?',(limit,offset)).fetchall()
        outbox=c.execute("SELECT id,event_type,payload,status,attempts,available_at,lease_until,lease_owner,last_error,created_at,sent_at,tenant_id FROM outbox WHERE event_type='message.created' ORDER BY created_at").fetchall()
    by_message={}
    malformed_count=0
    for item in outbox:
        try:
            mid=json.loads(item['payload']).get('message_id')
            if not isinstance(mid,str) or not mid: malformed_count+=1; continue
        except (TypeError,ValueError):
            malformed_count+=1; continue
        by_message.setdefault(mid,[]).append(item)
    items=[]
    counts={key:0 for key in ('NO_OUTBOX','DUPLICATE','PENDING','IN_FLIGHT','SENT','DEAD')}
    ack_counts={key:0 for key in ('PENDING','ACKNOWLEDGED','REJECTED')}
    for message in messages:
        records=by_message.get(message['id'],[])
        state='NO_OUTBOX' if not records else ('DUPLICATE' if len(records)>1 else records[0]['status'])
        if state not in counts: state='UNKNOWN'
        if state in counts: counts[state]+=1
        ack=message['status']
        if ack in ack_counts: ack_counts[ack]+=1
        if dispatch_status and state!=dispatch_status: continue
        if ack_status and ack!=ack_status: continue
        items.append({
            'message_id':message['id'],'recipient_member_id':message['recipient_member_id'],
            'tenant_id':message['tenant_id'],'task_id':message['task_id'],
            'message_type':message['message_type'],'priority':message['priority'],
            'ack_status':ack,'created_at':message['created_at'],'acked_at':message['acked_at'],
            'dispatch_status':state,'dispatch_records':[{
                'outbox_id':row['id'],'status':row['status'],'attempts':row['attempts'],
                'available_at':row['available_at'],'lease_until':row['lease_until'],
                'lease_owner':row['lease_owner'],'last_error':row['last_error'],
                'created_at':row['created_at'],'sent_at':row['sent_at']
            } for row in records]
        })
    return {'items':items,'count':len(items),'limit':limit,'offset':offset,
            'dispatch_counts':counts,'ack_counts':ack_counts,
            'malformed_outbox_records_seen':malformed_count,
            'semantics':{'SENT':'Broker dispatch completed; recipient acknowledgement is tracked separately in ack_status.',
                         'ACKNOWLEDGED':'Recipient explicitly acknowledged the message.',
                         'REJECTED':'Recipient explicitly rejected the message.'}}

@app.get('/api/v1/admin/message-delivery-integrity')
def message_delivery_integrity(authorization:str=Header(None),limit:int=5000):
    """Read-only reconciliation of durable messages and their outbox dispatch records."""
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    limit=max(1,min(limit,10000))
    with conn() as c:
        messages=c.execute('SELECT id,recipient_member_id,tenant_id,task_id FROM messages ORDER BY seq LIMIT ?',(limit+1,)).fetchall()
        outbox=c.execute("SELECT id,event_type,payload,tenant_id,status FROM outbox WHERE event_type='message.created' ORDER BY created_at LIMIT ?",(limit+1,)).fetchall()
    truncated=len(messages)>limit or len(outbox)>limit
    messages=messages[:limit]; outbox=outbox[:limit]
    by_message={}
    malformed=[]; orphaned=[]; tenant_mismatch=[]; recipient_mismatch=[]; task_mismatch=[]
    known={row['id']:row for row in messages}
    for item in outbox:
        try:
            payload=json.loads(item['payload'])
            message_id=payload.get('message_id')
            if not isinstance(message_id,str) or not message_id:
                malformed.append(item['id']); continue
        except (TypeError,ValueError):
            malformed.append(item['id']); continue
        by_message.setdefault(message_id,[]).append(item)
        message=known.get(message_id)
        if not message:
            orphaned.append(item['id']); continue
        if item['tenant_id'] != message['tenant_id']:
            tenant_mismatch.append(item['id'])
        if payload.get('recipient_member_id') != message['recipient_member_id']:
            recipient_mismatch.append(item['id'])
        if payload.get('task_id') != message['task_id']:
            task_mismatch.append(item['id'])
    missing=[mid for mid in known if mid not in by_message]
    duplicates={mid:[x['id'] for x in rows] for mid,rows in by_message.items() if len(rows)>1}
    issues={
        'messages_without_outbox':missing,
        'duplicate_outbox_by_message':duplicates,
        'orphaned_outbox':orphaned,
        'malformed_outbox':malformed,
        'tenant_mismatch_outbox':tenant_mismatch,
        'recipient_mismatch_outbox':recipient_mismatch,
        'task_mismatch_outbox':task_mismatch,
    }
    counts={key:(len(value) if isinstance(value,list) else len(value)) for key,value in issues.items()}
    return {'checked_messages':len(messages),'checked_message_outbox':len(outbox),'truncated':truncated,
            'healthy':not any(counts.values()) and not truncated,'issue_counts':counts,'issues':issues,
            'semantics':'Read-only structural reconciliation; SENT means broker dispatch completed, not recipient ACK.'}

@app.post('/api/v1/admin/outbox/{outbox_id}/replay')
def replay_dead_outbox(outbox_id:str,body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    reason=str(body.get('reason','')).strip()
    if not reason or len(reason)>1000: raise HTTPException(422,'A replay reason (1-1000 characters) is required')
    with conn() as c:
        row=c.execute("SELECT tenant_id,status FROM outbox WHERE id=?",(outbox_id,)).fetchone()
        if not row: raise HTTPException(404,'Outbox item not found')
        if row['status']!='DEAD': raise HTTPException(409,'Only DEAD outbox items can be replayed')
        stamp=now()
        cur=c.execute("UPDATE outbox SET status='PENDING',attempts=0,available_at=?,lease_until=NULL,lease_owner=NULL,lease_token=NULL,last_error=NULL,sent_at=NULL WHERE id=? AND status='DEAD'",(stamp,outbox_id))
        if not cur.rowcount: raise HTTPException(409,'Outbox item changed; refresh and retry')
        event(c,'outbox.dead.replayed',a['id'],None,{'outbox_id':outbox_id,'reason':reason},tenant_override=row['tenant_id'])
    return {'id':outbox_id,'status':'PENDING','replayed':True}

@app.websocket('/ws/v1')
async def websocket_endpoint(ws:WebSocket,token:str='',after:int=0):
    # Best-effort online notification channel. The durable inbox remains the source of truth.
    lookup_reset=_auth_lookup_ctx.set(True)
    try:
        with conn() as c: member=(c.execute("SELECT id,tenant_id,role FROM daep_authenticate_member(?,?)",(hashlib.sha256(token.encode()).hexdigest(),now())).fetchone() if DATABASE_URL.startswith(('postgresql://','postgres://')) else c.execute("SELECT id,tenant_id,role FROM members WHERE token=? AND token_status='ACTIVE' AND (token_expires_at IS NULL OR token_expires_at>?)",(hashlib.sha256(token.encode()).hexdigest(),now())).fetchone())
    finally:
        _auth_lookup_ctx.reset(lookup_reset)
    if not member: await ws.close(code=1008); return
    cursor=max(0,after)
    _tenant_ctx.set(member['tenant_id']); _admin_ctx.set(member['role']=='admin' and member['tenant_id']=='tenant-default')
    await ws.accept()
    try:
        await ws.send_json({'type':'connected','at':now(),'cursor':cursor,'delivery':'best-effort; reconnect with after=<last processed seq> or recover via inbox'})
        while True:
            with conn() as c:
                rows=[dict(r) for r in c.execute("SELECT * FROM messages WHERE recipient_member_id=? AND status='PENDING' AND seq>? ORDER BY seq LIMIT 100",(member['id'],cursor))]
                if rows:
                    for r in rows:
                        await ws.send_json({'type':'notification','message':r})
                        cursor=max(cursor,r['seq'])
                        c.execute('UPDATE messages SET attempts=attempts+1,last_attempt_at=? WHERE id=?',(now(),r['id']))
            try: await asyncio.wait_for(ws.receive_text(),timeout=3.0)
            except asyncio.TimeoutError: pass
    except WebSocketDisconnect: pass
    if not authorization or not authorization.startswith('Bearer '): raise HTTPException(401,'Bearer token required')
    token=hashlib.sha256(authorization[7:].encode()).hexdigest()
    lookup_reset=_auth_lookup_ctx.set(True)
    try:
        with conn() as c: r=(c.execute("SELECT * FROM daep_authenticate_member(?,?)",(token,now())).fetchone() if DATABASE_URL.startswith(('postgresql://','postgres://')) else c.execute("SELECT * FROM members WHERE token=? AND token_status='ACTIVE' AND (token_expires_at IS NULL OR token_expires_at>?)",(token,now())).fetchone())
    finally:
        _auth_lookup_ctx.reset(lookup_reset)
    if not r: raise HTTPException(401,'Invalid token')
    data=dict(r); _tenant_ctx.set(data.get('tenant_id','')); _admin_ctx.set(is_admin(data))
    return data

def require_worker(authorization):
    expected=os.getenv('DAEP_WORKER_TOKEN','')
    if len(expected)<32: raise HTTPException(503,'Dedicated DAEP_WORKER_TOKEN is not configured')
    if secrets.compare_digest(hashlib.sha256(expected.encode()).digest(),hashlib.sha256(ADMIN_TOKEN.encode()).digest()): raise HTTPException(503,'Worker credential must be different from DAEP_ADMIN_TOKEN')
    if not authorization or not authorization.startswith('Bearer '): raise HTTPException(401,'Worker bearer token required')
    supplied=authorization[7:]
    expected_digest=hashlib.sha256(expected.encode()).digest()
    supplied_digest=hashlib.sha256(supplied.encode()).digest()
    if not secrets.compare_digest(supplied_digest,expected_digest): raise HTTPException(401,'Invalid worker credential')
    _service_ctx.set(True)
def require_project_access(c, project_id, a, write=False):
    project=c.execute('SELECT tenant_id,status FROM projects WHERE id=?',(project_id,)).fetchone()
    if not project: raise HTTPException(404,'Project not found')
    if project['tenant_id'] != a.get('tenant_id','tenant-default') and not is_admin(a):
        raise HTTPException(403,'Tenant isolation violation')
    if write and project['status']=='CLOSED': raise HTTPException(409,'Project is closed')
    if is_admin(a): return
    if a.get('actor_type')=='AGENT':
        binding=c.execute("SELECT 1 FROM agent_project_bindings WHERE project_id=? AND agent_id=? AND status='ACTIVE'",
            (project_id,a['agent_id'])).fetchone()
        if not binding: raise HTTPException(403,'Agent project binding required')
        if write: raise HTTPException(403,'Agent cannot perform project-level governance or administration')
        return
    row=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(project_id,a['id'])).fetchone()
    if not row: raise HTTPException(403,'Project membership required')
    if write and row['role'] not in ('owner','manager'): raise HTTPException(403,'Project manager role required')
def task_project(c, tid):
    r=c.execute('SELECT r.project_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id WHERE t.id=?',(tid,)).fetchone()
    return r['project_id'] if r else None
def require_task_access(c, tid, a, assigned_only=False):
    pid=task_project(c,tid)
    if not pid: raise HTTPException(404,'Task not found')
    project=c.execute('SELECT status FROM projects WHERE id=?',(pid,)).fetchone()
    closed=bool(project and project['status']=='CLOSED')
    if is_admin(a):
        if assigned_only and closed: raise HTTPException(409,'Project is closed')
        return
    if a.get('actor_type')=='AGENT':
        require_project_access(c,pid,a)
        if assigned_only and closed:
            raise HTTPException(409,'Project is closed')
        assignment=c.execute("""SELECT 1 FROM agent_task_assignments
            WHERE task_id=? AND project_id=? AND agent_id=? AND status='ACCEPTED'""",
            (tid,pid,a['agent_id'])).fetchone()
        if not assignment:
            raise HTTPException(403,'Accepted Agent task assignment required')
        return
    if assigned_only:
        if closed: raise HTTPException(409,'Project is closed')
        ok=c.execute('SELECT 1 FROM assignments WHERE task_id=? AND member_id=?',(tid,a['id'])).fetchone()
        if not ok: raise HTTPException(403,'Task assignment required')
    else: require_project_access(c,pid,a)

def event(c,typ,member,task,payload,key=None,tenant_override=None):
    eid='evt_'+uuid.uuid4().hex
    tenant=tenant_override or 'tenant-default'
    if tenant_override:
        pass
    elif task:
        rr=c.execute('SELECT p.tenant_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE t.id=?',(task,)).fetchone()
        if rr: tenant=rr['tenant_id']
    elif member:
        rr=c.execute('SELECT tenant_id FROM members WHERE id=?',(member,)).fetchone()
        if rr: tenant=rr['tenant_id']
    audit_payload=dict(payload or {})
    audit_payload.setdefault('actor_type','AGENT' if _agent_ctx.get() else 'MEMBER')
    if _agent_ctx.get(): audit_payload.setdefault('agent_id',_agent_ctx.get())
    # Agent actions are attributed to the Agent identity, never to its owner's member row.
    actor_member_id=None if _agent_ctx.get() else member
    payload_json=json.dumps(audit_payload)
    if key:
        c.execute('INSERT INTO events(id,event_type,actor_member_id,task_id,payload,created_at,idempotency_key,tenant_id) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(idempotency_key) DO NOTHING',(eid,typ,actor_member_id,task,payload_json,now(),key,tenant))
        prior=c.execute('SELECT id,payload FROM events WHERE idempotency_key=?',(key,)).fetchone()
        if prior:
            if prior['payload'] != payload_json:
                raise HTTPException(409,'Idempotency key was used with a different payload')
            return prior['id']
    else:
        c.execute('INSERT INTO events(id,event_type,actor_member_id,task_id,payload,created_at,idempotency_key,tenant_id) VALUES(?,?,?,?,?,?,?,?)',(eid,typ,actor_member_id,task,payload_json,now(),key,tenant))
    return eid

@app.get('/',include_in_schema=False)
def dashboard(): return FileResponse(os.path.join(os.path.dirname(os.path.dirname(__file__)),'web','index.html'))
def _oidc_discovery():
    issuer=os.getenv('DAEP_OIDC_ISSUER','').rstrip('/')
    if not issuer: raise HTTPException(503,'OIDC is not configured')
    try:
        with urllib.request.urlopen(issuer+'/.well-known/openid-configuration',timeout=10) as r: return json.loads(r.read())
    except Exception as exc: raise HTTPException(503,f'OIDC discovery failed: {exc}')

def _oidc_state_record():
    """Create one-time server-side OIDC state, nonce and PKCE verifier."""
    state=secrets.token_urlsafe(32)
    nonce=secrets.token_urlsafe(32)
    verifier=secrets.token_urlsafe(64)
    expires=datetime.fromtimestamp(time.time()+600,timezone.utc).isoformat()
    with conn() as c:
        c.execute('DELETE FROM oidc_states WHERE expires_at<=?',(now(),))
        c.execute('INSERT INTO oidc_states(state_hash,nonce,code_verifier,expires_at,created_at) VALUES(?,?,?,?,?)',
                  (hashlib.sha256(state.encode()).hexdigest(),nonce,verifier,expires,now()))
    return state,nonce,verifier

def _verify_oidc_browser_state(state,cookie_state):
    if not cookie_state or not secrets.compare_digest(hashlib.sha256(cookie_state.encode()).digest(),hashlib.sha256(state.encode()).digest()):
        raise HTTPException(400,'OIDC browser state cookie mismatch')

def _consume_oidc_state(state):
    if not state or len(state)>512: raise HTTPException(400,'Invalid OIDC state')
    digest=hashlib.sha256(state.encode()).hexdigest()
    with conn() as c:
        row=c.execute('SELECT nonce,code_verifier,expires_at FROM oidc_states WHERE state_hash=?',(digest,)).fetchone()
        if not row: raise HTTPException(400,'Invalid or already used OIDC state')
        c.execute('DELETE FROM oidc_states WHERE state_hash=?',(digest,))
    if row['expires_at'] <= now(): raise HTTPException(400,'Expired OIDC state')
    return row['nonce'],row['code_verifier']

@app.get('/api/v1/auth/oidc/login')
def oidc_login():
    if not (os.getenv('DAEP_OIDC_CLIENT_ID') and os.getenv('DAEP_OIDC_REDIRECT_URI')): raise HTTPException(503,'OIDC is not configured')
    d=_oidc_discovery(); state,nonce,verifier=_oidc_state_record()
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    params={'client_id':os.getenv('DAEP_OIDC_CLIENT_ID'),'response_type':'code','redirect_uri':os.getenv('DAEP_OIDC_REDIRECT_URI'),'scope':os.getenv('DAEP_OIDC_SCOPES','openid profile email'),'state':state,'nonce':nonce,'code_challenge':challenge,'code_challenge_method':'S256'}
    if os.getenv('DAEP_OIDC_AUDIENCE'): params['audience']=os.getenv('DAEP_OIDC_AUDIENCE')
    response=RedirectResponse(d['authorization_endpoint']+'?'+urllib.parse.urlencode(params),status_code=302)
    response.set_cookie('daep_oidc_state',state,max_age=600,httponly=True,secure=os.getenv('DAEP_OIDC_REDIRECT_URI','').startswith('https://'),samesite='lax',path='/api/v1/auth/oidc/callback')
    return response

@app.get('/api/v1/auth/oidc/callback')
def oidc_callback(code:str,state:str,daep_oidc_state:Optional[str]=Cookie(None)):
    client_id=os.getenv('DAEP_OIDC_CLIENT_ID',''); client_secret=os.getenv('DAEP_OIDC_CLIENT_SECRET','')
    redirect_uri=os.getenv('DAEP_OIDC_REDIRECT_URI','')
    if not client_id or not client_secret or not redirect_uri: raise HTTPException(503,'OIDC client is not configured')
    _verify_oidc_browser_state(state,daep_oidc_state)
    nonce,code_verifier=_consume_oidc_state(state); d=_oidc_discovery()
    form=urllib.parse.urlencode({'grant_type':'authorization_code','code':code,'redirect_uri':redirect_uri,'client_id':client_id,'client_secret':client_secret,'code_verifier':code_verifier}).encode()
    req=urllib.request.Request(d['token_endpoint'],data=form,method='POST',headers={'Content-Type':'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req,timeout=15) as r: tokens=json.loads(r.read())
    except Exception: raise HTTPException(502,'OIDC token exchange failed')
    id_token=tokens.get('id_token')
    if not id_token: raise HTTPException(502,'OIDC provider did not return an id_token')
    try:
        import jwt
        jwks_client=jwt.PyJWKClient(d['jwks_uri'],timeout=10)
        signing_key=jwks_client.get_signing_key_from_jwt(id_token).key
        claims=jwt.decode(id_token,signing_key,algorithms=['RS256','RS384','RS512','PS256','ES256'],audience=client_id,issuer=os.getenv('DAEP_OIDC_ISSUER').rstrip('/'),options={'require':['exp','iat','sub','iss','aud']})
        if not secrets.compare_digest(str(claims.get('nonce','')),nonce): raise ValueError('OIDC nonce mismatch')
        audiences=claims.get('aud',[])
        if isinstance(audiences,list) and len(audiences)>1 and claims.get('azp')!=client_id: raise ValueError('OIDC authorized party mismatch')
    except Exception: raise HTTPException(401,'OIDC ID token validation failed')
    subject=str(claims.get('sub','')); email=str(claims.get('email',''))
    if not subject: raise HTTPException(401,'OIDC subject is missing')
    created=now(); raw=uuid.uuid4().hex+uuid.uuid4().hex; digest=hashlib.sha256(raw.encode()).hexdigest()
    service_reset=_service_ctx.set(True)
    try:
        with conn() as c:
            row=c.execute('SELECT id FROM members WHERE oidc_subject=?',(subject,)).fetchone()
            if row:
                c.execute("UPDATE members SET token=?,token_status='ACTIVE',token_created_at=?,token_revoked_at=NULL,oidc_email=? WHERE id=?",(digest,created,email,row['id']))
                member_id=row['id']
            else:
                if os.getenv('DAEP_OIDC_AUTO_PROVISION','false').lower()!='true': raise HTTPException(403,'OIDC identity is not provisioned')
                member_id='mem_'+uuid.uuid4().hex[:12]; tenant_id=os.getenv('DAEP_OIDC_DEFAULT_TENANT','tenant-default'); name=str(claims.get('name') or email or subject)
                if not c.execute("SELECT 1 FROM tenants WHERE id=? AND status='ACTIVE'",(tenant_id,)).fetchone(): raise HTTPException(403,'OIDC default tenant is unavailable')
                oidc_role=os.getenv('DAEP_OIDC_DEFAULT_ROLE','developer')
                if oidc_role not in ('developer','manager','reviewer'): oidc_role='developer'
                c.execute("INSERT INTO members(id,name,role,token,created_at,tenant_id,token_status,token_created_at,oidc_subject,oidc_email) VALUES(?,?,?,?,?,?,?,?,?,?)",(member_id,name,oidc_role,digest,created,tenant_id,'ACTIVE',created,subject,email))
    finally:
        _service_ctx.reset(service_reset)
    response=JSONResponse({'member_id':member_id,'token':raw,'token_expires_at':None,'message':'OIDC authentication succeeded; store this API token securely. It is returned only once.'})
    response.delete_cookie('daep_oidc_state',path='/api/v1/auth/oidc/callback')
    return response

@app.get('/api/v1/auth/oidc/config')
def oidc_config():
    enabled=bool(os.getenv('DAEP_OIDC_ISSUER') and os.getenv('DAEP_OIDC_CLIENT_ID') and os.getenv('DAEP_OIDC_REDIRECT_URI'))
    return {'enabled':enabled,'issuer':os.getenv('DAEP_OIDC_ISSUER',''),'client_id':os.getenv('DAEP_OIDC_CLIENT_ID',''),'redirect_uri':os.getenv('DAEP_OIDC_REDIRECT_URI',''),'scopes':os.getenv('DAEP_OIDC_SCOPES','openid profile email')}

@app.post('/api/v1/integrations/git/webhook')
async def git_webhook(request:Request, body:dict, x_daep_webhook_secret:str=Header('',alias='X-DAEP-Webhook-Secret'), x_daep_tenant_id:str=Header('',alias='X-DAEP-Tenant-ID'), x_daep_provider:str=Header('',alias='X-DAEP-Provider'), x_github_event:str=Header('',alias='X-GitHub-Event'), x_github_delivery:str=Header('',alias='X-GitHub-Delivery'), x_hub_signature_256:str=Header('',alias='X-Hub-Signature-256'), x_gitlab_event:str=Header('',alias='X-Gitlab-Event'), x_gitlab_event_uuid:str=Header('',alias='X-Gitlab-Event-UUID'), x_gitlab_token:str=Header('',alias='X-Gitlab-Token')):
    raw=await request.body()
    provider=(x_daep_provider or ('github' if x_github_event or x_hub_signature_256 else 'gitlab' if x_gitlab_event or x_gitlab_token else 'generic')).lower()
    if provider not in ('github','gitlab','generic'): raise HTTPException(422,'Unsupported Git provider')
    if provider=='github':
        expected=os.getenv('DAEP_GITHUB_WEBHOOK_SECRET') or os.getenv('DAEP_GIT_WEBHOOK_SECRET','')
        if not expected or not x_hub_signature_256 or not x_hub_signature_256.startswith('sha256='): raise HTTPException(401,'GitHub webhook signature is required')
        supplied=x_hub_signature_256.split('=',1)[1]
        actual=hmac.new(expected.encode(),raw,hashlib.sha256).hexdigest()
        if not hmac.compare_digest(actual,supplied): raise HTTPException(401,'Invalid GitHub webhook signature')
        delivery=x_github_delivery
    elif provider=='gitlab':
        expected=os.getenv('DAEP_GITLAB_WEBHOOK_SECRET') or os.getenv('DAEP_GIT_WEBHOOK_SECRET','')
        if not expected or not x_gitlab_token or not secrets.compare_digest(hashlib.sha256(x_gitlab_token.encode()).digest(),hashlib.sha256(expected.encode()).digest()): raise HTTPException(401,'Invalid GitLab webhook token')
        delivery=x_gitlab_event_uuid
    else:
        expected=os.getenv('DAEP_GIT_WEBHOOK_SECRET','')
        if not expected or not x_daep_webhook_secret or not secrets.compare_digest(hashlib.sha256(x_daep_webhook_secret.encode()).digest(),hashlib.sha256(expected.encode()).digest()): raise HTTPException(401,'Invalid webhook secret')
        delivery=request.headers.get('X-DAEP-Delivery','')
    if delivery and len(delivery)>200: raise HTTPException(422,'Webhook delivery id is too long')
    event_type=str(body.get('event_type') or body.get('action') or x_github_event or x_gitlab_event or 'push')[:80]
    task_id=body.get('task_id'); commit=body.get('after') or body.get('commit_sha')
    service_reset=_service_ctx.set(True)
    try:
        with conn() as c:
            if task_id:
                row=c.execute('SELECT p.tenant_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE t.id=?',(task_id,)).fetchone()
                if not row: raise HTTPException(404,'Task not found')
                tenant_id=row['tenant_id']
            else:
                tenant_id=str(x_daep_tenant_id or body.get('tenant_id') or '').strip()
                if not tenant_id: raise HTTPException(422,'X-DAEP-Tenant-ID is required when task_id is absent')
                if not c.execute("SELECT 1 FROM tenants WHERE id=? AND status='ACTIVE'",(tenant_id,)).fetchone(): raise HTTPException(404,'Tenant not found or inactive')
        _tenant_ctx.set(tenant_id); _admin_ctx.set(False)
        _service_ctx.reset(service_reset); service_reset=_service_ctx.set(False)
        with conn() as c:
            eid=event(c,'git.webhook.received',None,task_id,{'provider':provider,'delivery_id':delivery,'event_type':event_type,'commit_sha':commit,'payload':body},key=(f'git:{provider}:{delivery}' if delivery else None),tenant_override=tenant_id)
        return {'accepted':True,'event_id':eid,'event_type':event_type,'commit_sha':commit,'tenant_id':tenant_id,'provider':provider,'delivery_id':delivery}
    finally:
        _service_ctx.reset(service_reset)

@app.get('/health')
def health():
    service_reset=_service_ctx.set(True)
    try:
        with conn() as c:
            pending=c.execute("SELECT COUNT(*) n FROM outbox WHERE status IN ('PENDING','IN_FLIGHT')").fetchone()['n']
        return {'status':'ok','service':'daep-api','version':'1.0.0-rc9','outbox_pending':pending}
    finally:
        _service_ctx.reset(service_reset)

@app.get('/readyz')
def readiness():
    service_reset=_service_ctx.set(True)
    try:
        with conn() as c:
            c.execute('SELECT 1').fetchone()
            if DATABASE_URL.startswith(('postgresql://','postgres://')):
                c.execute("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='members'").fetchone()
        return {'status':'ready','service':'daep-api','version':'1.0.0-rc9'}
    except Exception:
        raise HTTPException(503,'DAEP database readiness check failed')
    finally:
        _service_ctx.reset(service_reset)
@app.post('/api/v1/auth/login')
def password_login(body:dict):
    username=str(body.get('username','')).strip().lower()
    password=str(body.get('password',''))
    if not username or len(username)>120 or not password:
        raise HTTPException(422,'Username and password are required')
    with conn() as c:
        row=c.execute("SELECT * FROM members WHERE lower(username)=? AND password_status='ACTIVE' AND token_status='ACTIVE'",(username,)).fetchone()
    if not row or not row['password_hash'] or not verify_password(password,row['password_hash']):
        raise HTTPException(401,'Invalid username or password')
    raw=issue_member_token(row['id'])
    return {'access_token':raw,'token_type':'bearer','member_id':row['id'],'name':row['name']}

@app.post('/api/v1/auth/change-password')
def change_password(body:dict,authorization:str=Header(None)):
    a=actor(authorization); current=str(body.get('current_password','')); new=str(body.get('new_password',''))
    if len(new)<12 or len(new)>256 or not current: raise HTTPException(422,'Password must be 12-256 characters')
    with conn() as c:
        row=c.execute("SELECT password_hash FROM members WHERE id=?",(a['id'],)).fetchone()
    if not row or not row['password_hash'] or not verify_password(current,row['password_hash']):
        raise HTTPException(401,'Current password is incorrect')
    with conn() as c: c.execute("UPDATE members SET password_hash=?,password_status='ACTIVE' WHERE id=?",(hash_password(new),a['id']))
    issue_member_token(a['id'])
    return {'changed':True}

@app.get('/api/v1/me')
def me(authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        row=c.execute('SELECT username FROM members WHERE id=?',(a['id'],)).fetchone()
    return {k:a[k] for k in ('id','name','role')} | {'username': row['username'] if row else None}
@app.post('/api/v1/tenants')
def create_tenant(body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    name=str(body.get('name','')).strip()
    if not name or len(name)>160: raise HTTPException(422,'Tenant name is required')
    tid='ten_'+uuid.uuid4().hex[:12]
    with conn() as c: c.execute('INSERT INTO tenants(id,name,status,created_at) VALUES(?,?,?,?)',(tid,name,'ACTIVE',now()))
    return {'id':tid,'name':name,'status':'ACTIVE'}

@app.get('/api/v1/tenants')
def list_tenants(authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    with conn() as c: return [dict(x) for x in c.execute('SELECT * FROM tenants ORDER BY created_at')]

@app.post('/api/v1/members')
def create_member(body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    name=str(body.get('name','')).strip()
    username=str(body.get('username','')).strip().lower()
    password=str(body.get('password',''))
    role=body.get('role','member')
    if not name or not username: raise HTTPException(422,'Name and username are required')
    if role!='member': raise HTTPException(422,'New platform users must use the member account role; project roles are assigned per project')
    if len(password)<12 or len(password)>256: raise HTTPException(422,'Password must be 12-256 characters')
    mid='mem_'+uuid.uuid4().hex[:12]; token=uuid.uuid4().hex+uuid.uuid4().hex; created=now()
    tenant_id=str(body.get('tenant_id') or a.get('tenant_id') or 'tenant-default')
    with conn() as c:
        if not c.execute("SELECT 1 FROM tenants WHERE id=? AND status='ACTIVE'",(tenant_id,)).fetchone(): raise HTTPException(404,'Tenant not found or inactive')
        if c.execute("SELECT 1 FROM members WHERE lower(username)=?",(username,)).fetchone(): raise HTTPException(409,'Username already exists')
        c.execute('INSERT INTO members(id,name,username,role,token,created_at,tenant_id,token_status,token_created_at,token_revoked_at,token_expires_at,password_hash,password_status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(mid,name,username,role,hashlib.sha256(token.encode()).hexdigest(),created,tenant_id,'ACTIVE',created,None,body.get('token_expires_at'),hash_password(password),'ACTIVE'))
    return {'id':mid,'name':name,'username':username,'role':role,'tenant_id':tenant_id}
@app.get('/api/v1/members')
def members(authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    with conn() as c: return [dict(x) for x in c.execute("SELECT id,name,username,role,tenant_id,token_status,password_status,created_at FROM members ORDER BY created_at")]
@app.get('/api/v1/members/{member_id}')
def member_detail(member_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    with conn() as c:
        row=c.execute("SELECT id,name,username,role,tenant_id,token_status,password_status,created_at FROM members WHERE id=?",(member_id,)).fetchone()
        if not row: raise HTTPException(404,'Member not found')
        projects=c.execute("""
            SELECT p.id,p.name,pm.role AS project_role,pm.work_function,pm.joined_at
            FROM project_members pm JOIN projects p ON p.id=pm.project_id
            WHERE pm.member_id=? ORDER BY p.created_at DESC
        """,(member_id,)).fetchall()
        return {**dict(row),'projects':[dict(x) for x in projects]}

@app.post('/api/v1/members/{member_id}/disable')
def disable_member(member_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    if member_id==a['id']: raise HTTPException(409,'The active platform administrator cannot disable their own account')
    with conn() as c:
        target=c.execute('SELECT tenant_id FROM members WHERE id=?',(member_id,)).fetchone()
        if not target: raise HTTPException(404,'Member not found')
        stamp=now()
        c.execute("UPDATE members SET password_status='DISABLED',token_status='REVOKED',token_revoked_at=? WHERE id=?",(stamp,member_id))
        owned_agents=c.execute("SELECT id FROM agents WHERE owner_member_id=? AND tenant_id=? AND status='ACTIVE'",
            (member_id,target['tenant_id'])).fetchall()
        for agent_row in owned_agents:
            agent_id=agent_row['id']
            c.execute("UPDATE agents SET status='DISABLED',updated_at=? WHERE id=?",(stamp,agent_id))
            c.execute("UPDATE agent_tokens SET status='REVOKED',revoked_at=? WHERE agent_id=? AND status='ACTIVE'",
                (stamp,agent_id))
            assignments=c.execute("""SELECT id,task_id FROM agent_task_assignments
                WHERE agent_id=? AND status IN ('ASSIGNED','ACCEPTED')""",(agent_id,)).fetchall()
            for assignment in assignments:
                c.execute("""UPDATE agent_task_assignments SET status='REVOKED',revoked_at=?,updated_at=?
                    WHERE id=? AND status IN ('ASSIGNED','ACCEPTED')""",(stamp,stamp,assignment['id']))
                event(c,'task.agent_assignment_revoked',a['id'],assignment['task_id'],{
                    'assignment_id':assignment['id'],'agent_id':agent_id,
                    'reason':'Agent owner account disabled'},tenant_override=target['tenant_id'])
            event(c,'agent.owner_account_disabled',a['id'],None,{'agent_id':agent_id,
                'revoked_assignment_count':len(assignments)},tenant_override=target['tenant_id'])
        event(c,'member.account.disabled',a['id'],None,{'member_id':member_id,
            'disabled_agent_count':len(owned_agents)},tenant_override=target['tenant_id'])
    return {'member_id':member_id,'password_status':'DISABLED','token_status':'REVOKED',
        'disabled_agent_count':len(owned_agents)}

@app.post('/api/v1/members/{member_id}/enable')
def enable_member(member_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    with conn() as c:
        target=c.execute('SELECT tenant_id,password_hash FROM members WHERE id=?',(member_id,)).fetchone()
        if not target: raise HTTPException(404,'Member not found')
        if not target['password_hash']: raise HTTPException(409,'Member has no password; reset password first')
        stamp=now()
        c.execute("UPDATE members SET password_status='ACTIVE',token_status='ACTIVE',token_created_at=?,token_revoked_at=NULL WHERE id=?",(stamp,member_id))
        event(c,'member.account.enabled',a['id'],None,{'member_id':member_id},tenant_override=target['tenant_id'])
    return {'member_id':member_id,'password_status':'ACTIVE','token_status':'ACTIVE'}

@app.post('/api/v1/members/{member_id}/reset-password')
def reset_member_password(member_id:str,body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    password=str(body.get('password',''))
    if len(password)<12 or len(password)>256: raise HTTPException(422,'Password must be 12-256 characters')
    with conn() as c:
        target=c.execute('SELECT tenant_id FROM members WHERE id=?',(member_id,)).fetchone()
        if not target: raise HTTPException(404,'Member not found')
        stamp=now()
        c.execute("UPDATE members SET password_hash=?,password_status='ACTIVE',token_status='REVOKED',token_revoked_at=? WHERE id=?",(hash_password(password),stamp,member_id))
        event(c,'member.password.reset',a['id'],None,{'member_id':member_id},tenant_override=target['tenant_id'])
    return {'member_id':member_id,'password_status':'ACTIVE','token_status':'REVOKED'}

@app.post('/api/v1/members/{member_id}/revoke-token')
def revoke_member_token(member_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    with conn() as c:
        target=c.execute('SELECT tenant_id FROM members WHERE id=?',(member_id,)).fetchone()
        if not target: raise HTTPException(404,'Member not found')
        cur=c.execute("UPDATE members SET token_status='REVOKED',token_revoked_at=? WHERE id=?" ,(now(),member_id))
        event(c,'member.token.revoked',a['id'],None,{'member_id':member_id},tenant_override=target['tenant_id'])
    return {'member_id':member_id,'token_status':'REVOKED'}

@app.post('/api/v1/members/{member_id}/rotate-token')
def rotate_member_token(member_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    token=uuid.uuid4().hex+uuid.uuid4().hex; created=now(); digest=hashlib.sha256(token.encode()).hexdigest()
    with conn() as c:
        target=c.execute('SELECT tenant_id FROM members WHERE id=?',(member_id,)).fetchone()
        if not target: raise HTTPException(404,'Member not found')
        cur=c.execute("UPDATE members SET token=?,token_status='ACTIVE',token_created_at=?,token_revoked_at=NULL WHERE id=?",(digest,created,member_id))
        event(c,'member.token.rotated',a['id'],None,{'member_id':member_id},tenant_override=target['tenant_id'])
    return {'member_id':member_id,'token':token,'token_status':'ACTIVE','token_created_at':created}

@app.post('/api/v1/projects')
def create_project(b:ProjectIn,authorization:str=Header(None)):
    a=actor(authorization); pid='prj_'+uuid.uuid4().hex[:12]
    with conn() as c:
        c.execute('INSERT INTO projects(id,name,description,created_by,created_at,tenant_id) VALUES(?,?,?,?,?,?)',(pid,b.name,b.description,a['id'],now(),a.get('tenant_id','tenant-default')))
        c.execute('INSERT INTO project_members(project_id,member_id,role,work_function,joined_at) VALUES(?,?,?,?,?)',(pid,a['id'],'owner','other',now()))
    return {'id':pid,'name':b.name,'description':b.description}
@app.get('/api/v1/projects')
def projects(authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        if is_admin(a): rows=c.execute('SELECT * FROM projects ORDER BY created_at DESC')
        else: rows=c.execute('SELECT p.*,pm.role AS project_role,pm.work_function FROM projects p JOIN project_members pm ON pm.project_id=p.id WHERE pm.member_id=? AND p.tenant_id=? ORDER BY p.created_at DESC',(a['id'],a.get('tenant_id','tenant-default')))
        return [dict(x) for x in rows]
@app.get('/api/v1/projects/{pid}/members')
def project_members(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        return [dict(x) for x in c.execute('SELECT m.id,m.name,m.username,m.role AS account_role,pm.role AS project_role,pm.work_function,pm.joined_at FROM project_members pm JOIN members m ON m.id=pm.member_id WHERE pm.project_id=? ORDER BY pm.joined_at',(pid,))]
@app.get('/api/v1/projects/{pid}/member-candidates')
def project_member_candidates(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        if not project: raise HTTPException(404,'Project not found')
        rows=c.execute("""
            SELECT m.id,m.name,m.username,m.role AS account_role,
                   CASE WHEN pm.member_id IS NULL THEN 0 ELSE 1 END AS already_member,
                   pm.role AS project_role,pm.work_function
            FROM members m
            LEFT JOIN project_members pm ON pm.project_id=? AND pm.member_id=m.id
            WHERE m.tenant_id=? AND m.password_status='ACTIVE'
            ORDER BY m.name
        """,(pid,project['tenant_id'])).fetchall()
        return [dict(x) for x in rows]

@app.post('/api/v1/projects/{pid}/members')
def add_project_member(pid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization)
    mid=b.get('member_id') or b.get('member_username'); role=b.get('role','member'); work_function=b.get('work_function','other')
    if role not in ('member','reviewer','manager'): raise HTTPException(422,'Invalid project role')
    if work_function not in ('developer','tester','product','architect','other'): raise HTTPException(422,'Invalid work function')
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        if role=='manager' and not is_admin(a):
            own=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not own or own['role']!='owner': raise HTTPException(403,'Only project owners may directly grant manager role; use an approval request')
        member_row=c.execute('SELECT tenant_id FROM members WHERE id=?',(mid,)).fetchone()
        project_row=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        if not member_row: raise HTTPException(404,'Member not found')
        if project_row['tenant_id'] != member_row['tenant_id']: raise HTTPException(400,'Member belongs to a different tenant')
        c.execute('INSERT INTO project_members(project_id,member_id,role,work_function,joined_at) VALUES(?,?,?,?,?) ON CONFLICT(project_id,member_id) DO UPDATE SET role=excluded.role,work_function=excluded.work_function',(pid,mid,role,work_function,now()))
        event(c,'project.member.role_set',a['id'],None,{'project_id':pid,'member_id':mid,'role':role},tenant_override=project_row['tenant_id'])
        return {'project_id':pid,'member_id':mid,'role':role,'work_function':work_function}
@app.patch('/api/v1/projects/{pid}/members/{member_id}/function')
def update_project_member_function(pid:str,member_id:str,b:ProjectMemberFunctionIn,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        target=c.execute('SELECT role,work_function FROM project_members WHERE project_id=? AND member_id=?',(pid,member_id)).fetchone()
        if not target: raise HTTPException(404,'Target is not a project member')
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        c.execute('UPDATE project_members SET work_function=? WHERE project_id=? AND member_id=?',(b.work_function,pid,member_id))
        event(c,'project.member.work_function_set',a['id'],None,{'project_id':pid,'member_id':member_id,'work_function':b.work_function},tenant_override=project['tenant_id'])
        return {'project_id':pid,'member_id':member_id,'project_role':target['role'],'work_function':b.work_function}

@app.post('/api/v1/projects/{pid}/role-change-requests')
def request_project_role_change(pid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization); member_id=str(b.get('member_id','')).strip(); new_role=str(b.get('new_role','')).strip()
    reason=str(b.get('reason','')).strip()
    if not member_id or new_role not in ('member','reviewer','manager') or not reason or len(reason)>1000:
        raise HTTPException(422,'member_id, valid new_role and reason (1-1000 chars) are required')
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        target=c.execute('SELECT tenant_id FROM members WHERE id=?',(member_id,)).fetchone()
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        if not target or target['tenant_id']!=project['tenant_id']: raise HTTPException(404,'Member not found in project tenant')
        if not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(pid,member_id)).fetchone(): raise HTTPException(404,'Target is not a project member')
        current=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,member_id)).fetchone()['role']
        if current==new_role: raise HTTPException(409,'Member already has requested role')
        aid='apr_'+uuid.uuid4().hex
        payload={'member_id':member_id,'previous_role':current,'new_role':new_role,'reason':reason}
        c.execute("INSERT INTO project_approvals(id,project_id,tenant_id,requester_member_id,action,payload,status,created_at) VALUES(?,?,?,?,? ,?,'PENDING',?)",
                  (aid,pid,project['tenant_id'],a['id'],'PROJECT_ROLE_CHANGE',json.dumps(payload),now()))
        event(c,'project.role_change.requested',a['id'],None,{'approval_id':aid,'project_id':pid,**payload},tenant_override=project['tenant_id'])
        return {'approval_id':aid,'status':'PENDING','project_id':pid,'payload':payload}

@app.get('/api/v1/projects/{pid}/approvals')
def list_project_approvals(pid:str,status:str='PENDING',limit:int=100,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,200))
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute('SELECT * FROM project_approvals WHERE project_id=? AND status=? ORDER BY created_at DESC LIMIT ?',(pid,status,limit)).fetchall()
        return {'items':[{'id':x['id'],'action':x['action'],'payload':json.loads(x['payload']),'status':x['status'],'requester_member_id':x['requester_member_id'],'decided_by':x['decided_by'],'decision_reason':x['decision_reason'],'created_at':x['created_at'],'decided_at':x['decided_at']} for x in rows]}

@app.post('/api/v1/projects/{pid}/approvals/{approval_id}/decision')
def decide_project_approval(pid:str,approval_id:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization); decision=str(b.get('decision','')).upper(); reason=str(b.get('reason','')).strip()
    if decision not in ('APPROVE','REJECT') or not reason or len(reason)>1000: raise HTTPException(422,'decision must be APPROVE or REJECT and reason is required')
    with conn() as c:
        require_project_access(c,pid,a)
        if not is_admin(a):
            own=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not own or own['role']!='owner': raise HTTPException(403,'Project owner approval required')
        row=c.execute('SELECT * FROM project_approvals WHERE id=? AND project_id=?',(approval_id,pid)).fetchone()
        if not row: raise HTTPException(404,'Approval not found')
        if row['status']!='PENDING': raise HTTPException(409,'Approval already decided')
        if row['requester_member_id']==a['id']: raise HTTPException(403,'Requester cannot approve their own request')
        payload=json.loads(row['payload'])
        if row['action']!='PROJECT_ROLE_CHANGE': raise HTTPException(409,'Unsupported approval action')
        if decision=='APPROVE':
            current=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,payload['member_id'])).fetchone()
            if not current or current['role']!=payload['previous_role']: raise HTTPException(409,'Target role changed since request; submit a new request')
            c.execute('UPDATE project_members SET role=? WHERE project_id=? AND member_id=?',(payload['new_role'],pid,payload['member_id']))
        stamp=now()
        approval_status='APPROVED' if decision=='APPROVE' else 'REJECTED'
        c.execute('UPDATE project_approvals SET status=?,decided_by=?,decision_reason=?,decided_at=? WHERE id=? AND status=?',(approval_status,a['id'],reason,stamp,approval_id,'PENDING'))
        event(c,'project.role_change.'+('approved' if decision=='APPROVE' else 'rejected'),a['id'],None,{'approval_id':approval_id,'project_id':pid,**payload,'decision_reason':reason},tenant_override=row['tenant_id'])
        return {'approval_id':approval_id,'status':approval_status,'member_id':payload['member_id'],'role':payload['new_role'] if decision=='APPROVE' else payload['previous_role']}

@app.get('/api/v1/requirements/{rid}/acceptance-report')
def requirement_acceptance_report(rid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        req=c.execute('SELECT * FROM requirements WHERE id=?',(rid,)).fetchone()
        if not req: raise HTTPException(404,'Requirement not found')
        require_project_access(c,req['project_id'],a)
        criteria=json.loads(req['acceptance_criteria'] or '[]')
        tasks=c.execute("SELECT t.id,t.title,t.status,t.progress,t.updated_at,(SELECT COUNT(*) FROM artifacts ar WHERE ar.task_id=t.id) AS artifact_count FROM tasks t WHERE t.requirement_id=? ORDER BY t.created_at,t.id",(rid,)).fetchall()
        items=[dict(x) for x in tasks]
        missing=[x['id'] for x in items if x['status']!='DONE' or x['artifact_count']<1]
        return {'requirement_id':rid,'project_id':req['project_id'],'title':req['title'],'status':req['status'],
            'acceptance_criteria':[{'index':i,'text':v} for i,v in enumerate(criteria)],'task_count':len(items),
            'tasks':items,'all_tasks_done':bool(items) and all(x['status']=='DONE' for x in items),
            'missing_delivery_evidence_task_ids':missing,'ready_for_acceptance':bool(items) and not missing and bool(criteria)}

@app.post('/api/v1/requirements/{rid}/acceptance')
def decide_requirement_acceptance(rid:str,b:RequirementAcceptanceIn,authorization:str=Header(None)):
    a=actor(authorization)
    if a.get('actor_type')=='AGENT': raise HTTPException(403,'Agent cannot approve or reject requirement acceptance')
    with conn() as c:
        req=c.execute('SELECT * FROM requirements WHERE id=?',(rid,)).fetchone()
        if not req: raise HTTPException(404,'Requirement not found')
        pid=req['project_id']; require_project_access(c,pid,a)
        if not is_admin(a):
            role=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not role or role['role'] not in ('owner','manager','reviewer'): raise HTTPException(403,'Reviewer role required')
        if req['status']=='ACCEPTED': raise HTTPException(409,'Requirement is already accepted')
        criteria=json.loads(req['acceptance_criteria'] or '[]')
        verified=list(dict.fromkeys(b.verified_criteria))
        if len(verified)!=len(b.verified_criteria): raise HTTPException(422,'verified_criteria must be unique')
        if any(i<0 or i>=len(criteria) for i in verified): raise HTTPException(422,'verified_criteria contains an unknown criterion index')
        tasks=c.execute("SELECT t.id,t.status,(SELECT COUNT(*) FROM artifacts ar WHERE ar.task_id=t.id) AS artifact_count FROM tasks t WHERE t.requirement_id=? ORDER BY t.id",(rid,)).fetchall()
        if b.decision=='APPROVE':
            if not criteria or verified!=list(range(len(criteria))): raise HTTPException(409,'Every acceptance criterion must be explicitly verified')
            pending=[x['id'] for x in tasks if x['status']!='DONE']
            missing=[x['id'] for x in tasks if x['artifact_count']<1]
            if not tasks or pending or missing: raise HTTPException(409,detail={'message':'Requirement cannot be accepted until every task is DONE and has delivery evidence','pending_task_ids':pending,'missing_artifact_task_ids':missing})
            status='ACCEPTED'
        else: status='OPEN'
        stamp=now(); c.execute('UPDATE requirements SET status=? WHERE id=?',(status,rid))
        tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id']
        payload={'project_id':pid,'requirement_id':rid,'decision':b.decision,'status':status,'verified_criteria':verified,
            'acceptance_criteria':criteria,'comment':b.comment,'task_ids':[x['id'] for x in tasks]}
        eid=event(c,'requirement.acceptance.'+b.decision.lower(),a['id'],None,payload,tenant_override=tenant)
        return {'requirement_id':rid,'status':status,'decision':b.decision,'event_id':eid,'decided_at':stamp,'verified_criteria':verified}

@app.post('/api/v1/projects/{pid}/decisions')
def record_project_decision(pid:str,b:ProjectDecisionIn,authorization:str=Header(None)):
    a=actor(authorization); decision_id='dec_'+uuid.uuid4().hex
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        accountable=c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(pid,b.accountable_member_id)).fetchone()
        if not accountable: raise HTTPException(422,'Accountable member must belong to this project')
        task_ids=list(dict.fromkeys(b.related_task_ids))
        if len(task_ids)!=len(b.related_task_ids): raise HTTPException(422,'related_task_ids must be unique')
        for task_id in task_ids:
            if task_project(c,task_id)!=pid: raise HTTPException(422,'Every related task must belong to this project')
        payload={'project_id':pid,'decision_id':decision_id,'title':b.title,'decision':b.decision,
            'rationale':b.rationale,'accountable_member_id':b.accountable_member_id,
            'related_task_ids':task_ids,'due_at':b.due_at,'recorded_by':a['id']}
        event(c,'project.decision.created',a['id'],None,payload)
    return {'id':decision_id,'project_id':pid,'status':'RECORDED','created_at':now(),**payload}

@app.get('/api/v1/projects/{pid}/decisions')
def list_project_decisions(pid:str,limit:int=100,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,500))
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("SELECT e.id,e.actor_member_id,e.payload,e.created_at,m.name AS actor_name FROM events e LEFT JOIN members m ON m.id=e.actor_member_id WHERE e.event_type='project.decision.created' AND e.payload LIKE ? ORDER BY e.created_at DESC LIMIT ?",('%"project_id"%"'+pid+'"%',limit)).fetchall()
        items=[]
        for row in rows:
            payload=json.loads(row['payload'] or '{}')
            if payload.get('project_id')!=pid: continue
            accountable=c.execute('SELECT name FROM members WHERE id=?',(payload.get('accountable_member_id'),)).fetchone()
            items.append({'id':payload.get('decision_id'),'title':payload.get('title'),'decision':payload.get('decision'),
                'rationale':payload.get('rationale',''),'accountable_member_id':payload.get('accountable_member_id'),
                'accountable_member_name':accountable['name'] if accountable else None,'related_task_ids':payload.get('related_task_ids',[]),
                'due_at':payload.get('due_at'),'recorded_by':row['actor_member_id'],'recorded_by_name':row['actor_name'],
                'created_at':row['created_at'],'audit_event_id':row['id']})
        return {'project_id':pid,'items':items,'count':len(items)}

@app.get('/api/v1/projects/{pid}/governance')
def project_governance_snapshot(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT t.id,t.status,t.progress,t.updated_at,a.member_id,m.name AS member_name
            FROM tasks t JOIN requirements r ON r.id=t.requirement_id
            LEFT JOIN assignments a ON a.task_id=t.id LEFT JOIN members m ON m.id=a.member_id
            WHERE r.project_id=? ORDER BY t.id""",(pid,)).fetchall()
        task_ids=set(); task_state={}
        for row in rows:
            task_ids.add(row['id'])
            task_state[row['id']]={'status':row['status'],'progress':row['progress']}
        total=len(task_ids)
        status_counts={}
        for item in task_state.values(): status_counts[item['status']]=status_counts.get(item['status'],0)+1
        responsibility={}
        for row in rows:
            if not row['member_id']: continue
            slot=responsibility.setdefault(row['member_id'],{'member_id':row['member_id'],'member_name':row['member_name'],'assigned_task_ids':[],'done':0,'active':0,'review':0,'blocked':0})
            if row['id'] not in slot['assigned_task_ids']:
                slot['assigned_task_ids'].append(row['id'])
                if row['status']=='DONE': slot['done']+=1
                elif row['status']=='REVIEW': slot['review']+=1
                elif row['status']=='BLOCKED': slot['blocked']+=1
                else: slot['active']+=1
        packages=c.execute("SELECT risk_state,COUNT(*) AS n FROM task_work_packages WHERE project_id=? AND status='ACTIVE' GROUP BY risk_state",(pid,)).fetchall()
        package_risks={x['risk_state']:x['n'] for x in packages}
        pending_reviews=status_counts.get('REVIEW',0)
        delivery_health=project_message_delivery_health(pid,authorization,120,300,500)
        review_rows=c.execute("""SELECT e.payload,e.created_at FROM events e
            WHERE e.event_type='message.delivery.incident.reviewed' AND e.payload LIKE ?
            ORDER BY e.created_at DESC LIMIT 1000""",('%'+pid+'%',)).fetchall()
        latest_reviews={}
        for review_row in review_rows:
            try:
                payload=json.loads(review_row['payload'] or '{}')
                if payload.get('project_id')!=pid: continue
                mid=payload.get('message_id')
                if mid and mid not in latest_reviews:
                    latest_reviews[mid]={'disposition':payload.get('disposition'),'comment':payload.get('comment'),
                                         'reviewed_at':review_row['created_at']}
            except (TypeError,ValueError):
                continue
        reviewed_incidents=[]
        open_incidents=0; resolved_incidents=0; accepted_risk_incidents=0; investigating_incidents=0
        for incident in delivery_health.get('incidents',[]):
            review=latest_reviews.get(incident['message_id'])
            disposition=review.get('disposition') if review else 'UNREVIEWED'
            item=dict(incident)
            item['review_disposition']=disposition
            item['reviewed_at']=review.get('reviewed_at') if review else None
            reviewed_incidents.append(item)
            if disposition=='RESOLVED': resolved_incidents+=1
            elif disposition=='ACCEPTED_RISK': accepted_risk_incidents+=1
            else:
                open_incidents+=1
                if disposition=='INVESTIGATING': investigating_incidents+=1
        daily=c.execute("""SELECT substr(m.created_at,1,10) AS day,COUNT(*) AS created,
            SUM(CASE WHEN m.status IN ('ACKNOWLEDGED','REJECTED') THEN 1 ELSE 0 END) AS terminal_ack
            FROM messages m JOIN tasks t ON t.id=m.task_id JOIN requirements r ON r.id=t.requirement_id
            WHERE r.project_id=? AND m.created_at>=? GROUP BY substr(m.created_at,1,10) ORDER BY day""",
            (pid,datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).isoformat())).fetchall()
        delivery_trend=[{'date':x['day'],'messages_created':x['created'],'terminal_ack':x['terminal_ack'] or 0} for x in daily]
        message_delivery_governance={
            'checked_messages':delivery_health.get('checked_messages',0),
            'dispatch_counts':delivery_health.get('dispatch_counts',{}),
            'ack_counts':delivery_health.get('ack_counts',{}),
            'incident_count':delivery_health.get('incident_count',0),
            'open_incidents':open_incidents,'investigating_incidents':investigating_incidents,
            'resolved_incidents':resolved_incidents,'accepted_risk_incidents':accepted_risk_incidents,
            'incidents':reviewed_incidents,'trend_since_utc_midnight':delivery_trend,
            'sla_policy':delivery_health.get('policy'),
            'truncated':delivery_health.get('truncated',False)
        }
        return {'project_id':pid,'task_total':total,'task_status_counts':status_counts,
            'completed_tasks':status_counts.get('DONE',0),'completion_percent':round(status_counts.get('DONE',0)*100/total) if total else 100,
            'pending_reviews':pending_reviews,'open_tasks':total-status_counts.get('DONE',0),
            'active_work_package_risk_counts':package_risks,
            'at_risk_work_packages':sum(package_risks.get(k,0) for k in ('OVERDUE','BLOCKED_DEPENDENCY','STALLED')),
            'responsibility':list(responsibility.values()),
            'completion_gate':'SATISFIED' if total and status_counts.get('DONE',0)==total else ('EMPTY' if not total else 'OPEN'),
            'message_delivery':message_delivery_governance}

@app.get('/api/v1/projects/{pid}/workflow')
def get_project_workflow(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        row=c.execute('SELECT config,updated_by,updated_at FROM project_workflows WHERE project_id=?',(pid,)).fetchone()
        if row: return {'project_id':pid,'config':json.loads(row['config']),'updated_by':row['updated_by'],'updated_at':row['updated_at']}
        return {'project_id':pid,'config':{'enabled':True,'stages':[{'key':'OPEN','name':'需求进入','order':1,'approval_role':'none','sla_seconds':None},{'key':'IN_PROGRESS','name':'执行','order':2,'approval_role':'none','sla_seconds':172800},{'key':'REVIEW','name':'评审验收','order':3,'approval_role':'reviewer','sla_seconds':86400},{'key':'DONE','name':'完成交付','order':4,'approval_role':'none','sla_seconds':None}]},'source':'system-default'}

@app.put('/api/v1/projects/{pid}/workflow')
def set_project_workflow(pid:str,b:WorkflowConfigIn,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        if not (a['role']=='admin' or project_role(c,pid,a) in ('owner','manager')): raise HTTPException(403,'Project manager or platform administrator required')
        stages=sorted([x.model_dump() for x in b.stages],key=lambda x:x['order'])
        if [x['order'] for x in stages] != list(range(1,len(stages)+1)): raise HTTPException(422,'Stage order must be contiguous from 1')
        if len({x['key'] for x in stages}) != len(stages): raise HTTPException(422,'Stage keys must be unique')
        if not any(x['key']=='REVIEW' for x in stages): raise HTTPException(422,'System governance requires a REVIEW stage')
        cfg={'enabled':b.enabled,'stages':stages}; stamp=now(); tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id']
        c.execute('INSERT INTO project_workflows(project_id,tenant_id,config,updated_by,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET config=excluded.config,updated_by=excluded.updated_by,updated_at=excluded.updated_at',(pid,tenant,json.dumps(cfg),a['id'],stamp))
        event(c,'project.workflow.updated',a['id'],None,{'project_id':pid,'config':cfg},tenant_override=tenant)
        return {'project_id':pid,'config':cfg,'updated_by':a['id'],'updated_at':stamp}

@app.get('/api/v1/projects/{pid}/gates')
def get_project_gates(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute('SELECT gate_key,config,updated_by,updated_at FROM project_gates WHERE project_id=? ORDER BY gate_key',(pid,)).fetchall()
        items={r['gate_key']:{'config':json.loads(r['config']),'updated_by':r['updated_by'],'updated_at':r['updated_at']} for r in rows}
        items.setdefault('REVIEW_REQUIRED',{'config':{'enabled':True,'required_roles':['reviewer'],'required_evidence':True,'required_all_tasks_done':False},'system_locked':True})
        items.setdefault('DELIVERY_EVIDENCE',{'config':{'enabled':True,'required_roles':['owner','manager','reviewer'],'required_evidence':True,'required_all_tasks_done':True},'system_locked':True})
        return {'project_id':pid,'gates':items}

@app.put('/api/v1/projects/{pid}/gates/{gate_key}')
def set_project_gate(pid:str,gate_key:str,b:GateConfigIn,authorization:str=Header(None)):
    a=actor(authorization)
    if gate_key in ('REVIEW_REQUIRED','DELIVERY_EVIDENCE'): raise HTTPException(409,'System governance gate cannot be disabled or weakened')
    if not re.fullmatch(r'[A-Z0-9_]{2,60}',gate_key): raise HTTPException(422,'Invalid gate key')
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        if not (a['role']=='admin' or project_role(c,pid,a) in ('owner','manager')): raise HTTPException(403,'Project manager or platform administrator required')
        cfg=b.model_dump(); cfg['applies_to']=cfg.get('applies_to') or 'DONE'; stamp=now(); tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id']
        c.execute('INSERT INTO project_gates(project_id,gate_key,tenant_id,config,updated_by,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(project_id,gate_key) DO UPDATE SET config=excluded.config,updated_by=excluded.updated_by,updated_at=excluded.updated_at',(pid,gate_key,tenant,json.dumps(cfg),a['id'],stamp))
        event(c,'project.gate.updated',a['id'],None,{'project_id':pid,'gate_key':gate_key,'config':cfg},tenant_override=tenant)
        return {'project_id':pid,'gate_key':gate_key,'config':cfg,'updated_at':stamp}


DEFAULT_PROJECT_WORKFLOW={'enabled':True,'stages':[{'key':'OPEN','name':'需求进入','order':1,'approval_role':'none','sla_seconds':None},{'key':'IN_PROGRESS','name':'执行','order':2,'approval_role':'none','sla_seconds':172800},{'key':'REVIEW','name':'评审验收','order':3,'approval_role':'reviewer','sla_seconds':86400},{'key':'DONE','name':'完成交付','order':4,'approval_role':'none','sla_seconds':None}]}
SYSTEM_GOVERNANCE_GATES={
    'REVIEW_REQUIRED':{'enabled':True,'required_roles':['reviewer'],'required_evidence':True,'required_all_tasks_done':False,'applies_to':'DONE'},
    'DELIVERY_EVIDENCE':{'enabled':True,'required_roles':['owner','manager','reviewer'],'required_evidence':True,'required_all_tasks_done':True,'applies_to':'DONE'}
}
def project_role(c,pid,actor_value):
    row=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,actor_value['id'])).fetchone()
    return row['role'] if row else None
def project_workflow_config(c,pid):
    row=c.execute('SELECT config FROM project_workflows WHERE project_id=?',(pid,)).fetchone()
    return json.loads(row['config']) if row else DEFAULT_PROJECT_WORKFLOW
def project_gate_config(c,pid,gate_key):
    if gate_key in SYSTEM_GOVERNANCE_GATES: return SYSTEM_GOVERNANCE_GATES[gate_key]
    row=c.execute('SELECT config FROM project_gates WHERE project_id=? AND gate_key=?',(pid,gate_key)).fetchone()
    return json.loads(row['config']) if row else None
def enforce_project_gate(c,pid,gate_key,actor_member_id,task_id=None,target_stage='DONE'):
    cfg=project_gate_config(c,pid,gate_key)
    if not cfg or not cfg.get('enabled',True) or cfg.get('applies_to','DONE')!=target_stage: return
    if cfg.get('required_roles'):
        platform=c.execute('SELECT role FROM members WHERE id=?',(actor_member_id,)).fetchone()
        if not platform or platform['role']!='admin':
            member_role=project_role(c,pid,{'id':actor_member_id})
            function_row=c.execute('SELECT work_function FROM project_members WHERE project_id=? AND member_id=?',(pid,actor_member_id)).fetchone()
            work_function=function_row['work_function'] if function_row else None
            if member_role not in cfg['required_roles'] and work_function not in cfg['required_roles']:
                raise HTTPException(403,f'Gate {gate_key} requires one of: {", ".join(cfg["required_roles"])}')
    if task_id and cfg.get('required_evidence'):
        if c.execute('SELECT 1 FROM artifacts WHERE task_id=? LIMIT 1',(task_id,)).fetchone() is None:
            raise HTTPException(409,detail={'message':f'Gate {gate_key} requires delivery evidence','gate_key':gate_key,'task_id':task_id})
    if task_id and cfg.get('required_all_tasks_done'):
        row=c.execute('SELECT requirement_id FROM tasks WHERE id=?',(task_id,)).fetchone()
        if row:
            pending=c.execute("SELECT id FROM tasks WHERE requirement_id=? AND status!='DONE' AND id!=?",(row['requirement_id'],task_id)).fetchall()
            if pending: raise HTTPException(409,detail={'message':f'Gate {gate_key} requires all other requirement tasks to be DONE before this task closes','gate_key':gate_key,'pending_task_ids':[x['id'] for x in pending]})
def enforce_workflow_exit(c,pid,current_stage,actor_member_id):
    cfg=project_workflow_config(c,pid)
    stage=next((x for x in cfg.get('stages',[]) if x.get('key')==current_stage),None)
    if not stage: raise HTTPException(409,detail={'message':'Current task status is not part of the configured workflow','current_stage':current_stage})
    approval_role=stage.get('approval_role','none')
    if approval_role!='none':
        platform=c.execute('SELECT role FROM members WHERE id=?',(actor_member_id,)).fetchone()
        if not platform or platform['role']!='admin':
            role=project_role(c,pid,{'id':actor_member_id})
            if role!=approval_role: raise HTTPException(403,f'Leaving workflow stage {current_stage} requires {approval_role} role')
def enforce_workflow_stage(c,pid,stage_key,actor_member_id,task_id=None):
    cfg=project_workflow_config(c,pid)
    stage=next((x for x in cfg.get('stages',[]) if x.get('key')==stage_key),None)
    if not stage: raise HTTPException(409,detail={'message':'Target workflow stage is not configured','stage_key':stage_key})
    for gate_key in [x['gate_key'] for x in c.execute('SELECT gate_key FROM project_gates WHERE project_id=?',(pid,)).fetchall()]:
        enforce_project_gate(c,pid,gate_key,actor_member_id,task_id,stage_key)
def transition_task_workflow(c,tid,target_stage,actor_member_id,comment=''):
    pid=task_project(c,tid)
    if not pid: raise HTTPException(404,'Task not found')
    task=c.execute('SELECT status,progress FROM tasks WHERE id=?',(tid,)).fetchone()
    if not task: raise HTTPException(404,'Task not found')
    enforce_workflow_stage(c,pid,target_stage,actor_member_id,tid)
    progress=100 if target_stage=='DONE' else (100 if target_stage=='REVIEW' else task['progress'])
    c.execute('UPDATE tasks SET status=?,progress=?,updated_at=? WHERE id=?',(target_stage,progress,now(),tid))
    eid=event(c,'task.workflow.transitioned',actor_member_id,tid,{'from_status':task['status'],'to_status':target_stage,'comment':comment})
    return eid

@app.get('/api/v1/projects/{pid}/audit')
def project_audit(pid:str,limit:int=100,before:str='',event_type:str='',authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,500))
    with conn() as c:
        require_project_access(c,pid,a)
        sql="SELECT e.* FROM events e LEFT JOIN tasks t ON t.id=e.task_id LEFT JOIN requirements r ON r.id=t.requirement_id WHERE (r.project_id=? OR (e.task_id IS NULL AND e.payload LIKE ?))"
        args=[pid,'%\"project_id\"%\"'+pid+'\"%']
        if before: sql+=" AND e.created_at<?"; args.append(before)
        if event_type: sql+=" AND e.event_type=?"; args.append(event_type)
        sql+=" ORDER BY e.created_at DESC LIMIT ?"; args.append(limit)
        rows=c.execute(sql,args).fetchall()
        return {'project_id':pid,'items':[{'id':x['id'],'event_type':x['event_type'],'actor_member_id':x['actor_member_id'],'task_id':x['task_id'],'payload':json.loads(x['payload'] or '{}'),'created_at':x['created_at']} for x in rows]}

@app.get('/api/v1/projects/{pid}/audit.csv')
def export_project_audit(pid:str,limit:int=5000,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,10000))
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT e.id,e.event_type,e.actor_member_id,e.task_id,e.payload,e.created_at
            FROM events e LEFT JOIN tasks t ON t.id=e.task_id LEFT JOIN requirements r ON r.id=t.requirement_id
            WHERE (r.project_id=? OR (e.task_id IS NULL AND e.payload LIKE ?)) ORDER BY e.created_at DESC LIMIT ?""",(pid,'%\"project_id\"%\"'+pid+'\"%',limit)).fetchall()
        def q(v): return '"'+str(v if v is not None else '').replace('"','""')+'"'
        lines=['id,event_type,actor_member_id,task_id,created_at,payload']
        for x in rows: lines.append(','.join(q(v) for v in (x['id'],x['event_type'],x['actor_member_id'],x['task_id'],x['created_at'],x['payload'])))
        return Response(content='\n'.join(lines)+'\n',media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="daep-audit-{pid}.csv"'})

@app.get('/api/v1/projects/{pid}/requirements')
def project_requirements(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        return [dict(x) for x in c.execute('SELECT * FROM requirements WHERE project_id=? ORDER BY created_at DESC',(pid,))]
@app.get('/api/v1/projects/{pid}/tasks')
def project_tasks(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute('SELECT t.* FROM tasks t JOIN requirements r ON r.id=t.requirement_id WHERE r.project_id=? ORDER BY t.created_at DESC',(pid,)).fetchall()
        result=[]
        for raw in rows:
            item=dict(raw)
            item['dependencies']=[x['depends_on_task_id'] for x in c.execute('SELECT depends_on_task_id FROM dependencies WHERE task_id=?',(item['id'],))]
            result.append(item)
        return result
@app.post('/api/v1/requirements')
def create_requirement(b:RequirementIn,authorization:str=Header(None)):
    a=actor(authorization); rid='req_'+uuid.uuid4().hex[:12]
    with conn() as c:
        if not c.execute('SELECT 1 FROM projects WHERE id=?',(b.project_id,)).fetchone(): raise HTTPException(404,'Project not found')
        require_project_access(c,b.project_id,a,write=True)
        c.execute('INSERT INTO requirements VALUES(?,?,?,?,?,?,?)',(rid,b.project_id,b.title,b.description,json.dumps(b.acceptance_criteria),'OPEN',now()))
    return {'id':rid,'project_id':b.project_id,'title':b.title,'status':'OPEN'}
@app.get('/api/v1/requirements/{rid}')
def get_requirement(rid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        r=c.execute('SELECT * FROM requirements WHERE id=?',(rid,)).fetchone()
        if r: require_project_access(c,r['project_id'],a)
        if not r: raise HTTPException(404,'Requirement not found')
        d=dict(r); d['acceptance_criteria']=json.loads(d['acceptance_criteria']); return d
@app.post('/api/v1/tasks')
def create_task(b:TaskIn,authorization:str=Header(None)):
    a=actor(authorization); tid='tsk_'+uuid.uuid4().hex[:12]
    with conn() as c:
        req=c.execute('SELECT * FROM requirements WHERE id=?',(b.requirement_id,)).fetchone()
        if not req: raise HTTPException(404,'Requirement not found')
        require_project_access(c,req['project_id'],a,write=True)
        for dep in b.dependencies:
            if dep == tid: raise HTTPException(400,'A task cannot depend on itself')
            if not c.execute('SELECT 1 FROM tasks WHERE id=?',(dep,)).fetchone(): raise HTTPException(400,f'Unknown dependency {dep}')
            require_task_access(c,dep,a)
            if task_project(c,dep) != req['project_id']: raise HTTPException(400,'Dependencies must belong to the same project')
        c.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?)',(tid,b.requirement_id,b.title,b.description,'READY',0,now(),now()))
        for mid in b.assignee_member_ids:
            member_row=c.execute('SELECT tenant_id FROM members WHERE id=?',(mid,)).fetchone()
            if not member_row: raise HTTPException(400,f'Unknown member {mid}')
            project_tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(req['project_id'],)).fetchone()['tenant_id']
            if member_row['tenant_id'] != project_tenant: raise HTTPException(400,'Assignee belongs to a different tenant')
            c.execute('INSERT INTO assignments VALUES(?,?)',(tid,mid))
            c.execute("INSERT OR IGNORE INTO project_members(project_id,member_id,role,work_function,joined_at) VALUES(?,?,?,'other',?)",(req['project_id'],mid,'member',now()))
        for dep in b.dependencies: c.execute('INSERT INTO dependencies VALUES(?,?)',(tid,dep))
        event(c,'task.created',a['id'],tid,{'title':b.title})
    return task_detail(tid,authorization)
def task_detail(tid,authorization):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a)
        r=c.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone()
        if not r: raise HTTPException(404,'Task not found')
        d=dict(r); d['assignees']=[dict(x) for x in c.execute('SELECT m.id,m.name FROM assignments a JOIN members m ON m.id=a.member_id JOIN tasks t ON t.id=a.task_id JOIN requirements rq ON rq.id=t.requirement_id JOIN projects p ON p.id=rq.project_id WHERE a.task_id=? AND m.tenant_id=p.tenant_id',(tid,))]; d['dependencies']=[x['depends_on_task_id'] for x in c.execute('SELECT depends_on_task_id FROM dependencies WHERE task_id=?',(tid,))]; return d
@app.get('/api/v1/tasks/{tid}')
def get_task(tid:str,authorization:str=Header(None)): return task_detail(tid,authorization)
@app.put('/api/v1/tasks/{tid}/dependencies')
def update_task_dependencies(tid:str,b:TaskDependenciesIn,authorization:str=Header(None)):
    a=actor(authorization)
    if len(set(b.dependencies)) != len(b.dependencies): raise HTTPException(400,'Duplicate dependencies are not allowed')
    with conn() as c:
        require_task_access(c,tid,a)
        project_id=task_project(c,tid)
        require_project_access(c,project_id,a,write=True)
        for dep in b.dependencies:
            if dep == tid: raise HTTPException(400,'A task cannot depend on itself')
            if task_project(c,dep) != project_id: raise HTTPException(400,'Dependencies must belong to the same project')
            require_task_access(c,dep,a)
            pending=[dep]; visited=set()
            while pending:
                current=pending.pop()
                if current == tid: raise HTTPException(409,'Dependency would create a cycle')
                if current in visited: continue
                visited.add(current)
                pending.extend(x['depends_on_task_id'] for x in c.execute('SELECT depends_on_task_id FROM dependencies WHERE task_id=?',(current,)).fetchall())
        c.execute('DELETE FROM dependencies WHERE task_id=?',(tid,))
        for dep in b.dependencies: c.execute('INSERT INTO dependencies(task_id,depends_on_task_id) VALUES(?,?)',(tid,dep))
        event(c,'task.dependencies.updated',a['id'],tid,{'dependencies':b.dependencies})
    return task_detail(tid,authorization)

@app.get('/api/v1/me/tasks')
def my_tasks(authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c: return [dict(x) for x in c.execute('SELECT t.* FROM tasks t JOIN assignments s ON s.task_id=t.id JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE s.member_id=? AND p.tenant_id=? ORDER BY t.created_at DESC',(a['id'],a.get('tenant_id','tenant-default')))]
@app.post('/api/v1/tasks/{tid}/progress')
def progress(tid:str,b:ProgressIn,authorization:str=Header(None),idempotency_key:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a,assigned_only=True)
        if b.progress==100:
            enforce_task_review_request(c,tid,a)
        identity=a.get('agent_id') if a.get('actor_type')=='AGENT' else a['id']
        scoped_key=f"{identity}:{tid}:{idempotency_key}" if idempotency_key else None
        if scoped_key:
            prior=c.execute('SELECT id,payload FROM events WHERE idempotency_key=?',(scoped_key,)).fetchone()
            if prior:
                prior_payload=json.loads(prior['payload'] or '{}')
                prior_payload.pop('actor_type',None); prior_payload.pop('agent_id',None)
                if prior_payload != b.model_dump(): raise HTTPException(409,'Idempotency-Key was already used with a different payload')
                return {'event_id':prior['id'],'task_id':tid,'progress':b.progress,'idempotent_replay':True}
        c.execute('UPDATE tasks SET progress=?,status=?,updated_at=? WHERE id=?',(b.progress,'REVIEW' if b.progress==100 else ('IN_PROGRESS' if b.progress>0 else 'READY'),now(),tid))
        eid=event(c,'task.progress.updated',a['id'],tid,b.model_dump(),scoped_key)
    return {'event_id':eid,'task_id':tid,'progress':b.progress}
@app.post('/api/v1/tasks/{tid}/blocked')
def blocked(tid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a,assigned_only=True)
        c.execute("UPDATE tasks SET status='BLOCKED',updated_at=? WHERE id=?",(now(),tid)); eid=event(c,'task.blocked',a['id'],tid,b)
    return {'event_id':eid,'status':'BLOCKED'}
@app.post('/api/v1/tasks/{tid}/work-result')
def report_work_result(tid:str,b:WorkResultIn,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        begin_serialized_write(c)
        require_task_access(c,tid,a,assigned_only=True)
        package_sql='SELECT id,parent_task_id,status,correlation_id FROM task_work_packages WHERE child_task_id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): package_sql += ' FOR UPDATE'
        package=c.execute(package_sql,(tid,)).fetchone()
        if not package: raise HTTPException(404,'Task is not a registered work package')
        identity=a.get('agent_id') if a.get('actor_type')=='AGENT' else a['id']
        key=f"work-result:{identity}:{tid}:{b.idempotency_key}" if b.idempotency_key else None
        payload={'outcome':b.outcome,'summary':b.summary,'work_package_id':package['id'],'correlation_id':package['correlation_id'],'parent_task_id':package['parent_task_id']}
        if key:
            prior=c.execute('SELECT id,payload FROM events WHERE idempotency_key=?',(key,)).fetchone()
            if prior:
                prior_payload=json.loads(prior['payload'] or '{}')
                prior_payload.pop('actor_type',None); prior_payload.pop('agent_id',None)
                if prior_payload!=payload: raise HTTPException(409,'Idempotency key was used with a different result')
                return {'task_id':tid,'status':'REVIEW' if b.outcome=='COMPLETE' else 'BLOCKED','event_id':prior['id'],'idempotent_replay':True}
        if package['status']!='ACTIVE': raise HTTPException(409,'Work package is no longer active')
        if b.outcome=='COMPLETE':
            count=c.execute('SELECT COUNT(*) AS n FROM artifacts WHERE task_id=?',(tid,)).fetchone()['n']
            if count<1: raise HTTPException(409,'Submit at least one artifact before reporting completion')
            status='REVIEW'; progress=100
        else:
            status='BLOCKED'; progress=0
        c.execute('UPDATE tasks SET status=?,progress=?,updated_at=? WHERE id=?',(status,progress,now(),tid))
        eid=event(c,'task.work_package.reported',a['id'],tid,payload,key)
    return {'task_id':tid,'status':status,'event_id':eid,'outcome':b.outcome}


@app.post('/api/v1/tasks/{tid}/workflow-transition')
def transition_task_workflow_endpoint(tid:str,b:dict,authorization:str=Header(None),idempotency_key:str=Header(None)):
    a=actor(authorization); target=str(b.get('target_stage','')).strip().upper(); comment=str(b.get('comment',''))[:4000]
    if not target: raise HTTPException(422,'target_stage is required')
    if target=='BLOCKED': raise HTTPException(409,'BLOCKED is controlled by the task blocked endpoint')
    with conn() as c:
        pid=task_project(c,tid)
        if not pid: raise HTTPException(404,'Task not found')
        cfg=project_workflow_config(c,pid)
        stage=next((x for x in cfg.get('stages',[]) if x.get('key')==target),None)
        if not stage: raise HTTPException(409,'Target workflow stage is not configured')
        current=c.execute('SELECT status FROM tasks WHERE id=?',(tid,)).fetchone()['status']
        if is_admin(a): pass
        elif current in ('REVIEW','DONE') or target in ('DONE',):
            require_project_access(c,pid,a,write=True)
        else:
            require_task_access(c,tid,a,assigned_only=True)
        scoped_key=f'workflow:{a["id"]}:{tid}:{idempotency_key}' if idempotency_key else None
        if scoped_key:
            prior=c.execute('SELECT id,payload FROM events WHERE idempotency_key=?',(scoped_key,)).fetchone()
            if prior:
                if prior['payload']!=json.dumps({'target_stage':target,'comment':comment}): raise HTTPException(409,'Idempotency-Key was already used with a different workflow transition')
                return {'task_id':tid,'target_stage':target,'event_id':prior['id'],'idempotent_replay':True}
        enforce_workflow_stage(c,pid,target,a['id'],tid)
        eid=transition_task_workflow(c,tid,target,a['id'],comment)
        if scoped_key:
            # The transition event itself is the idempotent record; attach a unique companion event only when needed.
            c.execute('UPDATE events SET idempotency_key=?,payload=? WHERE id=? AND idempotency_key IS NULL',(scoped_key,json.dumps({'target_stage':target,'comment':comment}),eid))
        return {'task_id':tid,'status':target,'event_id':eid}

@app.post('/api/v1/tasks/{tid}/artifacts')
def artifact(tid:str,b:ArtifactIn,authorization:str=Header(None)):
    a=actor(authorization); aid='art_'+uuid.uuid4().hex[:12]
    with conn() as c:
        require_task_access(c,tid,a,assigned_only=True)
        c.execute('INSERT INTO artifacts(id,task_id,artifact_type,uri,commit_sha,metadata,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',(aid,tid,b.artifact_type,b.uri,b.commit_sha,json.dumps(b.metadata),now(),c.execute('SELECT p.tenant_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE t.id=?',(tid,)).fetchone()['tenant_id'])); wp=c.execute('SELECT correlation_id,id FROM task_work_packages WHERE child_task_id=?',(tid,)).fetchone(); event(c,'artifact.submitted',a['id'],tid,{'artifact_id':aid,'uri':b.uri,'work_package_id':wp['id'] if wp else None,'correlation_id':wp['correlation_id'] if wp else None})
    return {'id':aid,'task_id':tid}
@app.post('/api/v1/tasks/{tid}/review')
def review_task(tid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization); decision=b.get('decision')
    if a.get('actor_type')=='AGENT': raise HTTPException(403,'Agent cannot review or approve tasks')
    if decision not in ('APPROVE','REJECT'): raise HTTPException(422,'decision must be APPROVE or REJECT')
    with conn() as c:
        begin_serialized_write(c)
        pid=task_project(c,tid)
        if not pid: raise HTTPException(404,'Task not found')
        if is_admin(a): pass
        else:
            row=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not row or row['role'] not in ('owner','manager','reviewer'): raise HTTPException(403,'Reviewer role required')
        task_sql='SELECT status FROM tasks WHERE id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): task_sql += ' FOR UPDATE'
        task=c.execute(task_sql,(tid,)).fetchone()
        if task['status']!='REVIEW': raise HTTPException(409,'Task is not awaiting review')
        if decision=='APPROVE':
            enforce_workflow_exit(c,pid,task['status'],a['id'])
            enforce_workflow_stage(c,pid,'DONE',a['id'],tid)
            packages=c.execute("SELECT w.child_task_id,t.status FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? AND w.status='ACTIVE'",(tid,)).fetchall()
            pending=[x['child_task_id'] for x in packages if x['status']!='DONE']
            missing=[x['child_task_id'] for x in packages if c.execute('SELECT 1 FROM artifacts WHERE task_id=? LIMIT 1',(x['child_task_id'],)).fetchone() is None]
            if pending or missing:
                raise HTTPException(409,detail={'message':'Parent task cannot be approved until every active work package is approved and has at least one artifact','pending_work_packages':pending,'missing_artifacts':missing})
        status='DONE' if decision=='APPROVE' else 'IN_PROGRESS'
        updated=c.execute('UPDATE tasks SET status=?,progress=?,updated_at=? WHERE id=? AND status=?',(status,100 if decision=='APPROVE' else 90,now(),tid,'REVIEW'))
        if updated.rowcount != 1: raise HTTPException(409,'Task is no longer awaiting review')
        eid=event(c,'task.reviewed',a['id'],tid,{'decision':decision,'comment':b.get('comment','')})
        return {'task_id':tid,'status':status,'event_id':eid}

@app.post('/api/v1/work-packages/{package_id}/review')
def review_work_package(package_id:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization)
    if a.get('actor_type')=='AGENT': raise HTTPException(403,'Agent cannot review or approve work packages')
    decision=str(b.get('decision','')).strip().upper()
    comment=str(b.get('comment',''))[:4000]
    if decision not in ('APPROVE','REJECT'): raise HTTPException(422,'decision must be APPROVE or REJECT')
    with conn() as c:
        begin_serialized_write(c)
        package_sql='SELECT w.*,t.status AS task_status,t.progress FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): package_sql += ' FOR UPDATE'
        package=c.execute(package_sql,(package_id,)).fetchone()
        if not package: raise HTTPException(404,'Work package not found')
        pid=package['project_id']
        if is_admin(a): pass
        else:
            row=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not row or row['role'] not in ('owner','manager','reviewer'): raise HTTPException(403,'Reviewer role required')
        if package['status']!='ACTIVE': raise HTTPException(409,'Work package is no longer active')
        if package['task_status']!='REVIEW': raise HTTPException(409,'Work package is not awaiting review')
        stamp=now()
        if decision=='APPROVE':
            enforce_workflow_exit(c,pid,package['task_status'],a['id'])
            enforce_workflow_stage(c,pid,'DONE',a['id'],package['child_task_id'])
            if c.execute('SELECT 1 FROM artifacts WHERE task_id=? LIMIT 1',(package['child_task_id'],)).fetchone() is None:
                raise HTTPException(409,'Work package must have at least one artifact before approval')
            status='DONE'; progress=100
        else:
            status='IN_PROGRESS'; progress=90
        updated=c.execute('UPDATE tasks SET status=?,progress=?,updated_at=? WHERE id=? AND status=?',(status,progress,stamp,package['child_task_id'],'REVIEW'))
        if updated.rowcount != 1: raise HTTPException(409,'Work package task is no longer awaiting review')
        eid=event(c,'task.work_package.reviewed',a['id'],package['child_task_id'],{'work_package_id':package_id,'parent_task_id':package['parent_task_id'],'decision':decision,'comment':comment})
        return {'work_package_id':package_id,'task_id':package['child_task_id'],'status':status,'progress':progress,'event_id':eid,'decision':decision}

@app.post('/api/v1/tasks/{parent_id}/work-packages')
def create_work_package(parent_id:str,b:WorkPackageIn,authorization:str=Header(None)):
    a=actor(authorization); child_id='tsk_'+uuid.uuid4().hex[:12]; package_id='wpk_'+uuid.uuid4().hex
    agent_name=b.agent_name.strip()
    if not agent_name: raise HTTPException(422,'agent_name must not be blank')
    with conn() as c:
        require_task_access(c,parent_id,a)
        project_id=task_project(c,parent_id)
        require_project_access(c,project_id,a,write=True)
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(project_id,)).fetchone()
        member=c.execute('SELECT tenant_id FROM members WHERE id=?',(b.assignee_member_id,)).fetchone()
        if not member or member['tenant_id']!=project['tenant_id']: raise HTTPException(404,'Assignee not found in this tenant')
        if not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(project_id,b.assignee_member_id)).fetchone(): raise HTTPException(400,'Assignee is not a project member')
        agent=c.execute('SELECT status,last_seen FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(project_id,b.assignee_member_id,agent_name)).fetchone()
        if not agent: raise HTTPException(404,'Assignee Agent is not registered in this project')
        if agent['status']=='OFFLINE' or agent['last_seen'] < datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat(): raise HTTPException(409,'Assignee Agent presence is offline or stale')
        for dep in b.dependencies:
            if dep==parent_id or not c.execute('SELECT 1 FROM tasks WHERE id=?',(dep,)).fetchone(): raise HTTPException(400,'Invalid dependency')
            require_task_access(c,dep,a)
            if task_project(c,dep)!=project_id: raise HTTPException(400,'Dependencies must belong to the same project')
        req=c.execute('SELECT r.id FROM tasks t JOIN requirements r ON r.id=t.requirement_id WHERE t.id=?',(parent_id,)).fetchone()
        if not req: raise HTTPException(409,'Create a requirement before adding work packages')
        stamp=now()
        c.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?)',(child_id,req['id'],b.title,b.description,'READY',0,stamp,stamp))
        c.execute('INSERT INTO assignments(task_id,member_id) VALUES(?,?)',(child_id,b.assignee_member_id))
        for dep in b.dependencies: c.execute('INSERT INTO dependencies(task_id,depends_on_task_id) VALUES(?,?)',(child_id,dep))
        correlation_id='corr_'+uuid.uuid4().hex
        sla_due_at=datetime.fromtimestamp(datetime.fromisoformat(stamp).timestamp()+b.sla_seconds,timezone.utc).isoformat() if b.sla_seconds else None
        c.execute('INSERT INTO task_work_packages(id,parent_task_id,child_task_id,project_id,tenant_id,assignee_member_id,agent_name,status,created_at,updated_at,correlation_id,sla_due_at,risk_state) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(package_id,parent_id,child_id,project_id,project['tenant_id'],b.assignee_member_id,agent_name,'ACTIVE',stamp,stamp,correlation_id,sla_due_at,'ON_TRACK'))
        mid='msg_'+uuid.uuid4().hex[:12]
        title='Work package assigned: '+b.title
        content=json.dumps({'work_package_id':package_id,'correlation_id':correlation_id,'parent_task_id':parent_id,'task_id':child_id,'agent_name':agent_name,'title':b.title,'sla_due_at':sla_due_at},ensure_ascii=False)
        c.execute('INSERT INTO messages(id,recipient_member_id,tenant_id,task_id,message_type,title,content,priority,status,created_at,acked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(mid,b.assignee_member_id,project['tenant_id'],child_id,'WORK_PACKAGE_ASSIGNED',title,content,'HIGH','PENDING',stamp,None))
        payload={'message_id':mid,'recipient_member_id':b.assignee_member_id,'project_id':project_id,'task_id':child_id,'message_type':'WORK_PACKAGE_ASSIGNED','title':title,'content':content,'priority':'HIGH'}
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',('obx_'+uuid.uuid4().hex,'message.created',json.dumps(payload),'PENDING',0,stamp,stamp,project['tenant_id']))
        event(c,'task.work_package.created',a['id'],parent_id,{'work_package_id':package_id,'correlation_id':correlation_id,'child_task_id':child_id,'assignee_member_id':b.assignee_member_id,'agent_name':agent_name,'sla_due_at':sla_due_at,'sla_seconds':b.sla_seconds})
    return {'id':package_id,'correlation_id':correlation_id,'parent_task_id':parent_id,'task_id':child_id,'assignee_member_id':b.assignee_member_id,'agent_name':agent_name,'status':'ACTIVE','sla_due_at':sla_due_at,'risk_state':'ON_TRACK','message_id':mid}

@app.get('/api/v1/tasks/{parent_id}/work-packages')
def list_work_packages(parent_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,parent_id,a)
        rows=c.execute('SELECT w.*,t.title,t.description,t.status AS task_status,t.progress,t.updated_at AS task_updated_at FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? ORDER BY w.created_at',(parent_id,)).fetchall()
        result=[]
        for raw in rows:
            row=dict(raw)
            row['artifacts']=[dict(x) for x in c.execute('SELECT id,artifact_type,uri,commit_sha,created_at FROM artifacts WHERE task_id=? ORDER BY created_at',(row['child_task_id'],))]
            result.append(row)
        return result

@app.get('/api/v1/tasks/{parent_id}/work-summary')
def work_package_summary(parent_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,parent_id,a)
        rows=c.execute("SELECT t.status,t.progress FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? AND w.status='ACTIVE'",(parent_id,)).fetchall()
        total=len(rows)
        counts={k:sum(1 for x in rows if x['status']==k) for k in ('READY','IN_PROGRESS','BLOCKED','REVIEW','DONE')}
        progress=round(sum(int(x['progress'] or 0) for x in rows)/total) if total else 0
        artifacts=c.execute('SELECT COUNT(*) AS n FROM artifacts a JOIN task_work_packages w ON w.child_task_id=a.task_id WHERE w.parent_task_id=? AND w.status=\'ACTIVE\'',(parent_id,)).fetchone()['n']
        blocked=c.execute("SELECT t.id,t.title,t.status FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? AND w.status='ACTIVE' AND t.status='BLOCKED'",(parent_id,)).fetchall()
        artifact_rows=c.execute('SELECT w.child_task_id,a.id,a.artifact_type,a.uri,a.commit_sha,a.created_at FROM task_work_packages w JOIN artifacts a ON a.task_id=w.child_task_id WHERE w.parent_task_id=? AND w.status=\'ACTIVE\' ORDER BY a.created_at',(parent_id,)).fetchall()
        return {'parent_task_id':parent_id,'work_package_count':total,'progress':progress,'status_counts':counts,'blocked_tasks':[dict(x) for x in blocked],'artifact_count':artifacts,'artifacts':[dict(x) for x in artifact_rows],'all_done':bool(total and counts['DONE']==total)}

@app.get('/api/v1/tasks/{parent_id}/work-timeline')
def work_package_timeline(parent_id:str,limit:int=200,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,500))
    with conn() as c:
        require_task_access(c,parent_id,a)
        packages=c.execute('SELECT w.*,t.title,t.status AS task_status,t.progress FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? ORDER BY w.created_at',(parent_id,)).fetchall()
        items=[]
        task_ids=[parent_id]+[w['child_task_id'] for w in packages]
        for e in c.execute("""SELECT e.*,m.name AS actor_name FROM events e
            LEFT JOIN members m ON m.id=e.actor_member_id WHERE e.task_id=? ORDER BY e.created_at""",(parent_id,)).fetchall():
            p=json.loads(e['payload'] or '{}')
            items.append({'occurred_at':e['created_at'],'kind':'event','event_type':e['event_type'],
                'task_id':parent_id,'event_id':e['id'],'actor_member_id':e['actor_member_id'],
                'actor_name':e['actor_name'],'payload':p})
        for w in packages:
            cid=w['correlation_id'] or w['id']; child=w['child_task_id']
            for e in c.execute("""SELECT e.*,m.name AS actor_name FROM events e
                LEFT JOIN members m ON m.id=e.actor_member_id WHERE e.task_id=? ORDER BY e.created_at""",(child,)).fetchall():
                p=json.loads(e['payload'] or '{}')
                items.append({'occurred_at':e['created_at'],'kind':'event','event_type':e['event_type'],
                    'task_id':child,'event_id':e['id'],'actor_member_id':e['actor_member_id'],
                    'actor_name':e['actor_name'],'correlation_id':cid,'payload':p})
            for msg in c.execute('SELECT id,message_type,title,status,created_at,acked_at,content FROM messages WHERE task_id=? ORDER BY created_at',(child,)).fetchall():
                try: body=json.loads(msg['content'] or '{}')
                except Exception: body={'content':msg['content']}
                items.append({'occurred_at':msg['created_at'],'kind':'message','message_id':msg['id'],
                    'message_type':msg['message_type'],'title':msg['title'],'status':msg['status'],
                    'acked_at':msg['acked_at'],'task_id':child,'correlation_id':body.get('correlation_id',cid),'payload':body})
            for art in c.execute('SELECT id,artifact_type,uri,commit_sha,created_at FROM artifacts WHERE task_id=? ORDER BY created_at',(child,)).fetchall():
                items.append({'occurred_at':art['created_at'],'kind':'artifact','task_id':child,'correlation_id':cid,'artifact':dict(art)})
        marks=','.join('?' for _ in task_ids)
        delegations=c.execute(f"""SELECT d.*,rq.name AS requester_name,rc.name AS recipient_name
            FROM task_delegations d JOIN members rq ON rq.id=d.requester_member_id
            JOIN members rc ON rc.id=d.recipient_member_id
            WHERE d.task_id IN ({marks}) ORDER BY d.created_at""",tuple(task_ids)).fetchall()
        for d in delegations:
            row=dict(d)
            items.append({'occurred_at':row['created_at'],'kind':'delegation','stage':'OFFERED',
                'task_id':row['task_id'],'delegation_id':row['id'],'status':row['status'],
                'requester_member_id':row['requester_member_id'],'requester_name':row['requester_name'],
                'recipient_member_id':row['recipient_member_id'],'recipient_name':row['recipient_name'],
                'agent_name':row['agent_name'],'reason':row['reason'],'expires_at':row['expires_at']})
            if row['status']!='PENDING':
                decision_at=row['responded_at'] or row['updated_at']
                items.append({'occurred_at':decision_at,'kind':'delegation','stage':row['status'],
                    'task_id':row['task_id'],'delegation_id':row['id'],'status':row['status'],
                    'requester_member_id':row['requester_member_id'],'requester_name':row['requester_name'],
                    'recipient_member_id':row['recipient_member_id'],'recipient_name':row['recipient_name'],
                    'agent_name':row['agent_name'],'reason':row['reason'],'expires_at':row['expires_at']})
        dependency_edges=[]
        for tid in task_ids:
            task=c.execute('SELECT title FROM tasks WHERE id=?',(tid,)).fetchone()
            for dep in c.execute("""SELECT d.depends_on_task_id,t.title AS depends_on_title,t.status AS depends_on_status
                FROM dependencies d JOIN tasks t ON t.id=d.depends_on_task_id WHERE d.task_id=?""",(tid,)).fetchall():
                dependency_edges.append({'task_id':tid,'task_title':task['title'] if task else tid,
                    'depends_on_task_id':dep['depends_on_task_id'],'depends_on_title':dep['depends_on_title'],
                    'depends_on_status':dep['depends_on_status'],'blocked':dep['depends_on_status']!='DONE'})
        items.sort(key=lambda x:(x['occurred_at'],x.get('event_id') or x.get('message_id') or x.get('delegation_id') or x.get('artifact',{}).get('id','')))
        items=items[-limit:]
        return {'parent_task_id':parent_id,'count':len(items),'items':items,
            'dependency_edges':dependency_edges,
            'delegations':[{'id':d['id'],'task_id':d['task_id'],'requester_member_id':d['requester_member_id'],
                'requester_name':d['requester_name'],'recipient_member_id':d['recipient_member_id'],
                'recipient_name':d['recipient_name'],'agent_name':d['agent_name'],'reason':d['reason'],
                'status':d['status'],'created_at':d['created_at'],'responded_at':d['responded_at'],
                'expires_at':d['expires_at']} for d in delegations],
            'work_packages':[{'id':w['id'],'correlation_id':w['correlation_id'] or w['id'],
                'child_task_id':w['child_task_id'],'title':w['title'],'status':w['task_status'],
                'progress':w['progress'],'assignee_member_id':w['assignee_member_id'],'agent_name':w['agent_name'],
                'sla_due_at':w['sla_due_at'],'risk_state':w['risk_state'],'needs_attention':bool(w['needs_attention'])}
                for w in packages]}
@app.post('/api/v1/projects/{pid}/work-packages/scan-health')
def scan_project_work_health(pid:str,authorization:str=Header(None)):
    a=actor(authorization); stamp=now()
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        rows=c.execute("""SELECT w.id,w.parent_task_id,w.child_task_id,w.correlation_id,w.sla_due_at,w.risk_state,w.needs_attention,
        t.title,t.status AS task_status FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id
        WHERE w.project_id=? AND w.status='ACTIVE' ORDER BY w.created_at""",(pid,)).fetchall()
        changed=[]; counts={'ON_TRACK':0,'OVERDUE':0,'BLOCKED_DEPENDENCY':0,'STALLED':0,'IN_REVIEW':0,'COMPLETED':0}
        for row in rows:
            blockers=c.execute("""SELECT d.depends_on_task_id,t.title,t.status FROM dependencies d
                JOIN tasks t ON t.id=d.depends_on_task_id WHERE d.task_id=? AND t.status!='DONE'""",(row['child_task_id'],)).fetchall()
            if row['task_status']=='DONE': risk='COMPLETED'
            elif row['task_status']=='REVIEW': risk='IN_REVIEW'
            elif blockers: risk='BLOCKED_DEPENDENCY'
            elif row['needs_attention']: risk='STALLED'
            elif row['sla_due_at'] and row['sla_due_at']<=stamp: risk='OVERDUE'
            else: risk='ON_TRACK'
            if risk!=row['risk_state']:
                c.execute('UPDATE task_work_packages SET risk_state=?,updated_at=? WHERE id=?',(risk,stamp,row['id']))
                detail={'work_package_id':row['id'],'correlation_id':row['correlation_id'],'child_task_id':row['child_task_id'],'previous_risk_state':row['risk_state'],'risk_state':risk,'sla_due_at':row['sla_due_at'],'blocking_dependencies':[dict(x) for x in blockers]}
                event(c,'task.work_package.risk_changed',a['id'],row['parent_task_id'],detail)
                changed.append(detail)
            counts[risk]=counts.get(risk,0)+1
        return {'project_id':pid,'scanned_count':len(rows),'changed_count':len(changed),'risk_counts':counts,'changes':changed}

@app.get('/api/v1/projects/{pid}/work-health')
def project_work_health(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT w.id,w.parent_task_id,w.child_task_id,w.correlation_id,w.assignee_member_id,w.agent_name,
            w.sla_due_at,w.risk_state,w.needs_attention,t.title,t.status AS task_status,t.progress,t.updated_at
            FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id
            WHERE w.project_id=? AND w.status='ACTIVE' ORDER BY w.created_at""",(pid,)).fetchall()
        counts={}
        items=[]
        for row in rows:
            risk=row['risk_state']; counts[risk]=counts.get(risk,0)+1
            blockers=c.execute("""SELECT d.depends_on_task_id,t.title,t.status FROM dependencies d
                JOIN tasks t ON t.id=d.depends_on_task_id WHERE d.task_id=? AND t.status!='DONE'""",(row['child_task_id'],)).fetchall()
            items.append({'work_package_id':row['id'],'parent_task_id':row['parent_task_id'],'child_task_id':row['child_task_id'],
                'correlation_id':row['correlation_id'],'title':row['title'],'task_status':row['task_status'],'progress':row['progress'],
                'assignee_member_id':row['assignee_member_id'],'agent_name':row['agent_name'],'sla_due_at':row['sla_due_at'],
                'risk_state':risk,'needs_attention':bool(row['needs_attention']),'blocking_dependencies':[dict(x) for x in blockers],
                'last_activity_at':row['updated_at']})
        total=len(items); at_risk=sum(counts.get(k,0) for k in ('OVERDUE','BLOCKED_DEPENDENCY','STALLED'))
        return {'project_id':pid,'work_package_count':total,'at_risk_count':at_risk,
            'health_score':round(100*(total-at_risk)/total) if total else 100,
            'risk_counts':counts,'items':items}

@app.get('/api/v1/projects/{pid}/coordination')
def project_coordination_center(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        packages=c.execute("""SELECT w.id AS work_package_id,w.parent_task_id,w.child_task_id,w.assignee_member_id,w.agent_name,
            w.sla_due_at,w.risk_state,w.needs_attention,w.stall_reason,w.stalled_at,t.title,t.status AS task_status,
            t.progress,t.updated_at,m.name AS assignee_name
            FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id
            LEFT JOIN members m ON m.id=w.assignee_member_id
            WHERE w.project_id=? AND w.status='ACTIVE'
            AND (w.needs_attention=1 OR w.risk_state IN ('OVERDUE','BLOCKED_DEPENDENCY','STALLED','IN_REVIEW'))
            ORDER BY CASE w.risk_state WHEN 'OVERDUE' THEN 0 WHEN 'STALLED' THEN 1 WHEN 'BLOCKED_DEPENDENCY' THEN 2 WHEN 'IN_REVIEW' THEN 3 ELSE 4 END,w.updated_at""",(pid,)).fetchall()
        package_items=[]
        for row in packages:
            blockers=c.execute("""SELECT d.depends_on_task_id,t.title,t.status FROM dependencies d
                JOIN tasks t ON t.id=d.depends_on_task_id WHERE d.task_id=? AND t.status!='DONE'""",(row['child_task_id'],)).fetchall()
            agent=c.execute('SELECT status,last_seen FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(pid,row['assignee_member_id'],row['agent_name'])).fetchone()
            package_items.append({**dict(row),'blocking_dependencies':[dict(x) for x in blockers],
                'agent_status':agent['status'] if agent else 'NOT_REGISTERED','agent_last_seen':agent['last_seen'] if agent else None})
        unclaimed=c.execute("""SELECT t.id AS task_id,t.title,t.status,t.progress,t.updated_at
            FROM tasks t JOIN requirements r ON r.id=t.requirement_id
            LEFT JOIN assignments a ON a.task_id=t.id
            WHERE r.project_id=? AND t.status!='DONE' AND a.task_id IS NULL
            AND NOT EXISTS (SELECT 1 FROM task_work_packages w WHERE w.child_task_id=t.id AND w.status='ACTIVE')
            ORDER BY t.updated_at""",(pid,)).fetchall()
        reviews=c.execute("""SELECT t.id AS task_id,t.title,t.progress,t.updated_at,
            (SELECT COUNT(*) FROM artifacts ar WHERE ar.task_id=t.id) AS artifact_count
            FROM tasks t JOIN requirements r ON r.id=t.requirement_id
            WHERE r.project_id=? AND t.status='REVIEW' ORDER BY t.updated_at""",(pid,)).fetchall()
        delegations=c.execute("""SELECT d.id,d.task_id,d.status,d.requester_member_id,d.recipient_member_id,
            d.agent_name,d.reason,d.created_at,d.expires_at,t.title AS task_title,
            rq.name AS requester_name,rc.name AS recipient_name
            FROM task_delegations d JOIN tasks t ON t.id=d.task_id
            JOIN members rq ON rq.id=d.requester_member_id JOIN members rc ON rc.id=d.recipient_member_id
            WHERE d.project_id=? AND d.status='PENDING' ORDER BY d.created_at""",(pid,)).fetchall()
        return {'project_id':pid,'exception_work_packages':[dict(x) for x in package_items],
            'unclaimed_tasks':[dict(x) for x in unclaimed],'pending_reviews':[dict(x) for x in reviews],
            'pending_delegations':[dict(x) for x in delegations],
            'counts':{'exception_work_packages':len(package_items),'unclaimed_tasks':len(unclaimed),
                'pending_reviews':len(reviews),'pending_delegations':len(delegations)}}

@app.post('/api/v1/projects/{pid}/work-packages/scan-stalled')
def scan_stalled_work_packages(pid:str,b:WorkPackageScanIn,authorization:str=Header(None)):
    a=actor(authorization)
    cutoff=datetime.fromtimestamp(time.time()-b.stale_after_seconds,timezone.utc).isoformat()
    stamp=now()
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        rows=c.execute("""SELECT w.id,w.parent_task_id,w.child_task_id,w.assignee_member_id,t.status,t.updated_at,t.title
        FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id
        WHERE w.project_id=? AND w.status='ACTIVE' AND w.needs_attention=0
        AND t.status IN ('READY','IN_PROGRESS','BLOCKED') AND t.updated_at<=?""",(pid,cutoff)).fetchall()
        marked=[]
        for row in rows:
            reason=f"No task activity for at least {b.stale_after_seconds} seconds"
            changed=c.execute('UPDATE task_work_packages SET needs_attention=1,stalled_at=?,stall_reason=?,updated_at=? WHERE id=? AND needs_attention=0',(stamp,reason,stamp,row['id']))
            if changed.rowcount:
                event(c,'task.work_package.stalled',a['id'],row['parent_task_id'],{'work_package_id':row['id'],'correlation_id':c.execute('SELECT correlation_id FROM task_work_packages WHERE id=?',(row['id'],)).fetchone()['correlation_id'],'child_task_id':row['child_task_id'],'assignee_member_id':row['assignee_member_id'],'stalled_at':stamp,'reason':reason})
                marked.append({'work_package_id':row['id'],'child_task_id':row['child_task_id'],'title':row['title'],'task_status':row['status'],'assignee_member_id':row['assignee_member_id'],'stalled_at':stamp,'reason':reason})
    return {'project_id':pid,'stale_after_seconds':b.stale_after_seconds,'marked_count':len(marked),'items':marked}

@app.post('/api/v1/work-packages/{package_id}/reassign')
def reassign_work_package(package_id:str,b:WorkPackageReassignIn,authorization:str=Header(None)):
    a=actor(authorization); agent_name=b.agent_name.strip()
    if not agent_name: raise HTTPException(422,'agent_name must not be blank')
    with conn() as c:
        begin_serialized_write(c)
        package_sql='SELECT * FROM task_work_packages WHERE id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): package_sql += ' FOR UPDATE'
        package=c.execute(package_sql,(package_id,)).fetchone()
        if not package: raise HTTPException(404,'Work package not found')
        require_project_access(c,package['project_id'],a,write=True)
        if package['status']!='ACTIVE': raise HTTPException(409,'Only active work packages can be reassigned')
        if not package['needs_attention']: raise HTTPException(409,'Work package must be marked stalled before reassignment')
        if package['assignee_member_id']==b.assignee_member_id and package['agent_name']==agent_name:
            raise HTTPException(400,'Choose a different assignee or Agent')
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(package['project_id'],)).fetchone()
        member=c.execute('SELECT tenant_id FROM members WHERE id=?',(b.assignee_member_id,)).fetchone()
        if not member or member['tenant_id']!=project['tenant_id']: raise HTTPException(404,'New assignee not found in this tenant')
        if not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(package['project_id'],b.assignee_member_id)).fetchone():
            raise HTTPException(400,'New assignee is not a project member')
        agent=c.execute('SELECT status,last_seen FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(package['project_id'],b.assignee_member_id,agent_name)).fetchone()
        cutoff=datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat()
        if not agent: raise HTTPException(404,'New assignee Agent is not registered in this project')
        if agent['status']=='OFFLINE' or agent['last_seen']<cutoff: raise HTTPException(409,'New assignee Agent presence is offline or stale')
        stamp=now()
        c.execute('DELETE FROM assignments WHERE task_id=? AND member_id=?',(package['child_task_id'],package['assignee_member_id']))
        c.execute('INSERT OR IGNORE INTO assignments(task_id,member_id) VALUES(?,?)',(package['child_task_id'],b.assignee_member_id))
        c.execute('UPDATE task_work_packages SET assignee_member_id=?,agent_name=?,needs_attention=0,stalled_at=NULL,stall_reason=NULL,updated_at=? WHERE id=?',(b.assignee_member_id,agent_name,stamp,package_id))
        c.execute('UPDATE tasks SET updated_at=? WHERE id=?',(stamp,package['child_task_id']))
        mid='msg_'+uuid.uuid4().hex[:12]
        title='Work package reassigned: '+package['child_task_id']
        content=json.dumps({'work_package_id':package_id,'correlation_id':package['correlation_id'],'parent_task_id':package['parent_task_id'],'task_id':package['child_task_id'],'previous_assignee_member_id':package['assignee_member_id'],'assignee_member_id':b.assignee_member_id,'agent_name':agent_name,'reason':b.reason},ensure_ascii=False)
        c.execute('INSERT INTO messages(id,recipient_member_id,tenant_id,task_id,message_type,title,content,priority,status,created_at,acked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(mid,b.assignee_member_id,project['tenant_id'],package['child_task_id'],'WORK_PACKAGE_REASSIGNED',title,content,'HIGH','PENDING',stamp,None))
        payload={'message_id':mid,'recipient_member_id':b.assignee_member_id,'project_id':package['project_id'],'task_id':package['child_task_id'],'message_type':'WORK_PACKAGE_REASSIGNED','title':title,'content':content,'priority':'HIGH'}
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',('obx_'+uuid.uuid4().hex,'message.created',json.dumps(payload),'PENDING',0,stamp,stamp,project['tenant_id']))
        eid=event(c,'task.work_package.reassigned',a['id'],package['parent_task_id'],{'work_package_id':package_id,'correlation_id':package['correlation_id'],'child_task_id':package['child_task_id'],'previous_assignee_member_id':package['assignee_member_id'],'assignee_member_id':b.assignee_member_id,'previous_agent_name':package['agent_name'],'agent_name':agent_name,'reason':b.reason})
    return {'work_package_id':package_id,'task_id':package['child_task_id'],'assignee_member_id':b.assignee_member_id,'agent_name':agent_name,'needs_attention':False,'message_id':mid,'event_id':eid}

@app.post('/api/v1/projects/{pid}/agents/register')
def register_project_agent(pid:str,b:AgentPresenceIn,authorization:str=Header(None)):
    a=actor(authorization)
    agent_name=b.agent_name.strip()
    if not agent_name: raise HTTPException(422,'agent_name must not be blank')
    clean_caps=sorted({str(x).strip().lower() for x in b.capabilities if str(x).strip()})
    clean_protocols=sorted({str(x).strip().lower() for x in b.protocols if str(x).strip()})
    if any(len(x)>80 for x in clean_caps) or any(len(x)>40 for x in clean_protocols):
        raise HTTPException(422,'Capability or protocol identifier is too long')
    if not clean_protocols: raise HTTPException(422,'At least one protocol is required')
    if len(json.dumps(b.metadata))>4000: raise HTTPException(422,'Agent metadata exceeds 4000 bytes')
    with conn() as c:
        require_project_access(c,pid,a)
        tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id']
        existing=c.execute('SELECT id,created_at FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(pid,a['id'],agent_name)).fetchone()
        aid=existing['id'] if existing else 'agt_'+uuid.uuid4().hex
        created=existing['created_at'] if existing else now()
        stamp=now()
        c.execute("""INSERT INTO project_agents(id,project_id,member_id,tenant_id,agent_name,capabilities,protocols,status,metadata,last_seen,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(project_id,member_id,agent_name) DO UPDATE SET capabilities=excluded.capabilities,protocols=excluded.protocols,status=excluded.status,metadata=excluded.metadata,last_seen=excluded.last_seen,updated_at=excluded.updated_at""",
        (aid,pid,a['id'],tenant,agent_name,json.dumps(clean_caps),json.dumps(clean_protocols),b.status,json.dumps(b.metadata),stamp,created,stamp))
        event(c,'agent.presence.updated',a['id'],None,{'project_id':pid,'agent_id':aid,'agent_name':agent_name,'status':b.status},tenant_override=tenant)
    return {'id':aid,'project_id':pid,'member_id':a['id'],'agent_name':b.agent_name.strip(),'status':b.status,'capabilities':clean_caps,'protocols':clean_protocols,'last_seen':stamp}

@app.post('/api/v1/projects/{pid}/agents/heartbeat')
def heartbeat_project_agent(pid:str,body:dict,authorization:str=Header(None)):
    a=actor(authorization); name=str(body.get('agent_name','')).strip()
    if not name or len(name)>120: raise HTTPException(422,'agent_name is required (max 120)')
    status=str(body.get('status','AVAILABLE')).upper()
    if status not in ('AVAILABLE','BUSY','OFFLINE'): raise HTTPException(422,'Invalid agent status')
    with conn() as c:
        require_project_access(c,pid,a)
        previous=c.execute('SELECT id,status FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(pid,a['id'],name)).fetchone()
        if not previous: raise HTTPException(404,'Agent registration not found; register the agent first')
        stamp=now()
        c.execute('UPDATE project_agents SET status=?,last_seen=?,updated_at=? WHERE id=?',(status,stamp,stamp,previous['id']))
        if previous['status'] != status:
            event(c,'agent.presence.changed',a['id'],None,{'project_id':pid,'agent_id':previous['id'],'status':status})
    return {'id':previous['id'],'status':status,'last_seen':stamp}

@app.get('/api/v1/projects/{pid}/agents')
def discover_project_agents(pid:str,authorization:str=Header(None),capability:str='',protocol:str=''):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("SELECT pa.*,m.name AS member_name FROM project_agents pa JOIN members m ON m.id=pa.member_id WHERE pa.project_id=? ORDER BY pa.agent_name,pa.member_id",(pid,)).fetchall()
        cutoff=datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat()
        items=[]
        for raw in rows:
            row=dict(raw)
            caps=json.loads(row['capabilities'] or '[]'); protocols=json.loads(row['protocols'] or '[]')
            live=row['status']!='OFFLINE' and row['last_seen']>=cutoff
            if capability and capability.lower() not in caps: continue
            if protocol and protocol.lower() not in protocols: continue
            items.append({'id':row['id'],'member_id':row['member_id'],'member_name':row['member_name'],'agent_name':row['agent_name'],'capabilities':caps,'protocols':protocols,'status':row['status'] if live else 'OFFLINE','last_seen':row['last_seen'],'metadata':json.loads(row['metadata'] or '{}')})
        return {'items':items,'count':len(items),'presence_ttl_seconds':120}

@app.get('/api/v1/projects/{pid}/agent-matches')
def recommend_project_agents(pid:str,required_capabilities:str='',protocol:str='mcp',authorization:str=Header(None)):
    """Rank project-local Agent registrations without assigning work or invoking a Runtime."""
    a=actor(authorization)
    requested=[x.strip().casefold() for x in required_capabilities.split(',') if x.strip()]
    if len(requested)>50 or any(len(x)>120 for x in requested):
        raise HTTPException(422,'At most 50 required capabilities are allowed; each must be at most 120 characters')
    requested=list(dict.fromkeys(requested))
    requested_protocol=protocol.strip().casefold()
    if not requested_protocol or len(requested_protocol)>40:
        raise HTTPException(422,'protocol must contain 1 to 40 characters')
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT pa.*,m.name AS member_name FROM project_agents pa
            JOIN members m ON m.id=pa.member_id WHERE pa.project_id=?""",(pid,)).fetchall()
        cutoff=datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat()
        items=[]
        for raw in rows:
            row=dict(raw)
            caps=sorted({str(x).strip().casefold() for x in json.loads(row['capabilities'] or '[]') if str(x).strip()})
            protocols=sorted({str(x).strip().casefold() for x in json.loads(row['protocols'] or '[]') if str(x).strip()})
            matched=[x for x in requested if x in caps]
            missing=[x for x in requested if x not in caps]
            live=row['status']!='OFFLINE' and row['last_seen']>=cutoff
            protocol_match=requested_protocol in protocols
            available=live and row['status']=='AVAILABLE'
            items.append({'id':row['id'],'member_id':row['member_id'],'member_name':row['member_name'],
                'agent_name':row['agent_name'],'capabilities':caps,'protocols':protocols,
                'presence_status':row['status'] if live else 'OFFLINE','last_seen':row['last_seen'],
                'matched_capabilities':matched,'missing_capabilities':missing,
                'match_count':len(matched),'required_count':len(requested),
                'protocol_match':protocol_match,'eligible':not missing and protocol_match and available,
                'availability_reason':('AVAILABLE' if available else ('BUSY' if live and row['status']=='BUSY' else 'OFFLINE_OR_STALE')),
                'match_score':round(100*len(matched)/len(requested)) if requested else (100 if protocol_match else 0)})
        items.sort(key=lambda x:(not x['eligible'],bool(x['missing_capabilities']),not x['protocol_match'],
            -x['match_count'],x['availability_reason']!='AVAILABLE',x['member_name'].casefold(),x['agent_name'].casefold()))
        return {'project_id':pid,'required_capabilities':requested,'protocol':requested_protocol,
            'items':items,'count':len(items),'eligible_count':sum(1 for x in items if x['eligible']),
            'recommendation_only':True,'runtime_controlled':False}

@app.post('/api/v1/tasks/{tid}/delegations')
def create_task_delegation(tid:str,b:DelegationIn,authorization:str=Header(None)):
    a=actor(authorization)
    if b.recipient_member_id == a['id']: raise HTTPException(400,'A task cannot be delegated to yourself')
    agent_name=b.agent_name.strip()
    if not agent_name: raise HTTPException(422,'agent_name must not be blank')
    did='dlg_'+uuid.uuid4().hex
    with conn() as c:
        require_task_access(c,tid,a,assigned_only=True)
        pid=task_project(c,tid)
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        recipient=c.execute('SELECT tenant_id FROM members WHERE id=?',(b.recipient_member_id,)).fetchone()
        if not recipient or recipient['tenant_id'] != project['tenant_id']: raise HTTPException(404,'Recipient not found in this tenant')
        if not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(pid,b.recipient_member_id)).fetchone(): raise HTTPException(400,'Recipient is not a project member')
        agent=c.execute("SELECT id,status,last_seen FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?",(pid,b.recipient_member_id,agent_name)).fetchone()
        if not agent: raise HTTPException(404,'Recipient Agent is not registered in this project')
        if agent['status']=='OFFLINE' or agent['last_seen'] < datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat():
            raise HTTPException(409,'Recipient Agent presence is offline or stale')
        stamp=now(); expiry=datetime.fromtimestamp(time.time()+b.expires_in_seconds,timezone.utc).isoformat()
        mid='msg_'+uuid.uuid4().hex[:12]
        title='Task delegation offer: '+tid
        content=json.dumps({'delegation_id':did,'task_id':tid,'agent_name':agent_name,'reason':b.reason,'expires_at':expiry},ensure_ascii=False)
        c.execute("INSERT INTO task_delegations(id,task_id,project_id,tenant_id,requester_member_id,recipient_member_id,agent_name,reason,status,message_id,expires_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(did,tid,pid,project['tenant_id'],a['id'],b.recipient_member_id,agent_name,b.reason,'PENDING',mid,expiry,stamp,stamp))
        c.execute("INSERT INTO messages(id,recipient_member_id,tenant_id,task_id,message_type,title,content,priority,status,created_at,acked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(mid,b.recipient_member_id,project['tenant_id'],tid,'TASK_DELEGATION',title,content,'HIGH','PENDING',stamp,None))
        payload={'message_id':mid,'recipient_member_id':b.recipient_member_id,'project_id':pid,'task_id':tid,'message_type':'TASK_DELEGATION','title':title,'content':content,'priority':'HIGH'}
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',('obx_'+uuid.uuid4().hex,'message.created',json.dumps(payload), 'PENDING',0,stamp,stamp,project['tenant_id']))
        event(c,'task.delegation.offered',a['id'],tid,{'delegation_id':did,'recipient_member_id':b.recipient_member_id,'agent_name':agent_name})
    return {'id':did,'task_id':tid,'recipient_member_id':b.recipient_member_id,'agent_name':agent_name,'status':'PENDING','expires_at':expiry,'message_id':mid}

@app.post('/api/v1/delegations/{did}/respond')
def respond_task_delegation(did:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization); decision=b.get('decision')
    if decision not in ('ACCEPT','REJECT'): raise HTTPException(422,'decision must be ACCEPT or REJECT')
    with conn() as c:
        begin_serialized_write(c)
        if DATABASE_URL.startswith(('postgresql://','postgres://')):
            row=c.execute('SELECT * FROM task_delegations WHERE id=? FOR UPDATE',(did,)).fetchone()
        else:
            row=c.execute('SELECT * FROM task_delegations WHERE id=?',(did,)).fetchone()
        if not row or row['recipient_member_id'] != a['id']: raise HTTPException(404,'Delegation not found')
        if row['status'] != 'PENDING': raise HTTPException(409,'Delegation is no longer pending')
        if row['expires_at'] <= now():
            stamp=now()
            cur=c.execute("UPDATE task_delegations SET status='EXPIRED',updated_at=? WHERE id=? AND status='PENDING'",(stamp,did))
            if cur.rowcount:
                event(c,'task.delegation.expired',a['id'],row['task_id'],{'delegation_id':did})
            return JSONResponse(status_code=410,content={'detail':'Delegation offer has expired','status':'EXPIRED'})
        if decision=='ACCEPT':
            c.execute('INSERT OR IGNORE INTO assignments(task_id,member_id) VALUES(?,?)',(row['task_id'],a['id']))
            c.execute('INSERT OR IGNORE INTO project_members(project_id,member_id,role,joined_at) VALUES(?,?,?,?)',(row['project_id'],a['id'],'member',now()))
            status='ACCEPTED'
        else: status='REJECTED'
        stamp=now()
        cur=c.execute('UPDATE task_delegations SET status=?,responded_at=?,updated_at=? WHERE id=? AND status=\'PENDING\'',(status,stamp,stamp,did))
        if cur.rowcount != 1:
            raise HTTPException(409,'Delegation response raced with another decision')
        event(c,'task.delegation.'+status.lower(),a['id'],row['task_id'],{'delegation_id':did,'agent_name':row['agent_name']})
        return {'id':did,'task_id':row['task_id'],'status':status,'responded_at':stamp}

@app.get('/api/v1/tasks/{tid}/delegations')
def list_task_delegations(tid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a)
        rows=c.execute('SELECT * FROM task_delegations WHERE task_id=? ORDER BY created_at DESC',(tid,)).fetchall()
        result=[]
        for raw in rows:
            row=dict(raw)
            if row['status']=='PENDING' and row['expires_at'] <= now():
                stamp=now()
                cur=c.execute("UPDATE task_delegations SET status='EXPIRED',updated_at=? WHERE id=? AND status='PENDING'",(stamp,row['id']))
                if cur.rowcount:
                    event(c,'task.delegation.expired',a['id'],tid,{'delegation_id':row['id']})
                row['status']='EXPIRED'
            result.append(row)
        return result

@app.get('/api/v1/projects/{pid}/delegations')
def project_delegations(pid:str,limit:int=100,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,500))
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT d.*,rq.name AS requester_name,rc.name AS recipient_name,t.title AS task_title
            FROM task_delegations d
            JOIN members rq ON rq.id=d.requester_member_id
            JOIN members rc ON rc.id=d.recipient_member_id
            JOIN tasks t ON t.id=d.task_id
            WHERE d.project_id=? ORDER BY d.created_at DESC LIMIT ?""",(pid,limit)).fetchall()
        items=[]
        for raw in rows:
            row=dict(raw)
            if row['status']=='PENDING' and row['expires_at'] <= now():
                stamp=now()
                cur=c.execute("UPDATE task_delegations SET status='EXPIRED',updated_at=? WHERE id=? AND status='PENDING'",(stamp,row['id']))
                if cur.rowcount:
                    event(c,'task.delegation.expired',a['id'],row['task_id'],{'delegation_id':row['id']})
                row['status']='EXPIRED'
            items.append(row)
        return {'project_id':pid,'count':len(items),'items':items}

@app.post('/api/v1/messages')
def send_message(b:MessageIn,authorization:str=Header(None)):
    a=actor(authorization); mid='msg_'+uuid.uuid4().hex[:12]
    with conn() as c:
        if not c.execute('SELECT 1 FROM members WHERE id=?',(b.recipient_member_id,)).fetchone(): raise HTTPException(404,'Recipient not found')
        if b.task_id:
            require_task_access(c,b.task_id,a)
            pid=task_project(c,b.task_id)
            if b.project_id and b.project_id != pid: raise HTTPException(400,'project_id does not match task')
        else: pid=b.project_id
        if not pid and not is_admin(a): raise HTTPException(400,'project_id is required for project-scoped messages')
        if pid:
            require_project_access(c,pid,a)
            recipient=c.execute('SELECT tenant_id FROM members WHERE id=?',(b.recipient_member_id,)).fetchone()
            project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
            if recipient and recipient['tenant_id'] != project['tenant_id']: raise HTTPException(400,'Recipient belongs to a different tenant')
            if not is_admin(a) and not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(pid,b.recipient_member_id)).fetchone(): raise HTTPException(400,'Recipient is not a project member')
        created=now()
        message_tenant=(c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id'] if pid else c.execute('SELECT tenant_id FROM members WHERE id=?',(b.recipient_member_id,)).fetchone()['tenant_id'])
        c.execute('INSERT INTO messages(id,recipient_member_id,tenant_id,task_id,message_type,title,content,priority,status,created_at,acked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(mid,b.recipient_member_id,message_tenant,b.task_id,b.message_type,b.title,b.content,b.priority,'PENDING',created,None))
        payload={'message_id':mid,'recipient_member_id':b.recipient_member_id,'project_id':pid,'task_id':b.task_id,'message_type':b.message_type,'title':b.title,'content':b.content,'priority':b.priority}
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',('obx_'+uuid.uuid4().hex,'message.created',json.dumps(payload),'PENDING',0,created,created,message_tenant))
        event(c,'message.created',a['id'],b.task_id,{'message_id':mid,'recipient':b.recipient_member_id},tenant_override=message_tenant)
    return {'id':mid,'status':'PENDING'}
@app.get('/api/v1/me/notifications')
def notifications(authorization:str=Header(None),after:int=0,limit:int=50):
    a=actor(authorization); limit=max(1,min(limit,100))
    with conn() as c:
        rows=[dict(x) for x in c.execute("SELECT * FROM messages WHERE recipient_member_id=? AND status='PENDING' AND seq>? ORDER BY seq LIMIT ?",(a['id'],after,limit))]
        for row in rows: c.execute('UPDATE messages SET attempts=attempts+1,last_attempt_at=? WHERE id=?',(now(),row['id']))
        return {'items':rows,'next_cursor':rows[-1]['seq'] if rows else after,'has_more':len(rows)==limit}
@app.post('/api/v1/messages/{mid}/ack')
def ack(mid:str,b:AckIn,authorization: str=Header(None)):
    a=actor(authorization)
    if b.status not in ('ACKNOWLEDGED','REJECTED'): raise HTTPException(422,'Invalid acknowledgement status')
    with conn() as c:
        existing=c.execute('SELECT status,task_id,tenant_id FROM messages WHERE id=? AND recipient_member_id=?',(mid,a['id'])).fetchone()
        if not existing: raise HTTPException(404,'Message not found for current member')
        if existing['status'] in ('ACKNOWLEDGED','REJECTED'):
            if existing['status'] != b.status: raise HTTPException(409,'Message has already reached a different terminal status')
            return {'id':mid,'status':existing['status'],'idempotent':True}
        stamp=now()
        cur=c.execute("UPDATE messages SET status=?,acked_at=? WHERE id=? AND recipient_member_id=? AND status='PENDING'",(b.status,stamp,mid,a['id']))
        if cur.rowcount==0: raise HTTPException(409,'Message status changed; retry the request')
        event(c,'message.acknowledged',a['id'],existing['task_id'],{'message_id':mid,'status':b.status},tenant_override=existing['tenant_id'])
    return {'id':mid,'status':b.status,'idempotent':False}
@app.get('/api/v1/tasks/{tid}/events')
def task_events(tid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a)
        return [dict(x) for x in c.execute('SELECT * FROM events WHERE task_id=? ORDER BY created_at',(tid,))]
@app.get('/api/v1/tasks/{tid}/artifacts')
def task_artifacts(tid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a)
        return [dict(x) for x in c.execute('SELECT * FROM artifacts WHERE task_id=? ORDER BY created_at',(tid,))]
@app.post('/internal/v1/outbox/claim')
def claim_outbox(body:dict,authorization:str=Header(None)):
    require_worker(authorization)
    worker=str(body.get('worker_id','')).strip()
    if not worker or len(worker)>120: raise HTTPException(422,'worker_id is required (max 120 chars)')
    limit=max(1,min(int(body.get('limit',20)),100)); lease_seconds=max(10,min(int(body.get('lease_seconds',60)),900))
    claimed=[]; timestamp=datetime.now(timezone.utc); stamp=timestamp.isoformat()
    with conn() as c:
        is_pg=DATABASE_URL.startswith(('postgresql://','postgres://'))
        if not is_pg: c.execute('BEGIN IMMEDIATE')
        query="SELECT * FROM outbox WHERE (status='PENDING' AND available_at<=?) OR (status='IN_FLIGHT' AND lease_until<=?) ORDER BY created_at LIMIT ?"
        if is_pg: query += " FOR UPDATE SKIP LOCKED"
        rows=c.execute(query,(stamp,stamp,limit)).fetchall()
        for row in rows:
            lease_until=datetime.fromtimestamp(timestamp.timestamp()+lease_seconds,timezone.utc).isoformat()
            lease_token=secrets.token_urlsafe(32)
            cur=c.execute("UPDATE outbox SET status='IN_FLIGHT',attempts=attempts+1,lease_until=?,lease_owner=?,lease_token=? WHERE id=? AND ((status='PENDING' AND available_at<=?) OR (status='IN_FLIGHT' AND lease_until<=?))",(lease_until,worker,lease_token,row['id'],stamp,stamp))
            if cur.rowcount:
                item=dict(row); item.update(status='IN_FLIGHT',attempts=row['attempts']+1,lease_until=lease_until,lease_owner=worker,lease_token=lease_token,payload=json.loads(row['payload']))
                claimed.append(item)
    return {'items':claimed,'count':len(claimed)}

@app.post('/internal/v1/outbox/{outbox_id}/complete')
def complete_outbox(outbox_id:str,body:dict,authorization:str=Header(None)):
    require_worker(authorization)
    worker=str(body.get('worker_id','')).strip(); lease_token=str(body.get('lease_token',''))
    if not worker or len(worker)>120 or len(lease_token)<32: raise HTTPException(422,'worker_id and lease_token are required')
    with conn() as c:
        stamp=now()
        cur=c.execute("UPDATE outbox SET status='SENT',sent_at=?,lease_until=NULL,lease_owner=NULL,lease_token=NULL,last_error=NULL WHERE id=? AND status='IN_FLIGHT' AND lease_owner=? AND lease_token=? AND lease_until>?",(stamp,outbox_id,worker,lease_token,stamp))
        if not cur.rowcount: raise HTTPException(409,'Outbox lease not owned by worker or item is not in flight')
    return {'id':outbox_id,'status':'SENT'}

@app.post('/internal/v1/outbox/{outbox_id}/fail')
def fail_outbox(outbox_id:str,body:dict,authorization:str=Header(None)):
    require_worker(authorization)
    worker=str(body.get('worker_id','')).strip(); lease_token=str(body.get('lease_token','')); error=str(body.get('error','Delivery failed'))[:2000]
    if not worker or len(worker)>120 or len(lease_token)<32: raise HTTPException(422,'worker_id and lease_token are required')
    with conn() as c:
        stamp=now()
        row=c.execute("SELECT attempts FROM outbox WHERE id=? AND status='IN_FLIGHT' AND lease_owner=? AND lease_token=? AND lease_until>?",(outbox_id,worker,lease_token,stamp)).fetchone()
        if not row: raise HTTPException(409,'Outbox lease not owned, expired, or item is not in flight')
        attempts=row['attempts']; terminal=attempts>=8
        delay=min(3600,5*(2**min(attempts-1,10)))
        available=datetime.fromtimestamp(datetime.now(timezone.utc).timestamp()+delay,timezone.utc).isoformat()
        cur=c.execute("UPDATE outbox SET status=?,available_at=?,lease_until=NULL,lease_owner=NULL,lease_token=NULL,last_error=? WHERE id=? AND status='IN_FLIGHT' AND lease_owner=? AND lease_token=? AND lease_until>?",('DEAD' if terminal else 'PENDING',available,error,outbox_id,worker,lease_token,stamp))
        if not cur.rowcount: raise HTTPException(409,'Outbox lease changed or expired during failure acknowledgement')
    return {'id':outbox_id,'status':'DEAD' if terminal else 'PENDING','retry_after_seconds':None if terminal else delay}

@app.get('/api/v1/admin/outbox/dead')
def list_dead_outbox(limit:int=50,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    limit=max(1,min(limit,200))
    with conn() as c:
        rows=c.execute("SELECT id,event_type,status,attempts,available_at,last_error,created_at,tenant_id FROM outbox WHERE status='DEAD' ORDER BY created_at LIMIT ?",(limit,)).fetchall()
        return {'items':[dict(x) for x in rows],'count':len(rows)}

@app.post('/api/v1/admin/messages/{message_id}/restore-outbox')
def restore_missing_message_outbox(message_id:str,body:dict,authorization:str=Header(None)):
    """Explicitly restore one missing message dispatch record; never duplicates an existing dispatch."""
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    reason=str(body.get('reason','')).strip()
    if not reason or len(reason)>1000: raise HTTPException(422,'A recovery reason (1-1000 characters) is required')
    with conn() as c:
        begin_serialized_write(c)
        query='SELECT * FROM messages WHERE id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): query += ' FOR UPDATE'
        message=c.execute(query,(message_id,)).fetchone()
        if not message: raise HTTPException(404,'Message not found')
        existing_rows=c.execute("SELECT id,payload FROM outbox WHERE event_type='message.created'").fetchall()
        matching=[]
        for item in existing_rows:
            try:
                if json.loads(item['payload']).get('message_id')==message_id: matching.append(item['id'])
            except (TypeError,ValueError):
                continue
        if matching:
            raise HTTPException(409,'A message.created outbox record already exists; refusing duplicate recovery')
        project_id=None
        if message['task_id']:
            project=c.execute('SELECT r.project_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id WHERE t.id=?',(message['task_id'],)).fetchone()
            if project: project_id=project['project_id']
        payload={'message_id':message_id,'recipient_member_id':message['recipient_member_id'],
                 'project_id':project_id,'task_id':message['task_id'],'message_type':message['message_type'],
                 'title':message['title'],'content':message['content'],'priority':message['priority']}
        stamp=now(); outbox_id='obx_'+uuid.uuid4().hex
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',
                  (outbox_id,'message.created',json.dumps(payload),'PENDING',0,stamp,stamp,message['tenant_id']))
        event(c,'message.outbox.restored',a['id'],message['task_id'],
              {'message_id':message_id,'outbox_id':outbox_id,'reason':reason},tenant_override=message['tenant_id'])
    return {'message_id':message_id,'outbox_id':outbox_id,'status':'PENDING','restored':True}

@app.get('/api/v1/projects/{project_id}/message-delivery-health')
def project_message_delivery_health(project_id:str,authorization:str=Header(None),
                                    dispatch_sla_seconds:int=120,ack_sla_seconds:int=300,
                                    limit:int=100):
    """Project-scoped delivery SLA health; broker dispatch and recipient ACK clocks are separate."""
    a=actor(authorization)
    dispatch_sla_seconds=max(10,min(dispatch_sla_seconds,86400))
    ack_sla_seconds=max(10,min(ack_sla_seconds,604800))
    limit=max(1,min(limit,500))
    stamp=datetime.now(timezone.utc)
    incidents=[]
    with conn() as c:
        require_project_access(c,project_id,a)
        messages=c.execute("""SELECT m.id,m.recipient_member_id,m.tenant_id,m.task_id,m.status,m.created_at,m.acked_at
            FROM messages m JOIN tasks t ON t.id=m.task_id
            JOIN requirements r ON r.id=t.requirement_id
            WHERE r.project_id=? ORDER BY m.seq DESC LIMIT ?""",(project_id,limit)).fetchall()
        outbox=c.execute("SELECT id,payload,status,attempts,available_at,lease_until,lease_owner,last_error,created_at,sent_at FROM outbox WHERE event_type='message.created'").fetchall()
    by_message={}
    malformed=0
    for row in outbox:
        try:
            mid=json.loads(row['payload']).get('message_id')
            if isinstance(mid,str) and mid: by_message.setdefault(mid,[]).append(row)
            else: malformed+=1
        except (TypeError,ValueError):
            malformed+=1
    dispatch_counts={k:0 for k in ('HEALTHY','MISSING','DUPLICATE','DEAD','DISPATCH_OVERDUE')}
    ack_counts={k:0 for k in ('NOT_DUE','ACK_OVERDUE','ACKNOWLEDGED','REJECTED')}
    def parse_stamp(value):
        if not value: return None
        try:
            parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError,ValueError):
            return None
    for message in messages:
        records=by_message.get(message['id'],[])
        dispatch='HEALTHY'; ack='NOT_DUE'; detail=None
        if not records:
            dispatch='MISSING'; detail='No message.created outbox record'
        elif len(records)>1:
            dispatch='DUPLICATE'; detail='Multiple message.created outbox records'
        elif records[0]['status']=='DEAD':
            dispatch='DEAD'; detail=records[0]['last_error'] or 'Outbox entered DEAD state'
        elif records[0]['status'] in ('PENDING','IN_FLIGHT'):
            created=parse_stamp(records[0]['created_at'])
            if created and (stamp-created).total_seconds()>dispatch_sla_seconds:
                dispatch='DISPATCH_OVERDUE'; detail='Broker dispatch exceeded SLA'
        elif records[0]['status']!='SENT':
            dispatch='HEALTHY'; detail='Unrecognized outbox state: '+str(records[0]['status'])
        if dispatch in dispatch_counts: dispatch_counts[dispatch]+=1
        if message['status'] in ('ACKNOWLEDGED','REJECTED'):
            ack=message['status']
        elif records and len(records)==1 and records[0]['status']=='SENT':
            sent=parse_stamp(records[0]['sent_at'])
            if sent and (stamp-sent).total_seconds()>ack_sla_seconds:
                ack='ACK_OVERDUE'
        if ack in ack_counts: ack_counts[ack]+=1
        if dispatch!='HEALTHY':
            incidents.append({'message_id':message['id'],'task_id':message['task_id'],
                'category':'DISPATCH_'+dispatch,'dispatch_status':dispatch,'ack_status':ack,
                'age_seconds':max(0,int((stamp-(parse_stamp(message['created_at']) or stamp)).total_seconds())),
                'detail':detail})
        if ack=='ACK_OVERDUE':
            incidents.append({'message_id':message['id'],'task_id':message['task_id'],
                'category':'ACK_OVERDUE','dispatch_status':dispatch,'ack_status':ack,
                'age_seconds':max(0,int((stamp-(parse_stamp(records[0]['sent_at']) or stamp)).total_seconds())),
                'detail':'Broker dispatch completed but recipient ACK exceeded SLA'})
    return {'project_id':project_id,'generated_at':stamp.isoformat(),
        'policy':{'dispatch_sla_seconds':dispatch_sla_seconds,'ack_sla_seconds':ack_sla_seconds},
        'checked_messages':len(messages),'truncated':len(messages)==limit,
        'dispatch_counts':dispatch_counts,'ack_counts':ack_counts,
        'incident_count':len(incidents),'incidents':incidents[:limit],
        'malformed_outbox_records_seen':malformed,
        'semantics':'ACK SLA starts at outbox sent_at only. SENT is broker dispatch completion, not recipient ACK.'}

@app.post('/api/v1/projects/{project_id}/message-delivery-incidents/{message_id}/review')
def review_message_delivery_incident(project_id:str,message_id:str,body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    disposition=str(body.get('disposition','')).strip().upper()
    comment=str(body.get('comment','')).strip()
    if disposition not in ('INVESTIGATING','RESOLVED','ACCEPTED_RISK'):
        raise HTTPException(422,'disposition must be INVESTIGATING, RESOLVED, or ACCEPTED_RISK')
    if not comment or len(comment)>2000:
        raise HTTPException(422,'A review comment (1-2000 characters) is required')
    with conn() as c:
        require_project_access(c,project_id,a,write=True)
        row=c.execute("""SELECT m.task_id,m.tenant_id FROM messages m JOIN tasks t ON t.id=m.task_id
            JOIN requirements r ON r.id=t.requirement_id WHERE m.id=? AND r.project_id=?""",
            (message_id,project_id)).fetchone()
        if not row: raise HTTPException(404,'Project message not found')
        event(c,'message.delivery.incident.reviewed',a['id'],row['task_id'],
              {'project_id':project_id,'message_id':message_id,'disposition':disposition,'comment':comment},
              tenant_override=row['tenant_id'])
    return {'project_id':project_id,'message_id':message_id,'disposition':disposition,'recorded':True}


@app.get('/api/v1/admin/message-delivery')
def message_delivery_overview(authorization:str=Header(None),limit:int=200,offset:int=0,
                              dispatch_status:str=None,ack_status:str=None):
    """Admin operational view separating broker dispatch from recipient acknowledgement."""
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    limit=max(1,min(limit,500)); offset=max(0,offset)
    allowed_dispatch={'NO_OUTBOX','DUPLICATE','PENDING','IN_FLIGHT','SENT','DEAD'}
    allowed_ack={'PENDING','ACKNOWLEDGED','REJECTED'}
    if dispatch_status and dispatch_status not in allowed_dispatch:
        raise HTTPException(422,'Invalid dispatch_status filter')
    if ack_status and ack_status not in allowed_ack:
        raise HTTPException(422,'Invalid ack_status filter')
    with conn() as c:
        messages=c.execute('SELECT id,recipient_member_id,tenant_id,task_id,message_type,priority,status,created_at,acked_at FROM messages ORDER BY seq DESC LIMIT ? OFFSET ?',(limit,offset)).fetchall()
        outbox=c.execute("SELECT id,event_type,payload,status,attempts,available_at,lease_until,lease_owner,last_error,created_at,sent_at,tenant_id FROM outbox WHERE event_type='message.created' ORDER BY created_at").fetchall()
    by_message={}
    malformed_count=0
    for item in outbox:
        try:
            mid=json.loads(item['payload']).get('message_id')
            if not isinstance(mid,str) or not mid: malformed_count+=1; continue
        except (TypeError,ValueError):
            malformed_count+=1; continue
        by_message.setdefault(mid,[]).append(item)
    items=[]
    counts={key:0 for key in ('NO_OUTBOX','DUPLICATE','PENDING','IN_FLIGHT','SENT','DEAD')}
    ack_counts={key:0 for key in ('PENDING','ACKNOWLEDGED','REJECTED')}
    for message in messages:
        records=by_message.get(message['id'],[])
        state='NO_OUTBOX' if not records else ('DUPLICATE' if len(records)>1 else records[0]['status'])
        if state not in counts: state='UNKNOWN'
        if state in counts: counts[state]+=1
        ack=message['status']
        if ack in ack_counts: ack_counts[ack]+=1
        if dispatch_status and state!=dispatch_status: continue
        if ack_status and ack!=ack_status: continue
        items.append({
            'message_id':message['id'],'recipient_member_id':message['recipient_member_id'],
            'tenant_id':message['tenant_id'],'task_id':message['task_id'],
            'message_type':message['message_type'],'priority':message['priority'],
            'ack_status':ack,'created_at':message['created_at'],'acked_at':message['acked_at'],
            'dispatch_status':state,'dispatch_records':[{
                'outbox_id':row['id'],'status':row['status'],'attempts':row['attempts'],
                'available_at':row['available_at'],'lease_until':row['lease_until'],
                'lease_owner':row['lease_owner'],'last_error':row['last_error'],
                'created_at':row['created_at'],'sent_at':row['sent_at']
            } for row in records]
        })
    return {'items':items,'count':len(items),'limit':limit,'offset':offset,
            'dispatch_counts':counts,'ack_counts':ack_counts,
            'malformed_outbox_records_seen':malformed_count,
            'semantics':{'SENT':'Broker dispatch completed; recipient acknowledgement is tracked separately in ack_status.',
                         'ACKNOWLEDGED':'Recipient explicitly acknowledged the message.',
                         'REJECTED':'Recipient explicitly rejected the message.'}}

@app.get('/api/v1/admin/message-delivery-integrity')
def message_delivery_integrity(authorization:str=Header(None),limit:int=5000):
    """Read-only reconciliation of durable messages and their outbox dispatch records."""
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    limit=max(1,min(limit,10000))
    with conn() as c:
        messages=c.execute('SELECT id,recipient_member_id,tenant_id,task_id FROM messages ORDER BY seq LIMIT ?',(limit+1,)).fetchall()
        outbox=c.execute("SELECT id,event_type,payload,tenant_id,status FROM outbox WHERE event_type='message.created' ORDER BY created_at LIMIT ?",(limit+1,)).fetchall()
    truncated=len(messages)>limit or len(outbox)>limit
    messages=messages[:limit]; outbox=outbox[:limit]
    by_message={}
    malformed=[]; orphaned=[]; tenant_mismatch=[]; recipient_mismatch=[]; task_mismatch=[]
    known={row['id']:row for row in messages}
    for item in outbox:
        try:
            payload=json.loads(item['payload'])
            message_id=payload.get('message_id')
            if not isinstance(message_id,str) or not message_id:
                malformed.append(item['id']); continue
        except (TypeError,ValueError):
            malformed.append(item['id']); continue
        by_message.setdefault(message_id,[]).append(item)
        message=known.get(message_id)
        if not message:
            orphaned.append(item['id']); continue
        if item['tenant_id'] != message['tenant_id']:
            tenant_mismatch.append(item['id'])
        if payload.get('recipient_member_id') != message['recipient_member_id']:
            recipient_mismatch.append(item['id'])
        if payload.get('task_id') != message['task_id']:
            task_mismatch.append(item['id'])
    missing=[mid for mid in known if mid not in by_message]
    duplicates={mid:[x['id'] for x in rows] for mid,rows in by_message.items() if len(rows)>1}
    issues={
        'messages_without_outbox':missing,
        'duplicate_outbox_by_message':duplicates,
        'orphaned_outbox':orphaned,
        'malformed_outbox':malformed,
        'tenant_mismatch_outbox':tenant_mismatch,
        'recipient_mismatch_outbox':recipient_mismatch,
        'task_mismatch_outbox':task_mismatch,
    }
    counts={key:(len(value) if isinstance(value,list) else len(value)) for key,value in issues.items()}
    return {'checked_messages':len(messages),'checked_message_outbox':len(outbox),'truncated':truncated,
            'healthy':not any(counts.values()) and not truncated,'issue_counts':counts,'issues':issues,
            'semantics':'Read-only structural reconciliation; SENT means broker dispatch completed, not recipient ACK.'}

@app.post('/api/v1/admin/outbox/{outbox_id}/replay')
def replay_dead_outbox(outbox_id:str,body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    reason=str(body.get('reason','')).strip()
    if not reason or len(reason)>1000: raise HTTPException(422,'A replay reason (1-1000 characters) is required')
    with conn() as c:
        row=c.execute("SELECT tenant_id,status FROM outbox WHERE id=?",(outbox_id,)).fetchone()
        if not row: raise HTTPException(404,'Outbox item not found')
        if row['status']!='DEAD': raise HTTPException(409,'Only DEAD outbox items can be replayed')
        stamp=now()
        cur=c.execute("UPDATE outbox SET status='PENDING',attempts=0,available_at=?,lease_until=NULL,lease_owner=NULL,lease_token=NULL,last_error=NULL,sent_at=NULL WHERE id=? AND status='DEAD'",(stamp,outbox_id))
        if not cur.rowcount: raise HTTPException(409,'Outbox item changed; refresh and retry')
        event(c,'outbox.dead.replayed',a['id'],None,{'outbox_id':outbox_id,'reason':reason},tenant_override=row['tenant_id'])
    return {'id':outbox_id,'status':'PENDING','replayed':True}

@app.websocket('/ws/v1')
async def websocket_endpoint(ws:WebSocket,token:str='',after:int=0):
    # Best-effort online notification channel. The durable inbox remains the source of truth.
    lookup_reset=_auth_lookup_ctx.set(True)
    try:
        with conn() as c: member=(c.execute("SELECT id,tenant_id,role FROM daep_authenticate_member(?,?)",(hashlib.sha256(token.encode()).hexdigest(),now())).fetchone() if DATABASE_URL.startswith(('postgresql://','postgres://')) else c.execute("SELECT id,tenant_id,role FROM members WHERE token=? AND token_status='ACTIVE' AND (token_expires_at IS NULL OR token_expires_at>?)",(hashlib.sha256(token.encode()).hexdigest(),now())).fetchone())
    finally:
        _auth_lookup_ctx.reset(lookup_reset)
    if not member: await ws.close(code=1008); return
    cursor=max(0,after)
    _tenant_ctx.set(member['tenant_id']); _admin_ctx.set(member['role']=='admin' and member['tenant_id']=='tenant-default')
    await ws.accept()
    try:
        await ws.send_json({'type':'connected','at':now(),'cursor':cursor,'delivery':'best-effort; reconnect with after=<last processed seq> or recover via inbox'})
        while True:
            with conn() as c:
                rows=[dict(r) for r in c.execute("SELECT * FROM messages WHERE recipient_member_id=? AND status='PENDING' AND seq>? ORDER BY seq LIMIT 100",(member['id'],cursor))]
                if rows:
                    for r in rows:
                        await ws.send_json({'type':'notification','message':r})
                        cursor=max(cursor,r['seq'])
                        c.execute('UPDATE messages SET attempts=attempts+1,last_attempt_at=? WHERE id=?',(now(),r['id']))
            try: await asyncio.wait_for(ws.receive_text(),timeout=3.0)
            except asyncio.TimeoutError: pass
    except WebSocketDisconnect: pass

def require_worker(authorization):
    expected=os.getenv('DAEP_WORKER_TOKEN','')
    if len(expected)<32: raise HTTPException(503,'Dedicated DAEP_WORKER_TOKEN is not configured')
    if secrets.compare_digest(hashlib.sha256(expected.encode()).digest(),hashlib.sha256(ADMIN_TOKEN.encode()).digest()): raise HTTPException(503,'Worker credential must be different from DAEP_ADMIN_TOKEN')
    if not authorization or not authorization.startswith('Bearer '): raise HTTPException(401,'Worker bearer token required')
    supplied=authorization[7:]
    expected_digest=hashlib.sha256(expected.encode()).digest()
    supplied_digest=hashlib.sha256(supplied.encode()).digest()
    if not secrets.compare_digest(supplied_digest,expected_digest): raise HTTPException(401,'Invalid worker credential')
    _service_ctx.set(True)
def require_project_access(c, project_id, a, write=False):
    project=c.execute('SELECT tenant_id,status FROM projects WHERE id=?',(project_id,)).fetchone()
    if not project: raise HTTPException(404,'Project not found')
    if project['tenant_id'] != a.get('tenant_id','tenant-default') and not is_admin(a):
        raise HTTPException(403,'Tenant isolation violation')
    if write and project['status']=='CLOSED': raise HTTPException(409,'Project is closed')
    if is_admin(a): return
    if a.get('actor_type')=='AGENT':
        binding=c.execute("SELECT 1 FROM agent_project_bindings WHERE project_id=? AND agent_id=? AND status='ACTIVE'",
            (project_id,a['agent_id'])).fetchone()
        if not binding: raise HTTPException(403,'Agent project binding required')
        if write: raise HTTPException(403,'Agent cannot perform project-level governance or administration')
        return
    row=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(project_id,a['id'])).fetchone()
    if not row: raise HTTPException(403,'Project membership required')
    if write and row['role'] not in ('owner','manager'): raise HTTPException(403,'Project manager role required')
def task_project(c, tid):
    r=c.execute('SELECT r.project_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id WHERE t.id=?',(tid,)).fetchone()
    return r['project_id'] if r else None
def require_task_access(c, tid, a, assigned_only=False):
    pid=task_project(c,tid)
    if not pid: raise HTTPException(404,'Task not found')
    project=c.execute('SELECT status FROM projects WHERE id=?',(pid,)).fetchone()
    closed=bool(project and project['status']=='CLOSED')
    if is_admin(a):
        if assigned_only and closed: raise HTTPException(409,'Project is closed')
        return
    if a.get('actor_type')=='AGENT':
        require_project_access(c,pid,a)
        if assigned_only and closed:
            raise HTTPException(409,'Project is closed')
        assignment=c.execute("""SELECT 1 FROM agent_task_assignments
            WHERE task_id=? AND project_id=? AND agent_id=? AND status='ACCEPTED'""",
            (tid,pid,a['agent_id'])).fetchone()
        if not assignment:
            raise HTTPException(403,'Accepted Agent task assignment required')
        return
    if assigned_only:
        if closed: raise HTTPException(409,'Project is closed')
        ok=c.execute('SELECT 1 FROM assignments WHERE task_id=? AND member_id=?',(tid,a['id'])).fetchone()
        if not ok: raise HTTPException(403,'Task assignment required')
    else: require_project_access(c,pid,a)

def event(c,typ,member,task,payload,key=None,tenant_override=None):
    eid='evt_'+uuid.uuid4().hex
    tenant=tenant_override or 'tenant-default'
    if tenant_override:
        pass
    elif task:
        rr=c.execute('SELECT p.tenant_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE t.id=?',(task,)).fetchone()
        if rr: tenant=rr['tenant_id']
    elif member:
        rr=c.execute('SELECT tenant_id FROM members WHERE id=?',(member,)).fetchone()
        if rr: tenant=rr['tenant_id']
    audit_payload=dict(payload or {})
    audit_payload.setdefault('actor_type','AGENT' if _agent_ctx.get() else 'MEMBER')
    if _agent_ctx.get(): audit_payload.setdefault('agent_id',_agent_ctx.get())
    # Agent actions are attributed to the Agent identity, never to its owner's member row.
    actor_member_id=None if _agent_ctx.get() else member
    payload_json=json.dumps(audit_payload)
    if key:
        c.execute('INSERT INTO events(id,event_type,actor_member_id,task_id,payload,created_at,idempotency_key,tenant_id) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(idempotency_key) DO NOTHING',(eid,typ,actor_member_id,task,payload_json,now(),key,tenant))
        prior=c.execute('SELECT id,payload FROM events WHERE idempotency_key=?',(key,)).fetchone()
        if prior:
            if prior['payload'] != payload_json:
                raise HTTPException(409,'Idempotency key was used with a different payload')
            return prior['id']
    else:
        c.execute('INSERT INTO events(id,event_type,actor_member_id,task_id,payload,created_at,idempotency_key,tenant_id) VALUES(?,?,?,?,?,?,?,?)',(eid,typ,actor_member_id,task,payload_json,now(),key,tenant))
    return eid

@app.get('/',include_in_schema=False)
def dashboard(): return FileResponse(os.path.join(os.path.dirname(os.path.dirname(__file__)),'web','index.html'))
def _oidc_discovery():
    issuer=os.getenv('DAEP_OIDC_ISSUER','').rstrip('/')
    if not issuer: raise HTTPException(503,'OIDC is not configured')
    try:
        with urllib.request.urlopen(issuer+'/.well-known/openid-configuration',timeout=10) as r: return json.loads(r.read())
    except Exception as exc: raise HTTPException(503,f'OIDC discovery failed: {exc}')

def _oidc_state_record():
    """Create one-time server-side OIDC state, nonce and PKCE verifier."""
    state=secrets.token_urlsafe(32)
    nonce=secrets.token_urlsafe(32)
    verifier=secrets.token_urlsafe(64)
    expires=datetime.fromtimestamp(time.time()+600,timezone.utc).isoformat()
    with conn() as c:
        c.execute('DELETE FROM oidc_states WHERE expires_at<=?',(now(),))
        c.execute('INSERT INTO oidc_states(state_hash,nonce,code_verifier,expires_at,created_at) VALUES(?,?,?,?,?)',
                  (hashlib.sha256(state.encode()).hexdigest(),nonce,verifier,expires,now()))
    return state,nonce,verifier

def _verify_oidc_browser_state(state,cookie_state):
    if not cookie_state or not secrets.compare_digest(hashlib.sha256(cookie_state.encode()).digest(),hashlib.sha256(state.encode()).digest()):
        raise HTTPException(400,'OIDC browser state cookie mismatch')

def _consume_oidc_state(state):
    if not state or len(state)>512: raise HTTPException(400,'Invalid OIDC state')
    digest=hashlib.sha256(state.encode()).hexdigest()
    with conn() as c:
        row=c.execute('SELECT nonce,code_verifier,expires_at FROM oidc_states WHERE state_hash=?',(digest,)).fetchone()
        if not row: raise HTTPException(400,'Invalid or already used OIDC state')
        c.execute('DELETE FROM oidc_states WHERE state_hash=?',(digest,))
    if row['expires_at'] <= now(): raise HTTPException(400,'Expired OIDC state')
    return row['nonce'],row['code_verifier']

@app.get('/api/v1/auth/oidc/login')
def oidc_login():
    if not (os.getenv('DAEP_OIDC_CLIENT_ID') and os.getenv('DAEP_OIDC_REDIRECT_URI')): raise HTTPException(503,'OIDC is not configured')
    d=_oidc_discovery(); state,nonce,verifier=_oidc_state_record()
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    params={'client_id':os.getenv('DAEP_OIDC_CLIENT_ID'),'response_type':'code','redirect_uri':os.getenv('DAEP_OIDC_REDIRECT_URI'),'scope':os.getenv('DAEP_OIDC_SCOPES','openid profile email'),'state':state,'nonce':nonce,'code_challenge':challenge,'code_challenge_method':'S256'}
    if os.getenv('DAEP_OIDC_AUDIENCE'): params['audience']=os.getenv('DAEP_OIDC_AUDIENCE')
    response=RedirectResponse(d['authorization_endpoint']+'?'+urllib.parse.urlencode(params),status_code=302)
    response.set_cookie('daep_oidc_state',state,max_age=600,httponly=True,secure=os.getenv('DAEP_OIDC_REDIRECT_URI','').startswith('https://'),samesite='lax',path='/api/v1/auth/oidc/callback')
    return response

@app.get('/api/v1/auth/oidc/callback')
def oidc_callback(code:str,state:str,daep_oidc_state:Optional[str]=Cookie(None)):
    client_id=os.getenv('DAEP_OIDC_CLIENT_ID',''); client_secret=os.getenv('DAEP_OIDC_CLIENT_SECRET','')
    redirect_uri=os.getenv('DAEP_OIDC_REDIRECT_URI','')
    if not client_id or not client_secret or not redirect_uri: raise HTTPException(503,'OIDC client is not configured')
    _verify_oidc_browser_state(state,daep_oidc_state)
    nonce,code_verifier=_consume_oidc_state(state); d=_oidc_discovery()
    form=urllib.parse.urlencode({'grant_type':'authorization_code','code':code,'redirect_uri':redirect_uri,'client_id':client_id,'client_secret':client_secret,'code_verifier':code_verifier}).encode()
    req=urllib.request.Request(d['token_endpoint'],data=form,method='POST',headers={'Content-Type':'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req,timeout=15) as r: tokens=json.loads(r.read())
    except Exception: raise HTTPException(502,'OIDC token exchange failed')
    id_token=tokens.get('id_token')
    if not id_token: raise HTTPException(502,'OIDC provider did not return an id_token')
    try:
        import jwt
        jwks_client=jwt.PyJWKClient(d['jwks_uri'],timeout=10)
        signing_key=jwks_client.get_signing_key_from_jwt(id_token).key
        claims=jwt.decode(id_token,signing_key,algorithms=['RS256','RS384','RS512','PS256','ES256'],audience=client_id,issuer=os.getenv('DAEP_OIDC_ISSUER').rstrip('/'),options={'require':['exp','iat','sub','iss','aud']})
        if not secrets.compare_digest(str(claims.get('nonce','')),nonce): raise ValueError('OIDC nonce mismatch')
        audiences=claims.get('aud',[])
        if isinstance(audiences,list) and len(audiences)>1 and claims.get('azp')!=client_id: raise ValueError('OIDC authorized party mismatch')
    except Exception: raise HTTPException(401,'OIDC ID token validation failed')
    subject=str(claims.get('sub','')); email=str(claims.get('email',''))
    if not subject: raise HTTPException(401,'OIDC subject is missing')
    created=now(); raw=uuid.uuid4().hex+uuid.uuid4().hex; digest=hashlib.sha256(raw.encode()).hexdigest()
    service_reset=_service_ctx.set(True)
    try:
        with conn() as c:
            row=c.execute('SELECT id FROM members WHERE oidc_subject=?',(subject,)).fetchone()
            if row:
                c.execute("UPDATE members SET token=?,token_status='ACTIVE',token_created_at=?,token_revoked_at=NULL,oidc_email=? WHERE id=?",(digest,created,email,row['id']))
                member_id=row['id']
            else:
                if os.getenv('DAEP_OIDC_AUTO_PROVISION','false').lower()!='true': raise HTTPException(403,'OIDC identity is not provisioned')
                member_id='mem_'+uuid.uuid4().hex[:12]; tenant_id=os.getenv('DAEP_OIDC_DEFAULT_TENANT','tenant-default'); name=str(claims.get('name') or email or subject)
                if not c.execute("SELECT 1 FROM tenants WHERE id=? AND status='ACTIVE'",(tenant_id,)).fetchone(): raise HTTPException(403,'OIDC default tenant is unavailable')
                oidc_role=os.getenv('DAEP_OIDC_DEFAULT_ROLE','developer')
                if oidc_role not in ('developer','manager','reviewer'): oidc_role='developer'
                c.execute("INSERT INTO members(id,name,role,token,created_at,tenant_id,token_status,token_created_at,oidc_subject,oidc_email) VALUES(?,?,?,?,?,?,?,?,?,?)",(member_id,name,oidc_role,digest,created,tenant_id,'ACTIVE',created,subject,email))
    finally:
        _service_ctx.reset(service_reset)
    response=JSONResponse({'member_id':member_id,'token':raw,'token_expires_at':None,'message':'OIDC authentication succeeded; store this API token securely. It is returned only once.'})
    response.delete_cookie('daep_oidc_state',path='/api/v1/auth/oidc/callback')
    return response

@app.get('/api/v1/auth/oidc/config')
def oidc_config():
    enabled=bool(os.getenv('DAEP_OIDC_ISSUER') and os.getenv('DAEP_OIDC_CLIENT_ID') and os.getenv('DAEP_OIDC_REDIRECT_URI'))
    return {'enabled':enabled,'issuer':os.getenv('DAEP_OIDC_ISSUER',''),'client_id':os.getenv('DAEP_OIDC_CLIENT_ID',''),'redirect_uri':os.getenv('DAEP_OIDC_REDIRECT_URI',''),'scopes':os.getenv('DAEP_OIDC_SCOPES','openid profile email')}

@app.post('/api/v1/integrations/git/webhook')
async def git_webhook(request:Request, body:dict, x_daep_webhook_secret:str=Header('',alias='X-DAEP-Webhook-Secret'), x_daep_tenant_id:str=Header('',alias='X-DAEP-Tenant-ID'), x_daep_provider:str=Header('',alias='X-DAEP-Provider'), x_github_event:str=Header('',alias='X-GitHub-Event'), x_github_delivery:str=Header('',alias='X-GitHub-Delivery'), x_hub_signature_256:str=Header('',alias='X-Hub-Signature-256'), x_gitlab_event:str=Header('',alias='X-Gitlab-Event'), x_gitlab_event_uuid:str=Header('',alias='X-Gitlab-Event-UUID'), x_gitlab_token:str=Header('',alias='X-Gitlab-Token')):
    raw=await request.body()
    provider=(x_daep_provider or ('github' if x_github_event or x_hub_signature_256 else 'gitlab' if x_gitlab_event or x_gitlab_token else 'generic')).lower()
    if provider not in ('github','gitlab','generic'): raise HTTPException(422,'Unsupported Git provider')
    if provider=='github':
        expected=os.getenv('DAEP_GITHUB_WEBHOOK_SECRET') or os.getenv('DAEP_GIT_WEBHOOK_SECRET','')
        if not expected or not x_hub_signature_256 or not x_hub_signature_256.startswith('sha256='): raise HTTPException(401,'GitHub webhook signature is required')
        supplied=x_hub_signature_256.split('=',1)[1]
        actual=hmac.new(expected.encode(),raw,hashlib.sha256).hexdigest()
        if not hmac.compare_digest(actual,supplied): raise HTTPException(401,'Invalid GitHub webhook signature')
        delivery=x_github_delivery
    elif provider=='gitlab':
        expected=os.getenv('DAEP_GITLAB_WEBHOOK_SECRET') or os.getenv('DAEP_GIT_WEBHOOK_SECRET','')
        if not expected or not x_gitlab_token or not secrets.compare_digest(hashlib.sha256(x_gitlab_token.encode()).digest(),hashlib.sha256(expected.encode()).digest()): raise HTTPException(401,'Invalid GitLab webhook token')
        delivery=x_gitlab_event_uuid
    else:
        expected=os.getenv('DAEP_GIT_WEBHOOK_SECRET','')
        if not expected or not x_daep_webhook_secret or not secrets.compare_digest(hashlib.sha256(x_daep_webhook_secret.encode()).digest(),hashlib.sha256(expected.encode()).digest()): raise HTTPException(401,'Invalid webhook secret')
        delivery=request.headers.get('X-DAEP-Delivery','')
    if delivery and len(delivery)>200: raise HTTPException(422,'Webhook delivery id is too long')
    event_type=str(body.get('event_type') or body.get('action') or x_github_event or x_gitlab_event or 'push')[:80]
    task_id=body.get('task_id'); commit=body.get('after') or body.get('commit_sha')
    service_reset=_service_ctx.set(True)
    try:
        with conn() as c:
            if task_id:
                row=c.execute('SELECT p.tenant_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE t.id=?',(task_id,)).fetchone()
                if not row: raise HTTPException(404,'Task not found')
                tenant_id=row['tenant_id']
            else:
                tenant_id=str(x_daep_tenant_id or body.get('tenant_id') or '').strip()
                if not tenant_id: raise HTTPException(422,'X-DAEP-Tenant-ID is required when task_id is absent')
                if not c.execute("SELECT 1 FROM tenants WHERE id=? AND status='ACTIVE'",(tenant_id,)).fetchone(): raise HTTPException(404,'Tenant not found or inactive')
        _tenant_ctx.set(tenant_id); _admin_ctx.set(False)
        _service_ctx.reset(service_reset); service_reset=_service_ctx.set(False)
        with conn() as c:
            eid=event(c,'git.webhook.received',None,task_id,{'provider':provider,'delivery_id':delivery,'event_type':event_type,'commit_sha':commit,'payload':body},key=(f'git:{provider}:{delivery}' if delivery else None),tenant_override=tenant_id)
        return {'accepted':True,'event_id':eid,'event_type':event_type,'commit_sha':commit,'tenant_id':tenant_id,'provider':provider,'delivery_id':delivery}
    finally:
        _service_ctx.reset(service_reset)

@app.get('/health')
def health():
    service_reset=_service_ctx.set(True)
    try:
        with conn() as c:
            pending=c.execute("SELECT COUNT(*) n FROM outbox WHERE status IN ('PENDING','IN_FLIGHT')").fetchone()['n']
        return {'status':'ok','service':'daep-api','version':'1.0.0-rc9','outbox_pending':pending}
    finally:
        _service_ctx.reset(service_reset)

@app.get('/readyz')
def readiness():
    service_reset=_service_ctx.set(True)
    try:
        with conn() as c:
            c.execute('SELECT 1').fetchone()
            if DATABASE_URL.startswith(('postgresql://','postgres://')):
                c.execute("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='members'").fetchone()
        return {'status':'ready','service':'daep-api','version':'1.0.0-rc9'}
    except Exception:
        raise HTTPException(503,'DAEP database readiness check failed')
    finally:
        _service_ctx.reset(service_reset)
@app.get('/api/v1/me')
def me(authorization:str=Header(None)):
    a=actor(authorization); return {k:a[k] for k in ('id','name','role')}
@app.post('/api/v1/tenants')
def create_tenant(body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    name=str(body.get('name','')).strip()
    if not name or len(name)>160: raise HTTPException(422,'Tenant name is required')
    tid='ten_'+uuid.uuid4().hex[:12]
    with conn() as c: c.execute('INSERT INTO tenants(id,name,status,created_at) VALUES(?,?,?,?)',(tid,name,'ACTIVE',now()))
    return {'id':tid,'name':name,'status':'ACTIVE'}

@app.get('/api/v1/tenants')
def list_tenants(authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    with conn() as c: return [dict(x) for x in c.execute('SELECT * FROM tenants ORDER BY created_at')]

@app.post('/api/v1/members')
def create_member(body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    if not isinstance(body.get('name'),str) or not body['name'].strip(): raise HTTPException(422,'Member name is required')
    if body.get('role','developer') not in ('manager','developer','reviewer'): raise HTTPException(422,'Only the bootstrap identity can hold the platform administrator role')
    mid='mem_'+uuid.uuid4().hex[:12]; token=uuid.uuid4().hex+uuid.uuid4().hex; created=now()
    tenant_id=str(body.get('tenant_id') or a.get('tenant_id') or 'tenant-default')
    with conn() as c:
        if not c.execute("SELECT 1 FROM tenants WHERE id=? AND status='ACTIVE'",(tenant_id,)).fetchone(): raise HTTPException(404,'Tenant not found or inactive')
        c.execute('INSERT INTO members(id,name,role,token,created_at,tenant_id,token_status,token_created_at,token_revoked_at,token_expires_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(mid,body['name'],body.get('role','developer'),hashlib.sha256(token.encode()).hexdigest(),created,tenant_id,'ACTIVE',created,None,body.get('token_expires_at')))
    return {'id':mid,'name':body['name'],'role':body.get('role','developer'),'tenant_id':tenant_id,'token':token}
@app.get('/api/v1/members')
def members(authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    with conn() as c: return [dict(x) for x in c.execute('SELECT id,name,role,tenant_id,token_status,token_created_at,token_revoked_at,token_expires_at,created_at FROM members ORDER BY created_at')]
@app.post('/api/v1/members/{member_id}/revoke-token')
def revoke_member_token(member_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    with conn() as c:
        target=c.execute('SELECT tenant_id FROM members WHERE id=?',(member_id,)).fetchone()
        if not target: raise HTTPException(404,'Member not found')
        cur=c.execute("UPDATE members SET token_status='REVOKED',token_revoked_at=? WHERE id=?" ,(now(),member_id))
        event(c,'member.token.revoked',a['id'],None,{'member_id':member_id},tenant_override=target['tenant_id'])
    return {'member_id':member_id,'token_status':'REVOKED'}

@app.post('/api/v1/members/{member_id}/rotate-token')
def rotate_member_token(member_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    token=uuid.uuid4().hex+uuid.uuid4().hex; created=now(); digest=hashlib.sha256(token.encode()).hexdigest()
    with conn() as c:
        target=c.execute('SELECT tenant_id FROM members WHERE id=?',(member_id,)).fetchone()
        if not target: raise HTTPException(404,'Member not found')
        cur=c.execute("UPDATE members SET token=?,token_status='ACTIVE',token_created_at=?,token_revoked_at=NULL WHERE id=?",(digest,created,member_id))
        event(c,'member.token.rotated',a['id'],None,{'member_id':member_id},tenant_override=target['tenant_id'])
    return {'member_id':member_id,'token':token,'token_status':'ACTIVE','token_created_at':created}

@app.post('/api/v1/projects')
def create_project(b:ProjectIn,authorization:str=Header(None)):
    a=actor(authorization); pid='prj_'+uuid.uuid4().hex[:12]
    with conn() as c:
        c.execute('INSERT INTO projects(id,name,description,created_by,created_at,tenant_id) VALUES(?,?,?,?,?,?)',(pid,b.name,b.description,a['id'],now(),a.get('tenant_id','tenant-default')))
        c.execute('INSERT INTO project_members(project_id,member_id,role,work_function,joined_at) VALUES(?,?,?,?,?)',(pid,a['id'],'owner','other',now()))
    return {'id':pid,'name':b.name,'description':b.description}
@app.get('/api/v1/projects')
def projects(authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        if is_admin(a): rows=c.execute('SELECT * FROM projects ORDER BY created_at DESC')
        else: rows=c.execute('SELECT p.*,pm.role AS project_role,pm.work_function FROM projects p JOIN project_members pm ON pm.project_id=p.id WHERE pm.member_id=? AND p.tenant_id=? ORDER BY p.created_at DESC',(a['id'],a.get('tenant_id','tenant-default')))
        return [dict(x) for x in rows]
@app.get('/api/v1/projects/{pid}/members')
def project_members(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        return [dict(x) for x in c.execute('SELECT m.id,m.name,m.role AS account_role,pm.role AS project_role,pm.work_function,pm.joined_at FROM project_members pm JOIN members m ON m.id=pm.member_id WHERE pm.project_id=? ORDER BY pm.joined_at',(pid,))]
@app.post('/api/v1/projects/{pid}/members')
def add_project_member(pid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization)
    mid=b.get('member_id'); role=b.get('role','member'); work_function=b.get('work_function','other')
    if role not in ('member','reviewer','manager'): raise HTTPException(422,'Invalid project role')
    if work_function not in ('developer','tester','product','architect','other'): raise HTTPException(422,'Invalid work function')
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        if role=='manager' and not is_admin(a):
            own=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not own or own['role']!='owner': raise HTTPException(403,'Only project owners may directly grant manager role; use an approval request')
        member_row=c.execute('SELECT tenant_id FROM members WHERE id=?',(mid,)).fetchone()
        project_row=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        if not member_row: raise HTTPException(404,'Member not found')
        if project_row['tenant_id'] != member_row['tenant_id']: raise HTTPException(400,'Member belongs to a different tenant')
        c.execute('INSERT INTO project_members(project_id,member_id,role,work_function,joined_at) VALUES(?,?,?,?,?) ON CONFLICT(project_id,member_id) DO UPDATE SET role=excluded.role,work_function=excluded.work_function',(pid,mid,role,work_function,now()))
        event(c,'project.member.role_set',a['id'],None,{'project_id':pid,'member_id':mid,'role':role},tenant_override=project_row['tenant_id'])
        return {'project_id':pid,'member_id':mid,'role':role,'work_function':work_function}
@app.patch('/api/v1/projects/{pid}/members/{member_id}/function')
def update_project_member_function(pid:str,member_id:str,b:ProjectMemberFunctionIn,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        target=c.execute('SELECT role,work_function FROM project_members WHERE project_id=? AND member_id=?',(pid,member_id)).fetchone()
        if not target: raise HTTPException(404,'Target is not a project member')
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        c.execute('UPDATE project_members SET work_function=? WHERE project_id=? AND member_id=?',(b.work_function,pid,member_id))
        event(c,'project.member.work_function_set',a['id'],None,{'project_id':pid,'member_id':member_id,'work_function':b.work_function},tenant_override=project['tenant_id'])
        return {'project_id':pid,'member_id':member_id,'project_role':target['role'],'work_function':b.work_function}

@app.post('/api/v1/projects/{pid}/role-change-requests')
def request_project_role_change(pid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization); member_id=str(b.get('member_id','')).strip(); new_role=str(b.get('new_role','')).strip()
    reason=str(b.get('reason','')).strip()
    if not member_id or new_role not in ('member','reviewer','manager') or not reason or len(reason)>1000:
        raise HTTPException(422,'member_id, valid new_role and reason (1-1000 chars) are required')
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        target=c.execute('SELECT tenant_id FROM members WHERE id=?',(member_id,)).fetchone()
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        if not target or target['tenant_id']!=project['tenant_id']: raise HTTPException(404,'Member not found in project tenant')
        if not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(pid,member_id)).fetchone(): raise HTTPException(404,'Target is not a project member')
        current=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,member_id)).fetchone()['role']
        if current==new_role: raise HTTPException(409,'Member already has requested role')
        aid='apr_'+uuid.uuid4().hex
        payload={'member_id':member_id,'previous_role':current,'new_role':new_role,'reason':reason}
        c.execute("INSERT INTO project_approvals(id,project_id,tenant_id,requester_member_id,action,payload,status,created_at) VALUES(?,?,?,?,? ,?,'PENDING',?)",
                  (aid,pid,project['tenant_id'],a['id'],'PROJECT_ROLE_CHANGE',json.dumps(payload),now()))
        event(c,'project.role_change.requested',a['id'],None,{'approval_id':aid,'project_id':pid,**payload},tenant_override=project['tenant_id'])
        return {'approval_id':aid,'status':'PENDING','project_id':pid,'payload':payload}

@app.get('/api/v1/projects/{pid}/approvals')
def list_project_approvals(pid:str,status:str='PENDING',limit:int=100,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,200))
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute('SELECT * FROM project_approvals WHERE project_id=? AND status=? ORDER BY created_at DESC LIMIT ?',(pid,status,limit)).fetchall()
        return {'items':[{'id':x['id'],'action':x['action'],'payload':json.loads(x['payload']),'status':x['status'],'requester_member_id':x['requester_member_id'],'decided_by':x['decided_by'],'decision_reason':x['decision_reason'],'created_at':x['created_at'],'decided_at':x['decided_at']} for x in rows]}

@app.post('/api/v1/projects/{pid}/approvals/{approval_id}/decision')
def decide_project_approval(pid:str,approval_id:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization); decision=str(b.get('decision','')).upper(); reason=str(b.get('reason','')).strip()
    if decision not in ('APPROVE','REJECT') or not reason or len(reason)>1000: raise HTTPException(422,'decision must be APPROVE or REJECT and reason is required')
    with conn() as c:
        require_project_access(c,pid,a)
        if not is_admin(a):
            own=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not own or own['role']!='owner': raise HTTPException(403,'Project owner approval required')
        row=c.execute('SELECT * FROM project_approvals WHERE id=? AND project_id=?',(approval_id,pid)).fetchone()
        if not row: raise HTTPException(404,'Approval not found')
        if row['status']!='PENDING': raise HTTPException(409,'Approval already decided')
        if row['requester_member_id']==a['id']: raise HTTPException(403,'Requester cannot approve their own request')
        payload=json.loads(row['payload'])
        if row['action']!='PROJECT_ROLE_CHANGE': raise HTTPException(409,'Unsupported approval action')
        if decision=='APPROVE':
            current=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,payload['member_id'])).fetchone()
            if not current or current['role']!=payload['previous_role']: raise HTTPException(409,'Target role changed since request; submit a new request')
            c.execute('UPDATE project_members SET role=? WHERE project_id=? AND member_id=?',(payload['new_role'],pid,payload['member_id']))
        stamp=now()
        approval_status='APPROVED' if decision=='APPROVE' else 'REJECTED'
        c.execute('UPDATE project_approvals SET status=?,decided_by=?,decision_reason=?,decided_at=? WHERE id=? AND status=?',(approval_status,a['id'],reason,stamp,approval_id,'PENDING'))
        event(c,'project.role_change.'+('approved' if decision=='APPROVE' else 'rejected'),a['id'],None,{'approval_id':approval_id,'project_id':pid,**payload,'decision_reason':reason},tenant_override=row['tenant_id'])
        return {'approval_id':approval_id,'status':approval_status,'member_id':payload['member_id'],'role':payload['new_role'] if decision=='APPROVE' else payload['previous_role']}

@app.get('/api/v1/requirements/{rid}/acceptance-report')
def requirement_acceptance_report(rid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        req=c.execute('SELECT * FROM requirements WHERE id=?',(rid,)).fetchone()
        if not req: raise HTTPException(404,'Requirement not found')
        require_project_access(c,req['project_id'],a)
        criteria=json.loads(req['acceptance_criteria'] or '[]')
        tasks=c.execute("SELECT t.id,t.title,t.status,t.progress,t.updated_at,(SELECT COUNT(*) FROM artifacts ar WHERE ar.task_id=t.id) AS artifact_count FROM tasks t WHERE t.requirement_id=? ORDER BY t.created_at,t.id",(rid,)).fetchall()
        items=[dict(x) for x in tasks]
        missing=[x['id'] for x in items if x['status']!='DONE' or x['artifact_count']<1]
        return {'requirement_id':rid,'project_id':req['project_id'],'title':req['title'],'status':req['status'],
            'acceptance_criteria':[{'index':i,'text':v} for i,v in enumerate(criteria)],'task_count':len(items),
            'tasks':items,'all_tasks_done':bool(items) and all(x['status']=='DONE' for x in items),
            'missing_delivery_evidence_task_ids':missing,'ready_for_acceptance':bool(items) and not missing and bool(criteria)}

@app.post('/api/v1/requirements/{rid}/acceptance')
def decide_requirement_acceptance(rid:str,b:RequirementAcceptanceIn,authorization:str=Header(None)):
    a=actor(authorization)
    if a.get('actor_type')=='AGENT': raise HTTPException(403,'Agent cannot approve or reject requirement acceptance')
    with conn() as c:
        req=c.execute('SELECT * FROM requirements WHERE id=?',(rid,)).fetchone()
        if not req: raise HTTPException(404,'Requirement not found')
        pid=req['project_id']; require_project_access(c,pid,a)
        if not is_admin(a):
            role=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not role or role['role'] not in ('owner','manager','reviewer'): raise HTTPException(403,'Reviewer role required')
        if req['status']=='ACCEPTED': raise HTTPException(409,'Requirement is already accepted')
        criteria=json.loads(req['acceptance_criteria'] or '[]')
        verified=list(dict.fromkeys(b.verified_criteria))
        if len(verified)!=len(b.verified_criteria): raise HTTPException(422,'verified_criteria must be unique')
        if any(i<0 or i>=len(criteria) for i in verified): raise HTTPException(422,'verified_criteria contains an unknown criterion index')
        tasks=c.execute("SELECT t.id,t.status,(SELECT COUNT(*) FROM artifacts ar WHERE ar.task_id=t.id) AS artifact_count FROM tasks t WHERE t.requirement_id=? ORDER BY t.id",(rid,)).fetchall()
        if b.decision=='APPROVE':
            if not criteria or verified!=list(range(len(criteria))): raise HTTPException(409,'Every acceptance criterion must be explicitly verified')
            pending=[x['id'] for x in tasks if x['status']!='DONE']
            missing=[x['id'] for x in tasks if x['artifact_count']<1]
            if not tasks or pending or missing: raise HTTPException(409,detail={'message':'Requirement cannot be accepted until every task is DONE and has delivery evidence','pending_task_ids':pending,'missing_artifact_task_ids':missing})
            status='ACCEPTED'
        else: status='OPEN'
        stamp=now(); c.execute('UPDATE requirements SET status=? WHERE id=?',(status,rid))
        tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id']
        payload={'project_id':pid,'requirement_id':rid,'decision':b.decision,'status':status,'verified_criteria':verified,
            'acceptance_criteria':criteria,'comment':b.comment,'task_ids':[x['id'] for x in tasks]}
        eid=event(c,'requirement.acceptance.'+b.decision.lower(),a['id'],None,payload,tenant_override=tenant)
        return {'requirement_id':rid,'status':status,'decision':b.decision,'event_id':eid,'decided_at':stamp,'verified_criteria':verified}

@app.post('/api/v1/projects/{pid}/decisions')
def record_project_decision(pid:str,b:ProjectDecisionIn,authorization:str=Header(None)):
    a=actor(authorization); decision_id='dec_'+uuid.uuid4().hex
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        accountable=c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(pid,b.accountable_member_id)).fetchone()
        if not accountable: raise HTTPException(422,'Accountable member must belong to this project')
        task_ids=list(dict.fromkeys(b.related_task_ids))
        if len(task_ids)!=len(b.related_task_ids): raise HTTPException(422,'related_task_ids must be unique')
        for task_id in task_ids:
            if task_project(c,task_id)!=pid: raise HTTPException(422,'Every related task must belong to this project')
        payload={'project_id':pid,'decision_id':decision_id,'title':b.title,'decision':b.decision,
            'rationale':b.rationale,'accountable_member_id':b.accountable_member_id,
            'related_task_ids':task_ids,'due_at':b.due_at,'recorded_by':a['id']}
        event(c,'project.decision.created',a['id'],None,payload)
    return {'id':decision_id,'project_id':pid,'status':'RECORDED','created_at':now(),**payload}

@app.get('/api/v1/projects/{pid}/decisions')
def list_project_decisions(pid:str,limit:int=100,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,500))
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("SELECT e.id,e.actor_member_id,e.payload,e.created_at,m.name AS actor_name FROM events e LEFT JOIN members m ON m.id=e.actor_member_id WHERE e.event_type='project.decision.created' AND e.payload LIKE ? ORDER BY e.created_at DESC LIMIT ?",('%"project_id"%"'+pid+'"%',limit)).fetchall()
        items=[]
        for row in rows:
            payload=json.loads(row['payload'] or '{}')
            if payload.get('project_id')!=pid: continue
            accountable=c.execute('SELECT name FROM members WHERE id=?',(payload.get('accountable_member_id'),)).fetchone()
            items.append({'id':payload.get('decision_id'),'title':payload.get('title'),'decision':payload.get('decision'),
                'rationale':payload.get('rationale',''),'accountable_member_id':payload.get('accountable_member_id'),
                'accountable_member_name':accountable['name'] if accountable else None,'related_task_ids':payload.get('related_task_ids',[]),
                'due_at':payload.get('due_at'),'recorded_by':row['actor_member_id'],'recorded_by_name':row['actor_name'],
                'created_at':row['created_at'],'audit_event_id':row['id']})
        return {'project_id':pid,'items':items,'count':len(items)}

@app.get('/api/v1/projects/{pid}/governance')
def project_governance_snapshot(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT t.id,t.status,t.progress,t.updated_at,a.member_id,m.name AS member_name
            FROM tasks t JOIN requirements r ON r.id=t.requirement_id
            LEFT JOIN assignments a ON a.task_id=t.id LEFT JOIN members m ON m.id=a.member_id
            WHERE r.project_id=? ORDER BY t.id""",(pid,)).fetchall()
        task_ids=set(); task_state={}
        for row in rows:
            task_ids.add(row['id'])
            task_state[row['id']]={'status':row['status'],'progress':row['progress']}
        total=len(task_ids)
        status_counts={}
        for item in task_state.values(): status_counts[item['status']]=status_counts.get(item['status'],0)+1
        responsibility={}
        for row in rows:
            if not row['member_id']: continue
            slot=responsibility.setdefault(row['member_id'],{'member_id':row['member_id'],'member_name':row['member_name'],'assigned_task_ids':[],'done':0,'active':0,'review':0,'blocked':0})
            if row['id'] not in slot['assigned_task_ids']:
                slot['assigned_task_ids'].append(row['id'])
                if row['status']=='DONE': slot['done']+=1
                elif row['status']=='REVIEW': slot['review']+=1
                elif row['status']=='BLOCKED': slot['blocked']+=1
                else: slot['active']+=1
        packages=c.execute("SELECT risk_state,COUNT(*) AS n FROM task_work_packages WHERE project_id=? AND status='ACTIVE' GROUP BY risk_state",(pid,)).fetchall()
        package_risks={x['risk_state']:x['n'] for x in packages}
        pending_reviews=status_counts.get('REVIEW',0)
        delivery_health=project_message_delivery_health(pid,authorization,120,300,500)
        review_rows=c.execute("""SELECT e.payload,e.created_at FROM events e
            WHERE e.event_type='message.delivery.incident.reviewed' AND e.payload LIKE ?
            ORDER BY e.created_at DESC LIMIT 1000""",('%'+pid+'%',)).fetchall()
        latest_reviews={}
        for review_row in review_rows:
            try:
                payload=json.loads(review_row['payload'] or '{}')
                if payload.get('project_id')!=pid: continue
                mid=payload.get('message_id')
                if mid and mid not in latest_reviews:
                    latest_reviews[mid]={'disposition':payload.get('disposition'),'comment':payload.get('comment'),
                                         'reviewed_at':review_row['created_at']}
            except (TypeError,ValueError):
                continue
        reviewed_incidents=[]
        open_incidents=0; resolved_incidents=0; accepted_risk_incidents=0; investigating_incidents=0
        for incident in delivery_health.get('incidents',[]):
            review=latest_reviews.get(incident['message_id'])
            disposition=review.get('disposition') if review else 'UNREVIEWED'
            item=dict(incident)
            item['review_disposition']=disposition
            item['reviewed_at']=review.get('reviewed_at') if review else None
            reviewed_incidents.append(item)
            if disposition=='RESOLVED': resolved_incidents+=1
            elif disposition=='ACCEPTED_RISK': accepted_risk_incidents+=1
            else:
                open_incidents+=1
                if disposition=='INVESTIGATING': investigating_incidents+=1
        daily=c.execute("""SELECT substr(m.created_at,1,10) AS day,COUNT(*) AS created,
            SUM(CASE WHEN m.status IN ('ACKNOWLEDGED','REJECTED') THEN 1 ELSE 0 END) AS terminal_ack
            FROM messages m JOIN tasks t ON t.id=m.task_id JOIN requirements r ON r.id=t.requirement_id
            WHERE r.project_id=? AND m.created_at>=? GROUP BY substr(m.created_at,1,10) ORDER BY day""",
            (pid,datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).isoformat())).fetchall()
        delivery_trend=[{'date':x['day'],'messages_created':x['created'],'terminal_ack':x['terminal_ack'] or 0} for x in daily]
        message_delivery_governance={
            'checked_messages':delivery_health.get('checked_messages',0),
            'dispatch_counts':delivery_health.get('dispatch_counts',{}),
            'ack_counts':delivery_health.get('ack_counts',{}),
            'incident_count':delivery_health.get('incident_count',0),
            'open_incidents':open_incidents,'investigating_incidents':investigating_incidents,
            'resolved_incidents':resolved_incidents,'accepted_risk_incidents':accepted_risk_incidents,
            'incidents':reviewed_incidents,'trend_since_utc_midnight':delivery_trend,
            'sla_policy':delivery_health.get('policy'),
            'truncated':delivery_health.get('truncated',False)
        }
        return {'project_id':pid,'task_total':total,'task_status_counts':status_counts,
            'completed_tasks':status_counts.get('DONE',0),'completion_percent':round(status_counts.get('DONE',0)*100/total) if total else 100,
            'pending_reviews':pending_reviews,'open_tasks':total-status_counts.get('DONE',0),
            'active_work_package_risk_counts':package_risks,
            'at_risk_work_packages':sum(package_risks.get(k,0) for k in ('OVERDUE','BLOCKED_DEPENDENCY','STALLED')),
            'responsibility':list(responsibility.values()),
            'completion_gate':'SATISFIED' if total and status_counts.get('DONE',0)==total else ('EMPTY' if not total else 'OPEN'),
            'message_delivery':message_delivery_governance}

@app.get('/api/v1/projects/{pid}/workflow')
def get_project_workflow(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        row=c.execute('SELECT config,updated_by,updated_at FROM project_workflows WHERE project_id=?',(pid,)).fetchone()
        if row: return {'project_id':pid,'config':json.loads(row['config']),'updated_by':row['updated_by'],'updated_at':row['updated_at']}
        return {'project_id':pid,'config':{'enabled':True,'stages':[{'key':'OPEN','name':'需求进入','order':1,'approval_role':'none','sla_seconds':None},{'key':'IN_PROGRESS','name':'执行','order':2,'approval_role':'none','sla_seconds':172800},{'key':'REVIEW','name':'评审验收','order':3,'approval_role':'reviewer','sla_seconds':86400},{'key':'DONE','name':'完成交付','order':4,'approval_role':'none','sla_seconds':None}]},'source':'system-default'}

@app.put('/api/v1/projects/{pid}/workflow')
def set_project_workflow(pid:str,b:WorkflowConfigIn,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        if not (a['role']=='admin' or project_role(c,pid,a) in ('owner','manager')): raise HTTPException(403,'Project manager or platform administrator required')
        stages=sorted([x.model_dump() for x in b.stages],key=lambda x:x['order'])
        if [x['order'] for x in stages] != list(range(1,len(stages)+1)): raise HTTPException(422,'Stage order must be contiguous from 1')
        if len({x['key'] for x in stages}) != len(stages): raise HTTPException(422,'Stage keys must be unique')
        if not any(x['key']=='REVIEW' for x in stages): raise HTTPException(422,'System governance requires a REVIEW stage')
        cfg={'enabled':b.enabled,'stages':stages}; stamp=now(); tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id']
        c.execute('INSERT INTO project_workflows(project_id,tenant_id,config,updated_by,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET config=excluded.config,updated_by=excluded.updated_by,updated_at=excluded.updated_at',(pid,tenant,json.dumps(cfg),a['id'],stamp))
        event(c,'project.workflow.updated',a['id'],None,{'project_id':pid,'config':cfg},tenant_override=tenant)
        return {'project_id':pid,'config':cfg,'updated_by':a['id'],'updated_at':stamp}

@app.get('/api/v1/projects/{pid}/gates')
def get_project_gates(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute('SELECT gate_key,config,updated_by,updated_at FROM project_gates WHERE project_id=? ORDER BY gate_key',(pid,)).fetchall()
        items={r['gate_key']:{'config':json.loads(r['config']),'updated_by':r['updated_by'],'updated_at':r['updated_at']} for r in rows}
        items.setdefault('REVIEW_REQUIRED',{'config':{'enabled':True,'required_roles':['reviewer'],'required_evidence':True,'required_all_tasks_done':False},'system_locked':True})
        items.setdefault('DELIVERY_EVIDENCE',{'config':{'enabled':True,'required_roles':['owner','manager','reviewer'],'required_evidence':True,'required_all_tasks_done':True},'system_locked':True})
        return {'project_id':pid,'gates':items}

@app.put('/api/v1/projects/{pid}/gates/{gate_key}')
def set_project_gate(pid:str,gate_key:str,b:GateConfigIn,authorization:str=Header(None)):
    a=actor(authorization)
    if gate_key in ('REVIEW_REQUIRED','DELIVERY_EVIDENCE'): raise HTTPException(409,'System governance gate cannot be disabled or weakened')
    if not re.fullmatch(r'[A-Z0-9_]{2,60}',gate_key): raise HTTPException(422,'Invalid gate key')
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        if not (a['role']=='admin' or project_role(c,pid,a) in ('owner','manager')): raise HTTPException(403,'Project manager or platform administrator required')
        cfg=b.model_dump(); cfg['applies_to']=cfg.get('applies_to') or 'DONE'; stamp=now(); tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id']
        c.execute('INSERT INTO project_gates(project_id,gate_key,tenant_id,config,updated_by,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(project_id,gate_key) DO UPDATE SET config=excluded.config,updated_by=excluded.updated_by,updated_at=excluded.updated_at',(pid,gate_key,tenant,json.dumps(cfg),a['id'],stamp))
        event(c,'project.gate.updated',a['id'],None,{'project_id':pid,'gate_key':gate_key,'config':cfg},tenant_override=tenant)
        return {'project_id':pid,'gate_key':gate_key,'config':cfg,'updated_at':stamp}


DEFAULT_PROJECT_WORKFLOW={'enabled':True,'stages':[{'key':'OPEN','name':'需求进入','order':1,'approval_role':'none','sla_seconds':None},{'key':'IN_PROGRESS','name':'执行','order':2,'approval_role':'none','sla_seconds':172800},{'key':'REVIEW','name':'评审验收','order':3,'approval_role':'reviewer','sla_seconds':86400},{'key':'DONE','name':'完成交付','order':4,'approval_role':'none','sla_seconds':None}]}
SYSTEM_GOVERNANCE_GATES={
    'REVIEW_REQUIRED':{'enabled':True,'required_roles':['reviewer'],'required_evidence':True,'required_all_tasks_done':False,'applies_to':'DONE'},
    'DELIVERY_EVIDENCE':{'enabled':True,'required_roles':['owner','manager','reviewer'],'required_evidence':True,'required_all_tasks_done':True,'applies_to':'DONE'}
}
def project_role(c,pid,actor_value):
    row=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,actor_value['id'])).fetchone()
    return row['role'] if row else None
def project_workflow_config(c,pid):
    row=c.execute('SELECT config FROM project_workflows WHERE project_id=?',(pid,)).fetchone()
    return json.loads(row['config']) if row else DEFAULT_PROJECT_WORKFLOW
def project_gate_config(c,pid,gate_key):
    if gate_key in SYSTEM_GOVERNANCE_GATES: return SYSTEM_GOVERNANCE_GATES[gate_key]
    row=c.execute('SELECT config FROM project_gates WHERE project_id=? AND gate_key=?',(pid,gate_key)).fetchone()
    return json.loads(row['config']) if row else None
def enforce_project_gate(c,pid,gate_key,actor_member_id,task_id=None,target_stage='DONE'):
    cfg=project_gate_config(c,pid,gate_key)
    if not cfg or not cfg.get('enabled',True) or cfg.get('applies_to','DONE')!=target_stage: return
    if cfg.get('required_roles'):
        platform=c.execute('SELECT role FROM members WHERE id=?',(actor_member_id,)).fetchone()
        if not platform or platform['role']!='admin':
            member_role=project_role(c,pid,{'id':actor_member_id})
            function_row=c.execute('SELECT work_function FROM project_members WHERE project_id=? AND member_id=?',(pid,actor_member_id)).fetchone()
            work_function=function_row['work_function'] if function_row else None
            if member_role not in cfg['required_roles'] and work_function not in cfg['required_roles']:
                raise HTTPException(403,f'Gate {gate_key} requires one of: {", ".join(cfg["required_roles"])}')
    if task_id and cfg.get('required_evidence'):
        if c.execute('SELECT 1 FROM artifacts WHERE task_id=? LIMIT 1',(task_id,)).fetchone() is None:
            raise HTTPException(409,detail={'message':f'Gate {gate_key} requires delivery evidence','gate_key':gate_key,'task_id':task_id})
    if task_id and cfg.get('required_all_tasks_done'):
        row=c.execute('SELECT requirement_id FROM tasks WHERE id=?',(task_id,)).fetchone()
        if row:
            pending=c.execute("SELECT id FROM tasks WHERE requirement_id=? AND status!='DONE' AND id!=?",(row['requirement_id'],task_id)).fetchall()
            if pending: raise HTTPException(409,detail={'message':f'Gate {gate_key} requires all other requirement tasks to be DONE before this task closes','gate_key':gate_key,'pending_task_ids':[x['id'] for x in pending]})
def enforce_workflow_exit(c,pid,current_stage,actor_member_id):
    cfg=project_workflow_config(c,pid)
    stage=next((x for x in cfg.get('stages',[]) if x.get('key')==current_stage),None)
    if not stage: raise HTTPException(409,detail={'message':'Current task status is not part of the configured workflow','current_stage':current_stage})
    approval_role=stage.get('approval_role','none')
    if approval_role!='none':
        platform=c.execute('SELECT role FROM members WHERE id=?',(actor_member_id,)).fetchone()
        if not platform or platform['role']!='admin':
            role=project_role(c,pid,{'id':actor_member_id})
            if role!=approval_role: raise HTTPException(403,f'Leaving workflow stage {current_stage} requires {approval_role} role')
def enforce_workflow_stage(c,pid,stage_key,actor_member_id,task_id=None):
    cfg=project_workflow_config(c,pid)
    stage=next((x for x in cfg.get('stages',[]) if x.get('key')==stage_key),None)
    if not stage: raise HTTPException(409,detail={'message':'Target workflow stage is not configured','stage_key':stage_key})
    for gate_key in [x['gate_key'] for x in c.execute('SELECT gate_key FROM project_gates WHERE project_id=?',(pid,)).fetchall()]:
        enforce_project_gate(c,pid,gate_key,actor_member_id,task_id,stage_key)
def transition_task_workflow(c,tid,target_stage,actor_member_id,comment=''):
    pid=task_project(c,tid)
    if not pid: raise HTTPException(404,'Task not found')
    task=c.execute('SELECT status,progress FROM tasks WHERE id=?',(tid,)).fetchone()
    if not task: raise HTTPException(404,'Task not found')
    enforce_workflow_stage(c,pid,target_stage,actor_member_id,tid)
    progress=100 if target_stage=='DONE' else (100 if target_stage=='REVIEW' else task['progress'])
    c.execute('UPDATE tasks SET status=?,progress=?,updated_at=? WHERE id=?',(target_stage,progress,now(),tid))
    eid=event(c,'task.workflow.transitioned',actor_member_id,tid,{'from_status':task['status'],'to_status':target_stage,'comment':comment})
    return eid

@app.get('/api/v1/projects/{pid}/audit')
def project_audit(pid:str,limit:int=100,before:str='',event_type:str='',authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,500))
    with conn() as c:
        require_project_access(c,pid,a)
        sql="SELECT e.* FROM events e LEFT JOIN tasks t ON t.id=e.task_id LEFT JOIN requirements r ON r.id=t.requirement_id WHERE (r.project_id=? OR (e.task_id IS NULL AND e.payload LIKE ?))"
        args=[pid,'%\"project_id\"%\"'+pid+'\"%']
        if before: sql+=" AND e.created_at<?"; args.append(before)
        if event_type: sql+=" AND e.event_type=?"; args.append(event_type)
        sql+=" ORDER BY e.created_at DESC LIMIT ?"; args.append(limit)
        rows=c.execute(sql,args).fetchall()
        return {'project_id':pid,'items':[{'id':x['id'],'event_type':x['event_type'],'actor_member_id':x['actor_member_id'],'task_id':x['task_id'],'payload':json.loads(x['payload'] or '{}'),'created_at':x['created_at']} for x in rows]}

@app.get('/api/v1/projects/{pid}/audit.csv')
def export_project_audit(pid:str,limit:int=5000,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,10000))
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT e.id,e.event_type,e.actor_member_id,e.task_id,e.payload,e.created_at
            FROM events e LEFT JOIN tasks t ON t.id=e.task_id LEFT JOIN requirements r ON r.id=t.requirement_id
            WHERE (r.project_id=? OR (e.task_id IS NULL AND e.payload LIKE ?)) ORDER BY e.created_at DESC LIMIT ?""",(pid,'%\"project_id\"%\"'+pid+'\"%',limit)).fetchall()
        def q(v): return '"'+str(v if v is not None else '').replace('"','""')+'"'
        lines=['id,event_type,actor_member_id,task_id,created_at,payload']
        for x in rows: lines.append(','.join(q(v) for v in (x['id'],x['event_type'],x['actor_member_id'],x['task_id'],x['created_at'],x['payload'])))
        return Response(content='\n'.join(lines)+'\n',media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="daep-audit-{pid}.csv"'})

@app.get('/api/v1/projects/{pid}/requirements')
def project_requirements(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        return [dict(x) for x in c.execute('SELECT * FROM requirements WHERE project_id=? ORDER BY created_at DESC',(pid,))]
@app.get('/api/v1/projects/{pid}/tasks')
def project_tasks(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute('SELECT t.* FROM tasks t JOIN requirements r ON r.id=t.requirement_id WHERE r.project_id=? ORDER BY t.created_at DESC',(pid,)).fetchall()
        result=[]
        for raw in rows:
            item=dict(raw)
            item['dependencies']=[x['depends_on_task_id'] for x in c.execute('SELECT depends_on_task_id FROM dependencies WHERE task_id=?',(item['id'],))]
            result.append(item)
        return result
@app.post('/api/v1/requirements')
def create_requirement(b:RequirementIn,authorization:str=Header(None)):
    a=actor(authorization); rid='req_'+uuid.uuid4().hex[:12]
    with conn() as c:
        if not c.execute('SELECT 1 FROM projects WHERE id=?',(b.project_id,)).fetchone(): raise HTTPException(404,'Project not found')
        require_project_access(c,b.project_id,a,write=True)
        c.execute('INSERT INTO requirements VALUES(?,?,?,?,?,?,?)',(rid,b.project_id,b.title,b.description,json.dumps(b.acceptance_criteria),'OPEN',now()))
    return {'id':rid,'project_id':b.project_id,'title':b.title,'status':'OPEN'}
@app.get('/api/v1/requirements/{rid}')
def get_requirement(rid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        r=c.execute('SELECT * FROM requirements WHERE id=?',(rid,)).fetchone()
        if r: require_project_access(c,r['project_id'],a)
        if not r: raise HTTPException(404,'Requirement not found')
        d=dict(r); d['acceptance_criteria']=json.loads(d['acceptance_criteria']); return d
@app.post('/api/v1/tasks')
def create_task(b:TaskIn,authorization:str=Header(None)):
    a=actor(authorization); tid='tsk_'+uuid.uuid4().hex[:12]
    with conn() as c:
        req=c.execute('SELECT * FROM requirements WHERE id=?',(b.requirement_id,)).fetchone()
        if not req: raise HTTPException(404,'Requirement not found')
        require_project_access(c,req['project_id'],a,write=True)
        for dep in b.dependencies:
            if dep == tid: raise HTTPException(400,'A task cannot depend on itself')
            if not c.execute('SELECT 1 FROM tasks WHERE id=?',(dep,)).fetchone(): raise HTTPException(400,f'Unknown dependency {dep}')
            require_task_access(c,dep,a)
            if task_project(c,dep) != req['project_id']: raise HTTPException(400,'Dependencies must belong to the same project')
        c.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?)',(tid,b.requirement_id,b.title,b.description,'READY',0,now(),now()))
        for mid in b.assignee_member_ids:
            member_row=c.execute('SELECT tenant_id FROM members WHERE id=?',(mid,)).fetchone()
            if not member_row: raise HTTPException(400,f'Unknown member {mid}')
            project_tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(req['project_id'],)).fetchone()['tenant_id']
            if member_row['tenant_id'] != project_tenant: raise HTTPException(400,'Assignee belongs to a different tenant')
            c.execute('INSERT INTO assignments VALUES(?,?)',(tid,mid))
            c.execute("INSERT OR IGNORE INTO project_members(project_id,member_id,role,work_function,joined_at) VALUES(?,?,?,'other',?)",(req['project_id'],mid,'member',now()))
        for dep in b.dependencies: c.execute('INSERT INTO dependencies VALUES(?,?)',(tid,dep))
        event(c,'task.created',a['id'],tid,{'title':b.title})
    return task_detail(tid,authorization)
def task_detail(tid,authorization):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a)
        r=c.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone()
        if not r: raise HTTPException(404,'Task not found')
        d=dict(r); d['assignees']=[dict(x) for x in c.execute('SELECT m.id,m.name FROM assignments a JOIN members m ON m.id=a.member_id JOIN tasks t ON t.id=a.task_id JOIN requirements rq ON rq.id=t.requirement_id JOIN projects p ON p.id=rq.project_id WHERE a.task_id=? AND m.tenant_id=p.tenant_id',(tid,))]; d['dependencies']=[x['depends_on_task_id'] for x in c.execute('SELECT depends_on_task_id FROM dependencies WHERE task_id=?',(tid,))]; return d
@app.get('/api/v1/tasks/{tid}')
def get_task(tid:str,authorization:str=Header(None)): return task_detail(tid,authorization)
@app.put('/api/v1/tasks/{tid}/dependencies')
def update_task_dependencies(tid:str,b:TaskDependenciesIn,authorization:str=Header(None)):
    a=actor(authorization)
    if len(set(b.dependencies)) != len(b.dependencies): raise HTTPException(400,'Duplicate dependencies are not allowed')
    with conn() as c:
        require_task_access(c,tid,a)
        project_id=task_project(c,tid)
        require_project_access(c,project_id,a,write=True)
        for dep in b.dependencies:
            if dep == tid: raise HTTPException(400,'A task cannot depend on itself')
            if task_project(c,dep) != project_id: raise HTTPException(400,'Dependencies must belong to the same project')
            require_task_access(c,dep,a)
            pending=[dep]; visited=set()
            while pending:
                current=pending.pop()
                if current == tid: raise HTTPException(409,'Dependency would create a cycle')
                if current in visited: continue
                visited.add(current)
                pending.extend(x['depends_on_task_id'] for x in c.execute('SELECT depends_on_task_id FROM dependencies WHERE task_id=?',(current,)).fetchall())
        c.execute('DELETE FROM dependencies WHERE task_id=?',(tid,))
        for dep in b.dependencies: c.execute('INSERT INTO dependencies(task_id,depends_on_task_id) VALUES(?,?)',(tid,dep))
        event(c,'task.dependencies.updated',a['id'],tid,{'dependencies':b.dependencies})
    return task_detail(tid,authorization)

@app.get('/api/v1/me/tasks')
def my_tasks(authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c: return [dict(x) for x in c.execute('SELECT t.* FROM tasks t JOIN assignments s ON s.task_id=t.id JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE s.member_id=? AND p.tenant_id=? ORDER BY t.created_at DESC',(a['id'],a.get('tenant_id','tenant-default')))]
@app.post('/api/v1/tasks/{tid}/progress')
def progress(tid:str,b:ProgressIn,authorization:str=Header(None),idempotency_key:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a,assigned_only=True)
        if b.progress==100:
            enforce_task_review_request(c,tid,a)
        identity=a.get('agent_id') if a.get('actor_type')=='AGENT' else a['id']
        scoped_key=f"{identity}:{tid}:{idempotency_key}" if idempotency_key else None
        if scoped_key:
            prior=c.execute('SELECT id,payload FROM events WHERE idempotency_key=?',(scoped_key,)).fetchone()
            if prior:
                prior_payload=json.loads(prior['payload'] or '{}')
                prior_payload.pop('actor_type',None); prior_payload.pop('agent_id',None)
                if prior_payload != b.model_dump(): raise HTTPException(409,'Idempotency-Key was already used with a different payload')
                return {'event_id':prior['id'],'task_id':tid,'progress':b.progress,'idempotent_replay':True}
        c.execute('UPDATE tasks SET progress=?,status=?,updated_at=? WHERE id=?',(b.progress,'REVIEW' if b.progress==100 else ('IN_PROGRESS' if b.progress>0 else 'READY'),now(),tid))
        eid=event(c,'task.progress.updated',a['id'],tid,b.model_dump(),scoped_key)
    return {'event_id':eid,'task_id':tid,'progress':b.progress}
@app.post('/api/v1/tasks/{tid}/blocked')
def blocked(tid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a,assigned_only=True)
        c.execute("UPDATE tasks SET status='BLOCKED',updated_at=? WHERE id=?",(now(),tid)); eid=event(c,'task.blocked',a['id'],tid,b)
    return {'event_id':eid,'status':'BLOCKED'}
@app.post('/api/v1/tasks/{tid}/work-result')
def report_work_result(tid:str,b:WorkResultIn,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        begin_serialized_write(c)
        require_task_access(c,tid,a,assigned_only=True)
        package_sql='SELECT id,parent_task_id,status,correlation_id FROM task_work_packages WHERE child_task_id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): package_sql += ' FOR UPDATE'
        package=c.execute(package_sql,(tid,)).fetchone()
        if not package: raise HTTPException(404,'Task is not a registered work package')
        identity=a.get('agent_id') if a.get('actor_type')=='AGENT' else a['id']
        key=f"work-result:{identity}:{tid}:{b.idempotency_key}" if b.idempotency_key else None
        payload={'outcome':b.outcome,'summary':b.summary,'work_package_id':package['id'],'correlation_id':package['correlation_id'],'parent_task_id':package['parent_task_id']}
        if key:
            prior=c.execute('SELECT id,payload FROM events WHERE idempotency_key=?',(key,)).fetchone()
            if prior:
                prior_payload=json.loads(prior['payload'] or '{}')
                prior_payload.pop('actor_type',None); prior_payload.pop('agent_id',None)
                if prior_payload!=payload: raise HTTPException(409,'Idempotency key was used with a different result')
                return {'task_id':tid,'status':'REVIEW' if b.outcome=='COMPLETE' else 'BLOCKED','event_id':prior['id'],'idempotent_replay':True}
        if package['status']!='ACTIVE': raise HTTPException(409,'Work package is no longer active')
        if b.outcome=='COMPLETE':
            count=c.execute('SELECT COUNT(*) AS n FROM artifacts WHERE task_id=?',(tid,)).fetchone()['n']
            if count<1: raise HTTPException(409,'Submit at least one artifact before reporting completion')
            status='REVIEW'; progress=100
        else:
            status='BLOCKED'; progress=0
        c.execute('UPDATE tasks SET status=?,progress=?,updated_at=? WHERE id=?',(status,progress,now(),tid))
        eid=event(c,'task.work_package.reported',a['id'],tid,payload,key)
    return {'task_id':tid,'status':status,'event_id':eid,'outcome':b.outcome}


@app.post('/api/v1/tasks/{tid}/workflow-transition')
def transition_task_workflow_endpoint(tid:str,b:dict,authorization:str=Header(None),idempotency_key:str=Header(None)):
    a=actor(authorization); target=str(b.get('target_stage','')).strip().upper(); comment=str(b.get('comment',''))[:4000]
    if not target: raise HTTPException(422,'target_stage is required')
    if target=='BLOCKED': raise HTTPException(409,'BLOCKED is controlled by the task blocked endpoint')
    with conn() as c:
        pid=task_project(c,tid)
        if not pid: raise HTTPException(404,'Task not found')
        cfg=project_workflow_config(c,pid)
        stage=next((x for x in cfg.get('stages',[]) if x.get('key')==target),None)
        if not stage: raise HTTPException(409,'Target workflow stage is not configured')
        current=c.execute('SELECT status FROM tasks WHERE id=?',(tid,)).fetchone()['status']
        if is_admin(a): pass
        elif current in ('REVIEW','DONE') or target in ('DONE',):
            require_project_access(c,pid,a,write=True)
        else:
            require_task_access(c,tid,a,assigned_only=True)
        scoped_key=f'workflow:{a["id"]}:{tid}:{idempotency_key}' if idempotency_key else None
        if scoped_key:
            prior=c.execute('SELECT id,payload FROM events WHERE idempotency_key=?',(scoped_key,)).fetchone()
            if prior:
                if prior['payload']!=json.dumps({'target_stage':target,'comment':comment}): raise HTTPException(409,'Idempotency-Key was already used with a different workflow transition')
                return {'task_id':tid,'target_stage':target,'event_id':prior['id'],'idempotent_replay':True}
        enforce_workflow_stage(c,pid,target,a['id'],tid)
        eid=transition_task_workflow(c,tid,target,a['id'],comment)
        if scoped_key:
            # The transition event itself is the idempotent record; attach a unique companion event only when needed.
            c.execute('UPDATE events SET idempotency_key=?,payload=? WHERE id=? AND idempotency_key IS NULL',(scoped_key,json.dumps({'target_stage':target,'comment':comment}),eid))
        return {'task_id':tid,'status':target,'event_id':eid}

@app.post('/api/v1/tasks/{tid}/artifacts')
def artifact(tid:str,b:ArtifactIn,authorization:str=Header(None)):
    a=actor(authorization); aid='art_'+uuid.uuid4().hex[:12]
    with conn() as c:
        require_task_access(c,tid,a,assigned_only=True)
        c.execute('INSERT INTO artifacts(id,task_id,artifact_type,uri,commit_sha,metadata,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',(aid,tid,b.artifact_type,b.uri,b.commit_sha,json.dumps(b.metadata),now(),c.execute('SELECT p.tenant_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE t.id=?',(tid,)).fetchone()['tenant_id'])); wp=c.execute('SELECT correlation_id,id FROM task_work_packages WHERE child_task_id=?',(tid,)).fetchone(); event(c,'artifact.submitted',a['id'],tid,{'artifact_id':aid,'uri':b.uri,'work_package_id':wp['id'] if wp else None,'correlation_id':wp['correlation_id'] if wp else None})
    return {'id':aid,'task_id':tid}
@app.post('/api/v1/tasks/{tid}/review')
def review_task(tid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization); decision=b.get('decision')
    if a.get('actor_type')=='AGENT': raise HTTPException(403,'Agent cannot review or approve tasks')
    if decision not in ('APPROVE','REJECT'): raise HTTPException(422,'decision must be APPROVE or REJECT')
    with conn() as c:
        begin_serialized_write(c)
        pid=task_project(c,tid)
        if not pid: raise HTTPException(404,'Task not found')
        if is_admin(a): pass
        else:
            row=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not row or row['role'] not in ('owner','manager','reviewer'): raise HTTPException(403,'Reviewer role required')
        task_sql='SELECT status FROM tasks WHERE id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): task_sql += ' FOR UPDATE'
        task=c.execute(task_sql,(tid,)).fetchone()
        if task['status']!='REVIEW': raise HTTPException(409,'Task is not awaiting review')
        if decision=='APPROVE':
            enforce_workflow_exit(c,pid,task['status'],a['id'])
            enforce_workflow_stage(c,pid,'DONE',a['id'],tid)
            packages=c.execute("SELECT w.child_task_id,t.status FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? AND w.status='ACTIVE'",(tid,)).fetchall()
            pending=[x['child_task_id'] for x in packages if x['status']!='DONE']
            missing=[x['child_task_id'] for x in packages if c.execute('SELECT 1 FROM artifacts WHERE task_id=? LIMIT 1',(x['child_task_id'],)).fetchone() is None]
            if pending or missing:
                raise HTTPException(409,detail={'message':'Parent task cannot be approved until every active work package is approved and has at least one artifact','pending_work_packages':pending,'missing_artifacts':missing})
        status='DONE' if decision=='APPROVE' else 'IN_PROGRESS'
        updated=c.execute('UPDATE tasks SET status=?,progress=?,updated_at=? WHERE id=? AND status=?',(status,100 if decision=='APPROVE' else 90,now(),tid,'REVIEW'))
        if updated.rowcount != 1: raise HTTPException(409,'Task is no longer awaiting review')
        eid=event(c,'task.reviewed',a['id'],tid,{'decision':decision,'comment':b.get('comment','')})
        return {'task_id':tid,'status':status,'event_id':eid}

@app.post('/api/v1/work-packages/{package_id}/review')
def review_work_package(package_id:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization)
    if a.get('actor_type')=='AGENT': raise HTTPException(403,'Agent cannot review or approve work packages')
    decision=str(b.get('decision','')).strip().upper()
    comment=str(b.get('comment',''))[:4000]
    if decision not in ('APPROVE','REJECT'): raise HTTPException(422,'decision must be APPROVE or REJECT')
    with conn() as c:
        begin_serialized_write(c)
        package_sql='SELECT w.*,t.status AS task_status,t.progress FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): package_sql += ' FOR UPDATE'
        package=c.execute(package_sql,(package_id,)).fetchone()
        if not package: raise HTTPException(404,'Work package not found')
        pid=package['project_id']
        if is_admin(a): pass
        else:
            row=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not row or row['role'] not in ('owner','manager','reviewer'): raise HTTPException(403,'Reviewer role required')
        if package['status']!='ACTIVE': raise HTTPException(409,'Work package is no longer active')
        if package['task_status']!='REVIEW': raise HTTPException(409,'Work package is not awaiting review')
        stamp=now()
        if decision=='APPROVE':
            enforce_workflow_exit(c,pid,package['task_status'],a['id'])
            enforce_workflow_stage(c,pid,'DONE',a['id'],package['child_task_id'])
            if c.execute('SELECT 1 FROM artifacts WHERE task_id=? LIMIT 1',(package['child_task_id'],)).fetchone() is None:
                raise HTTPException(409,'Work package must have at least one artifact before approval')
            status='DONE'; progress=100
        else:
            status='IN_PROGRESS'; progress=90
        updated=c.execute('UPDATE tasks SET status=?,progress=?,updated_at=? WHERE id=? AND status=?',(status,progress,stamp,package['child_task_id'],'REVIEW'))
        if updated.rowcount != 1: raise HTTPException(409,'Work package task is no longer awaiting review')
        eid=event(c,'task.work_package.reviewed',a['id'],package['child_task_id'],{'work_package_id':package_id,'parent_task_id':package['parent_task_id'],'decision':decision,'comment':comment})
        return {'work_package_id':package_id,'task_id':package['child_task_id'],'status':status,'progress':progress,'event_id':eid,'decision':decision}

@app.post('/api/v1/tasks/{parent_id}/work-packages')
def create_work_package(parent_id:str,b:WorkPackageIn,authorization:str=Header(None)):
    a=actor(authorization); child_id='tsk_'+uuid.uuid4().hex[:12]; package_id='wpk_'+uuid.uuid4().hex
    agent_name=b.agent_name.strip()
    if not agent_name: raise HTTPException(422,'agent_name must not be blank')
    with conn() as c:
        require_task_access(c,parent_id,a)
        project_id=task_project(c,parent_id)
        require_project_access(c,project_id,a,write=True)
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(project_id,)).fetchone()
        member=c.execute('SELECT tenant_id FROM members WHERE id=?',(b.assignee_member_id,)).fetchone()
        if not member or member['tenant_id']!=project['tenant_id']: raise HTTPException(404,'Assignee not found in this tenant')
        if not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(project_id,b.assignee_member_id)).fetchone(): raise HTTPException(400,'Assignee is not a project member')
        agent=c.execute('SELECT status,last_seen FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(project_id,b.assignee_member_id,agent_name)).fetchone()
        if not agent: raise HTTPException(404,'Assignee Agent is not registered in this project')
        if agent['status']=='OFFLINE' or agent['last_seen'] < datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat(): raise HTTPException(409,'Assignee Agent presence is offline or stale')
        for dep in b.dependencies:
            if dep==parent_id or not c.execute('SELECT 1 FROM tasks WHERE id=?',(dep,)).fetchone(): raise HTTPException(400,'Invalid dependency')
            require_task_access(c,dep,a)
            if task_project(c,dep)!=project_id: raise HTTPException(400,'Dependencies must belong to the same project')
        req=c.execute('SELECT r.id FROM tasks t JOIN requirements r ON r.id=t.requirement_id WHERE t.id=?',(parent_id,)).fetchone()
        if not req: raise HTTPException(409,'Create a requirement before adding work packages')
        stamp=now()
        c.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?)',(child_id,req['id'],b.title,b.description,'READY',0,stamp,stamp))
        c.execute('INSERT INTO assignments(task_id,member_id) VALUES(?,?)',(child_id,b.assignee_member_id))
        for dep in b.dependencies: c.execute('INSERT INTO dependencies(task_id,depends_on_task_id) VALUES(?,?)',(child_id,dep))
        correlation_id='corr_'+uuid.uuid4().hex
        sla_due_at=datetime.fromtimestamp(datetime.fromisoformat(stamp).timestamp()+b.sla_seconds,timezone.utc).isoformat() if b.sla_seconds else None
        c.execute('INSERT INTO task_work_packages(id,parent_task_id,child_task_id,project_id,tenant_id,assignee_member_id,agent_name,status,created_at,updated_at,correlation_id,sla_due_at,risk_state) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(package_id,parent_id,child_id,project_id,project['tenant_id'],b.assignee_member_id,agent_name,'ACTIVE',stamp,stamp,correlation_id,sla_due_at,'ON_TRACK'))
        mid='msg_'+uuid.uuid4().hex[:12]
        title='Work package assigned: '+b.title
        content=json.dumps({'work_package_id':package_id,'correlation_id':correlation_id,'parent_task_id':parent_id,'task_id':child_id,'agent_name':agent_name,'title':b.title,'sla_due_at':sla_due_at},ensure_ascii=False)
        c.execute('INSERT INTO messages(id,recipient_member_id,tenant_id,task_id,message_type,title,content,priority,status,created_at,acked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(mid,b.assignee_member_id,project['tenant_id'],child_id,'WORK_PACKAGE_ASSIGNED',title,content,'HIGH','PENDING',stamp,None))
        payload={'message_id':mid,'recipient_member_id':b.assignee_member_id,'project_id':project_id,'task_id':child_id,'message_type':'WORK_PACKAGE_ASSIGNED','title':title,'content':content,'priority':'HIGH'}
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',('obx_'+uuid.uuid4().hex,'message.created',json.dumps(payload),'PENDING',0,stamp,stamp,project['tenant_id']))
        event(c,'task.work_package.created',a['id'],parent_id,{'work_package_id':package_id,'correlation_id':correlation_id,'child_task_id':child_id,'assignee_member_id':b.assignee_member_id,'agent_name':agent_name,'sla_due_at':sla_due_at,'sla_seconds':b.sla_seconds})
    return {'id':package_id,'correlation_id':correlation_id,'parent_task_id':parent_id,'task_id':child_id,'assignee_member_id':b.assignee_member_id,'agent_name':agent_name,'status':'ACTIVE','sla_due_at':sla_due_at,'risk_state':'ON_TRACK','message_id':mid}

@app.get('/api/v1/tasks/{parent_id}/work-packages')
def list_work_packages(parent_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,parent_id,a)
        rows=c.execute('SELECT w.*,t.title,t.description,t.status AS task_status,t.progress,t.updated_at AS task_updated_at FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? ORDER BY w.created_at',(parent_id,)).fetchall()
        result=[]
        for raw in rows:
            row=dict(raw)
            row['artifacts']=[dict(x) for x in c.execute('SELECT id,artifact_type,uri,commit_sha,created_at FROM artifacts WHERE task_id=? ORDER BY created_at',(row['child_task_id'],))]
            result.append(row)
        return result

@app.get('/api/v1/tasks/{parent_id}/work-summary')
def work_package_summary(parent_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,parent_id,a)
        rows=c.execute("SELECT t.status,t.progress FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? AND w.status='ACTIVE'",(parent_id,)).fetchall()
        total=len(rows)
        counts={k:sum(1 for x in rows if x['status']==k) for k in ('READY','IN_PROGRESS','BLOCKED','REVIEW','DONE')}
        progress=round(sum(int(x['progress'] or 0) for x in rows)/total) if total else 0
        artifacts=c.execute('SELECT COUNT(*) AS n FROM artifacts a JOIN task_work_packages w ON w.child_task_id=a.task_id WHERE w.parent_task_id=? AND w.status=\'ACTIVE\'',(parent_id,)).fetchone()['n']
        blocked=c.execute("SELECT t.id,t.title,t.status FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? AND w.status='ACTIVE' AND t.status='BLOCKED'",(parent_id,)).fetchall()
        artifact_rows=c.execute('SELECT w.child_task_id,a.id,a.artifact_type,a.uri,a.commit_sha,a.created_at FROM task_work_packages w JOIN artifacts a ON a.task_id=w.child_task_id WHERE w.parent_task_id=? AND w.status=\'ACTIVE\' ORDER BY a.created_at',(parent_id,)).fetchall()
        return {'parent_task_id':parent_id,'work_package_count':total,'progress':progress,'status_counts':counts,'blocked_tasks':[dict(x) for x in blocked],'artifact_count':artifacts,'artifacts':[dict(x) for x in artifact_rows],'all_done':bool(total and counts['DONE']==total)}

@app.get('/api/v1/tasks/{parent_id}/work-timeline')
def work_package_timeline(parent_id:str,limit:int=200,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,500))
    with conn() as c:
        require_task_access(c,parent_id,a)
        packages=c.execute('SELECT w.*,t.title,t.status AS task_status,t.progress FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? ORDER BY w.created_at',(parent_id,)).fetchall()
        items=[]
        task_ids=[parent_id]+[w['child_task_id'] for w in packages]
        for e in c.execute("""SELECT e.*,m.name AS actor_name FROM events e
            LEFT JOIN members m ON m.id=e.actor_member_id WHERE e.task_id=? ORDER BY e.created_at""",(parent_id,)).fetchall():
            p=json.loads(e['payload'] or '{}')
            items.append({'occurred_at':e['created_at'],'kind':'event','event_type':e['event_type'],
                'task_id':parent_id,'event_id':e['id'],'actor_member_id':e['actor_member_id'],
                'actor_name':e['actor_name'],'payload':p})
        for w in packages:
            cid=w['correlation_id'] or w['id']; child=w['child_task_id']
            for e in c.execute("""SELECT e.*,m.name AS actor_name FROM events e
                LEFT JOIN members m ON m.id=e.actor_member_id WHERE e.task_id=? ORDER BY e.created_at""",(child,)).fetchall():
                p=json.loads(e['payload'] or '{}')
                items.append({'occurred_at':e['created_at'],'kind':'event','event_type':e['event_type'],
                    'task_id':child,'event_id':e['id'],'actor_member_id':e['actor_member_id'],
                    'actor_name':e['actor_name'],'correlation_id':cid,'payload':p})
            for msg in c.execute('SELECT id,message_type,title,status,created_at,acked_at,content FROM messages WHERE task_id=? ORDER BY created_at',(child,)).fetchall():
                try: body=json.loads(msg['content'] or '{}')
                except Exception: body={'content':msg['content']}
                items.append({'occurred_at':msg['created_at'],'kind':'message','message_id':msg['id'],
                    'message_type':msg['message_type'],'title':msg['title'],'status':msg['status'],
                    'acked_at':msg['acked_at'],'task_id':child,'correlation_id':body.get('correlation_id',cid),'payload':body})
            for art in c.execute('SELECT id,artifact_type,uri,commit_sha,created_at FROM artifacts WHERE task_id=? ORDER BY created_at',(child,)).fetchall():
                items.append({'occurred_at':art['created_at'],'kind':'artifact','task_id':child,'correlation_id':cid,'artifact':dict(art)})
        marks=','.join('?' for _ in task_ids)
        delegations=c.execute(f"""SELECT d.*,rq.name AS requester_name,rc.name AS recipient_name
            FROM task_delegations d JOIN members rq ON rq.id=d.requester_member_id
            JOIN members rc ON rc.id=d.recipient_member_id
            WHERE d.task_id IN ({marks}) ORDER BY d.created_at""",tuple(task_ids)).fetchall()
        for d in delegations:
            row=dict(d)
            items.append({'occurred_at':row['created_at'],'kind':'delegation','stage':'OFFERED',
                'task_id':row['task_id'],'delegation_id':row['id'],'status':row['status'],
                'requester_member_id':row['requester_member_id'],'requester_name':row['requester_name'],
                'recipient_member_id':row['recipient_member_id'],'recipient_name':row['recipient_name'],
                'agent_name':row['agent_name'],'reason':row['reason'],'expires_at':row['expires_at']})
            if row['status']!='PENDING':
                decision_at=row['responded_at'] or row['updated_at']
                items.append({'occurred_at':decision_at,'kind':'delegation','stage':row['status'],
                    'task_id':row['task_id'],'delegation_id':row['id'],'status':row['status'],
                    'requester_member_id':row['requester_member_id'],'requester_name':row['requester_name'],
                    'recipient_member_id':row['recipient_member_id'],'recipient_name':row['recipient_name'],
                    'agent_name':row['agent_name'],'reason':row['reason'],'expires_at':row['expires_at']})
        dependency_edges=[]
        for tid in task_ids:
            task=c.execute('SELECT title FROM tasks WHERE id=?',(tid,)).fetchone()
            for dep in c.execute("""SELECT d.depends_on_task_id,t.title AS depends_on_title,t.status AS depends_on_status
                FROM dependencies d JOIN tasks t ON t.id=d.depends_on_task_id WHERE d.task_id=?""",(tid,)).fetchall():
                dependency_edges.append({'task_id':tid,'task_title':task['title'] if task else tid,
                    'depends_on_task_id':dep['depends_on_task_id'],'depends_on_title':dep['depends_on_title'],
                    'depends_on_status':dep['depends_on_status'],'blocked':dep['depends_on_status']!='DONE'})
        items.sort(key=lambda x:(x['occurred_at'],x.get('event_id') or x.get('message_id') or x.get('delegation_id') or x.get('artifact',{}).get('id','')))
        items=items[-limit:]
        return {'parent_task_id':parent_id,'count':len(items),'items':items,
            'dependency_edges':dependency_edges,
            'delegations':[{'id':d['id'],'task_id':d['task_id'],'requester_member_id':d['requester_member_id'],
                'requester_name':d['requester_name'],'recipient_member_id':d['recipient_member_id'],
                'recipient_name':d['recipient_name'],'agent_name':d['agent_name'],'reason':d['reason'],
                'status':d['status'],'created_at':d['created_at'],'responded_at':d['responded_at'],
                'expires_at':d['expires_at']} for d in delegations],
            'work_packages':[{'id':w['id'],'correlation_id':w['correlation_id'] or w['id'],
                'child_task_id':w['child_task_id'],'title':w['title'],'status':w['task_status'],
                'progress':w['progress'],'assignee_member_id':w['assignee_member_id'],'agent_name':w['agent_name'],
                'sla_due_at':w['sla_due_at'],'risk_state':w['risk_state'],'needs_attention':bool(w['needs_attention'])}
                for w in packages]}
@app.post('/api/v1/projects/{pid}/work-packages/scan-health')
def scan_project_work_health(pid:str,authorization:str=Header(None)):
    a=actor(authorization); stamp=now()
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        rows=c.execute("""SELECT w.id,w.parent_task_id,w.child_task_id,w.correlation_id,w.sla_due_at,w.risk_state,w.needs_attention,
        t.title,t.status AS task_status FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id
        WHERE w.project_id=? AND w.status='ACTIVE' ORDER BY w.created_at""",(pid,)).fetchall()
        changed=[]; counts={'ON_TRACK':0,'OVERDUE':0,'BLOCKED_DEPENDENCY':0,'STALLED':0,'IN_REVIEW':0,'COMPLETED':0}
        for row in rows:
            blockers=c.execute("""SELECT d.depends_on_task_id,t.title,t.status FROM dependencies d
                JOIN tasks t ON t.id=d.depends_on_task_id WHERE d.task_id=? AND t.status!='DONE'""",(row['child_task_id'],)).fetchall()
            if row['task_status']=='DONE': risk='COMPLETED'
            elif row['task_status']=='REVIEW': risk='IN_REVIEW'
            elif blockers: risk='BLOCKED_DEPENDENCY'
            elif row['needs_attention']: risk='STALLED'
            elif row['sla_due_at'] and row['sla_due_at']<=stamp: risk='OVERDUE'
            else: risk='ON_TRACK'
            if risk!=row['risk_state']:
                c.execute('UPDATE task_work_packages SET risk_state=?,updated_at=? WHERE id=?',(risk,stamp,row['id']))
                detail={'work_package_id':row['id'],'correlation_id':row['correlation_id'],'child_task_id':row['child_task_id'],'previous_risk_state':row['risk_state'],'risk_state':risk,'sla_due_at':row['sla_due_at'],'blocking_dependencies':[dict(x) for x in blockers]}
                event(c,'task.work_package.risk_changed',a['id'],row['parent_task_id'],detail)
                changed.append(detail)
            counts[risk]=counts.get(risk,0)+1
        return {'project_id':pid,'scanned_count':len(rows),'changed_count':len(changed),'risk_counts':counts,'changes':changed}

@app.get('/api/v1/projects/{pid}/work-health')
def project_work_health(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT w.id,w.parent_task_id,w.child_task_id,w.correlation_id,w.assignee_member_id,w.agent_name,
            w.sla_due_at,w.risk_state,w.needs_attention,t.title,t.status AS task_status,t.progress,t.updated_at
            FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id
            WHERE w.project_id=? AND w.status='ACTIVE' ORDER BY w.created_at""",(pid,)).fetchall()
        counts={}
        items=[]
        for row in rows:
            risk=row['risk_state']; counts[risk]=counts.get(risk,0)+1
            blockers=c.execute("""SELECT d.depends_on_task_id,t.title,t.status FROM dependencies d
                JOIN tasks t ON t.id=d.depends_on_task_id WHERE d.task_id=? AND t.status!='DONE'""",(row['child_task_id'],)).fetchall()
            items.append({'work_package_id':row['id'],'parent_task_id':row['parent_task_id'],'child_task_id':row['child_task_id'],
                'correlation_id':row['correlation_id'],'title':row['title'],'task_status':row['task_status'],'progress':row['progress'],
                'assignee_member_id':row['assignee_member_id'],'agent_name':row['agent_name'],'sla_due_at':row['sla_due_at'],
                'risk_state':risk,'needs_attention':bool(row['needs_attention']),'blocking_dependencies':[dict(x) for x in blockers],
                'last_activity_at':row['updated_at']})
        total=len(items); at_risk=sum(counts.get(k,0) for k in ('OVERDUE','BLOCKED_DEPENDENCY','STALLED'))
        return {'project_id':pid,'work_package_count':total,'at_risk_count':at_risk,
            'health_score':round(100*(total-at_risk)/total) if total else 100,
            'risk_counts':counts,'items':items}

@app.get('/api/v1/projects/{pid}/coordination')
def project_coordination_center(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        packages=c.execute("""SELECT w.id AS work_package_id,w.parent_task_id,w.child_task_id,w.assignee_member_id,w.agent_name,
            w.sla_due_at,w.risk_state,w.needs_attention,w.stall_reason,w.stalled_at,t.title,t.status AS task_status,
            t.progress,t.updated_at,m.name AS assignee_name
            FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id
            LEFT JOIN members m ON m.id=w.assignee_member_id
            WHERE w.project_id=? AND w.status='ACTIVE'
            AND (w.needs_attention=1 OR w.risk_state IN ('OVERDUE','BLOCKED_DEPENDENCY','STALLED','IN_REVIEW'))
            ORDER BY CASE w.risk_state WHEN 'OVERDUE' THEN 0 WHEN 'STALLED' THEN 1 WHEN 'BLOCKED_DEPENDENCY' THEN 2 WHEN 'IN_REVIEW' THEN 3 ELSE 4 END,w.updated_at""",(pid,)).fetchall()
        package_items=[]
        for row in packages:
            blockers=c.execute("""SELECT d.depends_on_task_id,t.title,t.status FROM dependencies d
                JOIN tasks t ON t.id=d.depends_on_task_id WHERE d.task_id=? AND t.status!='DONE'""",(row['child_task_id'],)).fetchall()
            agent=c.execute('SELECT status,last_seen FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(pid,row['assignee_member_id'],row['agent_name'])).fetchone()
            package_items.append({**dict(row),'blocking_dependencies':[dict(x) for x in blockers],
                'agent_status':agent['status'] if agent else 'NOT_REGISTERED','agent_last_seen':agent['last_seen'] if agent else None})
        unclaimed=c.execute("""SELECT t.id AS task_id,t.title,t.status,t.progress,t.updated_at
            FROM tasks t JOIN requirements r ON r.id=t.requirement_id
            LEFT JOIN assignments a ON a.task_id=t.id
            WHERE r.project_id=? AND t.status!='DONE' AND a.task_id IS NULL
            AND NOT EXISTS (SELECT 1 FROM task_work_packages w WHERE w.child_task_id=t.id AND w.status='ACTIVE')
            ORDER BY t.updated_at""",(pid,)).fetchall()
        reviews=c.execute("""SELECT t.id AS task_id,t.title,t.progress,t.updated_at,
            (SELECT COUNT(*) FROM artifacts ar WHERE ar.task_id=t.id) AS artifact_count
            FROM tasks t JOIN requirements r ON r.id=t.requirement_id
            WHERE r.project_id=? AND t.status='REVIEW' ORDER BY t.updated_at""",(pid,)).fetchall()
        delegations=c.execute("""SELECT d.id,d.task_id,d.status,d.requester_member_id,d.recipient_member_id,
            d.agent_name,d.reason,d.created_at,d.expires_at,t.title AS task_title,
            rq.name AS requester_name,rc.name AS recipient_name
            FROM task_delegations d JOIN tasks t ON t.id=d.task_id
            JOIN members rq ON rq.id=d.requester_member_id JOIN members rc ON rc.id=d.recipient_member_id
            WHERE d.project_id=? AND d.status='PENDING' ORDER BY d.created_at""",(pid,)).fetchall()
        return {'project_id':pid,'exception_work_packages':[dict(x) for x in package_items],
            'unclaimed_tasks':[dict(x) for x in unclaimed],'pending_reviews':[dict(x) for x in reviews],
            'pending_delegations':[dict(x) for x in delegations],
            'counts':{'exception_work_packages':len(package_items),'unclaimed_tasks':len(unclaimed),
                'pending_reviews':len(reviews),'pending_delegations':len(delegations)}}

@app.post('/api/v1/projects/{pid}/work-packages/scan-stalled')
def scan_stalled_work_packages(pid:str,b:WorkPackageScanIn,authorization:str=Header(None)):
    a=actor(authorization)
    cutoff=datetime.fromtimestamp(time.time()-b.stale_after_seconds,timezone.utc).isoformat()
    stamp=now()
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        rows=c.execute("""SELECT w.id,w.parent_task_id,w.child_task_id,w.assignee_member_id,t.status,t.updated_at,t.title
        FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id
        WHERE w.project_id=? AND w.status='ACTIVE' AND w.needs_attention=0
        AND t.status IN ('READY','IN_PROGRESS','BLOCKED') AND t.updated_at<=?""",(pid,cutoff)).fetchall()
        marked=[]
        for row in rows:
            reason=f"No task activity for at least {b.stale_after_seconds} seconds"
            changed=c.execute('UPDATE task_work_packages SET needs_attention=1,stalled_at=?,stall_reason=?,updated_at=? WHERE id=? AND needs_attention=0',(stamp,reason,stamp,row['id']))
            if changed.rowcount:
                event(c,'task.work_package.stalled',a['id'],row['parent_task_id'],{'work_package_id':row['id'],'correlation_id':c.execute('SELECT correlation_id FROM task_work_packages WHERE id=?',(row['id'],)).fetchone()['correlation_id'],'child_task_id':row['child_task_id'],'assignee_member_id':row['assignee_member_id'],'stalled_at':stamp,'reason':reason})
                marked.append({'work_package_id':row['id'],'child_task_id':row['child_task_id'],'title':row['title'],'task_status':row['status'],'assignee_member_id':row['assignee_member_id'],'stalled_at':stamp,'reason':reason})
    return {'project_id':pid,'stale_after_seconds':b.stale_after_seconds,'marked_count':len(marked),'items':marked}

@app.post('/api/v1/work-packages/{package_id}/reassign')
def reassign_work_package(package_id:str,b:WorkPackageReassignIn,authorization:str=Header(None)):
    a=actor(authorization); agent_name=b.agent_name.strip()
    if not agent_name: raise HTTPException(422,'agent_name must not be blank')
    with conn() as c:
        begin_serialized_write(c)
        package_sql='SELECT * FROM task_work_packages WHERE id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): package_sql += ' FOR UPDATE'
        package=c.execute(package_sql,(package_id,)).fetchone()
        if not package: raise HTTPException(404,'Work package not found')
        require_project_access(c,package['project_id'],a,write=True)
        if package['status']!='ACTIVE': raise HTTPException(409,'Only active work packages can be reassigned')
        if not package['needs_attention']: raise HTTPException(409,'Work package must be marked stalled before reassignment')
        if package['assignee_member_id']==b.assignee_member_id and package['agent_name']==agent_name:
            raise HTTPException(400,'Choose a different assignee or Agent')
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(package['project_id'],)).fetchone()
        member=c.execute('SELECT tenant_id FROM members WHERE id=?',(b.assignee_member_id,)).fetchone()
        if not member or member['tenant_id']!=project['tenant_id']: raise HTTPException(404,'New assignee not found in this tenant')
        if not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(package['project_id'],b.assignee_member_id)).fetchone():
            raise HTTPException(400,'New assignee is not a project member')
        agent=c.execute('SELECT status,last_seen FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(package['project_id'],b.assignee_member_id,agent_name)).fetchone()
        cutoff=datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat()
        if not agent: raise HTTPException(404,'New assignee Agent is not registered in this project')
        if agent['status']=='OFFLINE' or agent['last_seen']<cutoff: raise HTTPException(409,'New assignee Agent presence is offline or stale')
        stamp=now()
        c.execute('DELETE FROM assignments WHERE task_id=? AND member_id=?',(package['child_task_id'],package['assignee_member_id']))
        c.execute('INSERT OR IGNORE INTO assignments(task_id,member_id) VALUES(?,?)',(package['child_task_id'],b.assignee_member_id))
        c.execute('UPDATE task_work_packages SET assignee_member_id=?,agent_name=?,needs_attention=0,stalled_at=NULL,stall_reason=NULL,updated_at=? WHERE id=?',(b.assignee_member_id,agent_name,stamp,package_id))
        c.execute('UPDATE tasks SET updated_at=? WHERE id=?',(stamp,package['child_task_id']))
        mid='msg_'+uuid.uuid4().hex[:12]
        title='Work package reassigned: '+package['child_task_id']
        content=json.dumps({'work_package_id':package_id,'correlation_id':package['correlation_id'],'parent_task_id':package['parent_task_id'],'task_id':package['child_task_id'],'previous_assignee_member_id':package['assignee_member_id'],'assignee_member_id':b.assignee_member_id,'agent_name':agent_name,'reason':b.reason},ensure_ascii=False)
        c.execute('INSERT INTO messages(id,recipient_member_id,tenant_id,task_id,message_type,title,content,priority,status,created_at,acked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(mid,b.assignee_member_id,project['tenant_id'],package['child_task_id'],'WORK_PACKAGE_REASSIGNED',title,content,'HIGH','PENDING',stamp,None))
        payload={'message_id':mid,'recipient_member_id':b.assignee_member_id,'project_id':package['project_id'],'task_id':package['child_task_id'],'message_type':'WORK_PACKAGE_REASSIGNED','title':title,'content':content,'priority':'HIGH'}
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',('obx_'+uuid.uuid4().hex,'message.created',json.dumps(payload),'PENDING',0,stamp,stamp,project['tenant_id']))
        eid=event(c,'task.work_package.reassigned',a['id'],package['parent_task_id'],{'work_package_id':package_id,'correlation_id':package['correlation_id'],'child_task_id':package['child_task_id'],'previous_assignee_member_id':package['assignee_member_id'],'assignee_member_id':b.assignee_member_id,'previous_agent_name':package['agent_name'],'agent_name':agent_name,'reason':b.reason})
    return {'work_package_id':package_id,'task_id':package['child_task_id'],'assignee_member_id':b.assignee_member_id,'agent_name':agent_name,'needs_attention':False,'message_id':mid,'event_id':eid}

@app.post('/api/v1/projects/{pid}/agents/register')
def register_project_agent(pid:str,b:AgentPresenceIn,authorization:str=Header(None)):
    a=actor(authorization)
    agent_name=b.agent_name.strip()
    if not agent_name: raise HTTPException(422,'agent_name must not be blank')
    clean_caps=sorted({str(x).strip().lower() for x in b.capabilities if str(x).strip()})
    clean_protocols=sorted({str(x).strip().lower() for x in b.protocols if str(x).strip()})
    if any(len(x)>80 for x in clean_caps) or any(len(x)>40 for x in clean_protocols):
        raise HTTPException(422,'Capability or protocol identifier is too long')
    if not clean_protocols: raise HTTPException(422,'At least one protocol is required')
    if len(json.dumps(b.metadata))>4000: raise HTTPException(422,'Agent metadata exceeds 4000 bytes')
    with conn() as c:
        require_project_access(c,pid,a)
        tenant=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id']
        existing=c.execute('SELECT id,created_at FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(pid,a['id'],agent_name)).fetchone()
        aid=existing['id'] if existing else 'agt_'+uuid.uuid4().hex
        created=existing['created_at'] if existing else now()
        stamp=now()
        c.execute("""INSERT INTO project_agents(id,project_id,member_id,tenant_id,agent_name,capabilities,protocols,status,metadata,last_seen,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(project_id,member_id,agent_name) DO UPDATE SET capabilities=excluded.capabilities,protocols=excluded.protocols,status=excluded.status,metadata=excluded.metadata,last_seen=excluded.last_seen,updated_at=excluded.updated_at""",
        (aid,pid,a['id'],tenant,agent_name,json.dumps(clean_caps),json.dumps(clean_protocols),b.status,json.dumps(b.metadata),stamp,created,stamp))
        event(c,'agent.presence.updated',a['id'],None,{'project_id':pid,'agent_id':aid,'agent_name':agent_name,'status':b.status},tenant_override=tenant)
    return {'id':aid,'project_id':pid,'member_id':a['id'],'agent_name':b.agent_name.strip(),'status':b.status,'capabilities':clean_caps,'protocols':clean_protocols,'last_seen':stamp}

@app.post('/api/v1/projects/{pid}/agents/heartbeat')
def heartbeat_project_agent(pid:str,body:dict,authorization:str=Header(None)):
    a=actor(authorization); name=str(body.get('agent_name','')).strip()
    if not name or len(name)>120: raise HTTPException(422,'agent_name is required (max 120)')
    status=str(body.get('status','AVAILABLE')).upper()
    if status not in ('AVAILABLE','BUSY','OFFLINE'): raise HTTPException(422,'Invalid agent status')
    with conn() as c:
        require_project_access(c,pid,a)
        previous=c.execute('SELECT id,status FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?',(pid,a['id'],name)).fetchone()
        if not previous: raise HTTPException(404,'Agent registration not found; register the agent first')
        stamp=now()
        c.execute('UPDATE project_agents SET status=?,last_seen=?,updated_at=? WHERE id=?',(status,stamp,stamp,previous['id']))
        if previous['status'] != status:
            event(c,'agent.presence.changed',a['id'],None,{'project_id':pid,'agent_id':previous['id'],'status':status})
    return {'id':previous['id'],'status':status,'last_seen':stamp}

@app.get('/api/v1/projects/{pid}/agents')
def discover_project_agents(pid:str,authorization:str=Header(None),capability:str='',protocol:str=''):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("SELECT pa.*,m.name AS member_name FROM project_agents pa JOIN members m ON m.id=pa.member_id WHERE pa.project_id=? ORDER BY pa.agent_name,pa.member_id",(pid,)).fetchall()
        cutoff=datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat()
        items=[]
        for raw in rows:
            row=dict(raw)
            caps=json.loads(row['capabilities'] or '[]'); protocols=json.loads(row['protocols'] or '[]')
            live=row['status']!='OFFLINE' and row['last_seen']>=cutoff
            if capability and capability.lower() not in caps: continue
            if protocol and protocol.lower() not in protocols: continue
            items.append({'id':row['id'],'member_id':row['member_id'],'member_name':row['member_name'],'agent_name':row['agent_name'],'capabilities':caps,'protocols':protocols,'status':row['status'] if live else 'OFFLINE','last_seen':row['last_seen'],'metadata':json.loads(row['metadata'] or '{}')})
        return {'items':items,'count':len(items),'presence_ttl_seconds':120}

@app.get('/api/v1/projects/{pid}/agent-matches')
def recommend_project_agents(pid:str,required_capabilities:str='',protocol:str='mcp',authorization:str=Header(None)):
    """Rank project-local Agent registrations without assigning work or invoking a Runtime."""
    a=actor(authorization)
    requested=[x.strip().casefold() for x in required_capabilities.split(',') if x.strip()]
    if len(requested)>50 or any(len(x)>120 for x in requested):
        raise HTTPException(422,'At most 50 required capabilities are allowed; each must be at most 120 characters')
    requested=list(dict.fromkeys(requested))
    requested_protocol=protocol.strip().casefold()
    if not requested_protocol or len(requested_protocol)>40:
        raise HTTPException(422,'protocol must contain 1 to 40 characters')
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT pa.*,m.name AS member_name FROM project_agents pa
            JOIN members m ON m.id=pa.member_id WHERE pa.project_id=?""",(pid,)).fetchall()
        cutoff=datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat()
        items=[]
        for raw in rows:
            row=dict(raw)
            caps=sorted({str(x).strip().casefold() for x in json.loads(row['capabilities'] or '[]') if str(x).strip()})
            protocols=sorted({str(x).strip().casefold() for x in json.loads(row['protocols'] or '[]') if str(x).strip()})
            matched=[x for x in requested if x in caps]
            missing=[x for x in requested if x not in caps]
            live=row['status']!='OFFLINE' and row['last_seen']>=cutoff
            protocol_match=requested_protocol in protocols
            available=live and row['status']=='AVAILABLE'
            items.append({'id':row['id'],'member_id':row['member_id'],'member_name':row['member_name'],
                'agent_name':row['agent_name'],'capabilities':caps,'protocols':protocols,
                'presence_status':row['status'] if live else 'OFFLINE','last_seen':row['last_seen'],
                'matched_capabilities':matched,'missing_capabilities':missing,
                'match_count':len(matched),'required_count':len(requested),
                'protocol_match':protocol_match,'eligible':not missing and protocol_match and available,
                'availability_reason':('AVAILABLE' if available else ('BUSY' if live and row['status']=='BUSY' else 'OFFLINE_OR_STALE')),
                'match_score':round(100*len(matched)/len(requested)) if requested else (100 if protocol_match else 0)})
        items.sort(key=lambda x:(not x['eligible'],bool(x['missing_capabilities']),not x['protocol_match'],
            -x['match_count'],x['availability_reason']!='AVAILABLE',x['member_name'].casefold(),x['agent_name'].casefold()))
        return {'project_id':pid,'required_capabilities':requested,'protocol':requested_protocol,
            'items':items,'count':len(items),'eligible_count':sum(1 for x in items if x['eligible']),
            'recommendation_only':True,'runtime_controlled':False}

@app.post('/api/v1/tasks/{tid}/delegations')
def create_task_delegation(tid:str,b:DelegationIn,authorization:str=Header(None)):
    a=actor(authorization)
    if b.recipient_member_id == a['id']: raise HTTPException(400,'A task cannot be delegated to yourself')
    agent_name=b.agent_name.strip()
    if not agent_name: raise HTTPException(422,'agent_name must not be blank')
    did='dlg_'+uuid.uuid4().hex
    with conn() as c:
        require_task_access(c,tid,a,assigned_only=True)
        pid=task_project(c,tid)
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        recipient=c.execute('SELECT tenant_id FROM members WHERE id=?',(b.recipient_member_id,)).fetchone()
        if not recipient or recipient['tenant_id'] != project['tenant_id']: raise HTTPException(404,'Recipient not found in this tenant')
        if not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(pid,b.recipient_member_id)).fetchone(): raise HTTPException(400,'Recipient is not a project member')
        agent=c.execute("SELECT id,status,last_seen FROM project_agents WHERE project_id=? AND member_id=? AND agent_name=?",(pid,b.recipient_member_id,agent_name)).fetchone()
        if not agent: raise HTTPException(404,'Recipient Agent is not registered in this project')
        if agent['status']=='OFFLINE' or agent['last_seen'] < datetime.fromtimestamp(time.time()-120,timezone.utc).isoformat():
            raise HTTPException(409,'Recipient Agent presence is offline or stale')
        stamp=now(); expiry=datetime.fromtimestamp(time.time()+b.expires_in_seconds,timezone.utc).isoformat()
        mid='msg_'+uuid.uuid4().hex[:12]
        title='Task delegation offer: '+tid
        content=json.dumps({'delegation_id':did,'task_id':tid,'agent_name':agent_name,'reason':b.reason,'expires_at':expiry},ensure_ascii=False)
        c.execute("INSERT INTO task_delegations(id,task_id,project_id,tenant_id,requester_member_id,recipient_member_id,agent_name,reason,status,message_id,expires_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(did,tid,pid,project['tenant_id'],a['id'],b.recipient_member_id,agent_name,b.reason,'PENDING',mid,expiry,stamp,stamp))
        c.execute("INSERT INTO messages(id,recipient_member_id,tenant_id,task_id,message_type,title,content,priority,status,created_at,acked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(mid,b.recipient_member_id,project['tenant_id'],tid,'TASK_DELEGATION',title,content,'HIGH','PENDING',stamp,None))
        payload={'message_id':mid,'recipient_member_id':b.recipient_member_id,'project_id':pid,'task_id':tid,'message_type':'TASK_DELEGATION','title':title,'content':content,'priority':'HIGH'}
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',('obx_'+uuid.uuid4().hex,'message.created',json.dumps(payload), 'PENDING',0,stamp,stamp,project['tenant_id']))
        event(c,'task.delegation.offered',a['id'],tid,{'delegation_id':did,'recipient_member_id':b.recipient_member_id,'agent_name':agent_name})
    return {'id':did,'task_id':tid,'recipient_member_id':b.recipient_member_id,'agent_name':agent_name,'status':'PENDING','expires_at':expiry,'message_id':mid}

@app.post('/api/v1/delegations/{did}/respond')
def respond_task_delegation(did:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization); decision=b.get('decision')
    if decision not in ('ACCEPT','REJECT'): raise HTTPException(422,'decision must be ACCEPT or REJECT')
    with conn() as c:
        begin_serialized_write(c)
        if DATABASE_URL.startswith(('postgresql://','postgres://')):
            row=c.execute('SELECT * FROM task_delegations WHERE id=? FOR UPDATE',(did,)).fetchone()
        else:
            row=c.execute('SELECT * FROM task_delegations WHERE id=?',(did,)).fetchone()
        if not row or row['recipient_member_id'] != a['id']: raise HTTPException(404,'Delegation not found')
        if row['status'] != 'PENDING': raise HTTPException(409,'Delegation is no longer pending')
        if row['expires_at'] <= now():
            stamp=now()
            cur=c.execute("UPDATE task_delegations SET status='EXPIRED',updated_at=? WHERE id=? AND status='PENDING'",(stamp,did))
            if cur.rowcount:
                event(c,'task.delegation.expired',a['id'],row['task_id'],{'delegation_id':did})
            return JSONResponse(status_code=410,content={'detail':'Delegation offer has expired','status':'EXPIRED'})
        if decision=='ACCEPT':
            c.execute('INSERT OR IGNORE INTO assignments(task_id,member_id) VALUES(?,?)',(row['task_id'],a['id']))
            c.execute('INSERT OR IGNORE INTO project_members(project_id,member_id,role,joined_at) VALUES(?,?,?,?)',(row['project_id'],a['id'],'member',now()))
            status='ACCEPTED'
        else: status='REJECTED'
        stamp=now()
        cur=c.execute('UPDATE task_delegations SET status=?,responded_at=?,updated_at=? WHERE id=? AND status=\'PENDING\'',(status,stamp,stamp,did))
        if cur.rowcount != 1:
            raise HTTPException(409,'Delegation response raced with another decision')
        event(c,'task.delegation.'+status.lower(),a['id'],row['task_id'],{'delegation_id':did,'agent_name':row['agent_name']})
        return {'id':did,'task_id':row['task_id'],'status':status,'responded_at':stamp}

@app.get('/api/v1/tasks/{tid}/delegations')
def list_task_delegations(tid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a)
        rows=c.execute('SELECT * FROM task_delegations WHERE task_id=? ORDER BY created_at DESC',(tid,)).fetchall()
        result=[]
        for raw in rows:
            row=dict(raw)
            if row['status']=='PENDING' and row['expires_at'] <= now():
                stamp=now()
                cur=c.execute("UPDATE task_delegations SET status='EXPIRED',updated_at=? WHERE id=? AND status='PENDING'",(stamp,row['id']))
                if cur.rowcount:
                    event(c,'task.delegation.expired',a['id'],tid,{'delegation_id':row['id']})
                row['status']='EXPIRED'
            result.append(row)
        return result

@app.get('/api/v1/projects/{pid}/delegations')
def project_delegations(pid:str,limit:int=100,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,500))
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute("""SELECT d.*,rq.name AS requester_name,rc.name AS recipient_name,t.title AS task_title
            FROM task_delegations d
            JOIN members rq ON rq.id=d.requester_member_id
            JOIN members rc ON rc.id=d.recipient_member_id
            JOIN tasks t ON t.id=d.task_id
            WHERE d.project_id=? ORDER BY d.created_at DESC LIMIT ?""",(pid,limit)).fetchall()
        items=[]
        for raw in rows:
            row=dict(raw)
            if row['status']=='PENDING' and row['expires_at'] <= now():
                stamp=now()
                cur=c.execute("UPDATE task_delegations SET status='EXPIRED',updated_at=? WHERE id=? AND status='PENDING'",(stamp,row['id']))
                if cur.rowcount:
                    event(c,'task.delegation.expired',a['id'],row['task_id'],{'delegation_id':row['id']})
                row['status']='EXPIRED'
            items.append(row)
        return {'project_id':pid,'count':len(items),'items':items}

@app.post('/api/v1/messages')
def send_message(b:MessageIn,authorization:str=Header(None)):
    a=actor(authorization); mid='msg_'+uuid.uuid4().hex[:12]
    with conn() as c:
        if not c.execute('SELECT 1 FROM members WHERE id=?',(b.recipient_member_id,)).fetchone(): raise HTTPException(404,'Recipient not found')
        if b.task_id:
            require_task_access(c,b.task_id,a)
            pid=task_project(c,b.task_id)
            if b.project_id and b.project_id != pid: raise HTTPException(400,'project_id does not match task')
        else: pid=b.project_id
        if not pid and not is_admin(a): raise HTTPException(400,'project_id is required for project-scoped messages')
        if pid:
            require_project_access(c,pid,a)
            recipient=c.execute('SELECT tenant_id FROM members WHERE id=?',(b.recipient_member_id,)).fetchone()
            project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
            if recipient and recipient['tenant_id'] != project['tenant_id']: raise HTTPException(400,'Recipient belongs to a different tenant')
            if not is_admin(a) and not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(pid,b.recipient_member_id)).fetchone(): raise HTTPException(400,'Recipient is not a project member')
        created=now()
        message_tenant=(c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()['tenant_id'] if pid else c.execute('SELECT tenant_id FROM members WHERE id=?',(b.recipient_member_id,)).fetchone()['tenant_id'])
        c.execute('INSERT INTO messages(id,recipient_member_id,tenant_id,task_id,message_type,title,content,priority,status,created_at,acked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(mid,b.recipient_member_id,message_tenant,b.task_id,b.message_type,b.title,b.content,b.priority,'PENDING',created,None))
        payload={'message_id':mid,'recipient_member_id':b.recipient_member_id,'project_id':pid,'task_id':b.task_id,'message_type':b.message_type,'title':b.title,'content':b.content,'priority':b.priority}
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',('obx_'+uuid.uuid4().hex,'message.created',json.dumps(payload),'PENDING',0,created,created,message_tenant))
        event(c,'message.created',a['id'],b.task_id,{'message_id':mid,'recipient':b.recipient_member_id},tenant_override=message_tenant)
    return {'id':mid,'status':'PENDING'}
@app.get('/api/v1/me/notifications')
def notifications(authorization:str=Header(None),after:int=0,limit:int=50):
    a=actor(authorization); limit=max(1,min(limit,100))
    with conn() as c:
        rows=[dict(x) for x in c.execute("SELECT * FROM messages WHERE recipient_member_id=? AND status='PENDING' AND seq>? ORDER BY seq LIMIT ?",(a['id'],after,limit))]
        for row in rows: c.execute('UPDATE messages SET attempts=attempts+1,last_attempt_at=? WHERE id=?',(now(),row['id']))
        return {'items':rows,'next_cursor':rows[-1]['seq'] if rows else after,'has_more':len(rows)==limit}
@app.post('/api/v1/messages/{mid}/ack')
def ack(mid:str,b:AckIn,authorization: str=Header(None)):
    a=actor(authorization)
    if b.status not in ('ACKNOWLEDGED','REJECTED'): raise HTTPException(422,'Invalid acknowledgement status')
    with conn() as c:
        existing=c.execute('SELECT status,task_id,tenant_id FROM messages WHERE id=? AND recipient_member_id=?',(mid,a['id'])).fetchone()
        if not existing: raise HTTPException(404,'Message not found for current member')
        if existing['status'] in ('ACKNOWLEDGED','REJECTED'):
            if existing['status'] != b.status: raise HTTPException(409,'Message has already reached a different terminal status')
            return {'id':mid,'status':existing['status'],'idempotent':True}
        stamp=now()
        cur=c.execute("UPDATE messages SET status=?,acked_at=? WHERE id=? AND recipient_member_id=? AND status='PENDING'",(b.status,stamp,mid,a['id']))
        if cur.rowcount==0: raise HTTPException(409,'Message status changed; retry the request')
        event(c,'message.acknowledged',a['id'],existing['task_id'],{'message_id':mid,'status':b.status},tenant_override=existing['tenant_id'])
    return {'id':mid,'status':b.status,'idempotent':False}
@app.get('/api/v1/tasks/{tid}/events')
def task_events(tid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a)
        return [dict(x) for x in c.execute('SELECT * FROM events WHERE task_id=? ORDER BY created_at',(tid,))]
@app.get('/api/v1/tasks/{tid}/artifacts')
def task_artifacts(tid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_task_access(c,tid,a)
        return [dict(x) for x in c.execute('SELECT * FROM artifacts WHERE task_id=? ORDER BY created_at',(tid,))]
@app.post('/internal/v1/outbox/claim')
def claim_outbox(body:dict,authorization:str=Header(None)):
    require_worker(authorization)
    worker=str(body.get('worker_id','')).strip()
    if not worker or len(worker)>120: raise HTTPException(422,'worker_id is required (max 120 chars)')
    limit=max(1,min(int(body.get('limit',20)),100)); lease_seconds=max(10,min(int(body.get('lease_seconds',60)),900))
    claimed=[]; timestamp=datetime.now(timezone.utc); stamp=timestamp.isoformat()
    with conn() as c:
        is_pg=DATABASE_URL.startswith(('postgresql://','postgres://'))
        if not is_pg: c.execute('BEGIN IMMEDIATE')
        query="SELECT * FROM outbox WHERE (status='PENDING' AND available_at<=?) OR (status='IN_FLIGHT' AND lease_until<=?) ORDER BY created_at LIMIT ?"
        if is_pg: query += " FOR UPDATE SKIP LOCKED"
        rows=c.execute(query,(stamp,stamp,limit)).fetchall()
        for row in rows:
            lease_until=datetime.fromtimestamp(timestamp.timestamp()+lease_seconds,timezone.utc).isoformat()
            lease_token=secrets.token_urlsafe(32)
            cur=c.execute("UPDATE outbox SET status='IN_FLIGHT',attempts=attempts+1,lease_until=?,lease_owner=?,lease_token=? WHERE id=? AND ((status='PENDING' AND available_at<=?) OR (status='IN_FLIGHT' AND lease_until<=?))",(lease_until,worker,lease_token,row['id'],stamp,stamp))
            if cur.rowcount:
                item=dict(row); item.update(status='IN_FLIGHT',attempts=row['attempts']+1,lease_until=lease_until,lease_owner=worker,lease_token=lease_token,payload=json.loads(row['payload']))
                claimed.append(item)
    return {'items':claimed,'count':len(claimed)}

@app.post('/internal/v1/outbox/{outbox_id}/complete')
def complete_outbox(outbox_id:str,body:dict,authorization:str=Header(None)):
    require_worker(authorization)
    worker=str(body.get('worker_id','')).strip(); lease_token=str(body.get('lease_token',''))
    if not worker or len(worker)>120 or len(lease_token)<32: raise HTTPException(422,'worker_id and lease_token are required')
    with conn() as c:
        stamp=now()
        cur=c.execute("UPDATE outbox SET status='SENT',sent_at=?,lease_until=NULL,lease_owner=NULL,lease_token=NULL,last_error=NULL WHERE id=? AND status='IN_FLIGHT' AND lease_owner=? AND lease_token=? AND lease_until>?",(stamp,outbox_id,worker,lease_token,stamp))
        if not cur.rowcount: raise HTTPException(409,'Outbox lease not owned by worker or item is not in flight')
    return {'id':outbox_id,'status':'SENT'}

@app.post('/internal/v1/outbox/{outbox_id}/fail')
def fail_outbox(outbox_id:str,body:dict,authorization:str=Header(None)):
    require_worker(authorization)
    worker=str(body.get('worker_id','')).strip(); lease_token=str(body.get('lease_token','')); error=str(body.get('error','Delivery failed'))[:2000]
    if not worker or len(worker)>120 or len(lease_token)<32: raise HTTPException(422,'worker_id and lease_token are required')
    with conn() as c:
        stamp=now()
        row=c.execute("SELECT attempts FROM outbox WHERE id=? AND status='IN_FLIGHT' AND lease_owner=? AND lease_token=? AND lease_until>?",(outbox_id,worker,lease_token,stamp)).fetchone()
        if not row: raise HTTPException(409,'Outbox lease not owned, expired, or item is not in flight')
        attempts=row['attempts']; terminal=attempts>=8
        delay=min(3600,5*(2**min(attempts-1,10)))
        available=datetime.fromtimestamp(datetime.now(timezone.utc).timestamp()+delay,timezone.utc).isoformat()
        cur=c.execute("UPDATE outbox SET status=?,available_at=?,lease_until=NULL,lease_owner=NULL,lease_token=NULL,last_error=? WHERE id=? AND status='IN_FLIGHT' AND lease_owner=? AND lease_token=? AND lease_until>?",('DEAD' if terminal else 'PENDING',available,error,outbox_id,worker,lease_token,stamp))
        if not cur.rowcount: raise HTTPException(409,'Outbox lease changed or expired during failure acknowledgement')
    return {'id':outbox_id,'status':'DEAD' if terminal else 'PENDING','retry_after_seconds':None if terminal else delay}

@app.get('/api/v1/admin/outbox/dead')
def list_dead_outbox(limit:int=50,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    limit=max(1,min(limit,200))
    with conn() as c:
        rows=c.execute("SELECT id,event_type,status,attempts,available_at,last_error,created_at,tenant_id FROM outbox WHERE status='DEAD' ORDER BY created_at LIMIT ?",(limit,)).fetchall()
        return {'items':[dict(x) for x in rows],'count':len(rows)}

@app.post('/api/v1/admin/messages/{message_id}/restore-outbox')
def restore_missing_message_outbox(message_id:str,body:dict,authorization:str=Header(None)):
    """Explicitly restore one missing message dispatch record; never duplicates an existing dispatch."""
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    reason=str(body.get('reason','')).strip()
    if not reason or len(reason)>1000: raise HTTPException(422,'A recovery reason (1-1000 characters) is required')
    with conn() as c:
        begin_serialized_write(c)
        query='SELECT * FROM messages WHERE id=?'
        if DATABASE_URL.startswith(('postgresql://','postgres://')): query += ' FOR UPDATE'
        message=c.execute(query,(message_id,)).fetchone()
        if not message: raise HTTPException(404,'Message not found')
        existing_rows=c.execute("SELECT id,payload FROM outbox WHERE event_type='message.created'").fetchall()
        matching=[]
        for item in existing_rows:
            try:
                if json.loads(item['payload']).get('message_id')==message_id: matching.append(item['id'])
            except (TypeError,ValueError):
                continue
        if matching:
            raise HTTPException(409,'A message.created outbox record already exists; refusing duplicate recovery')
        project_id=None
        if message['task_id']:
            project=c.execute('SELECT r.project_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id WHERE t.id=?',(message['task_id'],)).fetchone()
            if project: project_id=project['project_id']
        payload={'message_id':message_id,'recipient_member_id':message['recipient_member_id'],
                 'project_id':project_id,'task_id':message['task_id'],'message_type':message['message_type'],
                 'title':message['title'],'content':message['content'],'priority':message['priority']}
        stamp=now(); outbox_id='obx_'+uuid.uuid4().hex
        c.execute('INSERT INTO outbox(id,event_type,payload,status,attempts,available_at,created_at,tenant_id) VALUES(?,?,?,?,?,?,?,?)',
                  (outbox_id,'message.created',json.dumps(payload),'PENDING',0,stamp,stamp,message['tenant_id']))
        event(c,'message.outbox.restored',a['id'],message['task_id'],
              {'message_id':message_id,'outbox_id':outbox_id,'reason':reason},tenant_override=message['tenant_id'])
    return {'message_id':message_id,'outbox_id':outbox_id,'status':'PENDING','restored':True}

@app.get('/api/v1/projects/{project_id}/message-delivery-health')
def project_message_delivery_health(project_id:str,authorization:str=Header(None),
                                    dispatch_sla_seconds:int=120,ack_sla_seconds:int=300,
                                    limit:int=100):
    """Project-scoped delivery SLA health; broker dispatch and recipient ACK clocks are separate."""
    a=actor(authorization)
    dispatch_sla_seconds=max(10,min(dispatch_sla_seconds,86400))
    ack_sla_seconds=max(10,min(ack_sla_seconds,604800))
    limit=max(1,min(limit,500))
    stamp=datetime.now(timezone.utc)
    incidents=[]
    with conn() as c:
        require_project_access(c,project_id,a)
        messages=c.execute("""SELECT m.id,m.recipient_member_id,m.tenant_id,m.task_id,m.status,m.created_at,m.acked_at
            FROM messages m JOIN tasks t ON t.id=m.task_id
            JOIN requirements r ON r.id=t.requirement_id
            WHERE r.project_id=? ORDER BY m.seq DESC LIMIT ?""",(project_id,limit)).fetchall()
        outbox=c.execute("SELECT id,payload,status,attempts,available_at,lease_until,lease_owner,last_error,created_at,sent_at FROM outbox WHERE event_type='message.created'").fetchall()
    by_message={}
    malformed=0
    for row in outbox:
        try:
            mid=json.loads(row['payload']).get('message_id')
            if isinstance(mid,str) and mid: by_message.setdefault(mid,[]).append(row)
            else: malformed+=1
        except (TypeError,ValueError):
            malformed+=1
    dispatch_counts={k:0 for k in ('HEALTHY','MISSING','DUPLICATE','DEAD','DISPATCH_OVERDUE')}
    ack_counts={k:0 for k in ('NOT_DUE','ACK_OVERDUE','ACKNOWLEDGED','REJECTED')}
    def parse_stamp(value):
        if not value: return None
        try:
            parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError,ValueError):
            return None
    for message in messages:
        records=by_message.get(message['id'],[])
        dispatch='HEALTHY'; ack='NOT_DUE'; detail=None
        if not records:
            dispatch='MISSING'; detail='No message.created outbox record'
        elif len(records)>1:
            dispatch='DUPLICATE'; detail='Multiple message.created outbox records'
        elif records[0]['status']=='DEAD':
            dispatch='DEAD'; detail=records[0]['last_error'] or 'Outbox entered DEAD state'
        elif records[0]['status'] in ('PENDING','IN_FLIGHT'):
            created=parse_stamp(records[0]['created_at'])
            if created and (stamp-created).total_seconds()>dispatch_sla_seconds:
                dispatch='DISPATCH_OVERDUE'; detail='Broker dispatch exceeded SLA'
        elif records[0]['status']!='SENT':
            dispatch='HEALTHY'; detail='Unrecognized outbox state: '+str(records[0]['status'])
        if dispatch in dispatch_counts: dispatch_counts[dispatch]+=1
        if message['status'] in ('ACKNOWLEDGED','REJECTED'):
            ack=message['status']
        elif records and len(records)==1 and records[0]['status']=='SENT':
            sent=parse_stamp(records[0]['sent_at'])
            if sent and (stamp-sent).total_seconds()>ack_sla_seconds:
                ack='ACK_OVERDUE'
        if ack in ack_counts: ack_counts[ack]+=1
        if dispatch!='HEALTHY':
            incidents.append({'message_id':message['id'],'task_id':message['task_id'],
                'category':'DISPATCH_'+dispatch,'dispatch_status':dispatch,'ack_status':ack,
                'age_seconds':max(0,int((stamp-(parse_stamp(message['created_at']) or stamp)).total_seconds())),
                'detail':detail})
        if ack=='ACK_OVERDUE':
            incidents.append({'message_id':message['id'],'task_id':message['task_id'],
                'category':'ACK_OVERDUE','dispatch_status':dispatch,'ack_status':ack,
                'age_seconds':max(0,int((stamp-(parse_stamp(records[0]['sent_at']) or stamp)).total_seconds())),
                'detail':'Broker dispatch completed but recipient ACK exceeded SLA'})
    return {'project_id':project_id,'generated_at':stamp.isoformat(),
        'policy':{'dispatch_sla_seconds':dispatch_sla_seconds,'ack_sla_seconds':ack_sla_seconds},
        'checked_messages':len(messages),'truncated':len(messages)==limit,
        'dispatch_counts':dispatch_counts,'ack_counts':ack_counts,
        'incident_count':len(incidents),'incidents':incidents[:limit],
        'malformed_outbox_records_seen':malformed,
        'semantics':'ACK SLA starts at outbox sent_at only. SENT is broker dispatch completion, not recipient ACK.'}

@app.post('/api/v1/projects/{project_id}/message-delivery-incidents/{message_id}/review')
def review_message_delivery_incident(project_id:str,message_id:str,body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    disposition=str(body.get('disposition','')).strip().upper()
    comment=str(body.get('comment','')).strip()
    if disposition not in ('INVESTIGATING','RESOLVED','ACCEPTED_RISK'):
        raise HTTPException(422,'disposition must be INVESTIGATING, RESOLVED, or ACCEPTED_RISK')
    if not comment or len(comment)>2000:
        raise HTTPException(422,'A review comment (1-2000 characters) is required')
    with conn() as c:
        require_project_access(c,project_id,a,write=True)
        row=c.execute("""SELECT m.task_id,m.tenant_id FROM messages m JOIN tasks t ON t.id=m.task_id
            JOIN requirements r ON r.id=t.requirement_id WHERE m.id=? AND r.project_id=?""",
            (message_id,project_id)).fetchone()
        if not row: raise HTTPException(404,'Project message not found')
        event(c,'message.delivery.incident.reviewed',a['id'],row['task_id'],
              {'project_id':project_id,'message_id':message_id,'disposition':disposition,'comment':comment},
              tenant_override=row['tenant_id'])
    return {'project_id':project_id,'message_id':message_id,'disposition':disposition,'recorded':True}


@app.get('/api/v1/admin/message-delivery')
def message_delivery_overview(authorization:str=Header(None),limit:int=200,offset:int=0,
                              dispatch_status:str=None,ack_status:str=None):
    """Admin operational view separating broker dispatch from recipient acknowledgement."""
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    limit=max(1,min(limit,500)); offset=max(0,offset)
    allowed_dispatch={'NO_OUTBOX','DUPLICATE','PENDING','IN_FLIGHT','SENT','DEAD'}
    allowed_ack={'PENDING','ACKNOWLEDGED','REJECTED'}
    if dispatch_status and dispatch_status not in allowed_dispatch:
        raise HTTPException(422,'Invalid dispatch_status filter')
    if ack_status and ack_status not in allowed_ack:
        raise HTTPException(422,'Invalid ack_status filter')
    with conn() as c:
        messages=c.execute('SELECT id,recipient_member_id,tenant_id,task_id,message_type,priority,status,created_at,acked_at FROM messages ORDER BY seq DESC LIMIT ? OFFSET ?',(limit,offset)).fetchall()
        outbox=c.execute("SELECT id,event_type,payload,status,attempts,available_at,lease_until,lease_owner,last_error,created_at,sent_at,tenant_id FROM outbox WHERE event_type='message.created' ORDER BY created_at").fetchall()
    by_message={}
    malformed_count=0
    for item in outbox:
        try:
            mid=json.loads(item['payload']).get('message_id')
            if not isinstance(mid,str) or not mid: malformed_count+=1; continue
        except (TypeError,ValueError):
            malformed_count+=1; continue
        by_message.setdefault(mid,[]).append(item)
    items=[]
    counts={key:0 for key in ('NO_OUTBOX','DUPLICATE','PENDING','IN_FLIGHT','SENT','DEAD')}
    ack_counts={key:0 for key in ('PENDING','ACKNOWLEDGED','REJECTED')}
    for message in messages:
        records=by_message.get(message['id'],[])
        state='NO_OUTBOX' if not records else ('DUPLICATE' if len(records)>1 else records[0]['status'])
        if state not in counts: state='UNKNOWN'
        if state in counts: counts[state]+=1
        ack=message['status']
        if ack in ack_counts: ack_counts[ack]+=1
        if dispatch_status and state!=dispatch_status: continue
        if ack_status and ack!=ack_status: continue
        items.append({
            'message_id':message['id'],'recipient_member_id':message['recipient_member_id'],
            'tenant_id':message['tenant_id'],'task_id':message['task_id'],
            'message_type':message['message_type'],'priority':message['priority'],
            'ack_status':ack,'created_at':message['created_at'],'acked_at':message['acked_at'],
            'dispatch_status':state,'dispatch_records':[{
                'outbox_id':row['id'],'status':row['status'],'attempts':row['attempts'],
                'available_at':row['available_at'],'lease_until':row['lease_until'],
                'lease_owner':row['lease_owner'],'last_error':row['last_error'],
                'created_at':row['created_at'],'sent_at':row['sent_at']
            } for row in records]
        })
    return {'items':items,'count':len(items),'limit':limit,'offset':offset,
            'dispatch_counts':counts,'ack_counts':ack_counts,
            'malformed_outbox_records_seen':malformed_count,
            'semantics':{'SENT':'Broker dispatch completed; recipient acknowledgement is tracked separately in ack_status.',
                         'ACKNOWLEDGED':'Recipient explicitly acknowledged the message.',
                         'REJECTED':'Recipient explicitly rejected the message.'}}

@app.get('/api/v1/admin/message-delivery-integrity')
def message_delivery_integrity(authorization:str=Header(None),limit:int=5000):
    """Read-only reconciliation of durable messages and their outbox dispatch records."""
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    limit=max(1,min(limit,10000))
    with conn() as c:
        messages=c.execute('SELECT id,recipient_member_id,tenant_id,task_id FROM messages ORDER BY seq LIMIT ?',(limit+1,)).fetchall()
        outbox=c.execute("SELECT id,event_type,payload,tenant_id,status FROM outbox WHERE event_type='message.created' ORDER BY created_at LIMIT ?",(limit+1,)).fetchall()
    truncated=len(messages)>limit or len(outbox)>limit
    messages=messages[:limit]; outbox=outbox[:limit]
    by_message={}
    malformed=[]; orphaned=[]; tenant_mismatch=[]; recipient_mismatch=[]; task_mismatch=[]
    known={row['id']:row for row in messages}
    for item in outbox:
        try:
            payload=json.loads(item['payload'])
            message_id=payload.get('message_id')
            if not isinstance(message_id,str) or not message_id:
                malformed.append(item['id']); continue
        except (TypeError,ValueError):
            malformed.append(item['id']); continue
        by_message.setdefault(message_id,[]).append(item)
        message=known.get(message_id)
        if not message:
            orphaned.append(item['id']); continue
        if item['tenant_id'] != message['tenant_id']:
            tenant_mismatch.append(item['id'])
        if payload.get('recipient_member_id') != message['recipient_member_id']:
            recipient_mismatch.append(item['id'])
        if payload.get('task_id') != message['task_id']:
            task_mismatch.append(item['id'])
    missing=[mid for mid in known if mid not in by_message]
    duplicates={mid:[x['id'] for x in rows] for mid,rows in by_message.items() if len(rows)>1}
    issues={
        'messages_without_outbox':missing,
        'duplicate_outbox_by_message':duplicates,
        'orphaned_outbox':orphaned,
        'malformed_outbox':malformed,
        'tenant_mismatch_outbox':tenant_mismatch,
        'recipient_mismatch_outbox':recipient_mismatch,
        'task_mismatch_outbox':task_mismatch,
    }
    counts={key:(len(value) if isinstance(value,list) else len(value)) for key,value in issues.items()}
    return {'checked_messages':len(messages),'checked_message_outbox':len(outbox),'truncated':truncated,
            'healthy':not any(counts.values()) and not truncated,'issue_counts':counts,'issues':issues,
            'semantics':'Read-only structural reconciliation; SENT means broker dispatch completed, not recipient ACK.'}

@app.post('/api/v1/admin/outbox/{outbox_id}/replay')
def replay_dead_outbox(outbox_id:str,body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    reason=str(body.get('reason','')).strip()
    if not reason or len(reason)>1000: raise HTTPException(422,'A replay reason (1-1000 characters) is required')
    with conn() as c:
        row=c.execute("SELECT tenant_id,status FROM outbox WHERE id=?",(outbox_id,)).fetchone()
        if not row: raise HTTPException(404,'Outbox item not found')
        if row['status']!='DEAD': raise HTTPException(409,'Only DEAD outbox items can be replayed')
        stamp=now()
        cur=c.execute("UPDATE outbox SET status='PENDING',attempts=0,available_at=?,lease_until=NULL,lease_owner=NULL,lease_token=NULL,last_error=NULL,sent_at=NULL WHERE id=? AND status='DEAD'",(stamp,outbox_id))
        if not cur.rowcount: raise HTTPException(409,'Outbox item changed; refresh and retry')
        event(c,'outbox.dead.replayed',a['id'],None,{'outbox_id':outbox_id,'reason':reason},tenant_override=row['tenant_id'])
    return {'id':outbox_id,'status':'PENDING','replayed':True}

@app.websocket('/ws/v1')
async def websocket_endpoint(ws:WebSocket,token:str='',after:int=0):
    # Best-effort online notification channel. The durable inbox remains the source of truth.
    lookup_reset=_auth_lookup_ctx.set(True)
    try:
        with conn() as c: member=(c.execute("SELECT id,tenant_id,role FROM daep_authenticate_member(?,?)",(hashlib.sha256(token.encode()).hexdigest(),now())).fetchone() if DATABASE_URL.startswith(('postgresql://','postgres://')) else c.execute("SELECT id,tenant_id,role FROM members WHERE token=? AND token_status='ACTIVE' AND (token_expires_at IS NULL OR token_expires_at>?)",(hashlib.sha256(token.encode()).hexdigest(),now())).fetchone())
    finally:
        _auth_lookup_ctx.reset(lookup_reset)
    if not member: await ws.close(code=1008); return
    cursor=max(0,after)
    _tenant_ctx.set(member['tenant_id']); _admin_ctx.set(member['role']=='admin' and member['tenant_id']=='tenant-default')
    await ws.accept()
    try:
        await ws.send_json({'type':'connected','at':now(),'cursor':cursor,'delivery':'best-effort; reconnect with after=<last processed seq> or recover via inbox'})
        while True:
            with conn() as c:
                rows=[dict(r) for r in c.execute("SELECT * FROM messages WHERE recipient_member_id=? AND status='PENDING' AND seq>? ORDER BY seq LIMIT 100",(member['id'],cursor))]
                if rows:
                    for r in rows:
                        await ws.send_json({'type':'notification','message':r})
                        cursor=max(cursor,r['seq'])
                        c.execute('UPDATE messages SET attempts=attempts+1,last_attempt_at=? WHERE id=?',(now(),r['id']))
            try: await asyncio.wait_for(ws.receive_text(),timeout=3.0)
            except asyncio.TimeoutError: pass
    except WebSocketDisconnect: pass

def require_worker(authorization):
    expected=os.getenv('DAEP_WORKER_TOKEN','')
    if len(expected)<32: raise HTTPException(503,'Dedicated DAEP_WORKER_TOKEN is not configured')
    if secrets.compare_digest(hashlib.sha256(expected.encode()).digest(),hashlib.sha256(ADMIN_TOKEN.encode()).digest()): raise HTTPException(503,'Worker credential must be different from DAEP_ADMIN_TOKEN')
    if not authorization or not authorization.startswith('Bearer '): raise HTTPException(401,'Worker bearer token required')
    supplied=authorization[7:]
    expected_digest=hashlib.sha256(expected.encode()).digest()
    supplied_digest=hashlib.sha256(supplied.encode()).digest()
    if not secrets.compare_digest(supplied_digest,expected_digest): raise HTTPException(401,'Invalid worker credential')
    _service_ctx.set(True)
def require_project_access(c, project_id, a, write=False):
    project=c.execute('SELECT tenant_id,status FROM projects WHERE id=?',(project_id,)).fetchone()
    if not project: raise HTTPException(404,'Project not found')
    if project['tenant_id'] != a.get('tenant_id','tenant-default') and not is_admin(a):
        raise HTTPException(403,'Tenant isolation violation')
    if write and project['status']=='CLOSED': raise HTTPException(409,'Project is closed')
    if is_admin(a): return
    if a.get('actor_type')=='AGENT':
        binding=c.execute("SELECT 1 FROM agent_project_bindings WHERE project_id=? AND agent_id=? AND status='ACTIVE'",
            (project_id,a['agent_id'])).fetchone()
        if not binding: raise HTTPException(403,'Agent project binding required')
        if write: raise HTTPException(403,'Agent cannot perform project-level governance or administration')
        return
    row=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(project_id,a['id'])).fetchone()
    if not row: raise HTTPException(403,'Project membership required')
    if write and row['role'] not in ('owner','manager'): raise HTTPException(403,'Project manager role required')
def task_project(c, tid):
    r=c.execute('SELECT r.project_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id WHERE t.id=?',(tid,)).fetchone()
    return r['project_id'] if r else None
def require_task_access(c, tid, a, assigned_only=False):
    pid=task_project(c,tid)
    if not pid: raise HTTPException(404,'Task not found')
    project=c.execute('SELECT status FROM projects WHERE id=?',(pid,)).fetchone()
    closed=bool(project and project['status']=='CLOSED')
    if is_admin(a):
        if assigned_only and closed: raise HTTPException(409,'Project is closed')
        return
    if a.get('actor_type')=='AGENT':
        require_project_access(c,pid,a)
        if assigned_only and closed:
            raise HTTPException(409,'Project is closed')
        assignment=c.execute("""SELECT 1 FROM agent_task_assignments
            WHERE task_id=? AND project_id=? AND agent_id=? AND status='ACCEPTED'""",
            (tid,pid,a['agent_id'])).fetchone()
        if not assignment:
            raise HTTPException(403,'Accepted Agent task assignment required')
        return
    if assigned_only:
        if closed: raise HTTPException(409,'Project is closed')
        ok=c.execute('SELECT 1 FROM assignments WHERE task_id=? AND member_id=?',(tid,a['id'])).fetchone()
        if not ok: raise HTTPException(403,'Task assignment required')
    else: require_project_access(c,pid,a)

def event(c,typ,member,task,payload,key=None,tenant_override=None):
    eid='evt_'+uuid.uuid4().hex
    tenant=tenant_override or 'tenant-default'
    if tenant_override:
        pass
    elif task:
        rr=c.execute('SELECT p.tenant_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE t.id=?',(task,)).fetchone()
        if rr: tenant=rr['tenant_id']
    elif member:
        rr=c.execute('SELECT tenant_id FROM members WHERE id=?',(member,)).fetchone()
        if rr: tenant=rr['tenant_id']
    audit_payload=dict(payload or {})
    audit_payload.setdefault('actor_type','AGENT' if _agent_ctx.get() else 'MEMBER')
    if _agent_ctx.get(): audit_payload.setdefault('agent_id',_agent_ctx.get())
    # Agent actions are attributed to the Agent identity, never to its owner's member row.
    actor_member_id=None if _agent_ctx.get() else member
    payload_json=json.dumps(audit_payload)
    if key:
        c.execute('INSERT INTO events(id,event_type,actor_member_id,task_id,payload,created_at,idempotency_key,tenant_id) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(idempotency_key) DO NOTHING',(eid,typ,actor_member_id,task,payload_json,now(),key,tenant))
        prior=c.execute('SELECT id,payload FROM events WHERE idempotency_key=?',(key,)).fetchone()
        if prior:
            if prior['payload'] != payload_json:
                raise HTTPException(409,'Idempotency key was used with a different payload')
            return prior['id']
    else:
        c.execute('INSERT INTO events(id,event_type,actor_member_id,task_id,payload,created_at,idempotency_key,tenant_id) VALUES(?,?,?,?,?,?,?,?)',(eid,typ,actor_member_id,task,payload_json,now(),key,tenant))
    return eid

@app.get('/',include_in_schema=False)
def dashboard(): return FileResponse(os.path.join(os.path.dirname(os.path.dirname(__file__)),'web','index.html'))
def _oidc_discovery():
    issuer=os.getenv('DAEP_OIDC_ISSUER','').rstrip('/')
    if not issuer: raise HTTPException(503,'OIDC is not configured')
    try:
        with urllib.request.urlopen(issuer+'/.well-known/openid-configuration',timeout=10) as r: return json.loads(r.read())
    except Exception as exc: raise HTTPException(503,f'OIDC discovery failed: {exc}')

def _oidc_state_record():
    """Create one-time server-side OIDC state, nonce and PKCE verifier."""
    state=secrets.token_urlsafe(32)
    nonce=secrets.token_urlsafe(32)
    verifier=secrets.token_urlsafe(64)
    expires=datetime.fromtimestamp(time.time()+600,timezone.utc).isoformat()
    with conn() as c:
        c.execute('DELETE FROM oidc_states WHERE expires_at<=?',(now(),))
        c.execute('INSERT INTO oidc_states(state_hash,nonce,code_verifier,expires_at,created_at) VALUES(?,?,?,?,?)',
                  (hashlib.sha256(state.encode()).hexdigest(),nonce,verifier,expires,now()))
    return state,nonce,verifier

def _verify_oidc_browser_state(state,cookie_state):
    if not cookie_state or not secrets.compare_digest(hashlib.sha256(cookie_state.encode()).digest(),hashlib.sha256(state.encode()).digest()):
        raise HTTPException(400,'OIDC browser state cookie mismatch')

def _consume_oidc_state(state):
    if not state or len(state)>512: raise HTTPException(400,'Invalid OIDC state')
    digest=hashlib.sha256(state.encode()).hexdigest()
    with conn() as c:
        row=c.execute('SELECT nonce,code_verifier,expires_at FROM oidc_states WHERE state_hash=?',(digest,)).fetchone()
        if not row: raise HTTPException(400,'Invalid or already used OIDC state')
        c.execute('DELETE FROM oidc_states WHERE state_hash=?',(digest,))
    if row['expires_at'] <= now(): raise HTTPException(400,'Expired OIDC state')
    return row['nonce'],row['code_verifier']

@app.get('/api/v1/auth/oidc/login')
def oidc_login():
    if not (os.getenv('DAEP_OIDC_CLIENT_ID') and os.getenv('DAEP_OIDC_REDIRECT_URI')): raise HTTPException(503,'OIDC is not configured')
    d=_oidc_discovery(); state,nonce,verifier=_oidc_state_record()
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    params={'client_id':os.getenv('DAEP_OIDC_CLIENT_ID'),'response_type':'code','redirect_uri':os.getenv('DAEP_OIDC_REDIRECT_URI'),'scope':os.getenv('DAEP_OIDC_SCOPES','openid profile email'),'state':state,'nonce':nonce,'code_challenge':challenge,'code_challenge_method':'S256'}
    if os.getenv('DAEP_OIDC_AUDIENCE'): params['audience']=os.getenv('DAEP_OIDC_AUDIENCE')
    response=RedirectResponse(d['authorization_endpoint']+'?'+urllib.parse.urlencode(params),status_code=302)
    response.set_cookie('daep_oidc_state',state,max_age=600,httponly=True,secure=os.getenv('DAEP_OIDC_REDIRECT_URI','').startswith('https://'),samesite='lax',path='/api/v1/auth/oidc/callback')
    return response

@app.get('/api/v1/auth/oidc/callback')
def oidc_callback(code:str,state:str,daep_oidc_state:Optional[str]=Cookie(None)):
    client_id=os.getenv('DAEP_OIDC_CLIENT_ID',''); client_secret=os.getenv('DAEP_OIDC_CLIENT_SECRET','')
    redirect_uri=os.getenv('DAEP_OIDC_REDIRECT_URI','')
    if not client_id or not client_secret or not redirect_uri: raise HTTPException(503,'OIDC client is not configured')
    _verify_oidc_browser_state(state,daep_oidc_state)
    nonce,code_verifier=_consume_oidc_state(state); d=_oidc_discovery()
    form=urllib.parse.urlencode({'grant_type':'authorization_code','code':code,'redirect_uri':redirect_uri,'client_id':client_id,'client_secret':client_secret,'code_verifier':code_verifier}).encode()
    req=urllib.request.Request(d['token_endpoint'],data=form,method='POST',headers={'Content-Type':'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req,timeout=15) as r: tokens=json.loads(r.read())
    except Exception: raise HTTPException(502,'OIDC token exchange failed')
    id_token=tokens.get('id_token')
    if not id_token: raise HTTPException(502,'OIDC provider did not return an id_token')
    try:
        import jwt
        jwks_client=jwt.PyJWKClient(d['jwks_uri'],timeout=10)
        signing_key=jwks_client.get_signing_key_from_jwt(id_token).key
        claims=jwt.decode(id_token,signing_key,algorithms=['RS256','RS384','RS512','PS256','ES256'],audience=client_id,issuer=os.getenv('DAEP_OIDC_ISSUER').rstrip('/'),options={'require':['exp','iat','sub','iss','aud']})
        if not secrets.compare_digest(str(claims.get('nonce','')),nonce): raise ValueError('OIDC nonce mismatch')
        audiences=claims.get('aud',[])
        if isinstance(audiences,list) and len(audiences)>1 and claims.get('azp')!=client_id: raise ValueError('OIDC authorized party mismatch')
    except Exception: raise HTTPException(401,'OIDC ID token validation failed')
    subject=str(claims.get('sub','')); email=str(claims.get('email',''))
    if not subject: raise HTTPException(401,'OIDC subject is missing')
    created=now(); raw=uuid.uuid4().hex+uuid.uuid4().hex; digest=hashlib.sha256(raw.encode()).hexdigest()
    service_reset=_service_ctx.set(True)
    try:
        with conn() as c:
            row=c.execute('SELECT id FROM members WHERE oidc_subject=?',(subject,)).fetchone()
            if row:
                c.execute("UPDATE members SET token=?,token_status='ACTIVE',token_created_at=?,token_revoked_at=NULL,oidc_email=? WHERE id=?",(digest,created,email,row['id']))
                member_id=row['id']
            else:
                if os.getenv('DAEP_OIDC_AUTO_PROVISION','false').lower()!='true': raise HTTPException(403,'OIDC identity is not provisioned')
                member_id='mem_'+uuid.uuid4().hex[:12]; tenant_id=os.getenv('DAEP_OIDC_DEFAULT_TENANT','tenant-default'); name=str(claims.get('name') or email or subject)
                if not c.execute("SELECT 1 FROM tenants WHERE id=? AND status='ACTIVE'",(tenant_id,)).fetchone(): raise HTTPException(403,'OIDC default tenant is unavailable')
                oidc_role=os.getenv('DAEP_OIDC_DEFAULT_ROLE','developer')
                if oidc_role not in ('developer','manager','reviewer'): oidc_role='developer'
                c.execute("INSERT INTO members(id,name,role,token,created_at,tenant_id,token_status,token_created_at,oidc_subject,oidc_email) VALUES(?,?,?,?,?,?,?,?,?,?)",(member_id,name,oidc_role,digest,created,tenant_id,'ACTIVE',created,subject,email))
    finally:
        _service_ctx.reset(service_reset)
    response=JSONResponse({'member_id':member_id,'token':raw,'token_expires_at':None,'message':'OIDC authentication succeeded; store this API token securely. It is returned only once.'})
    response.delete_cookie('daep_oidc_state',path='/api/v1/auth/oidc/callback')
    return response

@app.get('/api/v1/auth/oidc/config')
def oidc_config():
    enabled=bool(os.getenv('DAEP_OIDC_ISSUER') and os.getenv('DAEP_OIDC_CLIENT_ID') and os.getenv('DAEP_OIDC_REDIRECT_URI'))
    return {'enabled':enabled,'issuer':os.getenv('DAEP_OIDC_ISSUER',''),'client_id':os.getenv('DAEP_OIDC_CLIENT_ID',''),'redirect_uri':os.getenv('DAEP_OIDC_REDIRECT_URI',''),'scopes':os.getenv('DAEP_OIDC_SCOPES','openid profile email')}

@app.post('/api/v1/integrations/git/webhook')
async def git_webhook(request:Request, body:dict, x_daep_webhook_secret:str=Header('',alias='X-DAEP-Webhook-Secret'), x_daep_tenant_id:str=Header('',alias='X-DAEP-Tenant-ID'), x_daep_provider:str=Header('',alias='X-DAEP-Provider'), x_github_event:str=Header('',alias='X-GitHub-Event'), x_github_delivery:str=Header('',alias='X-GitHub-Delivery'), x_hub_signature_256:str=Header('',alias='X-Hub-Signature-256'), x_gitlab_event:str=Header('',alias='X-Gitlab-Event'), x_gitlab_event_uuid:str=Header('',alias='X-Gitlab-Event-UUID'), x_gitlab_token:str=Header('',alias='X-Gitlab-Token')):
    raw=await request.body()
    provider=(x_daep_provider or ('github' if x_github_event or x_hub_signature_256 else 'gitlab' if x_gitlab_event or x_gitlab_token else 'generic')).lower()
    if provider not in ('github','gitlab','generic'): raise HTTPException(422,'Unsupported Git provider')
    if provider=='github':
        expected=os.getenv('DAEP_GITHUB_WEBHOOK_SECRET') or os.getenv('DAEP_GIT_WEBHOOK_SECRET','')
        if not expected or not x_hub_signature_256 or not x_hub_signature_256.startswith('sha256='): raise HTTPException(401,'GitHub webhook signature is required')
        supplied=x_hub_signature_256.split('=',1)[1]
        actual=hmac.new(expected.encode(),raw,hashlib.sha256).hexdigest()
        if not hmac.compare_digest(actual,supplied): raise HTTPException(401,'Invalid GitHub webhook signature')
        delivery=x_github_delivery
    elif provider=='gitlab':
        expected=os.getenv('DAEP_GITLAB_WEBHOOK_SECRET') or os.getenv('DAEP_GIT_WEBHOOK_SECRET','')
        if not expected or not x_gitlab_token or not secrets.compare_digest(hashlib.sha256(x_gitlab_token.encode()).digest(),hashlib.sha256(expected.encode()).digest()): raise HTTPException(401,'Invalid GitLab webhook token')
        delivery=x_gitlab_event_uuid
    else:
        expected=os.getenv('DAEP_GIT_WEBHOOK_SECRET','')
        if not expected or not x_daep_webhook_secret or not secrets.compare_digest(hashlib.sha256(x_daep_webhook_secret.encode()).digest(),hashlib.sha256(expected.encode()).digest()): raise HTTPException(401,'Invalid webhook secret')
        delivery=request.headers.get('X-DAEP-Delivery','')
    if delivery and len(delivery)>200: raise HTTPException(422,'Webhook delivery id is too long')
    event_type=str(body.get('event_type') or body.get('action') or x_github_event or x_gitlab_event or 'push')[:80]
    task_id=body.get('task_id'); commit=body.get('after') or body.get('commit_sha')
    service_reset=_service_ctx.set(True)
    try:
        with conn() as c:
            if task_id:
                row=c.execute('SELECT p.tenant_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id JOIN projects p ON p.id=r.project_id WHERE t.id=?',(task_id,)).fetchone()
                if not row: raise HTTPException(404,'Task not found')
                tenant_id=row['tenant_id']
            else:
                tenant_id=str(x_daep_tenant_id or body.get('tenant_id') or '').strip()
                if not tenant_id: raise HTTPException(422,'X-DAEP-Tenant-ID is required when task_id is absent')
                if not c.execute("SELECT 1 FROM tenants WHERE id=? AND status='ACTIVE'",(tenant_id,)).fetchone(): raise HTTPException(404,'Tenant not found or inactive')
        _tenant_ctx.set(tenant_id); _admin_ctx.set(False)
        _service_ctx.reset(service_reset); service_reset=_service_ctx.set(False)
        with conn() as c:
            eid=event(c,'git.webhook.received',None,task_id,{'provider':provider,'delivery_id':delivery,'event_type':event_type,'commit_sha':commit,'payload':body},key=(f'git:{provider}:{delivery}' if delivery else None),tenant_override=tenant_id)
        return {'accepted':True,'event_id':eid,'event_type':event_type,'commit_sha':commit,'tenant_id':tenant_id,'provider':provider,'delivery_id':delivery}
    finally:
        _service_ctx.reset(service_reset)

@app.get('/health')
def health():
    service_reset=_service_ctx.set(True)
    try:
        with conn() as c:
            pending=c.execute("SELECT COUNT(*) n FROM outbox WHERE status IN ('PENDING','IN_FLIGHT')").fetchone()['n']
        return {'status':'ok','service':'daep-api','version':'1.0.0-rc9','outbox_pending':pending}
    finally:
        _service_ctx.reset(service_reset)

@app.get('/readyz')
def readiness():
    service_reset=_service_ctx.set(True)
    try:
        with conn() as c:
            c.execute('SELECT 1').fetchone()
            if DATABASE_URL.startswith(('postgresql://','postgres://')):
                c.execute("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='members'").fetchone()
        return {'status':'ready','service':'daep-api','version':'1.0.0-rc9'}
    except Exception:
        raise HTTPException(503,'DAEP database readiness check failed')
    finally:
        _service_ctx.reset(service_reset)
@app.get('/api/v1/me')
def me(authorization:str=Header(None)):
    a=actor(authorization); return {k:a[k] for k in ('id','name','role')}
@app.post('/api/v1/tenants')
def create_tenant(body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    name=str(body.get('name','')).strip()
    if not name or len(name)>160: raise HTTPException(422,'Tenant name is required')
    tid='ten_'+uuid.uuid4().hex[:12]
    with conn() as c: c.execute('INSERT INTO tenants(id,name,status,created_at) VALUES(?,?,?,?)',(tid,name,'ACTIVE',now()))
    return {'id':tid,'name':name,'status':'ACTIVE'}

@app.get('/api/v1/tenants')
def list_tenants(authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    with conn() as c: return [dict(x) for x in c.execute('SELECT * FROM tenants ORDER BY created_at')]

@app.post('/api/v1/members')
def create_member(body:dict,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    if not isinstance(body.get('name'),str) or not body['name'].strip(): raise HTTPException(422,'Member name is required')
    if body.get('role','developer') not in ('manager','developer','reviewer'): raise HTTPException(422,'Only the bootstrap identity can hold the platform administrator role')
    mid='mem_'+uuid.uuid4().hex[:12]; token=uuid.uuid4().hex+uuid.uuid4().hex; created=now()
    tenant_id=str(body.get('tenant_id') or a.get('tenant_id') or 'tenant-default')
    with conn() as c:
        if not c.execute("SELECT 1 FROM tenants WHERE id=? AND status='ACTIVE'",(tenant_id,)).fetchone(): raise HTTPException(404,'Tenant not found or inactive')
        c.execute('INSERT INTO members(id,name,role,token,created_at,tenant_id,token_status,token_created_at,token_revoked_at,token_expires_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(mid,body['name'],body.get('role','developer'),hashlib.sha256(token.encode()).hexdigest(),created,tenant_id,'ACTIVE',created,None,body.get('token_expires_at')))
    return {'id':mid,'name':body['name'],'role':body.get('role','developer'),'tenant_id':tenant_id,'token':token}
@app.get('/api/v1/members')
def members(authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    with conn() as c: return [dict(x) for x in c.execute('SELECT id,name,role,tenant_id,token_status,token_created_at,token_revoked_at,token_expires_at,created_at FROM members ORDER BY created_at')]
@app.post('/api/v1/members/{member_id}/revoke-token')
def revoke_member_token(member_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    with conn() as c:
        target=c.execute('SELECT tenant_id FROM members WHERE id=?',(member_id,)).fetchone()
        if not target: raise HTTPException(404,'Member not found')
        cur=c.execute("UPDATE members SET token_status='REVOKED',token_revoked_at=? WHERE id=?" ,(now(),member_id))
        event(c,'member.token.revoked',a['id'],None,{'member_id':member_id},tenant_override=target['tenant_id'])
    return {'member_id':member_id,'token_status':'REVOKED'}

@app.post('/api/v1/members/{member_id}/rotate-token')
def rotate_member_token(member_id:str,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    token=uuid.uuid4().hex+uuid.uuid4().hex; created=now(); digest=hashlib.sha256(token.encode()).hexdigest()
    with conn() as c:
        target=c.execute('SELECT tenant_id FROM members WHERE id=?',(member_id,)).fetchone()
        if not target: raise HTTPException(404,'Member not found')
        cur=c.execute("UPDATE members SET token=?,token_status='ACTIVE',token_created_at=?,token_revoked_at=NULL WHERE id=?",(digest,created,member_id))
        event(c,'member.token.rotated',a['id'],None,{'member_id':member_id},tenant_override=target['tenant_id'])
    return {'member_id':member_id,'token':token,'token_status':'ACTIVE','token_created_at':created}

@app.post('/api/v1/projects')
def create_project(b:ProjectIn,authorization:str=Header(None)):
    a=actor(authorization)
    if not is_admin(a): raise HTTPException(403,'Platform administrator required')
    pid='prj_'+uuid.uuid4().hex[:12]
    with conn() as c:
        c.execute('INSERT INTO projects(id,name,description,created_by,created_at,tenant_id) VALUES(?,?,?,?,?,?)',(pid,b.name,b.description,a['id'],now(),a.get('tenant_id','tenant-default')))
        c.execute('INSERT INTO project_members(project_id,member_id,role,work_function,joined_at) VALUES(?,?,?,?,?)',(pid,a['id'],'owner','other',now()))
    return {'id':pid,'name':b.name,'description':b.description}
@app.get('/api/v1/projects')
def projects(authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        if is_admin(a): rows=c.execute('SELECT * FROM projects ORDER BY created_at DESC')
        else: rows=c.execute('SELECT p.*,pm.role AS project_role,pm.work_function FROM projects p JOIN project_members pm ON pm.project_id=p.id WHERE pm.member_id=? AND p.tenant_id=? ORDER BY p.created_at DESC',(a['id'],a.get('tenant_id','tenant-default')))
        return [dict(x) for x in rows]
@app.get('/api/v1/projects/{pid}/members')
def project_members(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        return [dict(x) for x in c.execute('SELECT m.id,m.name,m.role AS account_role,pm.role AS project_role,pm.work_function,pm.joined_at FROM project_members pm JOIN members m ON m.id=pm.member_id WHERE pm.project_id=? ORDER BY pm.joined_at',(pid,))]
@app.post('/api/v1/projects/{pid}/members')
def add_project_member(pid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization)
    mid=b.get('member_id'); role=b.get('role','member'); work_function=b.get('work_function','other')
    if role not in ('member','reviewer','manager'): raise HTTPException(422,'Invalid project role')
    if work_function not in ('developer','tester','product','architect','other'): raise HTTPException(422,'Invalid work function')
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        if role=='manager' and not is_admin(a):
            own=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not own or own['role']!='owner': raise HTTPException(403,'Only project owners may directly grant manager role; use an approval request')
        member_row=c.execute('SELECT tenant_id FROM members WHERE id=?',(mid,)).fetchone()
        project_row=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        if not member_row: raise HTTPException(404,'Member not found')
        if project_row['tenant_id'] != member_row['tenant_id']: raise HTTPException(400,'Member belongs to a different tenant')
        c.execute('INSERT INTO project_members(project_id,member_id,role,work_function,joined_at) VALUES(?,?,?,?,?) ON CONFLICT(project_id,member_id) DO UPDATE SET role=excluded.role,work_function=excluded.work_function',(pid,mid,role,work_function,now()))
        event(c,'project.member.role_set',a['id'],None,{'project_id':pid,'member_id':mid,'role':role},tenant_override=project_row['tenant_id'])
        return {'project_id':pid,'member_id':mid,'role':role,'work_function':work_function}
@app.patch('/api/v1/projects/{pid}/members/{member_id}/function')
def update_project_member_function(pid:str,member_id:str,b:ProjectMemberFunctionIn,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        target=c.execute('SELECT role,work_function FROM project_members WHERE project_id=? AND member_id=?',(pid,member_id)).fetchone()
        if not target: raise HTTPException(404,'Target is not a project member')
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        c.execute('UPDATE project_members SET work_function=? WHERE project_id=? AND member_id=?',(b.work_function,pid,member_id))
        event(c,'project.member.work_function_set',a['id'],None,{'project_id':pid,'member_id':member_id,'work_function':b.work_function},tenant_override=project['tenant_id'])
        return {'project_id':pid,'member_id':member_id,'project_role':target['role'],'work_function':b.work_function}

@app.post('/api/v1/projects/{pid}/role-change-requests')
def request_project_role_change(pid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization); member_id=str(b.get('member_id','')).strip(); new_role=str(b.get('new_role','')).strip()
    reason=str(b.get('reason','')).strip()
    if not member_id or new_role not in ('member','reviewer','manager') or not reason or len(reason)>1000:
        raise HTTPException(422,'member_id, valid new_role and reason (1-1000 chars) are required')
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        target=c.execute('SELECT tenant_id FROM members WHERE id=?',(member_id,)).fetchone()
        project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        if not target or target['tenant_id']!=project['tenant_id']: raise HTTPException(404,'Member not found in project tenant')
        if not c.execute('SELECT 1 FROM project_members WHERE project_id=? AND member_id=?',(pid,member_id)).fetchone(): raise HTTPException(404,'Target is not a project member')
        current=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,member_id)).fetchone()['role']
        if current==new_role: raise HTTPException(409,'Member already has requested role')
        aid='apr_'+uuid.uuid4().hex
        payload={'member_id':member_id,'previous_role':current,'new_role':new_role,'reason':reason}
        c.execute("INSERT INTO project_approvals(id,project_id,tenant_id,requester_member_id,action,payload,status,created_at) VALUES(?,?,?,?,? ,?,'PENDING',?)",
                  (aid,pid,project['tenant_id'],a['id'],'PROJECT_ROLE_CHANGE',json.dumps(payload),now()))
        event(c,'project.role_change.requested',a['id'],None,{'approval_id':aid,'project_id':pid,**payload},tenant_override=project['tenant_id'])
        return {'approval_id':aid,'status':'PENDING','project_id':pid,'payload':payload}

@app.get('/api/v1/projects/{pid}/approvals')
def list_project_approvals(pid:str,status:str='PENDING',limit:int=100,authorization:str=Header(None)):
    a=actor(authorization); limit=max(1,min(limit,200))
    with conn() as c:
        require_project_access(c,pid,a)
        rows=c.execute('SELECT * FROM project_approvals WHERE project_id=? AND status=? ORDER BY created_at DESC LIMIT ?',(pid,status,limit)).fetchall()
        return {'items':[{'id':x['id'],'action':x['action'],'payload':json.loads(x['payload']),'status':x['status'],'requester_member_id':x['requester_member_id'],'decided_by':x['decided_by'],'decision_reason':x['decision_reason'],'created_at':x['created_at'],'decided_at':x['decided_at']} for x in rows]}

@app.post('/api/v1/projects/{pid}/approvals/{approval_id}/decision')
def decide_project_approval(pid:str,approval_id:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization); decision=str(b.get('decision','')).upper(); reason=str(b.get('reason','')).strip()
    if decision not in ('APPROVE','REJECT') or not reason or len(reason)>1000: raise HTTPException(422,'decision must be APPROVE or REJECT and reason is required')
    with conn() as c:
        require_project_access(c,pid,a)
        if not is_admin(a):
            own=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not own or own['role']!='owner': raise HTTPException(403,'Project owner approval required')
        row=c.execute('SELECT * FROM project_approvals WHERE id=? AND project_id=?',(approval_id,pid)).fetchone()
        if not row: raise HTTPException(404,'Approval not found')
        if row['status']!='PENDING': raise HTTPException(409,'Approval already decided')
        if row['requester_member_id']==a['id']: raise HTTPException(403,'Requester cannot approve their own request')
        payload=json.loads(row['payload'])
        if row['action']!='PROJECT_ROLE_CHANGE': raise HTTPException(409,'Unsupported approval action')
        if decision=='APPROVE':
            current=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,payload['member_id'])).fetchone()
            if not current or current['role']!=payload['previous_role']: raise HTTPException(409,'Target role changed since request; submit a new request')
            c.execute('UPDATE project_members SET role=? WHERE project_id=? AND member_id=?',(payload['new_role'],pid,payload['member_id']))
        stamp=now()
        approval_status='APPROVED' if decision=='APPROVE' else 'REJECTED'
        c.execute('UPDATE project_approvals SET status=?,decided_by=?,decision_reason=?,decided_at=? WHERE id=? AND status=?',(approval_status,a['id'],reason,stamp,approval_id,'PENDING'))
        event(c,'project.role_change.'+('approved' if decision=='APPROVE' else 'rejected'),a['id'],None,{'approval_id':approval_id,'project_id':pid,**payload,'decision_reason':reason},tenant_override=row['tenant_id'])
        return {'approval_id':approval_id,'status':approval_status,'member_id':payload['member_id'],'role':payload['new_role'] if decision=='APPROVE' else payload['previous_role']}

@app.get('/api/v1/requirements/{rid}/acceptance-report')
def requirement_acceptance_report(rid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        req=c.execute('SELECT * FROM requirements WHERE id=?',(rid,)).fetchone()
        if not req: raise HTTPException(404,'Requirement not found')
        require_project_access(c,req['project_id'],a)

register_agent_routes(app, conn, actor, is_admin, require_project_access, event, now)
