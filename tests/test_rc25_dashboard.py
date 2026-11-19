from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_rc25_dashboard_exposes_project_metrics_and_task_board():
    html = (ROOT / "web" / "index.html").read_text()
    for feature in (
        'id="overview"', 'id="metrics"', 'id="taskBoard"', 'id="board"',
        'function renderTaskBoard()', 'function loadOverview()', '/work-health',
    ):
        assert feature in html


def test_rc25_task_detail_uses_existing_authorized_collaboration_apis():
    html = (ROOT / "web" / "index.html").read_text()
    assert "function openTask(id)" in html
    assert "/work-packages" in html
    assert "/work-timeline" in html
    assert "function esc(v)" in html
    assert "localStorage" not in html


def test_rc25_dependency_graph_is_interactive_and_accessible():
    html = (ROOT / "web" / "index.html").read_text()
    for feature in (
        'id="dependencyGraph"',
        'function renderDependencyGraph()',
        'function dependencyLinks(t)',
        'marker-end="url(#depArrow)"',
        'role="button"',
        'onkeydown=',
    ):
        assert feature in html


def test_project_task_listing_includes_dependency_ids():
    source = (ROOT / "app" / "main.py").read_text()
    endpoint = source.split("@app.get('/api/v1/projects/{pid}/tasks')", 1)[1].split("@app.post('/api/v1/requirements')", 1)[0]
    assert "item['dependencies']" in endpoint
    assert "depends_on_task_id" in endpoint
