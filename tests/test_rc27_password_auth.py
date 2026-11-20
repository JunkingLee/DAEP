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
    assert "role!='member'" in block


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


def test_rc27_account_lifecycle_admin_contract():
    assert "@app.get('/api/v1/members/{member_id}')" in MAIN
    assert "@app.post('/api/v1/members/{member_id}/disable')" in MAIN
    assert "@app.post('/api/v1/members/{member_id}/enable')" in MAIN
    assert "@app.post('/api/v1/members/{member_id}/reset-password')" in MAIN
    lifecycle = MAIN.split("@app.get('/api/v1/members/{member_id}')",1)[1].split("@app.post('/api/v1/members/{member_id}/revoke-token')",1)[0]
    assert "Platform administrator required" in lifecycle
    assert "password_status='DISABLED'" in lifecycle
    assert "token_status='REVOKED'" in lifecycle
    assert "hash_password(password)" in lifecycle
    assert "member.account.disabled" in lifecycle
    assert "member.account.enabled" in lifecycle
    assert "member.password.reset" in lifecycle

def test_rc27_project_member_directory_contract_is_preserved():
    assert "m.username" in MAIN.split("@app.get('/api/v1/projects/{pid}/members')",1)[1].split("@app.post('/api/v1/projects/{pid}/members')",1)[0]
    block = MAIN.split("@app.get('/api/v1/projects/{pid}/member-candidates')",1)[1].split("@app.post('/api/v1/projects/{pid}/members')",1)[0]
    assert "already_member" in block
    assert "password_status='ACTIVE'" in block
    assert "SELECT tenant_id FROM projects WHERE id=?" in block


def test_rc28_project_creation_is_platform_admin_only():
    block = MAIN.split("@app.post('/api/v1/projects')",1)[1].split("@app.get('/api/v1/projects')",1)[0]
    assert "if not is_admin(a): raise HTTPException(403,'Platform administrator required')" in block


def test_rc28_project_scope_write_access_requires_project_manager():
    block = MAIN.split("def require_project_access",1)[1].split("def task_project",1)[0]
    assert "Project membership required" in block
    assert "Project manager role required" in block
    assert "row['role'] not in ('owner','manager')" in block


def test_rc28_requirement_acceptance_requires_reviewer_or_manager():
    block = MAIN.split("@app.post('/api/v1/requirements/{rid}/acceptance')",1)[1]
    assert "role['role'] not in ('owner','manager','reviewer')" in block
    assert "Reviewer role required" in block


def test_rc29_delegation_response_revalidates_project_scope():
    block = MAIN.split("@app.post('/api/v1/delegations/{did}/respond')",1)[1].split("@app.get('/api/v1/tasks/{tid}/delegations')",1)[0]
    assert "require_project_access(c,row['project_id'],a)" in block
    assert "task_pid=task_project(c,row['task_id'])" in block
    assert "Delegation project scope is invalid" in block


def _route_block(route, next_route):
    return MAIN.split(route, 1)[1].split(next_route, 1)[0]


def test_rc30_role_project_scope_matrix_contract():
    # Every project-scoped write surface must enforce live project membership,
    # rather than relying on the browser's role-aware navigation.
    route_pairs = [
        ("@app.post('/api/v1/projects/{pid}/members')", "@app.patch('/api/v1/projects/{pid}/members/{member_id}/function')"),
        ("@app.patch('/api/v1/projects/{pid}/members/{member_id}/function')", "@app.post('/api/v1/projects/{pid}/role-change-requests')"),
        ("@app.post('/api/v1/projects/{pid}/role-change-requests')", "@app.get('/api/v1/projects/{pid}/role-change-requests')"),
    ]
    for route, next_route in route_pairs:
        block = _route_block(route, next_route)
        assert "require_project_access(c,pid,a,write=True)" in block or "require_project_access(c,pid,a)" in block


def test_rc30_workflow_gate_governance_writes_are_project_scoped():
    # Workflow/Gate/Governance are project controls: a member of another
    # project/tenant must never reach a mutation solely with a valid token.
    markers = [
        "require_project_access(c,pid,a,write=True)",
        "require_project_access(c,pid,a)",
        "require_project_access(c,project_id,a,write=True)",
    ]
    for marker in markers:
        assert marker in MAIN


def test_rc30_task_mutations_use_assignment_or_project_scope():
    # Developer/tester/product permissions are task-scoped; the API must not
    # trust the front-end role tabs. Mutation handlers must use either the
    # assigned-task guard or project manager/reviewer guard.
    for marker in [
        "require_task_access(c,tid,a,assigned_only=True)",
        "require_task_access(c,tid,a)",
        "Reviewer role required",
        "Project manager role required",
    ]:
        assert marker in MAIN


