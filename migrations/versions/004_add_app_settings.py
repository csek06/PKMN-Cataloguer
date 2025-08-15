"""Add AppSettings table and backup settings."""

from sqlmodel import Session, text


def upgrade(session: Session):
    """Add AppSettings table with backup configuration."""
    
    # Check if appsettings table exists
    table_exists = session.exec(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='appsettings'"
    )).first()
    
    if not table_exists:
        # Create AppSettings table from scratch
        session.exec(text("""
            CREATE TABLE appsettings (
                id INTEGER PRIMARY KEY,
                log_level VARCHAR NOT NULL DEFAULT 'INFO',
                local_tz VARCHAR NOT NULL DEFAULT 'America/New_York',
                price_refresh_batch_size INTEGER NOT NULL DEFAULT 200,
                price_refresh_requests_per_sec INTEGER NOT NULL DEFAULT 1,
                sql_echo BOOLEAN NOT NULL DEFAULT 0,
                auto_backup_enabled BOOLEAN NOT NULL DEFAULT 1,
                backup_schedule VARCHAR NOT NULL DEFAULT 'daily',
                backup_retention_days INTEGER NOT NULL DEFAULT 7,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
        """))
        
        # Insert default settings
        session.exec(text("""
            INSERT INTO appsettings (
                id, log_level, local_tz, price_refresh_batch_size, 
                price_refresh_requests_per_sec, sql_echo, auto_backup_enabled,
                backup_schedule, backup_retention_days, created_at, updated_at
            ) VALUES (
                1, 'INFO', 'America/New_York', 200, 1, 0, 1, 'daily', 7,
                datetime('now'), datetime('now')
            )
        """))
    else:
        # Table exists, check if backup columns exist and add them if missing
        columns_to_add = [
            ("auto_backup_enabled", "BOOLEAN NOT NULL DEFAULT 1"),
            ("backup_schedule", "VARCHAR NOT NULL DEFAULT 'daily'"),
            ("backup_retention_days", "INTEGER NOT NULL DEFAULT 7")
        ]
        
        for column_name, column_def in columns_to_add:
            # Check if column exists
            column_exists = session.exec(text(f"""
                SELECT COUNT(*) as count FROM pragma_table_info('appsettings') 
                WHERE name = '{column_name}'
            """)).first()
            
            if column_exists == 0:
                # Add the missing column
                session.exec(text(f"ALTER TABLE appsettings ADD COLUMN {column_name} {column_def}"))
    
    session.commit()
