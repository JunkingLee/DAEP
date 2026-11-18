-- Exercise RLS as a non-owner, non-superuser role. Run after Alembic migrations.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'daep_rls_probe') THEN
    CREATE ROLE daep_rls_probe NOLOGIN NOBYPASSRLS;
  END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO daep_rls_probe;
GRANT SELECT, INSERT, UPDATE, DELETE ON projects, members, events, artifacts, outbox, messages TO daep_rls_probe;

INSERT INTO projects (id, name, description, created_by, created_at, tenant_id)
VALUES
  ('rls-probe-a', 'RLS tenant A', '', NULL, now()::text, 'tenant-a'),
  ('rls-probe-b', 'RLS tenant B', '', NULL, now()::text, 'tenant-b')
ON CONFLICT (id) DO UPDATE SET tenant_id = EXCLUDED.tenant_id;

SET ROLE daep_rls_probe;
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

  UPDATE projects SET name = 'cross-tenant-write' WHERE id = 'rls-probe-b';
  GET DIAGNOSTICS changed_count = ROW_COUNT;
  IF changed_count <> 0 THEN
    RAISE EXCEPTION 'RLS update isolation failed: modified % foreign rows', changed_count;
  END IF;

  INSERT INTO projects (id, name, description, created_by, created_at, tenant_id)
  VALUES ('rls-probe-a-write', 'Tenant A write', '', NULL, now()::text, 'tenant-a');

  BEGIN
    INSERT INTO projects (id, name, description, created_by, created_at, tenant_id)
    VALUES ('rls-probe-b-write', 'Tenant B forbidden write', '', NULL, now()::text, 'tenant-b');
    RAISE EXCEPTION 'RLS write isolation failed: foreign tenant insert was accepted';
  EXCEPTION WHEN insufficient_privilege THEN
    NULL;
  END;
END
$$;

RESET ROLE;
