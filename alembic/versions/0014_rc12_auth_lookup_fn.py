"""RC12: replace caller-settable auth lookup GUC with a narrow SECURITY DEFINER function."""
from alembic import op

revision = "0014_rc12_auth_lookup_fn"
down_revision = "0013_rc11_db_privileged_role"
branch_labels = None
depends_on = None

def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
    DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='daep_authenticator') THEN
        CREATE ROLE daep_authenticator NOLOGIN BYPASSRLS;
      END IF;
    END $$;
    """)
    op.execute("GRANT USAGE ON SCHEMA public TO daep_authenticator")
    op.execute("GRANT SELECT ON TABLE members TO daep_authenticator")
    op.execute("GRANT CREATE ON SCHEMA public TO daep_authenticator")
    op.execute("""
    CREATE OR REPLACE FUNCTION public.daep_authenticate_member(p_token_hash text, p_now text)
    RETURNS SETOF public.members
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path = pg_catalog, public
    SET row_security = off
    AS $$
      SELECT m.* FROM public.members AS m
      WHERE m.token = p_token_hash AND m.token_status = 'ACTIVE'
        AND (m.token_expires_at IS NULL OR m.token_expires_at > p_now)
      LIMIT 1
    $$;
    """)
    op.execute("ALTER FUNCTION public.daep_authenticate_member(text,text) OWNER TO daep_authenticator")
    op.execute("REVOKE CREATE ON SCHEMA public FROM daep_authenticator")
    op.execute("REVOKE ALL ON FUNCTION public.daep_authenticate_member(text,text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION public.daep_authenticate_member(text,text) TO PUBLIC")
    op.execute("DROP POLICY IF EXISTS daep_members_auth_lookup ON members")

def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("REVOKE EXECUTE ON FUNCTION public.daep_authenticate_member(text,text) FROM PUBLIC")
    op.execute("DROP FUNCTION IF EXISTS public.daep_authenticate_member(text,text)")
    op.execute("""
    CREATE POLICY daep_members_auth_lookup ON members FOR SELECT
    USING (current_setting('app.auth_lookup', true) = 'true')
    """)
    # Keep the NOLOGIN role: ownership/dependencies may have been changed by an operator.