# DAEP local MCP adapter

The adapter runs on the developer workstation under the developer's MCP Host. DAEP does not create or manage the local Agent Runtime.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export DAEP_API_URL=https://daep.example.com
export DAEP_MEMBER_TOKEN='<individual-member-token>'
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
        "DAEP_MEMBER_TOKEN": "<individual-member-token>"
      }
    }
  }
}
```

Never commit tokens. This adapter uses stdio and REST calls; Host idle-model wake-up is not guaranteed.


## Local Agent collaboration tools

The MCP adapter also exposes `register_local_agent`, `discover_project_agents`, and `heartbeat_local_agent`. Registration is scoped to a project the member belongs to. Advertise only capabilities actually available from the locally operated Agent. Presence is considered offline after 120 seconds without a heartbeat. DAEP stores metadata only and cannot guarantee waking an idle MCP Host.
