from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app" / "main.py").read_text(encoding="utf-8")


def test_rc27_password_auth_backend_contract():
    assert "def hash_password(password):" in MAIN
    assert "def verify_password(password,encoded):" in MAIN
    assert "@app.post('/api/v1/auth/login')" in MAIN
    assert "lower(username)=?" in MAIN
    assert "password_hash" in MAIN
    assert "pbkdf2_hmac('sha256'" in MAIN
    assert "API token" not in MAIN.split("@app.post('/api/v1/auth/login')",1)[1].split("@app.post('/api/v1/auth/change-password')",1)[0]


def test_rc27_member_provisioning_requires_password_and_username():
    block = MAIN.split("@app.post('/api/v1/members')",1)[1].split("@app.get('/api/v1/members')",1)[0]
    assert "username" in block
    assert "password" in block
    assert "Password must be 12-256 characters" in block
    assert "Username already exists" in block
    assert "role not in ('member','manager','reviewer')" in block


def test_rc27_api_token_remains_machine_auth_not_web_login():
    assert "def actor(authorization):" in MAIN
    assert "Bearer token required" in MAIN
    assert "issue_member_token" in MAIN
    assert "DAEP_BOOTSTRAP_ADMIN_PASSWORD" in MAIN

def test_rc27_project_member_directory_and_roles_are_separate_from_platform_account():
    block = MAIN.split("@app.get('/api/v1/projects/{pid}/member-candidates')",1)[1].split("@app.post('/api/v1/projects/{pid}/members')",1)[0]
    assert "project_member_candidates" in block
    assert "m.username" in block
    assert "already_member" in block
    assert "password_status='ACTIVE'" in block
    member_route = MAIN.split("@app.post('/api/v1/projects/{pid}/members')",1)[1].split("@app.patch('/api/v1/projects/{pid}/members/{member_id}/function')",1)[0]
    assert "role not in ('member','reviewer','manager')" in member_route
    assert "work_function not in ('developer','tester','product','architect','other')" in member_route
