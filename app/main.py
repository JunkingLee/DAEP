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