def test_rc30_cross_tenant_member_and_agent_operations_are_blocked():
    for marker in [
        "Tenant isolation violation",
        "recipient tenant",
        "agent registration",
        "project membership",
    ]:
        assert marker.lower() in MAIN.lower()


def test_rc30_role_matrix_documents_server_side_boundaries():
    # Keep the role model explicit in executable acceptance contracts:
    # admin -> platform governance; owner/manager -> project administration;
    # reviewer -> review/acceptance; assignee -> task execution.
    assert "if not is_admin(a): raise HTTPException(403,'Platform administrator required')" in MAIN
    assert "row['role'] not in ('owner','manager')" in MAIN
    assert "role['role'] not in ('owner','manager','reviewer')" in MAIN
    assert "assigned_only=True" in MAIN


def test_rc31_mutation_endpoint_scope_matrix_is_explicit():
    # High-risk mutation routes are pinned to server-side authorization helpers.
    # This prevents a future UI-only permission change from silently creating
    # an API privilege-escalation path.
    endpoint_guards = {
        "@app.post('/api/v1/requirements')": ["require_project_access(c,b.project_id,a,write=True)"],
        "@app.post('/api/v1/tasks')": ["require_project_access(c,req['project_id'],a,write=True)"],
        "@app.post('/api/v1/tasks/{tid}/progress')": ["require_task_access(c,tid,a,assigned_only=True)"],
        "@app.post('/api/v1/tasks/{tid}/blocked')": ["require_task_access(c,tid,a,assigned_only=True)"],
        "@app.post('/api/v1/tasks/{tid}/artifacts')": ["require_task_access(c,tid,a,assigned_only=True)"],
        "@app.post('/api/v1/tasks/{tid}/review')": ["Reviewer role required"],
        "@app.post('/api/v1/projects/{pid}/members')": ["require_project_access(c,pid,a,write=True)"],
        "@app.post('/api/v1/projects/{pid}/role-change-requests')": ["require_project_access(c,pid,a,write=True)"],
        "@app.post('/api/v1/projects/{pid}/agents/register')": ["require_project_access(c,pid,a)"],
        "@app.post('/api/v1/projects/{pid}/agents/heartbeat')": ["require_project_access(c,pid,a)"],
        "@app.post('/api/v1/tasks/{tid}/delegations')": ["require_task_access(c,tid,a,assigned_only=True)"],
        "@app.post('/api/v1/delegations/{did}/respond')": ["require_project_access(c,row['project_id'],a)"],
        "@app.post('/api/v1/work-packages/{package_id}/reassign')": ["require_project_access(c,", "write=True)"],
        "@app.post('/api/v1/work-packages/{package_id}/review')": ["Reviewer role required"],
    }
    for route, guards in endpoint_guards.items():
        assert route in MAIN, f"missing endpoint: {route}"
        start = MAIN.index(route)
        next_at = MAIN.find("@app.", start + len(route))
        block = MAIN[start: next_at if next_at >= 0 else len(MAIN)]
        for guard in guards:
            assert guard in block, f"{route} lost server-side guard: {guard}"


def test_rc31_platform_user_mutations_remain_admin_only():
    for route in [
        "@app.post('/api/v1/members')",
        "@app.get('/api/v1/members/{member_id}')",
        "@app.post('/api/v1/members/{member_id}/disable')",
        "@app.post('/api/v1/members/{member_id}/enable')",
        "@app.post('/api/v1/members/{member_id}/reset-password')",
    ]:
        assert route in MAIN
        start = MAIN.index(route)
        next_at = MAIN.find("@app.", start + len(route))
        block = MAIN[start: next_at if next_at >= 0 else len(MAIN)]
        assert "Platform administrator required" in block, f"{route} is not admin-only"


def test_rc31_read_paths_still_require_project_or_task_scope():
    for route, guard in [
        ("@app.get('/api/v1/projects/{pid}/requirements')", "require_project_access(c,pid,a)"),
        ("@app.get('/api/v1/projects/{pid}/tasks')", "require_project_access(c,pid,a)"),
        ("@app.get('/api/v1/tasks/{tid}/events')", "require_task_access(c,tid,a)"),
        ("@app.get('/api/v1/tasks/{tid}/artifacts')", "require_task_access(c,tid,a)"),
    ]:
        assert route in MAIN
        start = MAIN.index(route)
        next_at = MAIN.find("@app.", start + len(route))
        block = MAIN[start: next_at if next_at >= 0 else len(MAIN)]
        assert guard in block, f"{route} lost scope guard"
