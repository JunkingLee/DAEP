import json
from io import BytesIO

from daep_worker import worker


class FakeResponse:
    status = 202
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return b'{}'


def test_deliver_requires_independent_broker_credential(monkeypatch):
    monkeypatch.setattr(worker, "DEST", "https://broker.example/events")
    monkeypatch.setattr(worker, "BROKER_TOKEN", "")
    item = {"id": "obx-1", "event_type": "message.created", "attempts": 1, "payload": {"message_id": "msg-1"}}
    try:
        worker.deliver(item)
    except RuntimeError as exc:
        assert "DAEP_BROKER_WEBHOOK_TOKEN" in str(exc)
    else:
        raise AssertionError("missing broker token must fail closed")


def test_deliver_sends_auth_and_stable_idempotency_headers(monkeypatch):
    captured = {}
    def fake_urlopen(req, timeout):
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode())
        captured["timeout"] = timeout
        return FakeResponse()
    monkeypatch.setattr(worker, "DEST", "https://broker.example/events")
    monkeypatch.setattr(worker, "BROKER_TOKEN", "broker-secret-" + "x" * 40)
    monkeypatch.setattr(worker.urllib.request, "urlopen", fake_urlopen)
    item = {"id": "obx-stable-123", "event_type": "message.created", "attempts": 3, "payload": {"message_id": "msg-1", "content": "hello"}}
    worker.deliver(item)
    headers = {k.lower(): v for k, v in captured["headers"].items()}
    assert headers["authorization"] == "Bearer " + worker.BROKER_TOKEN
    assert headers["x-daep-outbox-id"] == "obx-stable-123"
    assert headers["x-daep-delivery-attempt"] == "3"
    assert headers["x-daep-message-id"] == "msg-1"
    assert captured["body"] == item["payload"]


def test_run_once_dispatches_grant_reminders_without_blocking_outbox(monkeypatch):
    calls = []
    def fake_call(method, path, payload=None):
        calls.append((method, path, payload))
        if path == "/internal/v1/outbox/claim":
            return {"items": [], "count": 0}
        if path == "/internal/v1/collaboration-grants/reminders/dispatch":
            return {"dispatched": 2, "checked": 3}
        raise AssertionError(path)
    monkeypatch.setattr(worker, "call", fake_call)
    assert worker.run_once() == 0
    assert [path for _, path, _ in calls] == [
        "/internal/v1/outbox/claim",
        "/internal/v1/collaboration-grants/reminders/dispatch",
    ]


def test_run_once_keeps_outbox_working_when_reminder_dispatch_fails(monkeypatch):
    calls = []
    def fake_call(method, path, payload=None):
        calls.append(path)
        if path == "/internal/v1/outbox/claim":
            return {"items": [], "count": 0}
        raise RuntimeError("reminder endpoint unavailable")
    monkeypatch.setattr(worker, "call", fake_call)
    assert worker.run_once() == 0
    assert calls == [
        "/internal/v1/outbox/claim",
        "/internal/v1/collaboration-grants/reminders/dispatch",
    ]
