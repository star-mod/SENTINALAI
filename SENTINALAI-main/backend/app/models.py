from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from app.database import Base


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(String(32), primary_key=True)
    name = Column(String(160), nullable=False)
    location = Column(Text, nullable=False)
    status = Column(String(16), nullable=False, default="online")
    stream_url = Column(String(255), nullable=False)


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(String(32), primary_key=True)
    camera_id = Column(String(32), nullable=False, index=True)
    camera_name = Column(String(160), nullable=False)
    location = Column(Text, nullable=False)
    type = Column(String(40), nullable=False, index=True)
    confidence = Column(Float, nullable=False)
    severity = Column(String(16), nullable=False)
    severity_verified = Column(Boolean, nullable=False, default=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="new", index=True)
    snapshot_url = Column(String(255), nullable=False)
    clip_url = Column(String(255), nullable=False)
    notes = Column(Text, nullable=False, default="")
    verification = Column(Text, nullable=False)
    schema_version = Column(String(16), nullable=False, default="1.0")
    event_id = Column(String(128), unique=True, index=True, nullable=True)
    source = Column(String(32), nullable=False, default="simulation")
    priority = Column(String(16), nullable=False, default="normal")
    workflow_status = Column(String(32), nullable=False, default="not_configured")
    workflow_updated_at = Column(DateTime(timezone=True), nullable=True)
    notification_status = Column(String(24), nullable=False, default="not_configured")
    notification_attempts = Column(Integer, nullable=False, default=0)
    notification_sent_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    escalated_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    responder_id = Column(String(128), nullable=True)
    detection_metadata = Column(Text, nullable=False, default="{}")
    updated_at = Column(DateTime(timezone=True), nullable=True)


class WorkflowOutbox(Base):
    __tablename__ = "workflow_outbox"

    id = Column(String(32), primary_key=True)
    incident_id = Column(String(32), nullable=False, index=True)
    idempotency_key = Column(String(128), nullable=False, unique=True)
    payload = Column(Text, nullable=False)
    status = Column(String(16), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime(timezone=True), nullable=False, index=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class WorkflowAudit(Base):
    __tablename__ = "workflow_audit"

    event_id = Column(String(128), primary_key=True)
    incident_id = Column(String(32), nullable=False, index=True)
    event_type = Column(String(40), nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(String(32), primary_key=True)
    incident_id = Column(String(32), nullable=False, index=True)
    type = Column(String(32), nullable=False, default="snapshot")
    url = Column(String(512), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, index=True)


class User(Base):
    __tablename__ = "users"

    id = Column(String(32), primary_key=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False, default="operator")
    created_at = Column(DateTime(timezone=True), nullable=False)
