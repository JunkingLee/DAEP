"""RC12: add per-claim capability tokens to transactional outbox leases."""
from alembic import op, context
import sqlalchemy as sa

revision = "0015_rc12_outbox_lease_token"
down_revision = "0014_rc12_auth_lookup_fn"
branch_labels = None
depends_on = None

def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    if context.is_offline_mode():
        op.execute("ALTER TABLE outbox ADD COLUMN IF NOT EXISTS lease_token TEXT")
    elif "lease_token" not in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("outbox")}:
        op.add_column("outbox", sa.Column("lease_token", sa.Text(), nullable=True))

def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    if context.is_offline_mode():
        op.execute("ALTER TABLE outbox DROP COLUMN IF EXISTS lease_token")
    else:
        op.drop_column("outbox", "lease_token")
