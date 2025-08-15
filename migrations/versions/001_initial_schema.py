"""Initial schema migration - Create schema version table."""

from sqlmodel import Session, text


def upgrade(session: Session):
    """Create the schema version table."""
    
    # Create schema version table
    session.exec(text("""
        CREATE TABLE IF NOT EXISTS schemaversion (
            version INTEGER PRIMARY KEY,
            applied_at DATETIME NOT NULL,
            description TEXT NOT NULL
        )
    """))
    
    session.commit()
