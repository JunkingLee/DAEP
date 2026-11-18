-- Exercise RLS as a non-owner, non-superuser role. Run after Alembic migrations.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'daep_rls_probe') THEN
    CREATE ROLE daep_rls_probe NOLOGIN NOBYPASSRLS;
  END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO daep_rls_probe;
GRANT SELECT, INSERT, UPDATE, DELETE ON projects, members, events, artifacts, outbox, messages, requirements, tasks, project_members, assignments, dependencies TO daep_rls_probe;

INSERT INTO projects (id, name, description, created_by, created_at, tenant_id)
VALUES
  ('rls-probe-a', 'RLS tenant A', '', NULL, now()::text, 'tenant-a'),
  ('rls-probe-b', 'RLS tenant B', '', NULL, now()::text, 'tenant-b')
ON CONFLICT (id) DO UPDATE SET tenant_id = EXCLUDED.tenant_id;

INSERT INTO members (id,name,role,token,created_at,tenant_id)
VALUES
  ('rls-member-a','RLS A','developer','rls-token-a','2026-11-18T00:00:00+00:00','tenant-a'),
  ('rls-member-b','RLS B','developer','rls-token-b','2026-11-18T00:00:00+00:00','tenant-b')
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

INSERT INTO project_members (project_id,member_id,role,joined_at)
VALUES ('rls-probe-a','rls-member-a','owner','2026-11-18T00:00:00+00:00'),
       ('rls-probe-b','rls-member-b','owner','2026-11-18T00:00:00+00:00')
ON CONFLICT DO NOTHING;
INSERT INTO assignments (task_id,member_id)
VALUES ('rls-task-a','rls-member-a'),('rls-task-b','rls-member-b')
ON CONFLICT DO NOTHING;

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

  IF (SELECT count(*) FROM requirements WHERE id IN ('rls-req-a','rls-req-b')) <> 1 THEN
    RAISE EXCEPTION 'RLS requirement isolation failed';
  END IF;
  IF (SELECT count(*) FROM tasks WHERE id IN ('rls-task-a','rls-task-b')) <> 1 THEN
    RAISE EXCEPTION 'RLS task isolation failed';
  END IF;
  IF (SELECT count(*) FROM project_members WHERE project_id IN ('rls-probe-a','rls-probe-b')) <> 1 THEN
    RAISE EXCEPTION 'RLS project membership isolation failed';
  END IF;
  IF (SELECT count(*) FROM assignments WHERE task_id IN ('rls-task-a','rls-task-b')) <> 1 THEN
    RAISE EXCEPTION 'RLS assignment isolation failed';
  END IF;

  UPDATE projects SET name = 'cross-tenant-write' WHERE id = 'rls-probe-b';
  GET DIAGNOSTICS changed_count = ROW_COUNT;
  IF changed_count <> 0 THEN
    RAISE EXCEPTION 'RLS update isolation failed: modified % foreign rows', changed_count;
  END IF;

  INSERT INTO projects (id, name, description, created_by, created_at, tenant_id)
  VALUES ('rls-probe-a-write', 'Tenant A write', '', NULL, now()::text, 'tenant-a');

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
