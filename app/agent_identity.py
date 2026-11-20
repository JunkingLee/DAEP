import hashlib, secrets, uuid, json
from fastapi import Header, HTTPException
from pydantic import BaseModel, Field

class AgentCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default='', max_length=2000)

class AgentUpdateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default='', max_length=2000)
    status: str = Field(default='ACTIVE', pattern='^(ACTIVE|DISABLED)$')

class AgentProjectBindingIn(BaseModel):
    project_id: str = Field(min_length=1, max_length=120)
    role: str = Field(default='member', pattern='^(member|reviewer|manager)$')
    work_function: str = Field(default='other', pattern='^(developer|tester|product|architect|other)$')

def ensure_agent_schema(conn):
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS agents(
            id TEXT PRIMARY KEY,
            owner_member_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_seen_at TEXT,
            FOREIGN KEY(owner_member_id) REFERENCES members(id)
        )""")
        c.execute("""CREATE INDEX IF NOT EXISTS idx_agents_owner ON agents(owner_member_id,status)""")
        c.execute("""CREATE TABLE IF NOT EXISTS agent_tokens(
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            token_hash TEXT UNIQUE NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            created_at TEXT NOT NULL,
            last_used_at TEXT,
            expires_at TEXT,
            revoked_at TEXT,
            FOREIGN KEY(agent_id) REFERENCES agents(id)
        )""")
        c.execute("""CREATE INDEX IF NOT EXISTS idx_agent_tokens_agent ON agent_tokens(agent_id,status)""")
        c.execute("""CREATE TABLE IF NOT EXISTS agent_project_bindings(
            project_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            work_function TEXT NOT NULL DEFAULT 'other',
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(project_id,agent_id),
            FOREIGN KEY(project_id) REFERENCES projects(id),
            FOREIGN KEY(agent_id) REFERENCES agents(id)
        )""")
        c.execute("""CREATE INDEX IF NOT EXISTS idx_agent_project_bindings_agent ON agent_project_bindings(agent_id,status)""")

def _token():
    return 'daep_at_' + secrets.token_urlsafe(36)

def _hash(raw):
    return hashlib.sha256(raw.encode()).hexdigest()

def _agent_owner(c, agent_id, a):
    row=c.execute("SELECT * FROM agents WHERE id=? AND tenant_id=?",(agent_id,a.get('tenant_id','tenant-default'))).fetchone()
    if not row: raise HTTPException(404,'Agent not found')
    if not is_admin(a) and row['owner_member_id'] != a['id']:
        raise HTTPException(403,'Agent owner permission required')
    return row

def _issue(c, agent_id, timestamp):
    raw=_token()
    c.execute("UPDATE agent_tokens SET status='REVOKED',revoked_at=? WHERE agent_id=? AND status='ACTIVE'",(timestamp,agent_id))
    tid='agtok_'+uuid.uuid4().hex
    c.execute("INSERT INTO agent_tokens(id,agent_id,token_hash,status,created_at) VALUES(?,?,?,?,?)",(tid,agent_id,_hash(raw),'ACTIVE',timestamp))
    return raw,tid

def authenticate_agent_token(conn, raw_token):
    if not raw_token or not raw_token.startswith('daep_at_'):
        raise HTTPException(401,'Invalid Agent token')
    with conn() as c:
        row=c.execute("""SELECT t.id token_id,t.agent_id,a.owner_member_id,a.tenant_id,a.status agent_status,t.status token_status,t.expires_at
                         FROM agent_tokens t JOIN agents a ON a.id=t.agent_id
                         WHERE t.token_hash=?""",(_hash(raw_token),)).fetchone()
        if not row or row['token_status']!='ACTIVE' or row['agent_status']!='ACTIVE':
            raise HTTPException(401,'Invalid or revoked Agent token')
        if row['expires_at'] and row['expires_at'] <= now():
            raise HTTPException(401,'Agent token expired')
        c.execute("UPDATE agent_tokens SET last_used_at=? WHERE id=?",(now(),row['token_id']))
        c.execute("UPDATE agents SET last_seen_at=?,updated_at=? WHERE id=?",(now(),now(),row['agent_id']))
        return dict(row)

def register_agent_routes(app, conn, actor, is_admin, require_project_access, event, now):

    @app.get('/api/v1/agents')
    def list_agents(authorization: str = Header(default='')):
        a=actor(authorization)
        with conn() as c:
            if is_admin(a):
                rows=c.execute("SELECT id,name,description,status,owner_member_id,created_at,updated_at,last_seen_at FROM agents WHERE tenant_id=? ORDER BY created_at DESC",(a.get('tenant_id','tenant-default'),)).fetchall()
            else:
                rows=c.execute("SELECT id,name,description,status,owner_member_id,created_at,updated_at,last_seen_at FROM agents WHERE tenant_id=? AND owner_member_id=? ORDER BY created_at DESC",(a.get('tenant_id','tenant-default'),a['id'])).fetchall()
            out=[]
            for r in rows:
                b=c.execute("""SELECT b.project_id,p.name project_name,b.role,b.work_function,b.status
                               FROM agent_project_bindings b JOIN projects p ON p.id=b.project_id
                               WHERE b.agent_id=? ORDER BY p.name""",(r['id'],)).fetchall()
                out.append({**dict(r),'projects':[dict(x) for x in b]})
            return out

    @app.post('/api/v1/agents')
    def create_agent(body: AgentCreateIn, authorization: str = Header(default='')):
        a=actor(authorization)
        aid='agt_'+uuid.uuid4().hex[:16]
        ts=now()
        with conn() as c:
            c.execute("INSERT INTO agents(id,owner_member_id,tenant_id,name,description,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                      (aid,a['id'],a.get('tenant_id','tenant-default'),body.name,body.description,'ACTIVE',ts,ts))
            raw,token_id=_issue(c,aid,ts)
            event(c,'agent.created',a['id'],None,{'agent_id':aid,'name':body.name})
            event(c,'agent.token.issued',a['id'],None,{'agent_id':aid,'token_id':token_id})
            return {'agent':dict(c.execute("SELECT id,name,description,status,owner_member_id,created_at,updated_at,last_seen_at FROM agents WHERE id=?",(aid,)).fetchone()),'token':raw,'token_id':token_id,'token_once':True}

    @app.get('/api/v1/agents/{agent_id}')
    def get_agent(agent_id: str, authorization: str = Header(default='')):
        a=actor(authorization)
        with conn() as c:
            r=_agent_owner(c,agent_id,a)
            b=c.execute("""SELECT b.project_id,p.name project_name,b.role,b.work_function,b.status
                           FROM agent_project_bindings b JOIN projects p ON p.id=b.project_id
                           WHERE b.agent_id=? ORDER BY p.name""",(agent_id,)).fetchall()
            t=c.execute("SELECT id,status,created_at,last_used_at,expires_at,revoked_at FROM agent_tokens WHERE agent_id=? ORDER BY created_at DESC",(agent_id,)).fetchall()
            return {**dict(r),'projects':[dict(x) for x in b],'tokens':[dict(x) for x in t]}

    @app.patch('/api/v1/agents/{agent_id}')
    def update_agent(agent_id: str, body: AgentUpdateIn, authorization: str = Header(default='')):
        a=actor(authorization)
        with conn() as c:
            r=_agent_owner(c,agent_id,a)
            c.execute("UPDATE agents SET name=?,description=?,status=?,updated_at=? WHERE id=?",(body.name,body.description,body.status,now(),agent_id))
            event(c,'agent.updated',a['id'],None,{'agent_id':agent_id})
            return dict(c.execute("SELECT id,name,description,status,owner_member_id,created_at,updated_at,last_seen_at FROM agents WHERE id=?",(agent_id,)).fetchone())

    @app.post('/api/v1/agents/{agent_id}/tokens/rotate')
    def rotate_agent_token(agent_id: str, authorization: str = Header(default='')):
        a=actor(authorization)
        with conn() as c:
            _agent_owner(c,agent_id,a)
            raw,token_id=_issue(c,agent_id,now())
            event(c,'agent.token.rotated',a['id'],None,{'agent_id':agent_id,'token_id':token_id})
            return {'agent_id':agent_id,'token':raw,'token_id':token_id,'token_once':True}

    @app.post('/api/v1/agents/{agent_id}/tokens/revoke')
    def revoke_agent_token(agent_id: str, authorization: str = Header(default='')):
        a=actor(authorization)
        with conn() as c:
            _agent_owner(c,agent_id,a)
            ts=now()
            c.execute("UPDATE agent_tokens SET status='REVOKED',revoked_at=? WHERE agent_id=? AND status='ACTIVE'",(ts,agent_id))
            event(c,'agent.token.revoked',a['id'],None,{'agent_id':agent_id})
            return {'agent_id':agent_id,'status':'REVOKED'}

    @app.post('/api/v1/agents/{agent_id}/projects')
    def bind_agent(agent_id: str, body: AgentProjectBindingIn, authorization: str = Header(default='')):
        a=actor(authorization)
        with conn() as c:
            project=c.execute("SELECT tenant_id,status FROM projects WHERE id=?",(body.project_id,)).fetchone()
            if not project: raise HTTPException(404,'Project not found')
            if project['tenant_id'] != a.get('tenant_id','tenant-default'): raise HTTPException(403,'Tenant isolation violation')
            if project['status']=='CLOSED': raise HTTPException(409,'Project is closed')
            if not is_admin(a):
                prow=c.execute("SELECT role FROM project_members WHERE project_id=? AND member_id=?",(body.project_id,a['id'])).fetchone()
                if not prow or prow['role'] not in ('owner','manager'):
                    raise HTTPException(403,'Project manager role required')
            r=c.execute("SELECT * FROM agents WHERE id=? AND tenant_id=? AND status='ACTIVE'",(agent_id,project['tenant_id'])).fetchone()
            if not r: raise HTTPException(404,'Agent not found or inactive')
            ts=now()
            c.execute("""INSERT INTO agent_project_bindings(project_id,agent_id,tenant_id,role,work_function,status,created_at,updated_at)
                         VALUES(?,?,?,?,?,?,?,?)
                         ON CONFLICT(project_id,agent_id) DO UPDATE SET role=excluded.role,work_function=excluded.work_function,status='ACTIVE',updated_at=excluded.updated_at""",
                      (body.project_id,agent_id,project['tenant_id'],body.role,body.work_function,'ACTIVE',ts,ts))
            event(c,'agent.project.bound',a['id'],None,{'agent_id':agent_id,'project_id':body.project_id,'role':body.role,'work_function':body.work_function})
            return {'project_id':body.project_id,'agent_id':agent_id,'role':body.role,'work_function':body.work_function,'status':'ACTIVE'}

    @app.delete('/api/v1/agents/{agent_id}/projects/{project_id}')
    def unbind_agent(agent_id: str, project_id: str, authorization: str = Header(default='')):
        a=actor(authorization)
        with conn() as c:
            _agent_owner(c,agent_id,a)
            if not is_admin(a):
                prow=c.execute("SELECT role FROM project_members WHERE project_id=? AND member_id=?",(project_id,a['id'])).fetchone()
                if not prow or prow['role'] not in ('owner','manager'): raise HTTPException(403,'Project manager role required')
            c.execute("DELETE FROM agent_project_bindings WHERE agent_id=? AND project_id=?",(agent_id,project_id))
            event(c,'agent.project.unbound',a['id'],None,{'agent_id':agent_id,'project_id':project_id})
            return {'status':'UNBOUND'}

    @app.get('/api/v1/mcp/context')
    def mcp_context(authorization: str = Header(default='')):
        raw=authorization[7:] if authorization.startswith('Bearer ') else ''
        ident=authenticate_agent_token(conn,raw)
        with conn() as c:
            projects=c.execute("""SELECT b.project_id,p.name,b.role,b.work_function,p.status
                                  FROM agent_project_bindings b JOIN projects p ON p.id=b.project_id
                                  WHERE b.agent_id=? AND b.status='ACTIVE'""",(ident['agent_id'],)).fetchall()
            return {'actor_type':'AGENT','agent_id':ident['agent_id'],'owner_member_id':ident['owner_member_id'],'tenant_id':ident['tenant_id'],'projects':[dict(x) for x in projects]}

    return ensure_agent_schema
