import os
import sys
import tempfile
import sqlite3

if "app.main" not in sys.modules:
    os.environ["DAEP_DB_PATH"] = os.path.join(tempfile.gettempdir(), "daep-rc22-standalone.db")
    os.environ["DAEP_ADMIN_TOKEN"] = "rc22-admin-token-with-32-characters-minimum"
    os.environ["DAEP_WORKER_TOKEN"] = "rc22-worker-token-with-32-characters-minimum"

from fastapi.testclient import TestClient
import app.main as main_module

if "client" in globals():
    pass

main_module.init()
client = TestClient(main_module.app)
ADMIN_TOKEN = os.environ["DAEP_ADMIN_TOKEN"]
WORKER_TOKEN = os.environ["DAEP_WORKER_TOKEN"]
ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
WORKER = {"Authorization": f"Bearer {WORKER_TOKEN}"}


def test_rc22_cross_member_agent_collaboration_end_to_end():
    project = client.post("/api/v1/projects", headers=ADMIN, json={"name": "RC22 E2E"})
    assert project.status_code == 200
    pid = project.json()["id"]

    owner = client.post("/api/v1/members", headers=ADMIN, json={"name": "Requester"}).json()
    recipient = client.post("/api/v1/members", headers=ADMIN, json={"name": "Agent Member"}).json()
    assert client.post(f"/api/v1/projects/{pid}/members", headers=ADMIN,
                       json={"member_id": owner["id"], "role": "member"}).status_code == 200
    assert client.post(f"/api/v1/projects/{pid}/members", headers=ADMIN,
                       json={"member_id": recipient["id"], "role": "member"}).status_code == 200

    owner_h = {"Authorization": f"Bearer {owner['token']}"}
    recipient_h = {"Authorization": f"Bearer {recipient['token']}"}

    requirement = client.post("/api/v1/requirements", headers=ADMIN,
                              json={"project_id": pid, "title": "RC22 requirement"})
    assert requirement.status_code == 200
    task = client.post("/api/v1/tasks", headers=ADMIN, json={
        "requirement_id": requirement.json()["id"],
        "title": "RC22 parent task",
        "assignee_member_ids": [owner["id"]],
    })
    assert task.status_code == 200
    parent_id = task.json()["id"]

    registered = client.post(f"/api/v1/projects/{pid}/agents/register", headers=recipient_h, json={
        "agent_name": "rc22-local-agent",
        "capabilities": ["python", "testing"],
        "protocols": ["mcp"],
        "status": "AVAILABLE",
    })
    assert registered.status_code == 200

    offered = client.post(f"/api/v1/tasks/{parent_id}/delegations", headers=owner_h, json={
        "recipient_member_id": recipient["id"],
        "agent_name": "rc22-local-agent",
        "reason": "Implement the delegated work",
    })
    assert offered.status_code == 200
    delegation = offered.json()
    assert delegation["status"] == "PENDING"

    inbox = client.get("/api/v1/me/notifications", headers=recipient_h)
    assert inbox.status_code == 200
    delegation_message = next(x for x in inbox.json()["items"] if x["id"] == delegation["message_id"])
    assert delegation_message["message_type"] == "TASK_DELEGATION"

    accepted = client.post(f"/api/v1/delegations/{delegation['id']}/respond", headers=recipient_h,
                           json={"decision": "ACCEPT"})
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "ACCEPTED"

    created = client.post(f"/api/v1/tasks/{parent_id}/work-packages", headers=ADMIN, json={
        "title": "RC22 delegated package",
        "description": "Implement and verify the feature",
        "assignee_member_id": recipient["id"],
        "agent_name": "rc22-local-agent",
        "sla_seconds": 3600,
    })
    assert created.status_code == 200
    package = created.json()
    child_id = package["task_id"]
    correlation_id = package["correlation_id"]
    assert correlation_id.startswith("corr_")

    package_inbox = client.get("/api/v1/me/notifications", headers=recipient_h).json()["items"]
    package_message = next(x for x in package_inbox if x["id"] == package["message_id"])
    assert package_message["message_type"] == "WORK_PACKAGE_ASSIGNED"

    ack = client.post(f"/api/v1/messages/{package_message['id']}/ack", headers=recipient_h,
                      json={"status": "ACKNOWLEDGED"})
    assert ack.status_code == 200
    replay = client.post(f"/api/v1/messages/{package_message['id']}/ack", headers=recipient_h,
                         json={"status": "ACKNOWLEDGED"})
    assert replay.status_code == 200
    assert replay.json()["idempotent"] is True

    artifact = client.post(f"/api/v1/tasks/{child_id}/artifacts", headers=recipient_h, json={
        "artifact_type": "git_commit",
        "uri": "https://github.com/example/daep/commit/rc22",
        "commit_sha": "rc22-e2e",
        "metadata": {"suite": "rc22"},
    })
    assert artifact.status_code == 200

    result = client.post(f"/api/v1/tasks/{child_id}/work-result", headers=recipient_h, json={
        "outcome": "COMPLETE",
        "summary": "Delegated implementation completed",
        "idempotency_key": "rc22-result-1",
    })
    assert result.status_code == 200
    assert result.json()["status"] == "REVIEW"

    parent_progress = client.post(f"/api/v1/tasks/{parent_id}/progress", headers=owner_h,
                                  json={"progress": 100, "note": "Delegated work ready for review"})
    assert parent_progress.status_code == 200

    parent_blocked = client.post(f"/api/v1/tasks/{parent_id}/review", headers=ADMIN,
                                 json={"decision": "APPROVE"})
    assert parent_blocked.status_code == 409

    child_approved = client.post(f"/api/v1/tasks/{child_id}/review", headers=ADMIN,
                                 json={"decision": "APPROVE", "comment": "Artifact verified"})
    assert child_approved.status_code == 200
    assert child_approved.json()["status"] == "DONE"

    parent_approved = client.post(f"/api/v1/tasks/{parent_id}/review", headers=ADMIN,
                                  json={"decision": "APPROVE", "comment": "Delegated work accepted"})
    assert parent_approved.status_code == 200
    assert parent_approved.json()["status"] == "DONE"

    timeline = client.get(f"/api/v1/tasks/{parent_id}/work-timeline", headers=owner_h)
    assert timeline.status_code == 200
    body = timeline.json()
    assert body["work_packages"][0]["correlation_id"] == correlation_id
    assert any(item.get("kind") == "message" and item.get("correlation_id") == correlation_id
               for item in body["items"])
    assert any(item.get("kind") == "artifact" and item.get("correlation_id") == correlation_id
               for item in body["items"])
    assert any(item.get("event_type") == "task.work_package.reported"
               and item["payload"]["correlation_id"] == correlation_id for item in body["items"])

    summary = client.get(f"/api/v1/tasks/{parent_id}/work-summary", headers=owner_h)
    assert summary.status_code == 200
    assert summary.json()["all_done"] is True
    assert summary.json()["artifact_count"] == 1

    claimed = client.post("/internal/v1/outbox/claim", headers=WORKER,
                          json={"worker_id": "rc22-e2e-worker", "limit": 50, "lease_seconds": 30})
    assert claimed.status_code == 200
    for item in claimed.json()["items"]:
        completed = client.post(f"/internal/v1/outbox/{item['id']}/complete", headers=WORKER, json={
            "worker_id": "rc22-e2e-worker",
            "lease_token": item["lease_token"],
        })
        assert completed.status_code == 200
        assert completed.json()["status"] == "SENT"

    db = sqlite3.connect(os.environ["DAEP_DB_PATH"])
    row = db.execute("SELECT status FROM task_work_packages WHERE id=?", (package["id"],)).fetchone()
    db.close()
    assert row[0] == "DONE"
