"""RC46: owner-authorized, task-scoped Agent grants."""

from alembic import op

revision = "0036_rc46_agent_task_grants"
down_revision = "0035_rc45_agent_auth_lookup"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_task_grants (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
            owner_member_id TEXT NOT NULL REFERENCES members(id),
            human_assignee_member_id TEXT NOT NULL REFERENCES members(id),
            authorized_by_member_id TEXT NOT NULL REFERENCES members(id),
            scope_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'AUTHORIZED'
                CHECK (status IN ('AUTHORIZED','ACCEPTED','REVOKED','COMPLETED','EXPIRED')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            accepted_at TEXT,
            revoked_at TEXT,
            completed_at TEXT,
            revoked_by_member_id TEXT REFERENCES members(id),
            revoke_reason TEXT,
            last_activity_at TEXT,
            legacy_assignment_id TEXT REFERENCES agent_task_assignments(id),
            CHECK (expires_at > created_at),
            CHECK (
                (status <> 'ACCEPTED' OR accepted_at IS NOT NULL)
                AND (status <> 'REVOKED' OR revoked_at IS NOT NULL)
                AND (status <> 'COMPLETED' OR completed_at IS NOT NULL)
            )
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_task_grants_one_active_per_task
        ON agent_task_grants(task_id)
        WHERE status IN ('AUTHORIZED','ACCEPTED')
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_task_grants_agent_status_expiry
        ON agent_task_grants(tenant_id,agent_id,status,expires_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_task_grants_task_status
        ON agent_task_grants(tenant_id,task_id,status)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_task_grants_owner_status_created
        ON agent_task_grants(owner_member_id,status,created_at)
    """)
    op.execute("ALTER TABLE agent_task_grants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agent_task_grants FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS daep_agent_task_grants_tenant ON agent_task_grants")
    op.execute("""
        CREATE POLICY daep_agent_task_grants_tenant ON agent_task_grants
        USING (daep_tenant_visible(tenant_id))
        WITH CHECK (daep_tenant_visible(tenant_id))
    """)
    # Agent credential lookup must never become a task-grant lookup channel.
    op.execute("REVOKE ALL ON TABLE agent_task_grants FROM daep_authenticator")


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP POLICY IF EXISTS daep_agent_task_grants_tenant ON agent_task_grants")
    op.execute("DROP TABLE IF EXISTS agent_task_grants")
