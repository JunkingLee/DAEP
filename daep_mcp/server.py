"""DAEP MCP stdio adapter. The member controls and launches this process locally."""
import json, os, urllib.request, urllib.error, urllib.parse
from mcp.server.fastmcp import FastMCP

API=os.getenv('DAEP_API_URL','http://127.0.0.1:8000').rstrip('/')
TOKEN=os.getenv('DAEP_MEMBER_TOKEN','')
mcp=FastMCP('DAEP Engineering Platform')

def call(method, path, payload=None):
    if not TOKEN:
        raise RuntimeError('Set DAEP_MEMBER_TOKEN in the MCP process environment')
    data=None if payload is None else json.dumps(payload).encode()
    req=urllib.request.Request(API+path,data=data,method=method,headers={
        'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json','Accept':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=20) as r:
            raw=r.read()
            return json.loads(raw) if raw else {'ok':True}
    except urllib.error.HTTPError as e:
        detail=e.read().decode(errors='replace')
        raise RuntimeError(f'DAEP API {e.code}: {detail}') from e
    except urllib.error.URLError as e:
        raise RuntimeError(f'Cannot reach DAEP API at {API}: {e}') from e

@mcp.tool()
def get_my_tasks() -> list:
    """List engineering tasks assigned to the authenticated member."""
    return call('GET','/api/v1/me/tasks')

@mcp.tool()
def get_task_detail(task_id: str) -> dict:
    """Read a task, its assignees, dependencies and current status."""
    return call('GET',f'/api/v1/tasks/{task_id}')

@mcp.tool()
def get_my_notifications(after: int = 0, limit: int = 50) -> dict:
    """Read pending platform messages; pass next_cursor back as after to continue."""
    return call('GET',f'/api/v1/me/notifications?after={max(0,after)}&limit={max(1,min(limit,100))}')

@mcp.tool()
def acknowledge_notification(message_id: str, status: str = 'ACKNOWLEDGED') -> dict:
    """Acknowledge a platform message after it has been processed."""
    return call('POST',f'/api/v1/messages/{message_id}/ack',{'status':status})

@mcp.tool()
def report_task_progress(task_id: str, progress: int, note: str = '') -> dict:
    """Report task progress from 0 to 100 percent."""
    if not 0 <= progress <= 100: raise ValueError('progress must be between 0 and 100')
    return call('POST',f'/api/v1/tasks/{task_id}/progress',{'progress':progress,'note':note})

@mcp.tool()
def report_task_blocked(task_id: str, reason: str) -> dict:
    """Mark an assigned task as blocked and record the reason."""
    return call('POST',f'/api/v1/tasks/{task_id}/blocked',{'reason':reason})

@mcp.tool()
def submit_task_artifact(task_id: str, artifact_type: str, uri: str, commit_sha: str = '') -> dict:
    """Attach an engineering artifact or repository reference to a task."""
    return call('POST',f'/api/v1/tasks/{task_id}/artifacts',{
        'artifact_type':artifact_type,'uri':uri,'commit_sha':commit_sha or None,'metadata':{}})

@mcp.tool()
def register_local_agent(project_id: str, agent_name: str, capabilities: list, protocols: list = None, status: str = 'AVAILABLE', metadata: dict = None) -> dict:
    """Register this member's locally operated Agent and its project-scoped capabilities."""
    return call('POST',f'/api/v1/projects/{project_id}/agents/register',{
        'agent_name':agent_name,'capabilities':capabilities,'protocols':protocols or ['mcp'],
        'status':status,'metadata':metadata or {}})

@mcp.tool()
def discover_project_agents(project_id: str, capability: str = '', protocol: str = 'mcp') -> dict:
    """Discover project members' registered local Agents by capability and protocol."""
    query=urllib.parse.urlencode({k:v for k,v in {'capability':capability,'protocol':protocol}.items() if v})
    return call('GET',f'/api/v1/projects/{project_id}/agents'+(('?'+query) if query else ''))

@mcp.tool()
def heartbeat_local_agent(project_id: str, agent_name: str, status: str = 'AVAILABLE') -> dict:
    """Refresh presence for an already registered local Agent."""
    return call('POST',f'/api/v1/projects/{project_id}/agents/heartbeat',{'agent_name':agent_name,'status':status})

@mcp.tool()
def send_collaboration_message(recipient_member_id: str, title: str, content: str,
                               task_id: str = '', project_id: str = '', priority: str = 'NORMAL') -> dict:
    """Send a persistent collaboration message to another platform member."""
    return call('POST','/api/v1/messages',{
        'recipient_member_id':recipient_member_id,'project_id':project_id or None,'task_id':task_id or None,
        'message_type':'COLLABORATION','title':title,'content':content,'priority':priority})

if __name__=='__main__':
    import urllib.parse
    mcp.run(transport='stdio')
