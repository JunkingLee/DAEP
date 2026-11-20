from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_rc26_dashboard_exposes_project_metrics_and_task_board():
    html = (ROOT / "web" / "index.html").read_text()
    for feature in (
        'id="overview"',
        'id="overviewMetrics"',
        'id="taskBoard"',
        'id="taskBoardCard"',
        'function renderTaskBoard()',
        'function loadOverview()',
        '/work-health',
    ):
        assert feature in html


def test_rc26_task_detail_uses_existing_authorized_collaboration_apis():
    html = (ROOT / "web" / "index.html").read_text()
    for feature in (
        "function openTask(id)",
        "/work-packages",
        "/work-timeline",
        "function esc(v)",
    ):
        assert feature in html
    assert "localStorage" not in html


def test_rc26_dependency_graph_is_interactive_and_accessible():
    html = (ROOT / "web" / "index.html").read_text()
    for feature in (
        'id="dependencyView"',
        "function renderDependencyGraph()",
        "function dependencyLinks(t)",
        'marker-end="url(#depArrow)"',
        'role="button"',
        "onkeydown=",
    ):
        assert feature in html


def test_project_task_listing_includes_dependency_ids():
    source = (ROOT / "app" / "main.py").read_text()
    endpoint = source.split("@app.get('/api/v1/projects/{pid}/tasks')", 1)[1].split("@app.post('/api/v1/requirements')", 1)[0]
    assert "item['dependencies']" in endpoint
    assert "depends_on_task_id" in endpoint


def test_rc26_dependency_editor_is_manager_gated_and_calls_authorized_api():
    html = (ROOT / "web" / "index.html").read_text()
    assert "selectedProjectRole" in html
    assert "function saveTaskDependencies(id)" in html
    assert "method:'PUT'" in html
    assert "只有项目 Owner 或 Manager 可以修改依赖关系" in html


def test_dependency_update_endpoint_has_scope_and_cycle_guards():
    source = (ROOT / "app" / "main.py").read_text()
    start = source.index("@app.put('/api/v1/tasks/{tid}/dependencies')")
    end = source.index("@app.get('/api/v1/me/tasks')", start)
    endpoint = source[start:end]
    assert "require_project_access(c,project_id,a,write=True)" in endpoint
    assert "Dependencies must belong to the same project" in endpoint
    assert "Dependency would create a cycle" in endpoint
    assert "task.dependencies.updated" in endpoint


def test_rc26_project_work_package_board_uses_final_health_surface():
    html = (ROOT / "web" / "index.html").read_text()
    for feature in (
        'id="workPackageBoard"',
        "function renderWorkPackages()",
        "projectHealthItems=h.items||[]",
        "function scanProjectHealth()",
        "/work-packages/scan-health",
    ):
        assert feature in html
    assert 'id="workPackageRiskFilter"' not in html
