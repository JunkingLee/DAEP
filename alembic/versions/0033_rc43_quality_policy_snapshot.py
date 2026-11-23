"""RC43: preserve immutable artifact quality policy snapshots."""
from alembic import op

revision = "0033_rc43_quality_policy"
down_revision = "0032_rc42_artifact_versions"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE artifact_versions ADD COLUMN IF NOT EXISTS quality_policy_snapshot TEXT")
    op.execute("""
        CREATE OR REPLACE FUNCTION daep_artifact_quality_snapshot_immutable()
        RETURNS trigger AS $
        BEGIN
            IF NEW.quality_policy_snapshot IS DISTINCT FROM OLD.quality_policy_snapshot THEN
                RAISE EXCEPTION 'artifact quality policy snapshot is immutable';
            END IF;
            RETURN NEW;
        END;
        $ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_artifact_quality_snapshot_immutable
        BEFORE UPDATE OF quality_policy_snapshot ON artifact_versions
        FOR EACH ROW EXECUTE FUNCTION daep_artifact_quality_snapshot_immutable()
    """)


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER IF EXISTS trg_artifact_quality_snapshot_immutable ON artifact_versions")
    op.execute("DROP FUNCTION IF EXISTS daep_artifact_quality_snapshot_immutable()")
    op.execute("ALTER TABLE artifact_versions DROP COLUMN IF EXISTS quality_policy_snapshot")
