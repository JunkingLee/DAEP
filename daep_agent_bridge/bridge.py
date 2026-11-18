"""Local DAEP Agent Message Bridge.

Runs on a member workstation. It never starts or manages an Agent Runtime.
It polls the durable DAEP inbox, forwards each message to a configured local
command, and ACKs only after the command exits successfully. The cursor is
persisted locally so transient failures do not silently lose messages.
"""
import argparse, json, os, shlex, subprocess, time, urllib.error, urllib.request

API=os.getenv("DAEP_API_URL","http://127.0.0.1:8000").rstrip("/")
TOKEN=os.getenv("DAEP_AGENT_TOKEN","")
CURSOR_FILE=os.getenv("DAEP_AGENT_CURSOR_FILE", os.path.expanduser("~/.daep-agent-cursor"))
COMMAND=os.getenv("DAEP_AGENT_COMMAND","")
POLL=max(1,int(os.getenv("DAEP_AGENT_POLL_SECONDS","3")))
LIMIT=max(1,min(int(os.getenv("DAEP_AGENT_BATCH","20")),100))


def call(path, method="GET", payload=None):
    data=None if payload is None else json.dumps(payload).encode()
    headers={"Authorization":"Bearer "+TOKEN,"Content-Type":"application/json"}
    req=urllib.request.Request(API+path,data=data,method=method,headers=headers)
    with urllib.request.urlopen(req,timeout=20) as r:
        raw=r.read(); return json.loads(raw) if raw else {}


def read_cursor():
    try: return max(0,int(open(CURSOR_FILE).read().strip()))
    except (OSError,ValueError): return 0


def write_cursor(value):
    path=os.path.abspath(os.path.expanduser(CURSOR_FILE)); os.makedirs(os.path.dirname(path),exist_ok=True)
    tmp=path+".tmp"
    with open(tmp,"w") as f: f.write(str(value)+"\n")
    os.replace(tmp,path)


def dispatch(message, command):
    # The message is passed as a single JSON argument/stdin payload. No shell is used.
    argv=shlex.split(command)
    if not argv: raise RuntimeError("DAEP_AGENT_COMMAND is not configured")
    proc=subprocess.run(argv,input=json.dumps(message).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=300)
    if proc.returncode:
        detail=(proc.stderr or proc.stdout).decode(errors="replace")[-2000:]
        raise RuntimeError(f"local agent command failed ({proc.returncode}): {detail}")


def run_once(command=None):
    if len(TOKEN)<32: raise RuntimeError("DAEP_AGENT_TOKEN with at least 32 characters is required")
    command=command or COMMAND
    if not command: raise RuntimeError("DAEP_AGENT_COMMAND is required")
    cursor=read_cursor()
    result=call(f"/api/v1/me/notifications?after={cursor}&limit={LIMIT}")
    processed=0
    for message in result.get("items",[]):
        dispatch(message,command)
        ack=call(f"/api/v1/messages/{message['id']}/ack","POST",{"status":"ACKNOWLEDGED"})
        if ack.get("status") != "ACKNOWLEDGED": raise RuntimeError("DAEP message acknowledgement failed")
        cursor=max(cursor,int(message["seq"]))
        write_cursor(cursor); processed += 1
    return processed


def main():
    ap=argparse.ArgumentParser(description="DAEP local durable inbox bridge")
    ap.add_argument("--once",action="store_true",help="process one inbox batch and exit")
    ap.add_argument("--command",default=COMMAND,help="local command receiving message JSON on stdin")
    args=ap.parse_args()
    while True:
        try:
            run_once(args.command)
        except Exception as exc:
            print(f"[daep-agent-bridge] {exc}",flush=True)
        if args.once: break
        time.sleep(POLL)

if __name__ == "__main__": main()
