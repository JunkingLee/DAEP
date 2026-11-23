from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_rc23_restore_is_atomic_and_refuses_unsafe_targets():
    script = (ROOT / "scripts" / "restore_postgres.sh").read_text()
    assert 'DAEP_CONFIRM_RESTORE' in script
    assert 'source_db=' in script
    assert '[ "$target" != "$source_db" ]' in script
    assert 'object_count=' in script
    assert 'Target database is not empty' in script
    assert '--single-transaction' in script
    assert 'DO $$' in script
    assert '\n$$;' in script


def test_rc23_compose_verifier_checks_privilege_boundaries():
    script = (ROOT / "scripts" / "verify_production_compose.py").read_text()
    for invariant in (
        'PostgreSQL must not publish host ports',
        'API DATABASE_URL must use daep_runtime',
        'API must never receive bootstrap database credentials',
        'API filesystem must be read-only',
        'API must wait for successful one-shot migrations',
        'API must bind to loopback by default',
    ):
        assert invariant in script
