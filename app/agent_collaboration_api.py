"""Task-scoped collaboration Session and Owner-authorized Agent grants.

DAEP persists collaboration governance only. It never creates or runs Agent runtimes.
"""
import json
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Header, HTTPException


COLLABORATION_SCOPES = {
    "session.read",
    "session.message.send",
    "session.proposal.create",
}


def register_agent_collaboration_routes(
    app, conn, actor, event, now, begin_serialized_write,
    lock_task, task_context, ensure_policy, database_url,
):
    router = APIRouter()

    def _member_task_session(c, task_id, member, stamp):
        task = task_context(c, task_id, member)
        policy = ensure_policy(c, task, member["id"])
        if policy["responsible_member_id"] != member["id"]:
            raise HTTPException(
                409,
                "The current assignee must explicitly take over the Task Agent execution policy first",
            )
        c.execute(
            """INSERT INTO agent_collaboration_sessions
               (id,tenant_id,project_id,task_id,responsible_member_id,status,
                created_by_member_id,policy_version,created_at,updated_at)
               VALUES(?,?,?,?,?,'OPEN',?,1,?,?)
               ON CONFLICT(task_id) DO NOTHING""",
            (
                "acs_" + uuid.uuid4().hex[:20], task["project_tenant_id"],
                task["project_id"], task_id, member["id"], member["id"],
                stamp, stamp,
            ),
        )
        session = c.execute(
            """SELECT * FROM agent_collaboration_sessions
               WHERE task_id=? AND tenant_id=?""",
            (task_id, task["project_tenant_id"]),
        ).fetchone()
        if not session:
            raise HTTPException(500, "Task collaboration Session could not be initialized")
        if session["project_id"] != task["project_id"]:
            raise HTTPException(409, "Collaboration Session project relationship is invalid")
        # Policy takeover is an explicit human action. Once the new assignee has
        # taken over that policy, align Session governance to the same owner.
        if session["responsible_member_id"] != member["id"]:
            c.execute(
                """UPDATE agent_collaboration_sessions
                   SET responsible_member_id=?,policy_version=policy_version+1,updated_at=?
                   WHERE id=? AND status<>'CLOSED'""",
                (member["id"], stamp, session["id"]),
            )
            session = c.execute(
                "SELECT * FROM agent_collaboration_sessions WHERE id=?",
                (session["id"],),
            ).fetchone()
        return task, session

    def _effective_status(row, stamp):
        if row["status"] in ("AUTHORIZED", "ACCEPTED") and row["expires_at"] <= stamp:
            return "EXPIRED"
        return row["status"]

    @router.get("/api/v1/tasks/{task_id}/collaboration-session")
    def get_task_collaboration_session(task_id: str, authorization: str = Header(None)):
        current = actor(authorization)
        if current.get("actor_type") != "MEMBER":
            raise HTTPException(403, "Member authentication required")
        with conn() as c:
            begin_serialized_write(c)
            lock_task(c, task_id)
            _, session = _member_task_session(c, task_id, current, now())
            return dict(session)

    @router.patch("/api/v1/tasks/{task_id}/collaboration-session")
    def update_task_collaboration_session(task_id: str, body: dict, authorization: str = Header(None)):
        current = actor(authorization)
        if current.get("actor_type") != "MEMBER":
            raise HTTPException(403, "Member authentication required")
        status = str(body.get("status", "")).upper()
        if status not in ("OPEN", "PAUSED", "CLOSED"):
            raise HTTPException(422, "status must be OPEN, PAUSED or CLOSED")
        title = body.get("title")
        summary = body.get("summary")
        if title is not None and (not isinstance(title, str) or len(title) > 200):
            raise HTTPException(422, "title must be a string of at most 200 characters")
        if summary is not None and (not isinstance(summary, str) or len(summary) > 4000):
            raise HTTPException(422, "summary must be a string of at most 4000 characters")
        with conn() as c:
            begin_serialized_write(c)
            lock_task(c, task_id)
            task, session = _member_task_session(c, task_id, current, now())
            if session["status"] == "CLOSED" and status != "CLOSED":
                raise HTTPException(409, "A closed collaboration Session cannot be reopened")
            if session["status"] == status and title is None and summary is None:
                return dict(session)
            stamp = now()
            closed_at = stamp if status == "CLOSED" else None
            c.execute(
                """UPDATE agent_collaboration_sessions
                   SET status=?,title=COALESCE(?,title),summary=COALESCE(?,summary),
                       closed_at=?,policy_version=policy_version+1,updated_at=?
                   WHERE id=?""",
                (status, title, summary, closed_at, stamp, session["id"]),
            )
            event(
                c, "agent.collaboration_session.updated", current["id"], task_id,
                {"session_id": session["id"], "previous_status": session["status"],
                 "status": status, "policy_version": session["policy_version"] + 1},
                tenant_override=task["project_tenant_id"],
            )
            return dict(c.execute(
                "SELECT * FROM agent_collaboration_sessions WHERE id=?",
                (session["id"],),
            ).fetchone())

    @router.get("/api/v1/tasks/{task_id}/collaboration-grants")
    def list_task_collaboration_grants(task_id: str, authorization: str = Header(None)):
        current = actor(authorization)
        if current.get("actor_type") != "MEMBER":
            raise HTTPException(403, "Member authentication required")
        with conn() as c:
            begin_serialized_write(c)
            lock_task(c, task_id)
            task, session = _member_task_session(c, task_id, current, now())
            rows = c.execute(
                """SELECT g.*,a.name agent_name FROM agent_collaboration_grants g
                   JOIN agents a ON a.id=g.agent_id
                   WHERE g.tenant_id=? AND g.task_id=?
                   ORDER BY g.created_at DESC""",
                (task["project_tenant_id"], task_id),
            ).fetchall()
            stamp = now()
            return {"task_id": task_id, "session_id": session["id"], "items": [
                {**dict(row), "scopes": json.loads(row["scopes_json"]),
                 "resource_scope": json.loads(row["resource_scope_json"]),
                 "effective_status": _effective_status(row, stamp)}
                for row in rows
            ]}

    @router.post("/api/v1/tasks/{task_id}/collaboration-grants")
    def create_task_collaboration_grant(task_id: str, body: dict, authorization: str = Header(None)):
        current = actor(authorization)
        if current.get("actor_type") != "MEMBER":
            raise HTTPException(403, "Member authentication required to authorize Agent collaboration")
        agent_id = str(body.get("agent_id", "")).strip()
        if not agent_id or len(agent_id) > 120:
            raise HTTPException(422, "agent_id is required")
        scopes = body.get("scopes", ["session.read", "session.message.send"])
        if (
            not isinstance(scopes, list) or not scopes or len(scopes) > len(COLLABORATION_SCOPES)
            or any(not isinstance(scope, str) for scope in scopes)
            or len(set(scopes)) != len(scopes)
            or not set(scopes).issubset(COLLABORATION_SCOPES)
        ):
            raise HTTPException(422, "scopes must be a non-empty list of supported collaboration scopes")
        resource_scope = body.get("resource_scope", {})
        if not isinstance(resource_scope, dict) or set(resource_scope) - {"resource_ids"}:
            raise HTTPException(422, "resource_scope supports only resource_ids")
        resource_ids = resource_scope.get("resource_ids", [])
        if (
            not isinstance(resource_ids, list) or len(resource_ids) > 100
            or any(not isinstance(value, str) or not value or len(value) > 120 for value in resource_ids)
            or len(set(resource_ids)) != len(resource_ids)
        ):
            raise HTTPException(422, "resource_scope.resource_ids must contain unique non-empty IDs")
        days = body.get("expires_in_days", 30)
        if isinstance(days, bool) or not isinstance(days, int) or days < 1 or days > 90:
            raise HTTPException(422, "expires_in_days must be an integer between 1 and 90")
        with conn() as c:
            begin_serialized_write(c)
            lock_task(c, task_id)
            task, session = _member_task_session(c, task_id, current, now())
            if session["status"] != "OPEN":
                raise HTTPException(409, "Only an OPEN collaboration Session accepts new Agent grants")
            agent = c.execute(
                """SELECT id,name,status,owner_member_id,tenant_id FROM agents
                   WHERE id=? AND tenant_id=?""",
                (agent_id, task["project_tenant_id"]),
            ).fetchone()
            if not agent or agent["status"] != "ACTIVE":
                raise HTTPException(404, "Active Agent not found in this tenant")
            if agent["owner_member_id"] != current["id"]:
                raise HTTPException(403, "Only the Agent Owner can authorize their own Agent")
            stamp = now()
            c.execute(
                """UPDATE agent_collaboration_grants SET status='EXPIRED',updated_at=?
                   WHERE session_id=? AND status IN ('AUTHORIZED','ACCEPTED') AND expires_at<=?""",
                (stamp, session["id"], stamp),
            )
            existing = c.execute(
                """SELECT id,status FROM agent_collaboration_grants
                   WHERE session_id=? AND agent_id=? AND status IN ('AUTHORIZED','ACCEPTED')""",
                (session["id"], agent_id),
            ).fetchone()
            if existing:
                raise HTTPException(409, detail={
                    "message": "This Agent already has an active collaboration grant",
                    "grant_id": existing["id"], "status": existing["status"],
                })
            expires = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
            grant_id = "acg_" + uuid.uuid4().hex[:20]
            c.execute(
                """INSERT INTO agent_collaboration_grants
                   (id,tenant_id,project_id,task_id,session_id,agent_id,owner_member_id,
                    authorized_by_member_id,scopes_json,resource_scope_json,status,
                    created_at,updated_at,expires_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,'AUTHORIZED',?,?,?)""",
                (grant_id, task["project_tenant_id"], task["project_id"], task_id,
                 session["id"], agent_id, current["id"], current["id"],
                 json.dumps(sorted(scopes), separators=(",", ":")),
                 json.dumps({"resource_ids": sorted(resource_ids)}, separators=(",", ":")),
                 stamp, stamp, expires),
            )
            event(
                c, "agent.collaboration_grant.authorized", current["id"], task_id,
                {"grant_id": grant_id, "session_id": session["id"], "agent_id": agent_id,
                 "scopes": sorted(scopes), "resource_scope": {"resource_ids": sorted(resource_ids)},
                 "expires_at": expires},
                tenant_override=task["project_tenant_id"],
            )
            return {
                "id": grant_id, "task_id": task_id, "session_id": session["id"],
                "agent_id": agent_id, "agent_name": agent["name"],
                "owner_member_id": current["id"], "authorized_by_member_id": current["id"],
                "scopes": sorted(scopes), "resource_scope": {"resource_ids": sorted(resource_ids)},
                "status": "AUTHORIZED", "created_at": stamp, "expires_at": expires,
            }

    @router.delete("/api/v1/collaboration-grants/{grant_id}")
    def revoke_collaboration_grant(grant_id: str, body: dict = None, authorization: str = Header(None)):
        current = actor(authorization)
        if current.get("actor_type") != "MEMBER":
            raise HTTPException(403, "Member authentication required")
        reason = str((body or {}).get("reason", "")).strip()
        if len(reason) > 1000:
            raise HTTPException(422, "reason must be at most 1000 characters")
        with conn() as c:
            begin_serialized_write(c)
            lookup = c.execute(
                "SELECT task_id FROM agent_collaboration_grants WHERE id=? AND tenant_id=?",
                (grant_id, current.get("tenant_id", "tenant-default")),
            ).fetchone()
            if not lookup:
                raise HTTPException(404, "Collaboration grant not found")
            lock_task(c, lookup["task_id"])
            row = c.execute(
                "SELECT * FROM agent_collaboration_grants WHERE id=? AND tenant_id=?",
                (grant_id, current.get("tenant_id", "tenant-default")),
            ).fetchone()
            if not row:
                raise HTTPException(404, "Collaboration grant not found")
            if row["owner_member_id"] != current["id"] or row["authorized_by_member_id"] != current["id"]:
                raise HTTPException(403, "Only the Agent Owner who authorized this grant can revoke it")
            if row["status"] not in ("AUTHORIZED", "ACCEPTED"):
                raise HTTPException(409, "Collaboration grant is no longer active")
            stamp = now()
            if row["expires_at"] <= stamp:
                c.execute(
                    "UPDATE agent_collaboration_grants SET status='EXPIRED',updated_at=? WHERE id=?",
                    (stamp, grant_id),
                )
                raise HTTPException(409, "Collaboration grant has expired")
            c.execute(
                """UPDATE agent_collaboration_grants
                   SET status='REVOKED',revoked_at=?,updated_at=?,revoked_by_member_id=?,revoke_reason=?
                   WHERE id=? AND status IN ('AUTHORIZED','ACCEPTED')""",
                (stamp, stamp, current["id"], reason or None, grant_id),
            )
            event(
                c, "agent.collaboration_grant.revoked", current["id"], row["task_id"],
                {"grant_id": grant_id, "session_id": row["session_id"],
                 "agent_id": row["agent_id"], "reason": reason or "Owner revoked collaboration grant"},
                tenant_override=row["tenant_id"],
            )
            return {"id": grant_id, "status": "REVOKED", "revoked_at": stamp,
                    "revoked_by_member_id": current["id"]}

    @router.get("/api/v1/agents/me/collaboration-grants")
    def list_agent_collaboration_grants(authorization: str = Header(None)):
        current = actor(authorization)
        if current.get("actor_type") != "AGENT":
            raise HTTPException(403, "Agent Token required")
        stamp = now()
        with conn() as c:
            rows = c.execute(
                """SELECT g.id grant_id,g.task_id,g.project_id,g.session_id,g.owner_member_id,
                          g.scopes_json,g.resource_scope_json,g.status,g.created_at,g.expires_at,
                          s.status session_status,t.title task_title,p.name project_name
                   FROM agent_collaboration_grants g
                   JOIN agents a ON a.id=g.agent_id
                   JOIN agent_collaboration_sessions s ON s.id=g.session_id
                   JOIN tasks t ON t.id=g.task_id
                   JOIN projects p ON p.id=g.project_id
                   WHERE g.tenant_id=? AND g.agent_id=? AND a.owner_member_id=g.owner_member_id
                     AND a.status='ACTIVE' AND a.tenant_id=g.tenant_id
                     AND p.tenant_id=g.tenant_id AND p.status='ACTIVE'
                     AND g.status IN ('AUTHORIZED','ACCEPTED') AND g.expires_at>?
                   ORDER BY g.created_at DESC""",
                (current.get("tenant_id", "tenant-default"), current["agent_id"], stamp),
            ).fetchall()
            return {"agent_id": current["agent_id"], "items": [
                {**dict(row), "scopes": json.loads(row["scopes_json"]),
                 "resource_scope": json.loads(row["resource_scope_json"])}
                for row in rows
            ]}

    @router.post("/api/v1/collaboration-grants/{grant_id}/accept")
    def accept_collaboration_grant(grant_id: str, authorization: str = Header(None)):
        current = actor(authorization)
        if current.get("actor_type") != "AGENT":
            raise HTTPException(403, "Agent Token required")
        with conn() as c:
            begin_serialized_write(c)
            lookup = c.execute(
                "SELECT task_id FROM agent_collaboration_grants WHERE id=? AND tenant_id=? AND agent_id=?",
                (grant_id, current.get("tenant_id", "tenant-default"), current["agent_id"]),
            ).fetchone()
            if not lookup:
                raise HTTPException(404, "Collaboration grant not found")
            lock_task(c, lookup["task_id"])
            row = c.execute(
                """SELECT g.*,a.owner_member_id current_owner,a.status agent_status,
                          s.status session_status,p.status project_status
                   FROM agent_collaboration_grants g
                   JOIN agents a ON a.id=g.agent_id
                   JOIN agent_collaboration_sessions s ON s.id=g.session_id
                   JOIN projects p ON p.id=g.project_id
                   WHERE g.id=? AND g.tenant_id=? AND g.agent_id=?""",
                (grant_id, current.get("tenant_id", "tenant-default"), current["agent_id"]),
            ).fetchone()
            if not row or row["current_owner"] != row["owner_member_id"] or row["agent_status"] != "ACTIVE":
                raise HTTPException(404, "Collaboration grant not found")
            if row["project_status"] != "ACTIVE" or row["session_status"] != "OPEN":
                raise HTTPException(409, "Collaboration Session or Project is not open for joining")
            if row["status"] != "AUTHORIZED":
                raise HTTPException(409, "Collaboration grant is not awaiting acceptance")
            stamp = now()
            if row["expires_at"] <= stamp:
                c.execute(
                    "UPDATE agent_collaboration_grants SET status='EXPIRED',updated_at=? WHERE id=?",
                    (stamp, grant_id),
                )
                raise HTTPException(409, "Collaboration grant has expired")
            c.execute(
                """UPDATE agent_collaboration_grants SET status='ACCEPTED',accepted_at=?,updated_at=?
                   WHERE id=? AND status='AUTHORIZED'""",
                (stamp, stamp, grant_id),
            )
            event(
                c, "agent.collaboration_grant.accepted", None, row["task_id"],
                {"grant_id": grant_id, "session_id": row["session_id"],
                 "agent_id": current["agent_id"], "owner_member_id": row["owner_member_id"]},
                tenant_override=row["tenant_id"],
            )
            return {"id": grant_id, "status": "ACCEPTED", "accepted_at": stamp}

    app.include_router(router)
