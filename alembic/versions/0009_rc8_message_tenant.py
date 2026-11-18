"""RC8 add durable tenant ownership to inbox messages."""
from alembic import op, context
import sqlalchemy as sa

revision = "0009_rc8_message_tenant"
down_revision = "0008_rc7_indexes"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    if context.is_offline_mode():
        op.add_column("messages", sa.Column("tenant_id", sa.Text(), nullable=False, server_default="tenant-default"))
        op.alter_column("messages", "tenant_id", server_default=None)
        op.create_index("idx_messages_tenant_seq", "messages", ["tenant_id", "seq"], if_not_exists=True)
        return
    insp = sa.inspect(bind)
    if "messages" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("messages")}
    if "tenant_id" not in cols:
        op.add_column("messages", sa.Column("tenant_id", sa.Text(), nullable=False, server_default="tenant-default"))
        op.execute("UPDATE messages m SET tenant_id = COALESCE((SELECT tenant_id FROM members x WHERE x.id=m.recipient_member_id), 'tenant-default')")
        op.alter_column("messages", "tenant_id", server_default=None)
    op.create_index("idx_messages_tenant_seq", "messages", ["tenant_id", "seq"], if_not_exists=True)

def downgrade():
    try: op.drop_index("idx_messages_tenant_seq", table_name="messages")
    except Exception: pass
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        try: op.drop_column("messages", "tenant_id")
        except Exception: pass
