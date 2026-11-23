-- Exercise RLS as a non-owner, non-superuser role. Run after Alembic migrations.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'daep_rls_probe') THEN
    CREATE ROLE daep_rls_probe NOLOGIN NOBYPASSRLS;
  END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO daep_rls_probe;
GRANT SELECT, INSERT, UPDATE, DELETE ON projects, members, events, artifacts, outbox, messages, project_agents, task_delegations, task_work_packages, project_approvals, requirements, tasks, project_members, assignments, dependencies, agents, agent_tokens, agent_project_bindings, agent_task_assignments, artifact_versions TO daep_rls_probe;

INSERT INTO projects (id, name, description, created_by, created_at, tenant_id)
VALUES
  ('rls-probe-a', 'RLS tenant A', '', NULL, now()::text, 'tenant-a'),
  ('rls-probe-b', 'RLS tenant B', '', NULL, now()::text, 'tenant-b')
ON CONFLICT (id) DO UPDATE SET tenant_id = EXCLUDED.tenant_id;

INSERT INTO members (id,name,role,token,created_at,tenant_id)
VALUES
  ('rls-member-a','RLS A','developer','rls-token-a','2026-11-18T00:00:00+00:00','tenant-a'),
  ('rls-member-b','RLS B','developer','rls-token-b','2026-11-18T00:00:00+00:00','tenant-b'),
  ('rls-member-a2','RLS A2','developer','rls-token-a2','2026-11-18T00:00:00+00:00','tenant-a'),
  ('rls-member-am','RLS AM','developer','rls-token-am','2026-11-18T00:00:00+00:00','tenant-a')
ON CONFLICT (id) DO NOTHING;

INSERT INTO requirements (id,project_id,title,description,acceptance_criteria,status,created_at)
VALUES
  ('rls-req-a','rls-probe-a','A requirement','','[]','OPEN','2026-11-18T00:00:00+00:00'),
  ('rls-req-b','rls-probe-b','B requirement','','[]','OPEN','2026-11-18T00:00:00+00:00')
ON CONFLICT (id) DO NOTHING;

INSERT INTO tasks (id,requirement_id,title,description,status,progress,created_at,updated_at)
VALUES
  ('rls-task-a','rls-req-a','A task','','READY',0,'2026-11-18T00:00:00+00:00','2026-11-18T00:00:00+00:00'),
  ('rls-task-b','rls-req-b','B task','','READY',0,'2026-11-18T00:00:00+00:00','2026-11-18T00:00:00+00:00')
ON CONFLICT (id) DO NOTHING;

INSERT INTO agents(id,owner_member_id,tenant_id,name,description,status,created_at,updated_at)
VALUES ('rls-agent-identity-a','rls-member-a','tenant-a','identity-a','','ACTIVE',now()::text,now()::text),
       ('rls-agent-identity-b','rls-member-b','tenant-b','identity-b','','ACTIVE',now()::text,now()::text)
ON CONFLICT (id) DO NOTHING;
INSERT INTO agent_tokens(id,agent_id,tenant_id,token_hash,status,created_at)
VALUES ('rls-agent-token-a','rls-agent-identity-a','tenant-a','hash-a','ACTIVE',now()::text),
       ('rls-agent-token-b','rls-agent-identity-b','tenant-b','hash-b','ACTIVE',now()::text)
ON CONFLICT (id) DO NOTHING;
INSERT INTO agent_project_bindings(project_id,agent_id,tenant_id,role,work_function,status,created_at,updated_at)
VALUES ('rls-probe-a','rls-agent-identity-a','tenant-a','member','developer','ACTIVE',now()::text,now()::text),
       ('rls-probe-b','rls-agent-identity-b','tenant-b','member','developer','ACTIVE',now()::text,now()::text)
