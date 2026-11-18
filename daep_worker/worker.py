import json, os, time, urllib.error, urllib.request, uuid

API=os.getenv('DAEP_API_URL','http://127.0.0.1:8000').rstrip('/')
TOKEN=os.getenv('DAEP_WORKER_TOKEN','')
WORKER_ID=os.getenv('DAEP_WORKER_ID','worker-'+uuid.uuid4().hex[:8])
BATCH=max(1,min(int(os.getenv('DAEP_WORKER_BATCH','20')),100))
LEASE=max(10,min(int(os.getenv('DAEP_WORKER_LEASE_SECONDS','60')),900))
POLL=max(1,int(os.getenv('DAEP_WORKER_POLL_SECONDS','2')))
DEST=os.getenv('DAEP_BROKER_WEBHOOK_URL','')


def call(method,path,payload=None):
    data=None if payload is None else json.dumps(payload).encode()
    req=urllib.request.Request(API+path,data=data,method=method,headers={'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as r:
        raw=r.read(); return json.loads(raw) if raw else {}


def deliver(item):
    # A transport-neutral HTTP sink. The sink may be an internal broker gateway,
    # queue bridge, or service that translates the envelope to Kafka/RabbitMQ/etc.
    if not DEST:
        raise RuntimeError('DAEP_BROKER_WEBHOOK_URL is not configured')
    req=urllib.request.Request(DEST,data=json.dumps(item['payload']).encode(),method='POST',headers={
        'Content-Type':'application/json','X-DAEP-Event-Type':item['event_type'],'X-DAEP-Message-ID':item['payload'].get('message_id','')})
    with urllib.request.urlopen(req,timeout=20) as r:
        if r.status >= 300: raise RuntimeError(f'broker returned HTTP {r.status}')


def run_once():
    result=call('POST','/internal/v1/outbox/claim',{'worker_id':WORKER_ID,'limit':BATCH,'lease_seconds':LEASE})
    for item in result.get('items',[]):
        try:
            deliver(item)
            call('POST',f"/internal/v1/outbox/{item['id']}/complete",{'worker_id':WORKER_ID})
        except Exception as exc:
            try: call('POST',f"/internal/v1/outbox/{item['id']}/fail",{'worker_id':WORKER_ID,'error':str(exc)[:2000]})
            except Exception: pass
    return result.get('count',0)


def main():
    if len(TOKEN)<32: raise SystemExit('DAEP_WORKER_TOKEN with at least 32 characters is required')
    while True:
        try: run_once()
        except Exception as exc: print(f'[daep-worker] {exc}',flush=True)
        time.sleep(POLL)

if __name__=='__main__': main()
