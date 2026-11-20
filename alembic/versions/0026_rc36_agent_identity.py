"""RC36: first-class user-owned Agent identity and MCP token lifecycle."""
from alembic import op

revision = "0026_rc36_agent_identity"
down_revision = "0025_rc35_project_lifecycle"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("""CREATE TABLE IF NOT EXISTS agents(
        id TEXT PRIMARY KEY,
        owner_member_id TEXT NOT NULL REFERENCES members(id),
        tenant_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','DISABLED')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        last_seen_at TEXT
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agents_owner ON agents(owner_member_id,status)")
    op.execute("""CREATE TABLE IF NOT EXISTS agent_tokens(
        id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL REFERENCES agents(id),
        tenant_id TEXT NOT NULL,
        token_hash TEXT UNIQUE NOT NULL,
        status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','REVOKED')),
        created_at TEXT NOT NULL,
        last_used_at TEXT,
        expires_at TEXT,
        revoked_at TEXT
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_tokens_agent ON agent_tokens(agent_id,status)")
    op.execute("""CREATE TABLE IF NOT EXISTS agent_project_bindings(
        project_id TEXT NOT NULL REFERENCES projects(id),
        agent_id TEXT NOT NULL REFERENCES agents(id),
        tenant_id TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('member','reviewer','manager')),
        work_function TEXT NOT NULL DEFAULT 'other' CHECK (work_function IN ('developer','tester','product','architect','other')),
        status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','DISABLED')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(project_id,agent_id)
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_project_bindings_agent ON agent_project_bindings(agent_id,status)")
    for table in ("agents","agent_tokens","agent_project_bindings"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS daep_{table}_tenant ON {table}")
        op.execute(f"""CREATE POLICY daep_{table}_tenant ON {table}
          USING (daep_tenant_visible(tenant_id))
          WITH CHECK (daep_tenant_visible(tenant_id))""")

def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in ("agent_project_bindings","agent_tokens","agents"):
        op.execute(f"DROP POLICY IF EXISTS daep_{table}_tenant ON {table}")
        op.execute(f"DROP TABLE IF EXISTS {table}")