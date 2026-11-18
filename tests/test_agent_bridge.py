import json
from pathlib import Path
import daep_agent_bridge.bridge as bridge


def test_bridge_dispatches_json_without_shell(monkeypatch):
    seen = {}
    class Result:
        returncode = 0
        stdout = b"ok"
        stderr = b""
    def fake_run(argv, input, stdout, stderr, timeout):
        seen['argv'] = argv
        seen['payload'] = json.loads(input)
        return Result()
    monkeypatch.setattr(bridge.subprocess, 'run', fake_run)
    bridge.dispatch({'id':'m1','content':'hello'}, 'python local_agent.py --mode bridge')
    assert seen['argv'] == ['python','local_agent.py','--mode','bridge']
    assert seen['payload']['id'] == 'm1'


def test_bridge_does_not_ack_when_dispatch_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(bridge, 'TOKEN', 'x'*40)
    monkeypatch.setattr(bridge, 'CURSOR_FILE', str(tmp_path/'cursor'))
    calls=[]
    def fake_call(path, method='GET', payload=None):
        calls.append((path,method,payload))
        if path.startswith('/api/v1/me/notifications'):
            return {'items':[{'id':'m1','seq':1,'content':'x'}]}
        raise AssertionError('ACK must not be called')
    monkeypatch.setattr(bridge, 'call', fake_call)
    monkeypatch.setattr(bridge, 'dispatch', lambda message, command: (_ for _ in ()).throw(RuntimeError('agent unavailable')))
    import pytest
    with pytest.raises(RuntimeError):
        bridge.run_once('python local_agent.py')
    assert not (tmp_path/'cursor').exists()
    assert len(calls) == 1


def test_bridge_acks_and_persists_cursor_after_success(monkeypatch, tmp_path):
    monkeypatch.setattr(bridge, 'TOKEN', 'x'*40)
    monkeypatch.setattr(bridge, 'CURSOR_FILE', str(tmp_path/'cursor'))
    calls=[]
    def fake_call(path, method='GET', payload=None):
        calls.append((path,method,payload))
        if path.startswith('/api/v1/me/notifications'):
            return {'items':[{'id':'m1','seq':7,'content':'x'}]}
        return {'status':'ACKNOWLEDGED'}
    monkeypatch.setattr(bridge, 'call', fake_call)
    monkeypatch.setattr(bridge, 'dispatch', lambda message, command: None)
    assert bridge.run_once('python local_agent.py') == 1
    assert Path(tmp_path/'cursor').read_text().strip() == '7'
    assert calls[-1][0] == '/api/v1/messages/m1/ack'
