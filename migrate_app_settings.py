#!/usr/bin/env python3
"""
Migration script to add AppSettings table and populate with current environment values.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from sqlmodel import SQLModel, Session, create_engine, select
from app.models import AppSettings
from app.config import settings


def migrate_app_settings():
    """Create AppSettings table and populate with current environment values."""
    
    # Create database engine
    db_path = settings.db_path
    if not db_path.startswith('sqlite:///'):
        db_path = f"sqlite:///{db_path}"
    
    engine = create_engine(db_path, echo=False)
    
    print("Creating AppSettings table...")
    
    # Create the table
    SQLModel.metadata.create_all(engine, tables=[AppSettings.__table__])
    
    # Check if settings already exist
    with Session(engine) as session:
        existing_settings = session.exec(select(AppSettings)).first()
        
        if existing_settings:
            print("AppSettings already exist, skipping population.")
            print(f"Current settings ID: {existing_settings.id}")
            return
        
        # Create new settings record with current environment values
        app_settings = AppSettings(
            log_level=settings.log_level,
            local_tz=settings.local_tz,
            price_refresh_batch_size=settings.price_refresh_batch_size,
            price_refresh_requests_per_sec=settings.price_refresh_requests_per_sec,
            sql_echo=settings.sql_echo,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        session.add(app_settings)
        session.commit()
        session.refresh(app_settings)
        
        print(f"✅ Created AppSettings record with ID: {app_settings.id}")
        print(f"   - Log Level: {app_settings.log_level}")
        print(f"   - Timezone: {app_settings.local_tz}")
        print(f"   - Batch Size: {app_settings.price_refresh_batch_size}")
        print(f"   - Requests/sec: {app_settings.price_refresh_requests_per_sec}")
        print(f"   - SQL Echo: {app_settings.sql_echo}")


if __name__ == "__main__":
    try:
        migrate_app_settings()
        print("\n✅ Migration completed successfully!")
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        sys.exit(1)
