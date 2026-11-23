"""RC44: project quality risk events and immutable failure occurrences."""
from alembic import op

revision = "0034_rc44_quality_risk_events"
down_revision = "0033_rc43_quality_policy"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
        CREATE TABLE IF NOT EXISTS project_risk_events (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            artifact_version_id TEXT NOT NULL REFERENCES artifact_versions(id),
            risk_key TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            quality_check_key TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'LOW'
                CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
            status TEXT NOT NULL DEFAULT 'OPEN'
                CHECK (status IN ('OPEN','IN_PROGRESS','RESOLVED','DISMISSED')),
            occurrence_count INTEGER NOT NULL DEFAULT 1 CHECK (occurrence_count > 0),
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            source_actor_type TEXT,
            source_member_id TEXT REFERENCES members(id),
            source_agent_id TEXT,
            assignee_member_id TEXT REFERENCES members(id),
            due_at TEXT,
            resolved_at TEXT,
            resolution_note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (tenant_id, project_id, risk_key)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS project_risk_occurrences (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            risk_id TEXT NOT NULL REFERENCES project_risk_events(id) ON DELETE CASCADE,
            artifact_version_id TEXT NOT NULL REFERENCES artifact_versions(id),
            quality_check_key TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            actor_type TEXT,
            actor_member_id TEXT REFERENCES members(id),
            agent_id TEXT,
            occurred_at TEXT NOT NULL,
            UNIQUE (risk_id, artifact_version_id, quality_check_key)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_project_risk_events_project_status ON project_risk_events(project_id,status,severity,last_seen_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_project_risk_occurrences_risk ON project_risk_occurrences(risk_id,occurred_at DESC)")
    for table in ("project_risk_events", "project_risk_occurrences"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY daep_{table}_tenant ON {table}
            USING (daep_tenant_visible(tenant_id))
            WITH CHECK (daep_tenant_visible(tenant_id))
        """)


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in ("project_risk_occurrences", "project_risk_events"):
        op.execute(f"DROP POLICY IF EXISTS daep_{table}_tenant ON {table}")
        op.execute(f"DROP TABLE IF EXISTS {table}")
