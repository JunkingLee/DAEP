# DAEP Local Agent Message Bridge

This optional workstation-side process reads the member durable inbox and forwards messages to a local command. It does **not** create, host, supervise, or wake an Agent Runtime.

Environment:
- `DAEP_API_URL`
- `DAEP_AGENT_TOKEN` (member API token, never the platform or worker token)
- `DAEP_AGENT_COMMAND` (argv-style command; no shell execution)
- `DAEP_AGENT_CURSOR_FILE`
- `DAEP_AGENT_POLL_SECONDS`
- `DAEP_AGENT_BATCH`

The bridge ACKs only after the local command exits with status 0. If dispatch fails, the message remains pending and is retried.

Example:
```
DAEP_API_URL=http://127.0.0.1:8000 \
DAEP_AGENT_TOKEN=... \
DAEP_AGENT_COMMAND='python local_agent_entry.py' \
python -m daep_agent_bridge.bridge
```
The message JSON is supplied on stdin to the configured command.


For multi-member projects, each member may register their own local Agent through the DAEP MCP adapter. Discovery is project-scoped and capability-filtered. The bridge remains a message transport helper; it does not manage Agent runtimes or coordinate execution internally.
