"""RC42: immutable artifact submission versions and exact-version review state."""
from alembic import op

revision = "0032_rc42_artifact_versions"
down_revision = "0031_rc41_member_auth_status"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("""
        CREATE TABLE IF NOT EXISTS artifact_versions (
            id TEXT PRIMARY KEY,
            artifact_id TEXT NOT NULL UNIQUE REFERENCES artifacts(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            work_package_id TEXT REFERENCES task_work_packages(id),
            version_number INTEGER NOT NULL CHECK (version_number > 0),
            actor_type TEXT NOT NULL DEFAULT 'MEMBER' CHECK (actor_type IN ('MEMBER','AGENT')),
            actor_member_id TEXT REFERENCES members(id),
            agent_id TEXT,
            tenant_id TEXT NOT NULL,
            review_status TEXT NOT NULL DEFAULT 'PENDING' CHECK (review_status IN ('PENDING','APPROVED','REJECTED')),
            review_comment TEXT,
            reviewed_by_member_id TEXT REFERENCES members(id),
            reviewed_at TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(task_id, version_number),
            CHECK ((actor_type='AGENT' AND agent_id IS NOT NULL AND actor_member_id IS NULL)
                OR (actor_type='MEMBER' AND agent_id IS NULL))
        )
    """)
    op.execute("""
        WITH ranked AS (
            SELECT a.*,
                   ROW_NUMBER() OVER (PARTITION BY a.task_id ORDER BY a.created_at, a.id) AS version_number
            FROM artifacts a
        )
        INSERT INTO artifact_versions (
            id, artifact_id, task_id, work_package_id, version_number,
            actor_type, actor_member_id, agent_id, tenant_id, review_status, created_at
        )
        SELECT
            'av_' || substr(md5(r.id), 1, 24),
            r.id,
            r.task_id,
            wp.id,
            r.version_number,
            COALESCE(ev.payload->>'actor_type', 'MEMBER'),
            CASE WHEN ev.payload->>'actor_type' = 'AGENT' THEN NULL ELSE ev.actor_member_id END,
            ev.payload->>'agent_id',
            r.tenant_id,
            'PENDING',
            COALESCE(r.created_at, now()::text)
        FROM ranked r
        LEFT JOIN task_work_packages wp ON wp.child_task_id = r.task_id
        LEFT JOIN LATERAL (
            SELECT e.actor_member_id, e.payload::jsonb AS payload
            FROM events e
            WHERE e.event_type='artifact.submitted'
              AND e.task_id=r.task_id
              AND e.payload::jsonb->>'artifact_id'=r.id
            ORDER BY e.created_at DESC
            LIMIT 1
        ) ev ON TRUE
        ON CONFLICT (artifact_id) DO NOTHING
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_artifact_versions_task ON artifact_versions(task_id, version_number DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_artifact_versions_package ON artifact_versions(work_package_id, version_number DESC)")
    op.execute("ALTER TABLE artifact_versions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE artifact_versions FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY daep_artifact_versions_tenant ON artifact_versions
        USING (daep_tenant_visible(tenant_id))
        WITH CHECK (daep_tenant_visible(tenant_id))
    """)


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP POLICY IF EXISTS daep_artifact_versions_tenant ON artifact_versions")
    op.execute("DROP TABLE IF EXISTS artifact_versions")
