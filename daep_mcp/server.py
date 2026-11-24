"""DAEP MCP stdio adapter. The member controls and launches this process locally. Prefer DAEP_AGENT_TOKEN for first-class Agent identity; DAEP_MEMBER_TOKEN remains a compatibility fallback."""
import json, os, urllib.request, urllib.error, urllib.parse
from mcp.server.fastmcp import FastMCP

API=os.getenv('DAEP_API_URL','http://127.0.0.1:8000').rstrip('/')
TOKEN=os.getenv('DAEP_AGENT_TOKEN','')
if not TOKEN: TOKEN=os.getenv('DAEP_MEMBER_TOKEN','')  # backwards-compatible fallback
mcp=FastMCP('DAEP Engineering Platform')

def _agent_path_allowed(method, path):
    # Agent credentials never inherit the owner's Member permissions.
    route=urllib.parse.urlsplit(path).path
    if method=='GET' and route in ('/api/v1/mcp/context','/api/v1/agents/me/grants'):
        return True
    parts=route.strip('/').split('/')
    if method=='POST' and len(parts)==5 and parts[:3]==['api','v1','agent-grants'] and parts[4]=='accept' and parts[3]:
        return True
    if len(parts)==4 and parts[:2]==['api','v1'] and parts[2]=='tasks' and parts[3]:
        return method=='GET'
    if len(parts)==5 and parts[:2]==['api','v1'] and parts[2]=='tasks' and parts[3]:
        return (method=='POST' and parts[4] in ('progress','blocked','artifacts')) or (method=='GET' and parts[4] in ('artifacts','artifact-versions','artifact-quality'))
    return False


