"""Database migration manager for Pokémon Card Cataloguer."""

import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from sqlmodel import Session, select, text

from app.db import engine
from app.models import SchemaVersion

logger = logging.getLogger(__name__)


class MigrationManager:
    """Manages database schema migrations."""
    
    def __init__(self):
        self.engine = engine
        self.migrations_dir = Path(__file__).parent / "versions"
        
    def get_current_version(self) -> int:
        """Get the current database schema version."""
        try:
            with Session(self.engine) as session:
                # Check if schema_version table exists
                result = session.exec(text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='schemaversion'"
                )).first()
                
                if not result:
                    # Schema version table doesn't exist, this is version 0
                    return 0
                
                # Get the highest version number
                statement = select(SchemaVersion.version).order_by(SchemaVersion.version.desc())
                version = session.exec(statement).first()
                return version if version is not None else 0
                
        except Exception as e:
            logger.error(f"Error getting current schema version: {e}")
            return 0
    
    def get_available_migrations(self) -> List[Dict[str, Any]]:
        """Get list of available migration files."""
        migrations = []
        
        if not self.migrations_dir.exists():
            return migrations
            
        for file_path in sorted(self.migrations_dir.glob("*.py")):
            if file_path.name.startswith("__"):
                continue
                
            # Extract version number from filename (e.g., "001_initial_schema.py" -> 1)
            try:
                version_str = file_path.stem.split("_")[0]
                version = int(version_str)
                
                # Extract description from filename
                description = "_".join(file_path.stem.split("_")[1:]).replace("_", " ").title()
                
                migrations.append({
                    "version": version,
                    "description": description,
                    "file_path": file_path,
                    "module_name": f"migrations.versions.{file_path.stem}"
                })
            except (ValueError, IndexError):
                logger.warning(f"Skipping migration file with invalid name: {file_path.name}")
                continue
                
        return sorted(migrations, key=lambda x: x["version"])
    
    def apply_migration(self, migration: Dict[str, Any]) -> bool:
        """Apply a single migration."""
        try:
            logger.info(f"Applying migration {migration['version']}: {migration['description']}")
            
            # Import the migration module
            import importlib
            module = importlib.import_module(migration["module_name"])
            
            # Execute the migration
            if hasattr(module, "upgrade"):
                with Session(self.engine) as session:
                    module.upgrade(session)
                    
                    # Record the migration in schema_version table
                    schema_version = SchemaVersion(
                        version=migration["version"],
                        description=migration["description"],
                        applied_at=datetime.utcnow()
                    )
                    session.add(schema_version)
                    session.commit()
                    
                logger.info(f"Successfully applied migration {migration['version']}")
                return True
            else:
                logger.error(f"Migration {migration['version']} missing upgrade function")
                return False
                
        except Exception as e:
            logger.error(f"Error applying migration {migration['version']}: {e}")
            return False
    
    def run_migrations(self) -> bool:
        """Run all pending migrations."""
        try:
            current_version = self.get_current_version()
            available_migrations = self.get_available_migrations()
            
            # Filter to only pending migrations
            pending_migrations = [
                m for m in available_migrations 
                if m["version"] > current_version
            ]
            
            if not pending_migrations:
                logger.info(f"Database is up to date (version {current_version})")
                return True
            
            logger.info(f"Found {len(pending_migrations)} pending migrations")
            
            # Apply each migration in order
            for migration in pending_migrations:
                if not self.apply_migration(migration):
                    logger.error(f"Failed to apply migration {migration['version']}, stopping")
                    return False
            
            new_version = self.get_current_version()
            logger.info(f"Successfully updated database from version {current_version} to {new_version}")
            return True
            
        except Exception as e:
            logger.error(f"Error running migrations: {e}")
            return False
    
    def create_backup_before_migration(self) -> str:
        """Create a backup before running migrations."""
        try:
            from app.services.backup_service import BackupService
            backup_service = BackupService()
            
            backup_path = backup_service.create_backup(reason="pre_migration")
            logger.info(f"Created pre-migration backup: {backup_path}")
            return backup_path
            
        except Exception as e:
            logger.error(f"Failed to create pre-migration backup: {e}")
            raise


def run_migrations():
    """Main entry point for running migrations."""
    try:
        manager = MigrationManager()
        
        # Create backup before migrations
        try:
            backup_path = manager.create_backup_before_migration()
            logger.info(f"Pre-migration backup created: {backup_path}")
        except Exception as e:
            logger.warning(f"Could not create pre-migration backup: {e}")
            # Continue with migrations anyway
        
        # Run migrations
        success = manager.run_migrations()
        
        if success:
            logger.info("All migrations completed successfully")
            return True
        else:
            logger.error("Migration process failed")
            return False
            
    except Exception as e:
        logger.error(f"Migration process failed with error: {e}")
        return False


if __name__ == "__main__":
    # Configure logging for standalone execution
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    success = run_migrations()
    exit(0 if success else 1)