ON CONFLICT (project_id,agent_id) DO NOTHING;
INSERT INTO agent_task_assignments(id,task_id,project_id,agent_id,tenant_id,assigned_by_member_id,status,created_at,updated_at)
VALUES ('rls-agent-assignment-a','rls-task-a','rls-probe-a','rls-agent-identity-a','tenant-a','rls-member-a','ASSIGNED',now()::text,now()::text),
       ('rls-agent-assignment-b','rls-task-b','rls-probe-b','rls-agent-identity-b','tenant-b','rls-member-b','ASSIGNED',now()::text,now()::text)
ON CONFLICT (id) DO NOTHING;

INSERT INTO project_members (project_id,member_id,role,joined_at)
VALUES ('rls-probe-a','rls-member-a','owner','2026-11-18T00:00:00+00:00'),
       ('rls-probe-b','rls-member-b','owner','2026-11-18T00:00:00+00:00'),
       ('rls-probe-a','rls-member-a2','member','2026-11-18T00:00:00+00:00'),
       ('rls-probe-a','rls-member-am','manager','2026-11-18T00:00:00+00:00')
ON CONFLICT DO NOTHING;
INSERT INTO assignments (task_id,member_id)
VALUES ('rls-task-a','rls-member-a'),('rls-task-b','rls-member-b')
ON CONFLICT DO NOTHING;

INSERT INTO project_agents(id,project_id,member_id,tenant_id,agent_name,capabilities,protocols,status,metadata,last_seen,created_at,updated_at)
VALUES
 ('rls-agent-a','rls-probe-a','rls-member-a','tenant-a','agent-a','["python"]','["mcp"]','AVAILABLE','{}',now()::text,now()::text,now()::text),
 ('rls-agent-b','rls-probe-b','rls-member-b','tenant-b','agent-b','["python"]','["mcp"]','AVAILABLE','{}',now()::text,now()::text,now()::text)
ON CONFLICT (id) DO NOTHING;

INSERT INTO task_delegations(id,task_id,project_id,tenant_id,requester_member_id,recipient_member_id,agent_name,reason,status,expires_at,created_at,updated_at) VALUES ('rls-delegation-a','rls-task-a','rls-probe-a','tenant-a','rls-member-a','rls-member-a','agent-a','','PENDING','2027-01-01T00:00:00+00:00',now()::text,now()::text), ('rls-delegation-b','rls-task-b','rls-probe-b','tenant-b','rls-member-b','rls-member-b','agent-b','','PENDING','2027-01-01T00:00:00+00:00',now()::text,now()::text) ON CONFLICT (id) DO NOTHING;

INSERT INTO tasks (id,requirement_id,title,description,status,progress,created_at,updated_at) VALUES ('rls-child-a','rls-req-a','A child','','READY',0,now()::text,now()::text),('rls-child-b','rls-req-b','B child','','READY',0,now()::text,now()::text) ON CONFLICT (id) DO NOTHING;
INSERT INTO task_work_packages(id,parent_task_id,child_task_id,project_id,tenant_id,assignee_member_id,agent_name,status,created_at,updated_at) VALUES ('rls-work-package-a','rls-task-a','rls-child-a','rls-probe-a','tenant-a','rls-member-a','agent-a','ACTIVE',now()::text,now()::text),('rls-work-package-b','rls-task-b','rls-child-b','rls-probe-b','tenant-b','rls-member-b','agent-b','ACTIVE',now()::text,now()::text) ON CONFLICT (id) DO NOTHING;
INSERT INTO artifacts(id,task_id,artifact_type,uri,commit_sha,metadata,created_at,tenant_id)
VALUES ('rls-artifact-a','rls-child-a','test_report','https://example.invalid/a','a','{}',now()::text,'tenant-a'),
       ('rls-artifact-b','rls-child-b','test_report','https://example.invalid/b','b','{}',now()::text,'tenant-b')
ON CONFLICT (id) DO NOTHING;
INSERT INTO artifact_versions(id,artifact_id,task_id,work_package_id,version_number,actor_type,actor_member_id,tenant_id,review_status,created_at)
VALUES ('rls-artifact-version-a','rls-artifact-a','rls-child-a','rls-work-package-a',1,'MEMBER','rls-member-a','tenant-a','PENDING',now()::text),
       ('rls-artifact-version-b','rls-artifact-b','rls-child-b','rls-work-package-b',1,'MEMBER','rls-member-b','tenant-b','PENDING',now()::text)
