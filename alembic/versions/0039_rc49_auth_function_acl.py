"""RC49: restrict authentication function EXECUTE to application roles."""

from alembic import op

revision = "0039_rc49_auth_function_acl"
down_revision = "0038_rc48_workflow_governance_rls"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return

    functions = (
        "public.daep_authenticate_member(text,text)",
        "public.daep_authenticate_agent_token(text,text)",
    )
    for function in functions:
        op.execute(f"REVOKE EXECUTE ON FUNCTION {function} FROM PUBLIC")
        op.execute(f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'daep_runtime') THEN
                    GRANT EXECUTE ON FUNCTION {function} TO daep_runtime;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'daep_privileged_login') THEN
                    GRANT EXECUTE ON FUNCTION {function} TO daep_privileged_login;
                END IF;
            END $$;
        """)


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return

    for function in (
        "public.daep_authenticate_member(text,text)",
        "public.daep_authenticate_agent_token(text,text)",
    ):
        op.execute(f"REVOKE EXECUTE ON FUNCTION {function} FROM daep_runtime")
        op.execute(f"REVOKE EXECUTE ON FUNCTION {function} FROM daep_privileged_login")
        op.execute(f"GRANT EXECUTE ON FUNCTION {function} TO PUBLIC")
