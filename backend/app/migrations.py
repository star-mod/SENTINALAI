from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


MIGRATION_VERSION = "20261016_workflow_integration"
INCIDENT_COLUMNS = {
    "schema_version": "VARCHAR(16) NOT NULL DEFAULT '1.0'",
    "event_id": "VARCHAR(128)",
    "severity_verified": "BOOLEAN NOT NULL DEFAULT 0",
    "source": "VARCHAR(32) NOT NULL DEFAULT 'simulation'",
    "priority": "VARCHAR(16) NOT NULL DEFAULT 'normal'",
    "workflow_status": "VARCHAR(32) NOT NULL DEFAULT 'not_configured'",
    "workflow_updated_at": "DATETIME",
    "notification_status": "VARCHAR(24) NOT NULL DEFAULT 'not_configured'",
    "notification_attempts": "INTEGER NOT NULL DEFAULT 0",
    "notification_sent_at": "DATETIME",
    "acknowledged_at": "DATETIME",
    "escalated_at": "DATETIME",
    "resolved_at": "DATETIME",
    "responder_id": "VARCHAR(128)",
    "detection_metadata": "TEXT NOT NULL DEFAULT '{}'",
    "updated_at": "DATETIME",
}


def migrate_database(engine: Engine) -> None:
    """Apply additive schema updates; existing incident and evidence rows remain intact."""
    inspector = inspect(engine)
    if "incidents" not in inspector.get_table_names():
        return

    present = {column["name"] for column in inspector.get_columns("incidents")}
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version VARCHAR(80) PRIMARY KEY, applied_at DATETIME NOT NULL)"
            )
        )
        for name, definition in INCIDENT_COLUMNS.items():
            if name not in present:
                connection.execute(text(f"ALTER TABLE incidents ADD COLUMN {name} {definition}"))
        connection.execute(
            text(
                "UPDATE incidents SET event_id = 'legacy_' || id "
                "WHERE event_id IS NULL OR event_id = ''"
            )
        )
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_incidents_event_id ON incidents (event_id)")
        )
        connection.execute(
            text(
                "UPDATE incidents SET updated_at = timestamp "
                "WHERE updated_at IS NULL"
            )
        )
        connection.execute(
            text(
                "INSERT OR IGNORE INTO schema_migrations (version, applied_at) "
                "VALUES (:version, CURRENT_TIMESTAMP)"
            ),
            {"version": MIGRATION_VERSION},
        )
