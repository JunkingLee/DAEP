"""RC43: preserve immutable artifact quality policy snapshots."""
from alembic import op

revision = "0033_rc43_quality_policy_snapshot"
down_revision = "0032_rc42_artifact_versions"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE artifact_versions ADD COLUMN IF NOT EXISTS quality_policy_snapshot TEXT")


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE artifact_versions DROP COLUMN IF EXISTS quality_policy_snapshot")
