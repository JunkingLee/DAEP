# RC24 Restored Database Verification Gate

RC24 adds a mandatory, repeatable post-restore verification step. A successful `pg_restore` only proves that PostgreSQL accepted the restore operation; it does not prove the restored database is safe to receive application traffic.

## Runbook

1. Provision a separate, empty target database in the production PostgreSQL cluster. Do not use the live source database.
2. Restore the verified backup using `scripts/restore_postgres.sh` with the explicit confirmation variable.
3. Install the repository's pinned Python requirements on the deployment operator host so the local `alembic` command is available.
4. Set `DAEP_RESTORE_DATABASE` to the isolated target database and run:

   ```sh
   DAEP_RESTORE_DATABASE=daep_restore scripts/verify_restored_postgres.sh
   ```

5. Do not switch application traffic unless the verification exits successfully and the deployment owner separately completes API read/write, tenant-isolation, and operational smoke tests.

## What the gate verifies

- The restored `alembic_version` equals the repository's current Alembic head.
- All 15 tenant-scoped application tables exist with both RLS enabled and FORCE RLS enabled.
- All 15 expected tenant policies exist.
- The narrow SECURITY DEFINER member-authentication function exists.
- Runtime, privileged, and authenticator database roles retain their intended login/BYPASSRLS boundaries.
- The privileged login remains a member of the non-login `daep_privileged` role.

The script reads only catalog metadata and does not modify the target database. It requires Docker Compose access to the PostgreSQL service, the cluster-level DAEP roles, and a provisioned target database.

## Limits

This is an executable catalog/preflight gate, not a substitute for a real disaster-recovery exercise. CI validates script syntax and static invariants; it does not run a production backup, restore, API traffic cutover, TLS/OIDC, external broker, or MCP Host connectivity test. Record the backup identifier, restore timestamp, target database, verifier output, operator, and approval in the deployment evidence.
