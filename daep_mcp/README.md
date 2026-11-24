# DAEP local MCP adapter

The adapter runs on the developer workstation under the developer's MCP Host. DAEP does not create or manage the local Agent Runtime.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export DAEP_API_URL=https://daep.example.com
export DAEP_AGENT_TOKEN='<one-time-agent-token>'
python -m daep_mcp.server
```

Example host configuration:

```json
{
  "mcpServers": {
    "daep": {
      "command": "python",
      "args": ["/absolute/path/to/DAEP_Enterprise_Release/daep_mcp/server.py"],
      "env": {
        "DAEP_API_URL": "https://daep.example.com",
        "DAEP_AGENT_TOKEN": "<one-time-agent-token>"
      }
    }
  }
}
```

Never commit tokens. This adapter uses stdio and REST calls. For the DAEP Agent identity workflow, use `DAEP_AGENT_TOKEN`; `DAEP_MEMBER_TOKEN` is retained only as a legacy compatibility fallback. The dashboard-generated configuration uses the local stdio adapter, not the REST context endpoint as an MCP URL. Host idle-model wake-up is not guaranteed.


## Local Agent collaboration tools

The MCP adapter also exposes `register_local_agent`, `discover_project_agents`, and `heartbeat_local_agent`. Registration is scoped to a project the member belongs to. Advertise only capabilities actually available from the locally operated Agent. Presence is considered offline after 120 seconds without a heartbeat. DAEP stores metadata only and cannot guarantee waking an idle MCP Host.


## Agent Task Grants

With `DAEP_AGENT_TOKEN`, the adapter exposes only the Grant-scoped Agent task workflow: list grants, accept a grant, read an authorized task, report progress/blockers, and submit/read artifacts. The historical `list_my_agent_tasks` and `accept_agent_task` tool names remain as compatibility aliases but now use AgentTaskGrant inbox/accept endpoints. Agent credentials cannot use owner Member notifications, collaboration messaging, project governance, project audit, legacy assignment, or work-package management tools. The API independently enforces each task action's Grant scope.
