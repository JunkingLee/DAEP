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