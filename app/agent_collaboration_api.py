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
            # Reading grants must not implicitly create/take over the Session.
            # The responsible Member can inspect the Task-wide grant roster;
            # other Task Members can inspect only grants they personally own.
            task = c.execute(
                """SELECT t.id task_id,t.status task_status,r.project_id,p.tenant_id project_tenant_id,
                          p.status project_status,pm.member_id project_member_id,a.member_id assignee_member_id
                   FROM tasks t JOIN requirements r ON r.id=t.requirement_id
                   JOIN projects p ON p.id=r.project_id
                   LEFT JOIN project_members pm ON pm.project_id=r.project_id AND pm.member_id=?
                   LEFT JOIN assignments a ON a.task_id=t.id AND a.member_id=?
                   WHERE t.id=? AND p.tenant_id=?""",
                (current["id"], current["id"], task_id, current.get("tenant_id", "tenant-default")),
            ).fetchone()
            if not task:
                raise HTTPException(404, "Task not found")
            if task["project_status"] != "ACTIVE" or task["task_status"] in ("DONE", "CANCELLED", "CLOSED", "ARCHIVED"):
                raise HTTPException(409, "Task is not eligible for collaboration grant inspection")
            if task["project_member_id"] is None and task["assignee_member_id"] is None:
                raise HTTPException(404, "Task not found")
            session = c.execute(
                "SELECT id,responsible_member_id FROM agent_collaboration_sessions WHERE task_id=? AND tenant_id=?",
                (task_id, task["project_tenant_id"]),
            ).fetchone()
            is_responsible = bool(session and session["responsible_member_id"] == current["id"])
            query = """SELECT g.*,a.name agent_name FROM agent_collaboration_grants g
                       JOIN agents a ON a.id=g.agent_id
                       WHERE g.tenant_id=? AND g.task_id=?"""
            params = [task["project_tenant_id"], task_id]
            if not is_responsible:
                query += " AND g.owner_member_id=? AND g.authorized_by_member_id=?"
                params.extend([current["id"], current["id"]])
            query += " ORDER BY g.created_at DESC"
            rows = c.execute(query, tuple(params)).fetchall()
            stamp = now()
            items = []
            for row in rows:
                effective = _effective_status(row, stamp)
                if effective == "EXPIRED" and row["status"] != "EXPIRED":
                    c.execute(
                        "UPDATE agent_collaboration_grants SET status='EXPIRED',updated_at=? WHERE id=? AND status IN ('AUTHORIZED','ACCEPTED')",
                        (stamp, row["id"]),
                    )
                    event(
                        c, "agent.collaboration_grant.expired", row["owner_member_id"], task_id,
                        {"grant_id": row["id"], "agent_id": row["agent_id"], "source": "task_grant_list"},
                        tenant_override=row["tenant_id"],
                    )
                items.append({**dict(row), "scopes": json.loads(row["scopes_json"]),
                              "resource_scope": json.loads(row["resource_scope_json"]),
                              "effective_status": effective})
            return {"task_id": task_id, "session_id": session["id"] if session else None,
                    "visibility": "TASK_WIDE" if is_responsible else "OWNER_ONLY", "items": items}

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

    @router.get("/api/v1/members/me/collaboration-grants")
    def list_member_owned_collaboration_grants(authorization: str = Header(None)):
        current = actor(authorization)
        if current.get("actor_type") != "MEMBER":
            raise HTTPException(403, "Member authentication required")
        with conn() as c:
            begin_serialized_write(c)
            stamp = now()
            rows = c.execute(
                """SELECT g.id grant_id,g.agent_id,g.task_id,g.project_id,g.session_id,
                          g.owner_member_id,g.scopes_json,g.resource_scope_json,g.status,
                          g.created_at,g.expires_at,g.revoked_at,g.revoked_by_member_id,
                          g.revoke_reason,a.name agent_name,s.status session_status,
                          t.title task_title,p.name project_name
                   FROM agent_collaboration_grants g
                   JOIN agents a ON a.id=g.agent_id AND a.owner_member_id=g.owner_member_id
                   LEFT JOIN agent_collaboration_sessions s ON s.id=g.session_id
                   LEFT JOIN tasks t ON t.id=g.task_id
                   LEFT JOIN projects p ON p.id=g.project_id
                   WHERE g.tenant_id=? AND g.owner_member_id=? AND g.authorized_by_member_id=?
                   ORDER BY g.created_at DESC""",
                (current.get("tenant_id", "tenant-default"), current["id"], current["id"]),
            ).fetchall()
            items = []
            for row in rows:
                effective = _effective_status(row, stamp)
                if effective == "EXPIRED" and row["status"] != "EXPIRED":
                    c.execute(
                        "UPDATE agent_collaboration_grants SET status='EXPIRED',updated_at=? WHERE id=? AND status IN ('AUTHORIZED','ACCEPTED')",
                        (stamp, row["grant_id"]),
                    )
                    event(
                        c, "agent.collaboration_grant.expired", current["id"], row["task_id"],
                        {"grant_id": row["grant_id"], "agent_id": row["agent_id"], "source": "owner_inbox"},
                        tenant_override=current.get("tenant_id", "tenant-default"),
                    )
                item = dict(row)
                item["scopes"] = json.loads(item.pop("scopes_json"))
                item["resource_scope"] = json.loads(item.pop("resource_scope_json"))
                item["effective_status"] = effective
                items.append(item)
            return {"owner_member_id": current["id"], "items": items}

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


    def _agent_collaboration_grant_context(c, grant_id, current, task_id=None, required_scope=None, resource_id=None):
        row = c.execute(
            """SELECT g.*,a.status agent_status,a.owner_member_id current_owner,a.tenant_id agent_tenant,
                      s.status session_status,s.project_id session_project,s.task_id session_task,
                      p.status project_status,p.tenant_id project_tenant,t.status task_status,
                      r.project_id task_project,m.tenant_id owner_tenant
               FROM agent_collaboration_grants g
               JOIN agents a ON a.id=g.agent_id
               JOIN agent_collaboration_sessions s ON s.id=g.session_id
               JOIN projects p ON p.id=g.project_id
               JOIN tasks t ON t.id=g.task_id
               JOIN requirements r ON r.id=t.requirement_id
               JOIN members m ON m.id=g.owner_member_id
               WHERE g.id=? AND g.tenant_id=? AND g.agent_id=?""",
            (grant_id, current.get("tenant_id", "tenant-default"), current.get("agent_id")),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Collaboration grant not found")
        if (row["agent_tenant"] != row["tenant_id"] or row["project_tenant"] != row["tenant_id"]
            or row["session_project"] != row["project_id"] or row["session_task"] != row["task_id"]
            or row["task_project"] != row["project_id"] or row["owner_tenant"] != row["tenant_id"]
            or (task_id is not None and row["task_id"] != task_id)
            or row["current_owner"] != row["owner_member_id"] or row["agent_status"] != "ACTIVE"):
            raise HTTPException(403, "Agent collaboration identity or resource relationship is invalid")
        stamp = now()
        if row["status"] != "ACCEPTED" or row["revoked_at"] is not None or row["expires_at"] <= stamp:
            raise HTTPException(403, "An accepted active CollaborationGrant is required")
        if row["project_status"] != "ACTIVE":
            raise HTTPException(403, "Project is not active")
        scopes = set(json.loads(row["scopes_json"] or "[]"))
        if required_scope and required_scope not in scopes:
            raise HTTPException(403, "CollaborationGrant does not include the required scope")
        resource_scope = json.loads(row["resource_scope_json"] or "{}")
        allowed_resources = set(resource_scope.get("resource_ids", []))
        if allowed_resources and resource_id is not None and resource_id not in allowed_resources:
            raise HTTPException(403, "Resource is outside the CollaborationGrant scope")
        if allowed_resources and required_scope == "session.message.send" and not resource_id:
            raise HTTPException(403, "A resource_id within the CollaborationGrant scope is required")
        return row, scopes, allowed_resources

    def _message_payload(row):
        return {
            "id": row["id"], "task_id": row["task_id"], "session_id": row["session_id"],
            "author_type": row["author_type"], "author_member_id": row["author_member_id"],
            "author_agent_id": row["author_agent_id"], "agent_owner_member_id": row["agent_owner_member_id"],
            "collaboration_grant_id": row["collaboration_grant_id"],
            "message_type": row["message_type"], "content": row["content"],
            "metadata": json.loads(row["metadata_json"] or "{}"), "created_at": row["created_at"],
        }


    def _member_collaboration_history_session(c, task_id, member):
        task = c.execute(
            """SELECT t.id task_id,r.project_id,p.tenant_id project_tenant_id,p.status project_status
               FROM tasks t JOIN requirements r ON r.id=t.requirement_id
               JOIN projects p ON p.id=r.project_id WHERE t.id=?""",
            (task_id,),
        ).fetchone()
        if not task or task["project_tenant_id"] != member.get("tenant_id", "tenant-default"):
            raise HTTPException(404, "Task not found")
        if task["project_status"] != "ACTIVE":
            raise HTTPException(409, "Project is not active")
        assignees = c.execute(
            """SELECT a.member_id,m.tenant_id,m.password_status FROM assignments a
               JOIN members m ON m.id=a.member_id WHERE a.task_id=?""",
            (task_id,),
        ).fetchall()
        if (len(assignees) != 1 or assignees[0]["member_id"] != member["id"]
            or assignees[0]["tenant_id"] != task["project_tenant_id"]
            or assignees[0]["password_status"] != "ACTIVE"):
            raise HTTPException(403, "Only the active human Task assignee can read collaboration history")
        policy = c.execute(
            """SELECT responsible_member_id FROM agent_task_execution_policies
               WHERE task_id=? AND tenant_id=?""",
            (task_id, task["project_tenant_id"]),
        ).fetchone()
        if not policy or policy["responsible_member_id"] != member["id"]:
            raise HTTPException(403, "Task Agent execution policy responsibility is required")
        session = c.execute(
            """SELECT * FROM agent_collaboration_sessions
               WHERE task_id=? AND tenant_id=?""",
            (task_id, task["project_tenant_id"]),
        ).fetchone()
        if not session:
            raise HTTPException(404, "Task collaboration Session not found")
        if session["project_id"] != task["project_id"]:
            raise HTTPException(409, "Collaboration Session project relationship is invalid")
        return session


    @router.get("/api/v1/tasks/{task_id}/collaboration-proposals")
    def list_task_collaboration_proposals(task_id: str, grant_id: str = None, authorization: str = Header(None)):
        current = actor(authorization)
        stamp = now()
        with conn() as c:
            begin_serialized_write(c)
            lock_task(c, task_id)
            if current.get("actor_type") == "MEMBER":
                task, session = _member_task_session(c, task_id, current, stamp)
                rows = c.execute(
                    """SELECT p.*,a.name agent_name
                       FROM agent_collaboration_proposals p
                       JOIN agents a ON a.id=p.proposed_by_agent_id
                       WHERE p.tenant_id=? AND p.task_id=?
                       ORDER BY p.created_at DESC""",
                    (task["project_tenant_id"], task_id),
                ).fetchall()
            elif current.get("actor_type") == "AGENT":
                if not isinstance(grant_id, str) or not grant_id.strip():
                    raise HTTPException(422, "grant_id is required for Agent proposal access")
                grant, _, _ = _agent_collaboration_grant_context(
                    c, grant_id.strip(), current, task_id=task_id, required_scope="session.read")
                session = c.execute(
                    "SELECT * FROM agent_collaboration_sessions WHERE id=?",
                    (grant["session_id"],),
                ).fetchone()
                rows = c.execute(
                    """SELECT p.*,a.name agent_name
                       FROM agent_collaboration_proposals p
                       JOIN agents a ON a.id=p.proposed_by_agent_id
                       WHERE p.tenant_id=? AND p.task_id=? AND p.collaboration_grant_id=?
                       ORDER BY p.created_at DESC""",
                    (grant["tenant_id"], task_id, grant["id"]),
                ).fetchall()
            else:
                raise HTTPException(403, "Member or Agent authentication required")
            return {
                "task_id": task_id,
                "session_id": session["id"],
                "items": [
                    {
                        **dict(row),
                        "payload": json.loads(row["payload_json"]),
                    }
                    for row in rows
                ],
            }

    @router.post("/api/v1/tasks/{task_id}/collaboration-proposals")
    def create_task_collaboration_proposal(task_id: str, body: dict, authorization: str = Header(None)):
        current = actor(authorization)
        if current.get("actor_type") != "AGENT":
            raise HTTPException(403, "Agent authentication required to create collaboration proposals")
        grant_id = body.get("grant_id")
        if not isinstance(grant_id, str) or not grant_id.strip():
            raise HTTPException(422, "grant_id is required")
        proposal_type = str(body.get("proposal_type", "")).upper().strip()
        if proposal_type not in ("INVITE_AGENT", "WORK_PACKAGE", "MEMBER_DELEGATION", "HELP_REQUEST"):
            raise HTTPException(422, "proposal_type must be INVITE_AGENT, WORK_PACKAGE, MEMBER_DELEGATION or HELP_REQUEST")
        payload = body.get("payload", {})
        if not isinstance(payload, dict):
            raise HTTPException(422, "payload must be an object")
        payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        if len(payload_json) > 32000:
            raise HTTPException(422, "payload must be at most 32000 encoded characters")
        with conn() as c:
            begin_serialized_write(c)
            lock_task(c, task_id)
            grant, _, _ = _agent_collaboration_grant_context(
                c, grant_id.strip(), current, task_id=task_id, required_scope="session.proposal.create")
            session = c.execute(
                "SELECT * FROM agent_collaboration_sessions WHERE id=?",
                (grant["session_id"],),
            ).fetchone()
            task = c.execute(
                """SELECT t.id task_id,r.project_id,p.tenant_id project_tenant_id,t.status task_status
                   FROM tasks t JOIN requirements r ON r.id=t.requirement_id
                   JOIN projects p ON p.id=r.project_id WHERE t.id=?""",
                (task_id,),
            ).fetchone()
            if not task or task["project_tenant_id"] != grant["tenant_id"]:
                raise HTTPException(403, "Task collaboration identity is invalid")
            if session["status"] != "OPEN":
                raise HTTPException(409, "Only an OPEN collaboration Session accepts new proposals")
            if task["task_status"] in ("DONE", "CANCELLED", "CLOSED", "ARCHIVED"):
                raise HTTPException(409, "Only an active Task accepts new collaboration proposals")
            proposal_id = "acp_" + uuid.uuid4().hex[:20]
            stamp = now()
            c.execute(
                """INSERT INTO agent_collaboration_proposals
                   (id,tenant_id,project_id,task_id,session_id,proposal_type,
                    proposed_by_agent_id,owner_member_id,collaboration_grant_id,payload_json,
                    status,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?, 'PENDING',?)""",
                (proposal_id, grant["tenant_id"], task["project_id"], task_id, session["id"],
                 proposal_type, current["agent_id"], grant["owner_member_id"], grant["id"],
                 payload_json, stamp),
            )
            event(
                c, "agent.collaboration_proposal.created", None, task_id,
                {"proposal_id": proposal_id, "session_id": session["id"],
                 "agent_id": current["agent_id"], "owner_member_id": grant["owner_member_id"],
                 "collaboration_grant_id": grant["id"], "proposal_type": proposal_type},
                tenant_override=grant["tenant_id"],
            )
            row = c.execute(
                """SELECT p.*,a.name agent_name
                   FROM agent_collaboration_proposals p
                   JOIN agents a ON a.id=p.proposed_by_agent_id
                   WHERE p.id=?""",
                (proposal_id,),
            ).fetchone()
            return {**dict(row), "payload": payload}

    @router.post("/api/v1/collaboration-proposals/{proposal_id}/decision")
    def decide_collaboration_proposal(proposal_id: str, body: dict, authorization: str = Header(None)):
        current = actor(authorization)
        if current.get("actor_type") != "MEMBER":
            raise HTTPException(403, "Member authentication required")
        decision = str(body.get("decision", "")).upper().strip()
        if decision not in ("ACCEPTED", "REJECTED"):
            raise HTTPException(422, "decision must be ACCEPTED or REJECTED")
        note = body.get("decision_note")
        if note is not None and (not isinstance(note, str) or len(note) > 4000):
            raise HTTPException(422, "decision_note must be a string of at most 4000 characters")
        with conn() as c:
            begin_serialized_write(c)
            lookup = c.execute(
                "SELECT task_id FROM agent_collaboration_proposals WHERE id=? AND tenant_id=?",
                (proposal_id, current.get("tenant_id", "tenant-default")),
            ).fetchone()
            if not lookup:
                raise HTTPException(404, "Collaboration proposal not found")
            lock_task(c, lookup["task_id"])
            row = c.execute(
                """SELECT p.*,s.status session_status,t.status task_status,
                          a.status agent_status,a.owner_member_id current_owner
                   FROM agent_collaboration_proposals p
                   JOIN agent_collaboration_sessions s ON s.id=p.session_id
                   JOIN tasks t ON t.id=p.task_id
                   JOIN agents a ON a.id=p.proposed_by_agent_id
                   WHERE p.id=? AND p.tenant_id=?""",
                (proposal_id, current.get("tenant_id", "tenant-default")),
            ).fetchone()
            if not row:
                raise HTTPException(404, "Collaboration proposal not found")
            if row["owner_member_id"] != current["id"]:
                raise HTTPException(403, "Only the Agent Owner who authorized the proposal can decide it")
            if row["status"] != "PENDING":
                raise HTTPException(409, "Collaboration proposal is no longer pending")
            if row["current_owner"] != row["owner_member_id"] or row["agent_status"] != "ACTIVE":
                raise HTTPException(409, "The proposing Agent identity is no longer active for this proposal")
            if row["task_status"] in ("DONE", "CANCELLED", "CLOSED", "ARCHIVED"):
                raise HTTPException(409, "A terminal Task cannot receive a proposal decision")
            stamp = now()
            c.execute(
                """UPDATE agent_collaboration_proposals
                   SET status=?,decided_by_member_id=?,decision_note=?,decided_at=?
                   WHERE id=? AND status='PENDING'""",
                (decision, current["id"], note.strip() if isinstance(note, str) else None, stamp, proposal_id),
            )
            event(
                c, "agent.collaboration_proposal.decided", current["id"], row["task_id"],
                {"proposal_id": proposal_id, "session_id": row["session_id"],
                 "agent_id": row["proposed_by_agent_id"], "decision": decision},
                tenant_override=row["tenant_id"],
            )
            return {
                "id": proposal_id,
                "status": decision,
                "decided_by_member_id": current["id"],
                "decision_note": note.strip() if isinstance(note, str) else None,
                "decided_at": stamp,
                "formal_mutation_required": True,
            }

    @router.post("/api/v1/collaboration-proposals/{proposal_id}/withdraw")
    def withdraw_collaboration_proposal(proposal_id: str, authorization: str = Header(None)):
        current = actor(authorization)
        if current.get("actor_type") != "AGENT":
            raise HTTPException(403, "Agent authentication required")
        with conn() as c:
            begin_serialized_write(c)
            lookup = c.execute(
                """SELECT task_id FROM agent_collaboration_proposals
                   WHERE id=? AND tenant_id=? AND proposed_by_agent_id=?""",
                (proposal_id, current.get("tenant_id", "tenant-default"), current["agent_id"]),
            ).fetchone()
            if not lookup:
                raise HTTPException(404, "Collaboration proposal not found")
            lock_task(c, lookup["task_id"])
            row = c.execute(
                """SELECT p.*,a.owner_member_id current_owner,a.status agent_status
                   FROM agent_collaboration_proposals p
                   JOIN agents a ON a.id=p.proposed_by_agent_id
                   WHERE p.id=? AND p.tenant_id=? AND p.proposed_by_agent_id=?""",
                (proposal_id, current.get("tenant_id", "tenant-default"), current["agent_id"]),
            ).fetchone()
            if not row:
                raise HTTPException(404, "Collaboration proposal not found")
            if row["current_owner"] != row["owner_member_id"] or row["agent_status"] != "ACTIVE":
                raise HTTPException(404, "Collaboration proposal not found")
            if row["status"] != "PENDING":
                raise HTTPException(409, "Only a pending collaboration proposal can be withdrawn")
            stamp = now()
            c.execute(
                """UPDATE agent_collaboration_proposals
                   SET status='WITHDRAWN',decided_by_member_id=NULL,decision_note=NULL,decided_at=?
                   WHERE id=? AND status='PENDING'""",
                (stamp, proposal_id),
            )
            event(
                c, "agent.collaboration_proposal.withdrawn", None, row["task_id"],
                {"proposal_id": proposal_id, "session_id": row["session_id"],
                 "agent_id": current["agent_id"]},
                tenant_override=row["tenant_id"],
            )
            return {"id": proposal_id, "status": "WITHDRAWN", "withdrawn_at": stamp}

    @router.get("/api/v1/tasks/{task_id}/collaboration-messages")
    def list_task_collaboration_messages(task_id: str, grant_id: str = None, limit: int = 50,
                                         authorization: str = Header(None)):
        current = actor(authorization)
        if isinstance(limit, bool) or limit < 1 or limit > 100:
            raise HTTPException(422, "limit must be between 1 and 100")
        with conn() as c:
            if current.get("actor_type") == "MEMBER":
                session = _member_collaboration_history_session(c, task_id, current)
                allowed_resources = None
            elif current.get("actor_type") == "AGENT":
                if not grant_id:
                    raise HTTPException(422, "grant_id is required for Agent message access")
                grant, _, allowed_resources = _agent_collaboration_grant_context(
                    c, grant_id, current, task_id=task_id, required_scope="session.read")
                session = c.execute("SELECT * FROM agent_collaboration_sessions WHERE id=?",
                                     (grant["session_id"],)).fetchone()
                if not session:
                    raise HTTPException(404, "Collaboration Session not found")
            else:
                raise HTTPException(403, "Member or Agent authentication required")
            rows = c.execute(
                """SELECT * FROM agent_collaboration_messages
                   WHERE tenant_id=? AND task_id=? AND session_id=?
                   ORDER BY created_at DESC,id DESC LIMIT ?""",
                (session["tenant_id"], task_id, session["id"], limit)).fetchall()
            messages = [_message_payload(row) for row in rows]
            if allowed_resources:
                # Resource-scoped grants may read messages attached to explicitly
                # allowed resources and general session messages with no resource.
                messages = [
                    item for item in messages
                    if item["metadata"].get("resource_id") is None
                    or item["metadata"].get("resource_id") in allowed_resources
                ]
            messages.reverse()
            return {"task_id": task_id, "session_id": session["id"],
                    "session_status": session["status"], "items": messages}

    @router.post("/api/v1/tasks/{task_id}/collaboration-messages")
    def create_task_collaboration_message(task_id: str, body: dict, authorization: str = Header(None)):
        current = actor(authorization)
        content = body.get("content")
        if not isinstance(content, str) or not content.strip() or len(content) > 10000:
            raise HTTPException(422, "content must be a non-empty string of at most 10000 characters")
        message_type = str(body.get("message_type", "MESSAGE")).upper()
        if message_type != "MESSAGE":
            raise HTTPException(422, "Only MESSAGE collaboration entries are currently supported")
        resource_id = body.get("resource_id")
        if resource_id is not None and (not isinstance(resource_id, str) or not resource_id or len(resource_id) > 120):
            raise HTTPException(422, "resource_id must be a non-empty string of at most 120 characters")
        metadata = body.get("metadata", {})
        if not isinstance(metadata, dict):
            raise HTTPException(422, "metadata must be an object")
        if "resource_id" in metadata and metadata["resource_id"] != resource_id:
            raise HTTPException(422, "resource_id must be supplied through the top-level field")
        stored_metadata = dict(metadata)
        if resource_id is not None:
            stored_metadata["resource_id"] = resource_id
        metadata_json = json.dumps(stored_metadata, separators=(",", ":"), ensure_ascii=False)
        if len(metadata_json) > 16000:
            raise HTTPException(422, "metadata must be at most 16000 encoded characters")
        with conn() as c:
            begin_serialized_write(c)
            lock_task(c, task_id)
            stamp = now()
            if current.get("actor_type") == "MEMBER":
                _, session = _member_task_session(c, task_id, current, stamp)
                if session["status"] != "OPEN":
                    raise HTTPException(409, "Only an OPEN collaboration Session accepts new messages")
                author_type, author_member_id, author_agent_id = "MEMBER", current["id"], None
                owner_member_id = collaboration_grant_id = None
                audit_actor = current["id"]
            elif current.get("actor_type") == "AGENT":
                grant_id = body.get("grant_id")
                if not isinstance(grant_id, str) or not grant_id:
                    raise HTTPException(422, "grant_id is required for Agent message sending")
                grant, _, _ = _agent_collaboration_grant_context(
                    c, grant_id, current, task_id=task_id,
                    required_scope="session.message.send", resource_id=resource_id)
                session = c.execute("SELECT * FROM agent_collaboration_sessions WHERE id=?",
                                    (grant["session_id"],)).fetchone()
                if (not session or session["status"] != "OPEN"
                    or grant["task_status"] in ("DONE", "CANCELLED", "CLOSED", "ARCHIVED")):
                    raise HTTPException(409, "Only an OPEN collaboration Session on an active Task accepts new messages")
                author_type, author_member_id, author_agent_id = "AGENT", None, current["agent_id"]
                owner_member_id, collaboration_grant_id = grant["owner_member_id"], grant["id"]
                audit_actor = None
            else:
                raise HTTPException(403, "Member or Agent authentication required")
            message_id = "acm_" + uuid.uuid4().hex[:20]
            c.execute(
                """INSERT INTO agent_collaboration_messages
                   (id,tenant_id,project_id,task_id,session_id,author_type,author_member_id,
                    author_agent_id,agent_owner_member_id,collaboration_grant_id,message_type,
                    content,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (message_id, session["tenant_id"], session["project_id"], task_id, session["id"],
                 author_type, author_member_id, author_agent_id, owner_member_id,
                 collaboration_grant_id, message_type, content.strip(), metadata_json, stamp))
            event(c, "agent.collaboration_message.created", audit_actor, task_id, {
                "message_id": message_id, "session_id": session["id"], "author_type": author_type,
                "author_member_id": author_member_id, "author_agent_id": author_agent_id,
                "agent_owner_member_id": owner_member_id, "collaboration_grant_id": collaboration_grant_id,
                "resource_id": resource_id,
            }, tenant_override=session["tenant_id"])
            return _message_payload(c.execute(
                "SELECT * FROM agent_collaboration_messages WHERE id=?", (message_id,)).fetchone())

    app.include_router(router)