ON CONFLICT (id) DO NOTHING;
INSERT INTO project_approvals(id,project_id,tenant_id,requester_member_id,action,payload,status,created_at) VALUES ('rls-approval-a','rls-probe-a','tenant-a','rls-member-a','PROJECT_ROLE_CHANGE','{}','PENDING',now()::text),('rls-approval-b','rls-probe-b','tenant-b','rls-member-b','PROJECT_ROLE_CHANGE','{}','PENDING',now()::text) ON CONFLICT (id) DO NOTHING;
BEGIN;
SET SESSION AUTHORIZATION daep_rls_probe;
SELECT set_config('app.tenant_id', 'tenant-a', true);
SELECT set_config('app.platform_admin', 'false', true);
SELECT set_config('app.internal_service', 'false', true);
SELECT set_config('app.auth_lookup', 'false', true);

DO $$
DECLARE
  visible_count integer;
  changed_count integer;
BEGIN
  SELECT count(*) INTO visible_count
    FROM projects WHERE id IN ('rls-probe-a', 'rls-probe-b');
  IF visible_count <> 1 THEN
    RAISE EXCEPTION 'RLS read isolation failed: expected 1 visible project, got %', visible_count;
  END IF;

  -- Caller-controlled custom GUCs must not grant privileged bypass.
  PERFORM set_config('app.platform_admin', 'true', true);
  PERFORM set_config('app.internal_service', 'true', true);
  IF (SELECT count(*) FROM projects WHERE id IN ('rls-probe-a','rls-probe-b')) <> 1 THEN
    RAISE EXCEPTION 'RLS privilege escalation: caller-set GUC bypassed tenant isolation';
  END IF;
  PERFORM set_config('app.platform_admin', 'false', true);
  PERFORM set_config('app.internal_service', 'false', true);
  PERFORM set_config('app.auth_lookup', 'true', true);
  IF (SELECT count(*) FROM members WHERE id IN ('rls-member-a','rls-member-b')) <> 1 THEN
    RAISE EXCEPTION 'RLS privilege escalation: caller-forged auth_lookup exposed foreign members';
  END IF;
  PERFORM set_config('app.auth_lookup', 'false', true);
  PERFORM set_config('app.member_id', 'rls-member-a', true);
  PERFORM set_config('app.lifecycle_action', '', true);

  IF (SELECT count(*) FROM project_members WHERE project_id='rls-probe-a' AND member_id='rls-member-a' AND role='owner') <> 1 THEN
    RAISE EXCEPTION 'RLS lifecycle fixture failed: owner membership is not visible to the restricted role';
  END IF;
  IF NOT daep_project_owner('rls-probe-a') THEN
    RAISE EXCEPTION 'RLS lifecycle owner predicate failed: current member is not recognized as project owner';
  END IF;

  -- A tenant member who is not the project owner must not close the project.
  PERFORM set_config('app.member_id', 'rls-member-a2', true);
  BEGIN
    UPDATE projects SET status='CLOSED' WHERE id='rls-probe-a';
    RAISE EXCEPTION 'RLS lifecycle authorization failed: non-owner closed project'
      USING ERRCODE = 'P0001';
  EXCEPTION WHEN insufficient_privilege THEN
    NULL;
  END;
  IF (SELECT status FROM projects WHERE id='rls-probe-a') <> 'ACTIVE' THEN
    RAISE EXCEPTION 'RLS lifecycle authorization failed: non-owner changed project status';
  END IF;
  -- A project manager may close the project, matching the API contract.
  PERFORM set_config('app.member_id', 'rls-member-am', true);
  UPDATE projects SET status='CLOSED' WHERE id='rls-probe-a';
  BEGIN
    UPDATE projects SET name='closed-write-must-fail' WHERE id='rls-probe-a';
    RAISE EXCEPTION 'RLS lifecycle freeze failed: closed project accepted normal write'
      USING ERRCODE = 'P0001';
  EXCEPTION WHEN insufficient_privilege THEN
    NULL;
  END;
  IF (SELECT name FROM projects WHERE id='rls-probe-a') <> 'RLS tenant A' THEN
    RAISE EXCEPTION 'RLS lifecycle freeze failed: closed project data was modified';
  END IF;

  -- A manager may not reopen; owner approval is required.
  PERFORM set_config('app.lifecycle_action', 'REOPEN', true);
  BEGIN
    UPDATE projects SET status='ACTIVE' WHERE id='rls-probe-a';
    RAISE EXCEPTION 'RLS lifecycle authorization failed: manager reopened project'
      USING ERRCODE = 'P0001';
  EXCEPTION WHEN insufficient_privilege THEN
    NULL;
  END;
  PERFORM set_config('app.member_id', 'rls-member-a', true);
  UPDATE projects SET status='ACTIVE' WHERE id='rls-probe-a';
  PERFORM set_config('app.lifecycle_action', '', true);

  IF (SELECT count(*) FROM requirements WHERE id IN ('rls-req-a','rls-req-b')) <> 1 THEN
    RAISE EXCEPTION 'RLS requirement isolation failed';
  END IF;
  IF (SELECT count(*) FROM tasks WHERE id IN ('rls-task-a','rls-task-b')) <> 1 THEN
    RAISE EXCEPTION 'RLS task isolation failed';
  END IF;
  IF (SELECT count(*) FROM project_members WHERE project_id IN ('rls-probe-a','rls-probe-b')) <> 3 THEN
    RAISE EXCEPTION 'RLS project membership isolation failed';
  END IF;
  IF (SELECT count(*) FROM assignments WHERE task_id IN ('rls-task-a','rls-task-b')) <> 1 THEN
    RAISE EXCEPTION 'RLS assignment isolation failed';
  END IF;
  IF (SELECT count(*) FROM agents WHERE id IN ('rls-agent-identity-a','rls-agent-identity-b')) <> 1 THEN
    RAISE EXCEPTION 'RLS Agent identity isolation failed';
  END IF;
  IF (SELECT count(*) FROM agent_tokens WHERE id IN ('rls-agent-token-a','rls-agent-token-b')) <> 1 THEN
    RAISE EXCEPTION 'RLS Agent token isolation failed';
  END IF;
  IF (SELECT count(*) FROM agent_project_bindings WHERE agent_id IN ('rls-agent-identity-a','rls-agent-identity-b')) <> 1 THEN
    RAISE EXCEPTION 'RLS Agent project binding isolation failed';
  END IF;
  IF (SELECT count(*) FROM agent_task_assignments WHERE id IN ('rls-agent-assignment-a','rls-agent-assignment-b')) <> 1 THEN
    RAISE EXCEPTION 'RLS Agent task assignment isolation failed';
  END IF;
  IF (SELECT count(*) FROM artifact_versions WHERE id IN ('rls-artifact-version-a','rls-artifact-version-b')) <> 1 THEN
    RAISE EXCEPTION 'RLS artifact version isolation failed';
  END IF;

  IF (SELECT count(*) FROM project_agents WHERE id IN ('rls-agent-a','rls-agent-b')) <> 1 THEN
    RAISE EXCEPTION 'RLS project Agent isolation failed';
  END IF;

  IF (SELECT count(*) FROM task_delegations WHERE id IN ('rls-delegation-a','rls-delegation-b')) <> 1 THEN
    RAISE EXCEPTION 'RLS task delegation isolation failed';
  END IF;

  IF (SELECT count(*) FROM task_work_packages WHERE id IN ('rls-work-package-a','rls-work-package-b')) <> 1 THEN
    RAISE EXCEPTION 'RLS work package isolation failed';
  END IF;
  IF (SELECT count(*) FROM project_approvals WHERE id IN ('rls-approval-a','rls-approval-b')) <> 1 THEN
    RAISE EXCEPTION 'RLS project approval isolation failed';
  END IF;

  UPDATE agents SET name='cross-tenant-agent-write' WHERE id='rls-agent-identity-b';
  GET DIAGNOSTICS changed_count = ROW_COUNT;
  IF changed_count <> 0 THEN
    RAISE EXCEPTION 'RLS Agent identity update isolation failed';
  END IF;
  UPDATE agent_tokens SET status='REVOKED' WHERE id='rls-agent-token-b';
  GET DIAGNOSTICS changed_count = ROW_COUNT;
  IF changed_count <> 0 THEN
    RAISE EXCEPTION 'RLS Agent token update isolation failed';
  END IF;
  UPDATE agent_project_bindings SET status='DISABLED' WHERE agent_id='rls-agent-identity-b';
  GET DIAGNOSTICS changed_count = ROW_COUNT;
  IF changed_count <> 0 THEN
    RAISE EXCEPTION 'RLS Agent project binding update isolation failed';
  END IF;
  UPDATE agent_task_assignments SET status='REVOKED' WHERE id='rls-agent-assignment-b';
  GET DIAGNOSTICS changed_count = ROW_COUNT;
  IF changed_count <> 0 THEN
    RAISE EXCEPTION 'RLS Agent task assignment update isolation failed';
  END IF;
  UPDATE artifact_versions SET review_status='APPROVED' WHERE id='rls-artifact-version-b';
  GET DIAGNOSTICS changed_count = ROW_COUNT;
  IF changed_count <> 0 THEN
    RAISE EXCEPTION 'RLS artifact version update isolation failed';
  END IF;

  UPDATE projects SET name = 'cross-tenant-write' WHERE id = 'rls-probe-b';
  GET DIAGNOSTICS changed_count = ROW_COUNT;
  IF changed_count <> 0 THEN
    RAISE EXCEPTION 'RLS update isolation failed: modified % foreign rows', changed_count;
  END IF;

  IF NOT daep_tenant_visible('tenant-a') THEN
    RAISE EXCEPTION 'RLS same-tenant insert precondition failed: tenant context is not visible';
  END IF;
  BEGIN
    INSERT INTO projects (id, name, description, created_by, created_at, tenant_id, status)
    VALUES ('rls-probe-a-write', 'Tenant A write', '', NULL, now()::text, 'tenant-a', 'ACTIVE');
  EXCEPTION WHEN OTHERS THEN
    RAISE EXCEPTION 'RLS same-tenant project insert failed: % [SQLSTATE %]', SQLERRM, SQLSTATE;
  END;

  INSERT INTO project_members (project_id,member_id,role,joined_at)
  VALUES ('rls-probe-a','rls-member-a','member',now()::text)
  ON CONFLICT DO NOTHING;

  BEGIN
    INSERT INTO assignments (task_id,member_id) VALUES ('rls-task-a','rls-member-b');
    RAISE EXCEPTION 'RLS assignment write isolation failed';
  EXCEPTION WHEN insufficient_privilege THEN
    NULL;
  END;

  BEGIN
    INSERT INTO dependencies (task_id,depends_on_task_id) VALUES ('rls-task-a','rls-task-b');
    RAISE EXCEPTION 'RLS dependency isolation failed';
  EXCEPTION WHEN insufficient_privilege THEN
    NULL;
  END;

  BEGIN
    INSERT INTO projects (id, name, description, created_by, created_at, tenant_id)
    VALUES ('rls-probe-b-write', 'Tenant B forbidden write', '', NULL, now()::text, 'tenant-b');
    RAISE EXCEPTION 'RLS write isolation failed: foreign tenant insert was accepted';
  EXCEPTION WHEN insufficient_privilege THEN
    NULL;
  END;
END
$$;

RESET SESSION AUTHORIZATION;
COMMIT;
