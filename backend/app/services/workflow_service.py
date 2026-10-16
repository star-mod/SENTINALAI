import asyncio
import json
import logging
import math
import os
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.incident_service import as_contract
from app.models import Incident, WorkflowAudit, WorkflowOutbox
from app.services.ws_manager import ws_manager

logger = logging.getLogger(__name__)
_dispatch_lock = asyncio.Lock()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def queue_incident(db: Session, event: dict) -> None:
    now = utc_now()
    is_enabled = os.getenv("N8N_ENABLED", "false").lower() == "true"
    row = WorkflowOutbox(
        id=f"ob_{uuid.uuid4().hex}",
        incident_id=event["id"],
        idempotency_key=event["event_id"],
        payload=json.dumps(event),
        status="pending" if is_enabled else "disabled",
        attempts=0,
        next_attempt_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    incident = db.get(Incident, event["id"])
    if incident is not None:
        incident.workflow_status = "queued" if is_enabled else "not_configured"
        incident.notification_status = "pending" if is_enabled else "not_configured"
        incident.workflow_updated_at = now


async def dispatch_pending_once() -> int:
    """Attempt due webhook deliveries without holding a database session over HTTP."""
    if os.getenv("N8N_ENABLED", "false").lower() != "true":
        return 0
    webhook_url = os.getenv("N8N_WEBHOOK_URL", "").strip()
    if not webhook_url:
        logger.error("n8n dispatch enabled without N8N_WEBHOOK_URL; queued events remain pending")
        return 0
    secret = os.getenv("N8N_WEBHOOK_SECRET", "").strip()
    if not secret:
        logger.error("n8n dispatch enabled without N8N_WEBHOOK_SECRET; queued events remain pending")
        return 0
    try:
        parsed_url = urlsplit(webhook_url)
    except ValueError:
        logger.error("Invalid n8n webhook URL; queued events remain pending")
        return 0
    if (
        parsed_url.scheme not in {"https", "http"}
        or not parsed_url.hostname
        or (parsed_url.scheme == "http" and parsed_url.hostname not in {"localhost", "127.0.0.1", "::1"})
    ):
        logger.error("n8n webhook must use HTTPS except for local development")
        return 0
    try:
        timeout_seconds = float(os.getenv("N8N_TIMEOUT_SECONDS", "5"))
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout must be a positive finite number")
        timeout = httpx.Timeout(timeout_seconds)
    except ValueError:
        logger.error("Invalid N8N_TIMEOUT_SECONDS; queued events remain pending")
        return 0

    if _dispatch_lock.locked():
        return 0
    async with _dispatch_lock:
        with SessionLocal() as db:
            now = utc_now()
            rows = db.scalars(
                select(WorkflowOutbox)
                .where(WorkflowOutbox.status == "pending", WorkflowOutbox.next_attempt_at <= now)
                .order_by(WorkflowOutbox.created_at)
                .limit(10)
            ).all()
            batch = [
                {
                    "id": row.id,
                    "incident_id": row.incident_id,
                    "idempotency_key": row.idempotency_key,
                    "payload": row.payload,
                    "attempts": row.attempts,
                }
                for row in rows
            ]

        delivered = 0
        async with httpx.AsyncClient(timeout=timeout) as client:
            for item in batch:
                with SessionLocal() as db:
                    row = db.get(WorkflowOutbox, item["id"])
                    incident = db.get(Incident, item["incident_id"])
                    if row is None or row.status != "pending":
                        continue
                    if incident is not None and (incident.acknowledged_at or incident.status == "resolved"):
                        row.status = "cancelled"
                        row.updated_at = utc_now()
                        db.commit()
                        continue
                headers = {
                    "Content-Type": "application/json",
                    "Idempotency-Key": item["idempotency_key"],
                }
                headers["X-Webhook-Secret"] = secret
                try:
                    response = await client.post(webhook_url, content=item["payload"], headers=headers)
                    response.raise_for_status()
                except (httpx.HTTPError, httpx.InvalidURL, ValueError) as error:
                    with SessionLocal() as db:
                        row = db.get(WorkflowOutbox, item["id"])
                        if row is None or row.status != "pending":
                            continue
                        row.attempts += 1
                        row.updated_at = utc_now()
                        incident = db.get(Incident, row.incident_id)
                        if incident is not None and (incident.acknowledged_at or incident.status == "resolved"):
                            row.status = "cancelled"
                            row.last_error = "retry cancelled after acknowledgement"
                        else:
                            delay = min(300, 2 ** min(row.attempts, 8))
                            row.next_attempt_at = row.updated_at + timedelta(seconds=delay)
                            row.last_error = (
                                f"HTTP {error.response.status_code}"
                                if isinstance(error, httpx.HTTPStatusError)
                                else f"{type(error).__name__}: webhook request failed"
                            )
                        if incident is not None and incident.workflow_status in {"queued", "dispatch_pending"}:
                            incident.workflow_status = "dispatch_pending"
                            incident.workflow_updated_at = row.updated_at
                            contract = as_contract(incident)
                        else:
                            contract = None
                        db.commit()
                    if contract is not None:
                        await ws_manager.broadcast("workflow.updated", contract)
                    logger.warning(
                        "n8n webhook delivery failed",
                        extra={"incident_id": item["incident_id"], "attempt": item["attempts"] + 1},
                    )
                else:
                    with SessionLocal() as db:
                        row = db.get(WorkflowOutbox, item["id"])
                        if row is None or row.status != "pending":
                            continue
                        row.status = "sent"
                        row.attempts += 1
                        row.updated_at = utc_now()
                        row.last_error = None
                        incident = db.get(Incident, row.incident_id)
                        if incident is not None:
                            incident.workflow_status = "dispatched"
                            incident.workflow_updated_at = row.updated_at
                            contract = as_contract(incident)
                        else:
                            contract = None
                        db.commit()
                    if contract is not None:
                        await ws_manager.broadcast("workflow.updated", contract)
                    delivered += 1
                    logger.info(
                        "n8n webhook delivered",
                        extra={"incident_id": item["incident_id"], "idempotency_key": item["idempotency_key"]},
                    )
        return delivered


async def dispatch_worker(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await dispatch_pending_once()
        except Exception:
            logger.exception("Unexpected error in n8n outbox dispatcher")
        try:
            await asyncio.wait_for(stop.wait(), timeout=2)
        except asyncio.TimeoutError:
            pass


def apply_workflow_event(db: Session, incident_id: str, event) -> tuple[dict, bool]:
    existing = db.get(WorkflowAudit, event.event_id)
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise LookupError("Incident not found")
    if existing is not None:
        if existing.incident_id != incident_id or existing.event_type != event.type:
            raise ValueError("event_id was already used for a different workflow event")
        return incident, True

    now = event.timestamp.astimezone(timezone.utc)
    if event.type == "notification.sent":
        incident.notification_status = "sent"
        incident.notification_sent_at = incident.notification_sent_at or now
        incident.notification_attempts += 1
        incident.workflow_status = "notified"
    elif event.type == "notification.failed":
        incident.notification_attempts += 1
        if incident.notification_status != "sent":
            incident.notification_status = "failed"
            incident.workflow_status = "notification_failed"
    elif event.type == "acknowledgement.received":
        if incident.status != "new":
            raise ValueError("incident has already been acknowledged or resolved")
        incident.status = "acknowledged"
        incident.acknowledged_at = now
        incident.responder_id = event.responder_id
        incident.workflow_status = "acknowledged"
    elif event.type == "escalation.triggered":
        if incident.status == "resolved":
            raise ValueError("resolved incidents cannot be escalated")
        incident.escalated_at = incident.escalated_at or now
        incident.workflow_status = "escalated"
    elif event.type == "workflow.completed":
        if incident.status != "acknowledged":
            raise ValueError("incident must be acknowledged before workflow completion")
        incident.status = "resolved"
        incident.resolved_at = now
        incident.workflow_status = "completed"

    incident.workflow_updated_at = now
    incident.updated_at = now
    db.add(
        WorkflowAudit(
            event_id=event.event_id,
            incident_id=incident_id,
            event_type=event.type,
            payload=json.dumps(event.model_dump(mode="json")),
            created_at=now,
        )
    )
    db.commit()
    db.refresh(incident)
    return incident, False
