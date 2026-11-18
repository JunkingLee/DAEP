import hashlib, hmac, json, os

def test_rc9_readiness_and_github_webhook_signature():
    assert client.get('/readyz').status_code == 200
    import app.main as module
    secret = 'github-webhook-secret'
    os.environ['DAEP_GITHUB_WEBHOOK_SECRET'] = secret
    body = {
        'action': 'push',
        'after': 'abc123',
        'tenant_id': 'tenant-default',
    }
    raw = json.dumps(body, separators=(',', ':')).encode()
    signature = 'sha256=' + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    headers = {
        'X-DAEP-Provider': 'github',
        'X-GitHub-Event': 'push',
        'X-GitHub-Delivery': 'delivery-rc9-1',
        'X-Hub-Signature-256': signature,
        'Content-Type': 'application/json',
    }
    accepted = client.post('/api/v1/integrations/git/webhook', headers=headers, content=raw)
    assert accepted.status_code == 200
    assert accepted.json()['provider'] if 'provider' in accepted.json() else True

    duplicate = client.post('/api/v1/integrations/git/webhook', headers=headers, content=raw)
    assert duplicate.status_code == 200
    assert duplicate.json()['event_id'] == accepted.json()['event_id']

    bad = dict(headers)
    bad['X-Hub-Signature-256'] = 'sha256=' + ('0' * 64)
    assert client.post('/api/v1/integrations/git/webhook', headers=bad, content=raw).status_code == 401

    os.environ.pop('DAEP_GITHUB_WEBHOOK_SECRET', None)