def call(method, path, payload=None):
    if not TOKEN:
        raise RuntimeError('Set DAEP_AGENT_TOKEN in the MCP process environment')
    if TOKEN.startswith('daep_at_') and not _agent_path_allowed(method, path):
        raise RuntimeError('Agent tokens may only use Grant-scoped task tools; owner Member permissions are not inherited')
    data=None if payload is None else json.dumps(payload).encode()
    req=urllib.request.Request(API+path,data=data,method=method,headers={
        'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json','Accept':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=20) as r:
            raw=r.read()
            content_type=r.headers.get('Content-Type','')
            if 'json' in content_type:
                return json.loads(raw) if raw else {'ok':True}
            return {'content_type':content_type,'body':raw.decode('utf-8',errors='replace')}
    except urllib.error.HTTPError as e:
        detail=e.read().decode(errors='replace')
        raise RuntimeError(f'DAEP API {e.code}: {detail}') from e
    except urllib.error.URLError as e:
        raise RuntimeError(f'Cannot reach DAEP API at {API}: {e}') from e

@mcp.tool()
def get_agent_context() -> dict:
    """Identify the connected Agent, its owner and its explicitly bound projects."""
    return call('GET','/api/v1/mcp/context')

@mcp.tool()
def list_my_agent_tasks() -> dict:
    """List owner-authorized task grants addressed to this Agent identity."""
    return call('GET','/api/v1/agents/me/grants')

@mcp.tool()
def list_my_agent_grants() -> dict:
    """List active owner-authorized task grants for this Agent identity."""
    return call('GET','/api/v1/agents/me/grants')

@mcp.tool()
def accept_agent_task(grant_id: str) -> dict:
    """Accept an owner-authorized task grant addressed to this Agent identity."""
    return call('POST',f'/api/v1/agent-grants/{grant_id}/accept',{})

@mcp.tool()
def accept_agent_task_grant(grant_id: str) -> dict:
    """Accept an owner-authorized task grant addressed to this Agent identity."""
    return call('POST',f'/api/v1/agent-grants/{grant_id}/accept',{})

@mcp.tool()
def get_my_tasks() -> list:
    """List tasks assigned to the authenticated member. Agent tokens should call list_my_agent_tasks."""
    return call('GET','/api/v1/me/tasks')

@mcp.tool()
def accept_agent_task_assignment(assignment_id: str) -> dict:
    """Accept an assignment explicitly addressed to this Agent identity."""
    return call('POST',f'/api/v1/agent-assignments/{assignment_id}/accept',{})

@mcp.tool()
def list_agent_task_assignments(task_id: str) -> dict:
    """List Agent assignments for a task; requires project access."""
    return call('GET',f'/api/v1/tasks/{task_id}/agent-assignments')

@mcp.tool()
def assign_task_to_agent(task_id: str, agent_id: str) -> dict:
    """Assign a task to an active Agent bound to the same project; requires project manager authority."""
    return call('POST',f'/api/v1/tasks/{task_id}/agent-assignments',{'agent_id':agent_id})

@mcp.tool()
def revoke_agent_task_assignment(assignment_id: str, reason: str = '') -> dict:
    """Revoke an active Agent task assignment; requires project manager authority."""
    return call('POST',f'/api/v1/agent-assignments/{assignment_id}/revoke',{'reason':reason})

@mcp.tool()
def get_task_detail(task_id: str) -> dict:
    """Read a task only when the authenticated identity has access to its project."""
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

@mcp.tool()
def offer_task_delegation(task_id: str, recipient_member_id: str, agent_name: str, reason: str = '', expires_in_seconds: int = 86400) -> dict:
    """Offer an assigned task to another project member's online local Agent."""
    return call('POST',f'/api/v1/tasks/{task_id}/delegations',{
        'recipient_member_id':recipient_member_id,'agent_name':agent_name,
        'reason':reason,'expires_in_seconds':expires_in_seconds})

@mcp.tool()
def respond_task_delegation(delegation_id: str, decision: str) -> dict:
    """Accept or reject a task delegation addressed to the authenticated member."""
    if decision not in ('ACCEPT','REJECT'): raise ValueError('decision must be ACCEPT or REJECT')
    return call('POST',f'/api/v1/delegations/{delegation_id}/respond',{'decision':decision})

@mcp.tool()
def list_task_delegations(task_id: str) -> list:
    """List delegation offers and their current status for a task."""
    return call('GET',f'/api/v1/tasks/{task_id}/delegations')


@mcp.tool()
def create_task_work_package(parent_task_id: str, title: str, assignee_member_id: str, agent_name: str, description: str = '', dependencies: list = None) -> dict:
    """Create and assign a child work package to another member's registered local Agent."""
    return call('POST',f'/api/v1/tasks/{parent_task_id}/work-packages',{
        'title':title,'description':description,'assignee_member_id':assignee_member_id,
        'agent_name':agent_name,'dependencies':dependencies or []})

@mcp.tool()
def report_work_package_result(task_id: str, outcome: str, summary: str, idempotency_key: str = '') -> dict:
    """Report a child work package as complete (requires artifacts) or blocked/failed."""
    return call('POST',f'/api/v1/tasks/{task_id}/work-result',{
        'outcome':outcome,'summary':summary,'idempotency_key':idempotency_key})

@mcp.tool()
def request_project_role_change(project_id: str, member_id: str, new_role: str, reason: str) -> dict:
    """Request a governed project role change; a different project owner must approve."""
    return call('POST',f'/api/v1/projects/{project_id}/role-change-requests',{'member_id':member_id,'new_role':new_role,'reason':reason})

@mcp.tool()
def list_project_approvals(project_id: str, status: str = "PENDING") -> dict:
    """List project governance approvals."""
    return call('GET',f'/api/v1/projects/{project_id}/approvals?status={status}')

@mcp.tool()
def decide_project_approval(project_id: str, approval_id: str, decision: str, reason: str) -> dict:
    """Approve or reject a role-change request as a project owner."""
    return call('POST',f'/api/v1/projects/{project_id}/approvals/{approval_id}/decision',{'decision':decision,'reason':reason})

@mcp.tool()
def get_project_audit(project_id: str, limit: int = 100, event_type: str = "") -> dict:
    """Query project-scoped audit events."""
    return call('GET',f'/api/v1/projects/{project_id}/audit?limit={max(1,min(limit,500))}&event_type={urllib.parse.quote(event_type)}')

@mcp.tool()
def export_project_audit_csv(project_id: str, limit: int = 5000) -> dict:
    """Export project audit CSV (raw response is returned by the DAEP API client)."""
    return call('GET',f'/api/v1/projects/{project_id}/audit.csv?limit={max(1,min(limit,10000))}')

@mcp.tool()
def scan_project_work_health(project_id: str) -> dict:
    """Recalculate work-package SLA and dependency risk states for a project."""
    return call('POST',f'/api/v1/projects/{project_id}/work-packages/scan-health',{})

@mcp.tool()
def get_project_work_health(project_id: str) -> dict:
    """Get project work-package health score, SLA risks and dependency blockers."""
    return call('GET',f'/api/v1/projects/{project_id}/work-health')

@mcp.tool()
def scan_stalled_work_packages(project_id: str, stale_after_seconds: int = 3600) -> dict:
    """Mark inactive work packages for manager attention; never auto-reassigns them."""
    return call('POST',f'/api/v1/projects/{project_id}/work-packages/scan-stalled',{
        'stale_after_seconds':stale_after_seconds})

@mcp.tool()
def reassign_stalled_work_package(work_package_id: str, assignee_member_id: str, agent_name: str, reason: str) -> dict:
    """Manager-approved reassignment of a work package already marked stalled."""
    return call('POST',f'/api/v1/work-packages/{work_package_id}/reassign',{
        'assignee_member_id':assignee_member_id,'agent_name':agent_name,'reason':reason})

@mcp.tool()
def list_task_work_packages(parent_task_id: str) -> list:
    """List child work packages, current task states and their submitted artifacts."""
    return call('GET',f'/api/v1/tasks/{parent_task_id}/work-packages')

@mcp.tool()
def get_task_work_timeline(parent_task_id: str, limit: int = 200) -> dict:
    """Read the chronological work-package timeline, including events, messages and artifacts."""
    return call('GET',f'/api/v1/tasks/{parent_task_id}/work-timeline?limit={max(1,min(limit,500))}')

@mcp.tool()
def get_task_work_summary(parent_task_id: str) -> dict:
    """Aggregate child work package progress, blockers and artifact count."""
    return call('GET',f'/api/v1/tasks/{parent_task_id}/work-summary')


@mcp.tool()
def report_agent_task_progress(task_id: str, progress: int, note: str = '') -> dict:
    """Report progress for a task accepted by this Agent identity; 100% requires at least one artifact."""
    if not 0 <= progress <= 100: raise ValueError('progress must be between 0 and 100')
    return call('POST',f'/api/v1/tasks/{task_id}/progress',{'progress':progress,'note':note})


@mcp.tool()
def report_agent_task_blocked(task_id: str, reason: str) -> dict:
    """Report a blocker for a task accepted by this Agent identity."""
    if not reason.strip(): raise ValueError('reason is required')
    return call('POST',f'/api/v1/tasks/{task_id}/blocked',{'reason':reason})


@mcp.tool()
def submit_agent_task_artifact(task_id: str, artifact_type: str, uri: str, commit_sha: str = '') -> dict:
    """Submit an artifact for a task accepted by this Agent identity before requesting human review."""
    if not artifact_type.strip() or not uri.strip(): raise ValueError('artifact_type and uri are required')
    return call('POST',f'/api/v1/tasks/{task_id}/artifacts',{
        'artifact_type':artifact_type,'uri':uri,'commit_sha':commit_sha or None,'metadata':{}})


if __name__=='__main__':
    import urllib.parse
    mcp.run(transport='stdio')
