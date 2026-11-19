class ArtifactIn(BaseModel): artifact_type:str=Field(min_length=1,max_length=80); uri:str=Field(min_length=1,max_length=2048); commit_sha:Optional[str]=None; metadata:dict=Field(default_factory=dict)
class WorkResultIn(BaseModel): outcome:str=Field(pattern='^(COMPLETE|FAILED)$'); summary:str=Field(min_length=1,max_length=5000); idempotency_key:str=Field(default='',max_length=200)
class WorkPackageScanIn(BaseModel): stale_after_seconds:int=Field(default=3600,ge=300,le=604800)
class WorkPackageReassignIn(BaseModel): assignee_member_id:str=Field(min_length=1,max_length=120); agent_name:str=Field(min_length=1,max_length=120); reason:str=Field(min_length=1,max_length=2000)
class ProjectDecisionIn(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    decision:str=Field(min_length=1,max_length=4000)
    rationale:str=Field(default='',max_length=5000)
    accountable_member_id:str=Field(min_length=1,max_length=120)
    related_task_ids:list[str]=Field(default_factory=list,max_length=50)
    due_at:Optional[str]=Field(default=None,max_length=40)
class WorkflowStageIn(BaseModel):
    name:str=Field(min_length=1,max_length=120)
    key:str=Field(min_length=1,max_length=80)
    order:int=Field(ge=1,le=100)
    approval_role:str=Field(default='none',pattern='^(none|owner|manager|reviewer)$')
    sla_seconds:Optional[int]=Field(default=None,ge=300,le=2592000)
class WorkflowConfigIn(BaseModel):
    stages:list[WorkflowStageIn]=Field(min_length=1,max_length=30)
    enabled:bool=True
class GateConfigIn(BaseModel):
    enabled:bool=True
    required_roles:list[str]=Field(default_factory=list,max_length=10)
    required_evidence:bool=False
    required_all_tasks_done:bool=False
class RequirementAcceptanceIn(BaseModel):
    decision:str=Field(pattern='^(APPROVE|REJECT)$')
    verified_criteria:list[int]=Field(default_factory=list,max_length=100)
    comment:str=Field(default='',max_length=4000)
def now(): return datetime.now(timezone.utc).isoformat()
DATABASE_URL=os.getenv('DATABASE_URL','')
PRIVILEGED_DATABASE_URL=os.getenv('DAEP_PRIVILEGED_DATABASE_URL','')
_tenant_ctx=contextvars.ContextVar('daep_tenant_id',default='')
_admin_ctx=contextvars.ContextVar('daep_platform_admin',default=False)
_auth_lookup_ctx=contextvars.ContextVar('daep_auth_lookup',default=False)
_service_ctx=contextvars.ContextVar('daep_internal_service',default=False)
