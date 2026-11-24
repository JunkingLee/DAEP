"""Initial SQLite schema for task-scoped Agent collaboration.

DAEP does not host Agent runtimes. These tables persist collaboration governance,
messages and proposals only; they never contain runtime launch/configuration data.
"""

def ensure_agent_collaboration_schema(conn_factory):
    """Create the development database's collaboration schema from scratch."""
    with conn_factory() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS agent_task_execution_policies (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            task_id TEXT NOT NULL UNIQUE,
            responsible_member_id TEXT NOT NULL,
            allow_multiple_agents INTEGER NOT NULL DEFAULT 0
                CHECK (allow_multiple_agents IN (0,1)),
            max_agents INTEGER
                CHECK (max_agents IS NULL OR max_agents > 0),
            collaboration_mode TEXT NOT NULL DEFAULT 'TEAM'
                CHECK (collaboration_mode = 'TEAM'),
            policy_version INTEGER NOT NULL DEFAULT 1 CHECK (policy_version > 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (responsible_member_id) REFERENCES members(id)
        );

        CREATE TABLE IF NOT EXISTS agent_task_contributions (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            grant_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            contribution_type TEXT NOT NULL
                CHECK (contribution_type IN ('PROGRESS','BLOCKER','ACTIVITY','DELIVERY')),
            progress INTEGER CHECK (progress IS NULL OR (progress >= 0 AND progress <= 100)),
            summary TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (grant_id, task_id, agent_id) REFERENCES agent_task_grants(id, task_id, agent_id) ON DELETE CASCADE,
            FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS agent_collaboration_sessions (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            task_id TEXT NOT NULL UNIQUE,
            responsible_member_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'OPEN'
                CHECK (status IN ('OPEN','PAUSED','CLOSED')),
            title TEXT,
            summary TEXT,
            created_by_member_id TEXT NOT NULL,
            policy_version INTEGER NOT NULL DEFAULT 1 CHECK (policy_version > 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            closed_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (responsible_member_id) REFERENCES members(id),
            FOREIGN KEY (created_by_member_id) REFERENCES members(id),
            CHECK ((status = 'CLOSED' AND closed_at IS NOT NULL) OR
                   (status <> 'CLOSED' AND closed_at IS NULL))
        );

        CREATE TABLE IF NOT EXISTS agent_collaboration_grants (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            owner_member_id TEXT NOT NULL,
            authorized_by_member_id TEXT NOT NULL,
            scopes_json TEXT NOT NULL,
            resource_scope_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'AUTHORIZED'
                CHECK (status IN ('AUTHORIZED','ACCEPTED','REVOKED','EXPIRED')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            accepted_at TEXT,
            revoked_at TEXT,
            revoked_by_member_id TEXT,
            revoke_reason TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (session_id) REFERENCES agent_collaboration_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE,
            FOREIGN KEY (owner_member_id) REFERENCES members(id),
            FOREIGN KEY (authorized_by_member_id) REFERENCES members(id),
            FOREIGN KEY (revoked_by_member_id) REFERENCES members(id),
            UNIQUE (id, session_id, task_id, agent_id, owner_member_id),
            CHECK (expires_at > created_at),
            CHECK ((status <> 'ACCEPTED' OR accepted_at IS NOT NULL) AND
                   (status <> 'REVOKED' OR revoked_at IS NOT NULL))
        );

        -- Existing messages are recipient inbox/notification records, not a
        -- shared conversation. Keep collaboration messages in their own table.
        CREATE TABLE IF NOT EXISTS agent_collaboration_messages (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            author_type TEXT NOT NULL CHECK (author_type IN ('MEMBER','AGENT')),
            author_member_id TEXT,
            author_agent_id TEXT,
            agent_owner_member_id TEXT,
            collaboration_grant_id TEXT,
            message_type TEXT NOT NULL DEFAULT 'MESSAGE',
            content TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (session_id) REFERENCES agent_collaboration_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (author_member_id) REFERENCES members(id),
            FOREIGN KEY (author_agent_id) REFERENCES agents(id),
            FOREIGN KEY (agent_owner_member_id) REFERENCES members(id),
            FOREIGN KEY (collaboration_grant_id, session_id, task_id, author_agent_id, agent_owner_member_id) REFERENCES agent_collaboration_grants(id, session_id, task_id, agent_id, owner_member_id),
            CHECK (
                (author_type = 'MEMBER' AND author_member_id IS NOT NULL
                    AND author_agent_id IS NULL AND agent_owner_member_id IS NULL
                    AND collaboration_grant_id IS NULL)
                OR
                (author_type = 'AGENT' AND author_member_id IS NULL
                    AND author_agent_id IS NOT NULL AND agent_owner_member_id IS NOT NULL
                    AND collaboration_grant_id IS NOT NULL)
            )
        );

        CREATE TABLE IF NOT EXISTS agent_collaboration_proposals (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            proposal_type TEXT NOT NULL
                CHECK (proposal_type IN ('INVITE_AGENT','WORK_PACKAGE','MEMBER_DELEGATION','HELP_REQUEST')),
            proposed_by_agent_id TEXT NOT NULL,
            owner_member_id TEXT NOT NULL,
            collaboration_grant_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING'
                CHECK (status IN ('PENDING','ACCEPTED','REJECTED','WITHDRAWN')),
            decided_by_member_id TEXT,
            decision_note TEXT,
            created_at TEXT NOT NULL,
            decided_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (session_id) REFERENCES agent_collaboration_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (proposed_by_agent_id) REFERENCES agents(id) ON DELETE CASCADE,
            FOREIGN KEY (owner_member_id) REFERENCES members(id),
            FOREIGN KEY (collaboration_grant_id, session_id, task_id, proposed_by_agent_id, owner_member_id) REFERENCES agent_collaboration_grants(id, session_id, task_id, agent_id, owner_member_id),
            FOREIGN KEY (decided_by_member_id) REFERENCES members(id)
        );

        CREATE INDEX IF NOT EXISTS idx_agent_task_policy_project
            ON agent_task_execution_policies(tenant_id, project_id, task_id);
        CREATE INDEX IF NOT EXISTS idx_agent_task_contributions_grant
            ON agent_task_contributions(tenant_id, grant_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_agent_task_contributions_task
            ON agent_task_contributions(tenant_id, task_id, agent_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_agent_collaboration_sessions_project
            ON agent_collaboration_sessions(tenant_id, project_id, status, updated_at);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_collaboration_grants_active_session_agent
            ON agent_collaboration_grants(session_id, agent_id)
            WHERE status IN ('AUTHORIZED','ACCEPTED');
        CREATE INDEX IF NOT EXISTS idx_agent_collaboration_grants_owner
            ON agent_collaboration_grants(tenant_id, owner_member_id, status, expires_at);
        CREATE INDEX IF NOT EXISTS idx_agent_collaboration_messages_session
            ON agent_collaboration_messages(tenant_id, session_id, created_at, id);
        CREATE INDEX IF NOT EXISTS idx_agent_collaboration_proposals_session
            ON agent_collaboration_proposals(tenant_id, session_id, status, created_at);

        CREATE TABLE IF NOT EXISTS member_notification_preferences (
            member_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            collaboration_grant_events INTEGER NOT NULL DEFAULT 1 CHECK (collaboration_grant_events IN (0,1)),
            collaboration_expiry_reminders INTEGER NOT NULL DEFAULT 1 CHECK (collaboration_expiry_reminders IN (0,1)),
            reminder_days_json TEXT NOT NULL DEFAULT '[7,3,1]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_member_notification_preferences_tenant
            ON member_notification_preferences(tenant_id, member_id);
        """)

        # The base bootstrap defines active-grant uniqueness.
