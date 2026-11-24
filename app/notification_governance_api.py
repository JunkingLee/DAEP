"""Member-scoped notification delivery observability.

This module correlates the existing inbox and outbox records without introducing
another notification store or changing the delivery lifecycle.
"""
import json

from fastapi import APIRouter, Header, HTTPException


def register_notification_governance_routes(app, conn, actor, now):
    router = APIRouter()

    @router.get("/api/v1/me/notification-preferences")
    def get_notification_preferences(authorization: str = Header(None)):
        current = actor(authorization)
        if current.get("actor_type") != "MEMBER":
            raise HTTPException(403, "Member authentication required")
        with conn() as c:
            row = c.execute(
                "SELECT * FROM member_notification_preferences WHERE member_id=? AND tenant_id=?",
                (current["id"], current.get("tenant_id", "tenant-default")),
            ).fetchone()
            if not row:
                return {
                    "member_id": current["id"],
                    "collaboration_grant_events": True,
                    "collaboration_expiry_reminders": True,
                    "reminder_days": [7, 3, 1],
                }
            return {
                "member_id": row["member_id"],
                "collaboration_grant_events": bool(row["collaboration_grant_events"]),
                "collaboration_expiry_reminders": bool(row["collaboration_expiry_reminders"]),
                "reminder_days": json.loads(row["reminder_days_json"]),
                "updated_at": row["updated_at"],
            }

    @router.put("/api/v1/me/notification-preferences")
    def update_notification_preferences(body: dict, authorization: str = Header(None)):
        current = actor(authorization)
        if current.get("actor_type") != "MEMBER":
            raise HTTPException(403, "Member authentication required")
        grant_events = body.get("collaboration_grant_events", True)
        expiry_reminders = body.get("collaboration_expiry_reminders", True)
        reminder_days = body.get("reminder_days", [7, 3, 1])
        if not isinstance(grant_events, bool) or not isinstance(expiry_reminders, bool):
            raise HTTPException(422, "Notification category preferences must be boolean")
        if (not isinstance(reminder_days, list) or
                any(type(day) is not int or day not in (1, 3, 7) for day in reminder_days) or
                len(set(reminder_days)) != len(reminder_days)):
            raise HTTPException(422, "reminder_days must be a unique subset of [7, 3, 1]")
        reminder_days = sorted(reminder_days, reverse=True)
        stamp = now()
        with conn() as c:
            c.execute(
                """INSERT INTO member_notification_preferences
                   (member_id,tenant_id,collaboration_grant_events,
                    collaboration_expiry_reminders,reminder_days_json,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(member_id) DO UPDATE SET
                     collaboration_grant_events=excluded.collaboration_grant_events,
                     collaboration_expiry_reminders=excluded.collaboration_expiry_reminders,
                     reminder_days_json=excluded.reminder_days_json,
                     updated_at=excluded.updated_at
                   WHERE member_notification_preferences.tenant_id=excluded.tenant_id""",
                (current["id"], current.get("tenant_id", "tenant-default"),
                 int(grant_events), int(expiry_reminders), json.dumps(reminder_days),
                 stamp, stamp),
            )
            row = c.execute(
                "SELECT * FROM member_notification_preferences WHERE member_id=? AND tenant_id=?",
                (current["id"], current.get("tenant_id", "tenant-default")),
            ).fetchone()
            if not row:
                raise HTTPException(409, "Notification preferences could not be saved")
            return {
                "member_id": row["member_id"],
                "collaboration_grant_events": bool(row["collaboration_grant_events"]),
                "collaboration_expiry_reminders": bool(row["collaboration_expiry_reminders"]),
                "reminder_days": json.loads(row["reminder_days_json"]),
                "updated_at": row["updated_at"],
            }

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
