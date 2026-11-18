"""RC7 tenancy and inbox indexes."""
from alembic import op

revision="0008_rc7_indexes"
down_revision="0007_platform_admin_boundary"
branch_labels=None
depends_on=None

def upgrade():
    # These are additive and intentionally emitted without schema inspection so
    # Alembic offline SQL generation remains deterministic.
    op.create_index("idx_members_tenant_status", "members", ["tenant_id","token_status"], if_not_exists=True)
    op.create_index("idx_projects_tenant_created", "projects", ["tenant_id","created_at"], if_not_exists=True)
    op.create_index("idx_messages_recipient_seq", "messages", ["recipient_member_id","seq"], if_not_exists=True)
    op.create_index("idx_outbox_claim", "outbox", ["status","available_at","lease_until"], if_not_exists=True)

def downgrade():
    for table,name in [("members","idx_members_tenant_status"),("projects","idx_projects_tenant_created"),("messages","idx_messages_recipient_seq"),("outbox","idx_outbox_claim")]:
        try: op.drop_index(name,table_name=table)
        except Exception: pass
