"""Add User table for authentication system."""

from sqlmodel import Session, text


def upgrade(session: Session):
    """Add User table for authentication."""
    
    # Create User table
    session.exec(text("""
        CREATE TABLE IF NOT EXISTS user (
            id INTEGER PRIMARY KEY,
            username VARCHAR NOT NULL UNIQUE,
            password_hash VARCHAR NOT NULL,
            is_setup_complete BOOLEAN NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
    """))
    
    # Create index on username
    session.exec(text("""
        CREATE INDEX IF NOT EXISTS ix_user_username ON user (username)
    """))
    
    session.commit()
