from sqlalchemy import Column, DateTime, Float, String, Text
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
	timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
	status = Column(String(20), nullable=False, default="new", index=True)
	snapshot_url = Column(String(255), nullable=False)
	clip_url = Column(String(255), nullable=False)
	notes = Column(Text, nullable=False, default="")
	verification = Column(Text, nullable=False)
