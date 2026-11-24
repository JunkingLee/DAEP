"""Member-scoped notification delivery observability.

This module correlates the existing inbox and outbox records without introducing
another notification store or changing the delivery lifecycle.
"""
import json

from fastapi import APIRouter, Header, HTTPException


def register_notification_governance_routes(app, conn, actor, now):
    router = APIRouter()

    @router.get("/api/v1/me/notification-delivery")
    def notification_delivery(
        status: str = "ALL", task_id: str = None, limit: int = 50,
        authorization: str = Header(None),
    ):
        current = actor(authorization)
        if current.get("actor_type") != "MEMBER":
            raise HTTPException(403, "Member authentication required")
        status = status.upper()
        if status not in {"PENDING", "ACKNOWLEDGED", "REJECTED", "ALL"}:
            raise HTTPException(422, "Unsupported notification status")
        if not 1 <= limit <= 200:
            raise HTTPException(422, "limit must be between 1 and 200")
        with conn() as c:
            clauses = ["recipient_member_id=?"]
            params = [current["id"]]
            if status != "ALL":
                clauses.append("status=?")
                params.append(status)
            if task_id:
                clauses.append("task_id=?")
                params.append(task_id)
            messages = c.execute(
                "SELECT id,tenant_id,task_id,message_type,title,priority,status,created_at,acked_at "
                "FROM messages WHERE " + " AND ".join(clauses) +
                " ORDER BY created_at DESC LIMIT ?", tuple(params + [limit])
            ).fetchall()
            ids = {row["id"] for row in messages}
            deliveries = {}
            if ids:
                # Outbox payloads are JSON across both supported database engines.
                rows = c.execute(
                    "SELECT id,event_type,payload,status,attempts,available_at,last_error,created_at,sent_at "
                    "FROM outbox WHERE tenant_id=? AND event_type='message.created' "
                    "ORDER BY created_at DESC LIMIT 2000",
                    (current.get("tenant_id", "tenant-default"),),
                ).fetchall()
                for item in rows:
                    try:
                        message_id = json.loads(item["payload"] or "{}").get("message_id")
                    except (TypeError, ValueError):
                        continue
                    if message_id in ids and message_id not in deliveries:
                        deliveries[message_id] = dict(item)
            items = []
            for message in messages:
                item = dict(message)
                delivery = deliveries.get(message["id"])
                if delivery:
                    delivery.pop("payload", None)
                    # Do not expose lease owner/token or broker credentials.
                    delivery.pop("lease_owner", None)
                    delivery.pop("lease_token", None)
                item["delivery"] = delivery
                item["delivery_status"] = delivery["status"] if delivery else "MISSING"
                items.append(item)
            return {"items": items, "count": len(items), "status": status}

    @router.get("/api/v1/me/notification-audit")
    def notification_audit(
        task_id: str = None, event_type: str = None, limit: int = 100,
        authorization: str = Header(None),
    ):
        current = actor(authorization)
        if current.get("actor_type") != "MEMBER":
            raise HTTPException(403, "Member authentication required")
        if not 1 <= limit <= 200:
            raise HTTPException(422, "limit must be between 1 and 200")
        allowed = {
            "notification.queued", "message.acknowledged",
            "agent.collaboration_grant.reminder_sent",
            "agent.collaboration_grant.expired",
        }
        if event_type and event_type not in allowed:
            raise HTTPException(422, "Unsupported notification audit event")
        with conn() as c:
            clauses = ["tenant_id=?", "event_type IN (" + ",".join("?" for _ in allowed) + ")",
                       "(actor_member_id=? OR payload LIKE ?)"]
            params = [current.get("tenant_id", "tenant-default"), *sorted(allowed),
                      current["id"], '%"owner_member_id": "' + current["id"] + '"%']
            if task_id:
                clauses.append("task_id=?")
                params.append(task_id)
            if event_type:
                clauses.append("event_type=?")
                params.append(event_type)
            rows = c.execute(
                "SELECT id,event_type,actor_member_id,task_id,payload,created_at FROM events WHERE "
                + " AND ".join(clauses) + " ORDER BY created_at DESC LIMIT ?",
                tuple(params + [limit]),
            ).fetchall()
            items = []
            for row in rows:
                item = dict(row)
                try:
                    item["payload"] = json.loads(item["payload"] or "{}")
                except (TypeError, ValueError):
                    item["payload"] = {}
                items.append(item)
            return {"items": items, "count": len(items), "limit": limit}

    app.include_router(router)
