"""RC41: require active platform accounts for member token authentication."""
from alembic import op

revision = "0031_rc41_member_auth_status"
down_revision = "0030_rc40_agent_assignment"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
    CREATE OR REPLACE FUNCTION public.daep_authenticate_member(p_token_hash text, p_now text)
    RETURNS SETOF public.members
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path = pg_catalog, public
    SET row_security = off
    AS $$
      SELECT m.* FROM public.members AS m
      WHERE m.token = p_token_hash
        AND m.token_status = 'ACTIVE'
        AND m.password_status = 'ACTIVE'
        AND (m.token_expires_at IS NULL OR m.token_expires_at > p_now)
      LIMIT 1
    $$;
    """)


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    # Keep the stronger account-status check on downgrade; restoring disabled-account
    # authentication would reintroduce a credential lifecycle security flaw.
