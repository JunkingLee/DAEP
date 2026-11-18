"""RC6 baseline marker.

The application bootstrap owns the cross-database core schema because DAEP
supports both SQLite and PostgreSQL without requiring SQLAlchemy ORM models.
This revision anchors the Alembic history; RC7+ additive schema changes are
managed by Alembic migrations.
"""
from alembic import op
revision = "0007_platform_admin_boundary"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    pass

def downgrade():
    pass
