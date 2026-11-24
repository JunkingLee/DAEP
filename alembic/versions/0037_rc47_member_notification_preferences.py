"""RC47: Member notification preferences."""

from alembic import op

revision = "0037_rc47_notify_prefs"
down_revision = "0036_rc46_agent_task_grants"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("""
        CREATE TABLE IF NOT EXISTS member_notification_preferences (
            member_id TEXT PRIMARY KEY REFERENCES members(id) ON DELETE CASCADE,
            tenant_id TEXT NOT NULL,
            collaboration_grant_events BOOLEAN NOT NULL DEFAULT TRUE,
            collaboration_expiry_reminders BOOLEAN NOT NULL DEFAULT TRUE,
            reminder_days_json TEXT NOT NULL DEFAULT '[7,3,1]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_member_notification_preferences_tenant
        ON member_notification_preferences(tenant_id,member_id)
    """)
    op.execute("ALTER TABLE member_notification_preferences ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE member_notification_preferences FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS daep_member_notification_preferences_tenant ON member_notification_preferences")
    op.execute("""
        CREATE POLICY daep_member_notification_preferences_tenant
        ON member_notification_preferences
        USING (daep_tenant_visible(tenant_id))
        WITH CHECK (daep_tenant_visible(tenant_id))
    """)


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TABLE IF EXISTS member_notification_preferences CASCADE")
