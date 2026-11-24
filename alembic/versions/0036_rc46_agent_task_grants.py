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
            legacy_assignment_id TEXT,
            CHECK (expires_at > created_at),
            CHECK (
                (status <> 'ACCEPTED' OR accepted_at IS NOT NULL)
                AND (status <> 'REVOKED' OR revoked_at IS NOT NULL)
                AND (status <> 'COMPLETED' OR completed_at IS NOT NULL)
            )
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_task_grants_active_task_agent
        ON agent_task_grants(task_id,agent_id)
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


    # Task execution policy: one policy per Task. NULL max_agents means no
    # task-level fixed cap; TEAM is the only supported collaboration mode.
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_task_execution_policies (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL UNIQUE REFERENCES tasks(id) ON DELETE CASCADE,
            responsible_member_id TEXT NOT NULL REFERENCES members(id),
            allow_multiple_agents BOOLEAN NOT NULL DEFAULT FALSE,
            max_agents INTEGER CHECK (max_agents IS NULL OR max_agents > 0),
            collaboration_mode TEXT NOT NULL DEFAULT 'TEAM' CHECK (collaboration_mode = 'TEAM'),
            policy_version INTEGER NOT NULL DEFAULT 1 CHECK (policy_version > 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_task_contributions (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            grant_id TEXT NOT NULL REFERENCES agent_task_grants(id) ON DELETE CASCADE,
            agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
            contribution_type TEXT NOT NULL CHECK (contribution_type IN ('PROGRESS','BLOCKER','ACTIVITY','DELIVERY')),
            progress INTEGER CHECK (progress IS NULL OR (progress >= 0 AND progress <= 100)),
            summary TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_collaboration_sessions (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL UNIQUE REFERENCES tasks(id) ON DELETE CASCADE,
            responsible_member_id TEXT NOT NULL REFERENCES members(id),
            status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','PAUSED','CLOSED')),
            title TEXT,
            summary TEXT,
            created_by_member_id TEXT NOT NULL REFERENCES members(id),
            policy_version INTEGER NOT NULL DEFAULT 1 CHECK (policy_version > 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            closed_at TEXT,
            CHECK ((status = 'CLOSED' AND closed_at IS NOT NULL) OR
                   (status <> 'CLOSED' AND closed_at IS NULL))
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_collaboration_grants (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            session_id TEXT NOT NULL REFERENCES agent_collaboration_sessions(id) ON DELETE CASCADE,
            agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
            owner_member_id TEXT NOT NULL REFERENCES members(id),
            authorized_by_member_id TEXT NOT NULL REFERENCES members(id),
            scopes_json TEXT NOT NULL,
            resource_scope_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'AUTHORIZED'
                CHECK (status IN ('AUTHORIZED','ACCEPTED','REVOKED','EXPIRED')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            accepted_at TEXT,
            revoked_at TEXT,
            revoked_by_member_id TEXT REFERENCES members(id),
            revoke_reason TEXT,
            CHECK (expires_at > created_at),
            CHECK ((status <> 'ACCEPTED' OR accepted_at IS NOT NULL) AND
                   (status <> 'REVOKED' OR revoked_at IS NOT NULL))
        )
    """)
    # The existing messages table is a recipient inbox, not a shared thread.
    # Collaboration conversations therefore have their own author-aware table.
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_collaboration_messages (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            session_id TEXT NOT NULL REFERENCES agent_collaboration_sessions(id) ON DELETE CASCADE,
            author_type TEXT NOT NULL CHECK (author_type IN ('MEMBER','AGENT')),
            author_member_id TEXT REFERENCES members(id),
            author_agent_id TEXT REFERENCES agents(id),
            agent_owner_member_id TEXT REFERENCES members(id),
            collaboration_grant_id TEXT REFERENCES agent_collaboration_grants(id),
            message_type TEXT NOT NULL DEFAULT 'MESSAGE',
            content TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            CHECK (
                (author_type = 'MEMBER' AND author_member_id IS NOT NULL
                    AND author_agent_id IS NULL AND agent_owner_member_id IS NULL
                    AND collaboration_grant_id IS NULL)
                OR
                (author_type = 'AGENT' AND author_member_id IS NULL
                    AND author_agent_id IS NOT NULL AND agent_owner_member_id IS NOT NULL
                    AND collaboration_grant_id IS NOT NULL)
            )
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_collaboration_proposals (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            session_id TEXT NOT NULL REFERENCES agent_collaboration_sessions(id) ON DELETE CASCADE,
            proposal_type TEXT NOT NULL
                CHECK (proposal_type IN ('INVITE_AGENT','WORK_PACKAGE','MEMBER_DELEGATION','HELP_REQUEST')),
            proposed_by_agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
            owner_member_id TEXT NOT NULL REFERENCES members(id),
            collaboration_grant_id TEXT NOT NULL REFERENCES agent_collaboration_grants(id),
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING'
                CHECK (status IN ('PENDING','ACCEPTED','REJECTED','WITHDRAWN')),
            decided_by_member_id TEXT REFERENCES members(id),
            decision_note TEXT,
            created_at TEXT NOT NULL,
            decided_at TEXT
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_task_policy_project ON agent_task_execution_policies(tenant_id,project_id,task_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_task_contributions_grant ON agent_task_contributions(tenant_id,grant_id,created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_task_contributions_task ON agent_task_contributions(tenant_id,task_id,agent_id,created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_collaboration_sessions_project ON agent_collaboration_sessions(tenant_id,project_id,status,updated_at)")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_collaboration_grants_active_session_agent
        ON agent_collaboration_grants(session_id,agent_id)
        WHERE status IN ('AUTHORIZED','ACCEPTED')
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_collaboration_grants_owner ON agent_collaboration_grants(tenant_id,owner_member_id,status,expires_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_collaboration_messages_session ON agent_collaboration_messages(tenant_id,session_id,created_at,id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_collaboration_proposals_session ON agent_collaboration_proposals(tenant_id,session_id,status,created_at)")

    tenant_tables = (
        "agent_task_grants",
        "agent_task_execution_policies",
        "agent_task_contributions",
        "agent_collaboration_sessions",
        "agent_collaboration_grants",
        "agent_collaboration_messages",
        "agent_collaboration_proposals",
    )
    for table in tenant_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS daep_{table}_tenant ON {table}")
        op.execute(f"""
            CREATE POLICY daep_{table}_tenant ON {table}
            USING (daep_tenant_visible(tenant_id))
            WITH CHECK (daep_tenant_visible(tenant_id))
        """)
        op.execute(f"REVOKE ALL ON TABLE {table} FROM daep_authenticator")

    # Agent credential lookup must never become a task-grant lookup channel.
    op.execute("REVOKE ALL ON TABLE agent_task_grants FROM daep_authenticator")


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP POLICY IF EXISTS daep_agent_task_grants_tenant ON agent_task_grants")
    op.execute("DROP TABLE IF EXISTS agent_task_grants")
