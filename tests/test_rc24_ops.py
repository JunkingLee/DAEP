from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_rc24_restore_verifier_checks_revision_rls_and_role_boundaries():
    script = (ROOT / "scripts" / "verify_restored_postgres.sh").read_text()
    for invariant in (
        "alembic heads",
        "alembic_version",
        "relrowsecurity AND c.relforcerowsecurity",
        "pg_policies",
        "daep_authenticate_member",
        "daep_runtime",
        "daep_privileged_login",
        "daep_authenticator",
        "pg_has_role",
    ):
        assert invariant in script
    assert "does not modify" in (ROOT / "docs" / "RC24_RESTORE_VERIFICATION.md").read_text()
