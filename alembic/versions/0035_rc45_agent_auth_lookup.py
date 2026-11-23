"""RC45: tenant-safe Agent token authentication under PostgreSQL RLS."""

from alembic import op

revision = "0035_rc45_agent_auth_lookup"
down_revision = "0034_rc44_quality_risk_events"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return

    # Reuse the narrowly scoped BYPASSRLS authenticator role introduced for
    # member-token lookup. It can read only the credential tables required by
    # this function; the application role still has no general RLS bypass.
    op.execute("GRANT SELECT ON TABLE agents, agent_tokens TO daep_authenticator")
    op.execute("""
        CREATE OR REPLACE FUNCTION public.daep_authenticate_agent_token(
            p_token_hash text,
            p_now text
        )
        RETURNS TABLE(
            token_id text,
            agent_id text,
            owner_member_id text,
            tenant_id text,
            agent_status text,
            token_status text,
            expires_at text
        )
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        SET row_security = off
        AS $$
            SELECT t.id, t.agent_id, a.owner_member_id, a.tenant_id,
                   a.status, t.status, t.expires_at
            FROM public.agent_tokens AS t
            JOIN public.agents AS a ON a.id = t.agent_id
            WHERE t.token_hash = p_token_hash
              AND t.status = 'ACTIVE'
              AND a.status = 'ACTIVE'
              AND (t.expires_at IS NULL OR t.expires_at > p_now)
            LIMIT 1
        $$
    """)
    op.execute(
        "ALTER FUNCTION public.daep_authenticate_agent_token(text,text) "
        "OWNER TO daep_authenticator"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION public.daep_authenticate_agent_token(text,text) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION public.daep_authenticate_agent_token(text,text) TO PUBLIC"
    )


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        "REVOKE EXECUTE ON FUNCTION public.daep_authenticate_agent_token(text,text) FROM PUBLIC"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS public.daep_authenticate_agent_token(text,text)"
    )
    op.execute("REVOKE SELECT ON TABLE agents, agent_tokens FROM daep_authenticator")
