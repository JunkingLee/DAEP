import os, json, sqlite3, uuid, asyncio, hashlib, base64, secrets, urllib.parse, urllib.request, time, contextvars, hmac
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
    yield

app=FastAPI(title='DAEP Enterprise Platform API',version='1.0.0-rc9',description='Task-centric distributed agent engineering platform',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=os.getenv('CORS_ORIGINS','http://localhost:3000').split(','),allow_credentials=False,allow_methods=['*'],allow_headers=['*'])
@app.middleware('http')
async def tenant_context(request, call_next):
    token=request.headers.get('authorization','')
    tok=token[7:] if token.startswith('Bearer ') else ''
    reset_tenant=_tenant_ctx.set('')
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
        _tenant_ctx.reset(reset_tenant); _admin_ctx.reset(reset_admin); _service_ctx.reset(reset_service)

@app.middleware('http')
async def security_headers(request, call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    return response

class ProjectIn(BaseModel): name:str=Field(min_length=1,max_length=160); description:str=Field(default='',max_length=5000)
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
def now(): return datetime.now(timezone.utc).isoformat()
DATABASE_URL=os.getenv('DATABASE_URL','')
PRIVILEGED_DATABASE_URL=os.getenv('DAEP_PRIVILEGED_DATABASE_URL','')
_tenant_ctx=contextvars.ContextVar('daep_tenant_id',default='')
_admin_ctx=contextvars.ContextVar('daep_platform_admin',default=False)
_auth_lookup_ctx=contextvars.ContextVar('daep_auth_lookup',default=False)
_service_ctx=contextvars.ContextVar('daep_internal_service',default=False)

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
        self.c.execute("SELECT set_config('app.tenant_id', %s, false), set_config('app.platform_admin', %s, false), set_config('app.internal_service', %s, false), set_config('app.auth_lookup', %s, false)",(
            _tenant_ctx.get() or '', 'true' if _admin_ctx.get() else 'false', 'true' if _service_ctx.get() else 'false', 'true' if _auth_lookup_ctx.get() else 'false'))
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
        CREATE TABLE IF NOT EXISTS members(id TEXT PRIMARY KEY,name TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'developer',token TEXT UNIQUE NOT NULL,created_at TEXT NOT NULL,tenant_id TEXT NOT NULL DEFAULT 'tenant-default',token_status TEXT NOT NULL DEFAULT 'ACTIVE',token_created_at TEXT,token_revoked_at TEXT,token_expires_at TEXT,oidc_subject TEXT,oidc_email TEXT);
        CREATE TABLE IF NOT EXISTS schema_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS oidc_states(state_hash TEXT PRIMARY KEY,nonce TEXT NOT NULL,code_verifier TEXT NOT NULL,expires_at TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT,created_by TEXT,created_at TEXT NOT NULL,tenant_id TEXT NOT NULL DEFAULT 'tenant-default');
        CREATE TABLE IF NOT EXISTS project_members(project_id TEXT NOT NULL,member_id TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'member',joined_at TEXT NOT NULL,PRIMARY KEY(project_id,member_id),FOREIGN KEY(project_id) REFERENCES projects(id),FOREIGN KEY(member_id) REFERENCES members(id));
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
        table_cols = {
            'members': {r['name'] for r in c.execute('PRAGMA table_info(members)').fetchall()},
            'projects': {r['name'] for r in c.execute('PRAGMA table_info(projects)').fetchall()},
            'events': {r['name'] for r in c.execute('PRAGMA table_info(events)').fetchall()},
            'artifacts': {r['name'] for r in c.execute('PRAGMA table_info(artifacts)').fetchall()},
            'outbox': {r['name'] for r in c.execute('PRAGMA table_info(outbox)').fetchall()},
        }
        for col, ddl in [('tenant_id', "TEXT NOT NULL DEFAULT 'tenant-default'"),('token_status',"TEXT NOT NULL DEFAULT 'ACTIVE'"),('token_created_at','TEXT'),('token_revoked_at','TEXT'),('token_expires_at','TEXT'),('oidc_subject','TEXT'),('oidc_email','TEXT')]:
            if col not in table_cols['members']: c.execute(f'ALTER TABLE members ADD COLUMN {col} {ddl}')
        for table in ('projects','events','artifacts','outbox'):
            if 'tenant_id' not in table_cols[table]: c.execute(f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'tenant-default'")
        if 'lease_token' not in table_cols['outbox']:
            c.execute('ALTER TABLE outbox ADD COLUMN lease_token TEXT')
        c.execute("CREATE INDEX IF NOT EXISTS idx_members_tenant ON members(tenant_id)")
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
def actor(authorization):
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
    project=c.execute('SELECT tenant_id FROM projects WHERE id=?',(project_id,)).fetchone()
    if not project: raise HTTPException(404,'Project not found')
    if project['tenant_id'] != a.get('tenant_id','tenant-default') and not is_admin(a): raise HTTPException(403,'Tenant isolation violation')
    if is_admin(a): return
    row=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(project_id,a['id'])).fetchone()
    if not row: raise HTTPException(403,'Project membership required')
    if write and row['role'] not in ('owner','manager'): raise HTTPException(403,'Project manager role required')
def task_project(c, tid):
    r=c.execute('SELECT r.project_id FROM tasks t JOIN requirements r ON r.id=t.requirement_id WHERE t.id=?',(tid,)).fetchone()
    return r['project_id'] if r else None
def require_task_access(c, tid, a, assigned_only=False):
    pid=task_project(c,tid)
    if not pid: raise HTTPException(404,'Task not found')
    if is_admin(a): return
    if assigned_only:
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
    try:
        c.execute('INSERT INTO events(id,event_type,actor_member_id,task_id,payload,created_at,idempotency_key,tenant_id) VALUES(?,?,?,?,?,?,?,?)',(eid,typ,member,task,json.dumps(payload),now(),key,tenant))
    except sqlite3.IntegrityError:
        if key: return c.execute('SELECT id FROM events WHERE idempotency_key=?',(key,)).fetchone()['id']
        raise
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
        c.execute('INSERT INTO project_members VALUES(?,?,?,?)',(pid,a['id'],'owner',now()))
    return {'id':pid,'name':b.name,'description':b.description}
@app.get('/api/v1/projects')
def projects(authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        if is_admin(a): rows=c.execute('SELECT * FROM projects ORDER BY created_at DESC')
        else: rows=c.execute('SELECT p.* FROM projects p JOIN project_members pm ON pm.project_id=p.id WHERE pm.member_id=? AND p.tenant_id=? ORDER BY p.created_at DESC',(a['id'],a.get('tenant_id','tenant-default')))
        return [dict(x) for x in rows]
@app.get('/api/v1/projects/{pid}/members')
def project_members(pid:str,authorization:str=Header(None)):
    a=actor(authorization)
    with conn() as c:
        require_project_access(c,pid,a)
        return [dict(x) for x in c.execute('SELECT m.id,m.name,m.role AS account_role,pm.role AS project_role,pm.joined_at FROM project_members pm JOIN members m ON m.id=pm.member_id WHERE pm.project_id=? ORDER BY pm.joined_at',(pid,))]
@app.post('/api/v1/projects/{pid}/members')
def add_project_member(pid:str,b:dict,authorization:str=Header(None)):
    a=actor(authorization)
    mid=b.get('member_id'); role=b.get('role','member')
    if role not in ('member','reviewer','manager'): raise HTTPException(422,'Invalid project role')
    with conn() as c:
        require_project_access(c,pid,a,write=True)
        if role=='manager' and not is_admin(a):
            own=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not own or own['role']!='owner': raise HTTPException(403,'Only project owners may directly grant manager role; use an approval request')
        member_row=c.execute('SELECT tenant_id FROM members WHERE id=?',(mid,)).fetchone()
        project_row=c.execute('SELECT tenant_id FROM projects WHERE id=?',(pid,)).fetchone()
        if not member_row: raise HTTPException(404,'Member not found')
        if project_row['tenant_id'] != member_row['tenant_id']: raise HTTPException(400,'Member belongs to a different tenant')
        c.execute('INSERT INTO project_members(project_id,member_id,role,joined_at) VALUES(?,?,?,?) ON CONFLICT(project_id,member_id) DO UPDATE SET role=excluded.role',(pid,mid,role,now()))
        event(c,'project.member.role_set',a['id'],None,{'project_id':pid,'member_id':mid,'role':role},tenant_override=project_row['tenant_id'])
        return {'project_id':pid,'member_id':mid,'role':role}
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
            c.execute('INSERT OR IGNORE INTO project_members VALUES(?,?,?,?)',(req['project_id'],mid,'member',now()))
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
        scoped_key=f"{a['id']}:{tid}:{idempotency_key}" if idempotency_key else None
        if scoped_key:
            prior=c.execute('SELECT id,payload FROM events WHERE idempotency_key=?',(scoped_key,)).fetchone()
            if prior:
                if prior['payload'] != json.dumps(b.model_dump()): raise HTTPException(409,'Idempotency-Key was already used with a different payload')
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
        require_task_access(c,tid,a,assigned_only=True)
        package=c.execute('SELECT id,parent_task_id,status,correlation_id FROM task_work_packages WHERE child_task_id=?',(tid,)).fetchone()
        if not package: raise HTTPException(404,'Task is not a registered work package')
        if package['status']!='ACTIVE': raise HTTPException(409,'Work package is no longer active')
        key=f"work-result:{a['id']}:{tid}:{b.idempotency_key}" if b.idempotency_key else None
        payload={'outcome':b.outcome,'summary':b.summary,'work_package_id':package['id'],'correlation_id':package['correlation_id'],'parent_task_id':package['parent_task_id']}
        if key:
            prior=c.execute('SELECT id,payload FROM events WHERE idempotency_key=?',(key,)).fetchone()
            if prior:
                if prior['payload']!=json.dumps(payload): raise HTTPException(409,'Idempotency key was used with a different result')
                return {'task_id':tid,'status':'REVIEW' if b.outcome=='COMPLETE' else 'BLOCKED','event_id':prior['id'],'idempotent_replay':True}
        if b.outcome=='COMPLETE':
            count=c.execute('SELECT COUNT(*) AS n FROM artifacts WHERE task_id=?',(tid,)).fetchone()['n']
            if count<1: raise HTTPException(409,'Submit at least one artifact before reporting completion')
            status='REVIEW'; progress=100
        else:
            status='BLOCKED'; progress=0
        c.execute('UPDATE tasks SET status=?,progress=?,updated_at=? WHERE id=?',(status,progress,now(),tid))
        eid=event(c,'task.work_package.reported',a['id'],tid,payload,key)
    return {'task_id':tid,'status':status,'event_id':eid,'outcome':b.outcome}

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
    if decision not in ('APPROVE','REJECT'): raise HTTPException(422,'decision must be APPROVE or REJECT')
    with conn() as c:
        pid=task_project(c,tid)
        if not pid: raise HTTPException(404,'Task not found')
        if is_admin(a): pass
        else:
            row=c.execute('SELECT role FROM project_members WHERE project_id=? AND member_id=?',(pid,a['id'])).fetchone()
            if not row or row['role'] not in ('owner','manager','reviewer'): raise HTTPException(403,'Reviewer role required')
        task=c.execute('SELECT status FROM tasks WHERE id=?',(tid,)).fetchone()
        if task['status']!='REVIEW': raise HTTPException(409,'Task is not awaiting review')
        if decision=='APPROVE':
            packages=c.execute("SELECT w.child_task_id,t.status FROM task_work_packages w JOIN tasks t ON t.id=w.child_task_id WHERE w.parent_task_id=? AND w.status='ACTIVE'",(tid,)).fetchall()
            pending=[x['child_task_id'] for x in packages if x['status']!='DONE']
            missing=[x['child_task_id'] for x in packages if c.execute('SELECT 1 FROM artifacts WHERE task_id=? LIMIT 1',(x['child_task_id'],)).fetchone() is None]
            if pending or missing:
                raise HTTPException(409,detail={'message':'Parent task cannot be approved until every active work package is approved and has at least one artifact','pending_work_packages':pending,'missing_artifacts':missing})
        status='DONE' if decision=='APPROVE' else 'IN_PROGRESS'
        c.execute('UPDATE tasks SET status=?,progress=?,updated_at=? WHERE id=?',(status,100 if decision=='APPROVE' else 90,now(),tid))
        eid=event(c,'task.reviewed',a['id'],tid,{'decision':decision,'comment':b.get('comment','')})
        return {'task_id':tid,'status':status,'event_id':eid}

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
        package=c.execute('SELECT * FROM task_work_packages WHERE id=?',(package_id,)).fetchone()
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
        row=c.execute('SELECT * FROM task_delegations WHERE id=?',(did,)).fetchone()
        if not row or row['recipient_member_id'] != a['id']: raise HTTPException(404,'Delegation not found')
        if row['status'] != 'PENDING': raise HTTPException(409,'Delegation is no longer pending')
        if row['expires_at'] <= now():
            c.execute("UPDATE task_delegations SET status='EXPIRED',updated_at=? WHERE id=?",(now(),did))
            event(c,'task.delegation.expired',a['id'],row['task_id'],{'delegation_id':did})
            return JSONResponse(status_code=410,content={'detail':'Delegation offer has expired','status':'EXPIRED'})
        if decision=='ACCEPT':
            c.execute('INSERT OR IGNORE INTO assignments(task_id,member_id) VALUES(?,?)',(row['task_id'],a['id']))
            c.execute('INSERT OR IGNORE INTO project_members(project_id,member_id,role,joined_at) VALUES(?,?,?,?)',(row['project_id'],a['id'],'member',now()))
            status='ACCEPTED'
        else: status='REJECTED'
        stamp=now()
        c.execute('UPDATE task_delegations SET status=?,responded_at=?,updated_at=? WHERE id=? AND status=\'PENDING\'',(status,stamp,stamp,did))
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
                c.execute("UPDATE task_delegations SET status='EXPIRED',updated_at=? WHERE id=? AND status='PENDING'",(now(),row['id']))
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
                c.execute("UPDATE task_delegations SET status='EXPIRED',updated_at=? WHERE id=? AND status='PENDING'",(now(),row['id']))
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
def ack(mid:str,b:AckIn,authorization:str=Header(None)):
    a=actor(authorization)
    if b.status not in ('ACKNOWLEDGED','REJECTED'): raise HTTPException(422,'Invalid acknowledgement status')
    with conn() as c:
        existing=c.execute('SELECT status FROM messages WHERE id=? AND recipient_member_id=?',(mid,a['id'])).fetchone()
        if not existing: raise HTTPException(404,'Message not found for current member')
        if existing['status'] in ('ACKNOWLEDGED','REJECTED'):
            if existing['status'] != b.status: raise HTTPException(409,'Message has already reached a different terminal status')
            return {'id':mid,'status':existing['status'],'idempotent':True}
        cur=c.execute("UPDATE messages SET status=?,acked_at=? WHERE id=? AND recipient_member_id=? AND status='PENDING'",(b.status,now(),mid,a['id']))
        if cur.rowcount==0: raise HTTPException(409,'Message status changed; retry the request')
        event(c,'message.acknowledged',a['id'],None,{'message_id':mid,'status':b.status})
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
