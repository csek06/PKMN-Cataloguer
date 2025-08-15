"""Database backup service for Pokémon Card Cataloguer."""

import gzip
import logging
import os
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from app.config import get_data_dir

logger = logging.getLogger(__name__)


class BackupService:
    """Manages database backups and restoration."""
    
    def __init__(self):
        self.data_dir = Path(get_data_dir())
        self.backup_dir = self.data_dir / "backups"
        self.db_path = Path(get_data_dir()) / "app.db"
        
        # Ensure backup directory exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    def create_backup(self, reason: str = "manual", compress: bool = True) -> str:
        """Create a database backup."""
        try:
            if not self.db_path.exists():
                raise FileNotFoundError(f"Database file not found: {self.db_path}")
            
            # Generate backup filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"cataloguer_backup_{timestamp}_{reason}.db"
            
            if compress:
                backup_name += ".gz"
            
            backup_path = self.backup_dir / backup_name
            
            logger.info(f"Creating backup: {backup_path}")
            
            if compress:
                # Create compressed backup
                with open(self.db_path, 'rb') as f_in:
                    with gzip.open(backup_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
            else:
                # Create uncompressed backup
                shutil.copy2(self.db_path, backup_path)
            
            # Verify backup was created
            if not backup_path.exists():
                raise Exception("Backup file was not created")
            
            backup_size = backup_path.stat().st_size
            logger.info(f"Backup created successfully: {backup_path} ({backup_size:,} bytes)")
            
            return str(backup_path)
            
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            raise
    
    def list_backups(self) -> List[dict]:
        """List all available backups."""
        backups = []
        
        if not self.backup_dir.exists():
            return backups
        
        for backup_file in self.backup_dir.glob("cataloguer_backup_*.db*"):
            try:
                # Parse filename to extract metadata
                filename = backup_file.name
                
                # Remove extension(s)
                name_parts = filename.replace(".db.gz", "").replace(".db", "")
                parts = name_parts.split("_")
                
                if len(parts) >= 4:
                    # Extract timestamp and reason
                    date_str = parts[2]  # YYYYMMDD
                    time_str = parts[3]  # HHMMSS
                    reason = "_".join(parts[4:]) if len(parts) > 4 else "unknown"
                    
                    # Parse datetime
                    timestamp_str = f"{date_str}_{time_str}"
                    created_at = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                    
                    # Get file size
                    file_size = backup_file.stat().st_size
                    
                    # Determine if compressed
                    is_compressed = filename.endswith(".gz")
                    
                    backups.append({
                        "filename": filename,
                        "path": str(backup_file),
                        "created_at": created_at,
                        "reason": reason,
                        "size_bytes": file_size,
                        "size_mb": round(file_size / (1024 * 1024), 2),
                        "compressed": is_compressed
                    })
                    
            except Exception as e:
                logger.warning(f"Could not parse backup file {backup_file.name}: {e}")
                continue
        
        # Sort by creation date (newest first)
        return sorted(backups, key=lambda x: x["created_at"], reverse=True)
    
    def cleanup_old_backups(self, retention_days: int = 7) -> int:
        """Remove backups older than retention_days."""
        try:
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            backups = self.list_backups()
            
            removed_count = 0
            for backup in backups:
                if backup["created_at"] < cutoff_date:
                    try:
                        Path(backup["path"]).unlink()
                        logger.info(f"Removed old backup: {backup['filename']}")
                        removed_count += 1
                    except Exception as e:
                        logger.error(f"Failed to remove backup {backup['filename']}: {e}")
            
            if removed_count > 0:
                logger.info(f"Cleaned up {removed_count} old backups")
            
            return removed_count
            
        except Exception as e:
            logger.error(f"Error during backup cleanup: {e}")
            return 0
    
    def restore_backup(self, backup_path: str) -> bool:
        """Restore database from backup."""
        try:
            backup_file = Path(backup_path)
            
            if not backup_file.exists():
                raise FileNotFoundError(f"Backup file not found: {backup_path}")
            
            # Create a backup of current database before restore
            current_backup = self.create_backup(reason="pre_restore", compress=False)
            logger.info(f"Created backup of current database: {current_backup}")
            
            # Stop any active connections (this is a simple approach)
            # In a production system, you'd want more sophisticated connection management
            
            if backup_file.name.endswith(".gz"):
                # Decompress and restore
                with gzip.open(backup_file, 'rb') as f_in:
                    with open(self.db_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
            else:
                # Direct copy
                shutil.copy2(backup_file, self.db_path)
            
            logger.info(f"Successfully restored database from: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to restore backup {backup_path}: {e}")
            return False
    
    def get_database_size(self) -> dict:
        """Get current database size information."""
        try:
            if not self.db_path.exists():
                return {"size_bytes": 0, "size_mb": 0, "exists": False}
            
            size_bytes = self.db_path.stat().st_size
            size_mb = round(size_bytes / (1024 * 1024), 2)
            
            return {
                "size_bytes": size_bytes,
                "size_mb": size_mb,
                "exists": True,
                "path": str(self.db_path)
            }
            
        except Exception as e:
            logger.error(f"Error getting database size: {e}")
            return {"size_bytes": 0, "size_mb": 0, "exists": False, "error": str(e)}
    
    def verify_backup(self, backup_path: str) -> bool:
        """Verify that a backup file is a valid SQLite database."""
        try:
            backup_file = Path(backup_path)
            
            if not backup_file.exists():
                return False
            
            # For compressed backups, we need to decompress first
            if backup_file.name.endswith(".gz"):
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".db") as temp_file:
                    with gzip.open(backup_file, 'rb') as f_in:
                        shutil.copyfileobj(f_in, temp_file)
                    
                    temp_file.flush()
                    return self._verify_sqlite_file(temp_file.name)
            else:
                return self._verify_sqlite_file(str(backup_file))
                
        except Exception as e:
            logger.error(f"Error verifying backup {backup_path}: {e}")
            return False
    
    def _verify_sqlite_file(self, file_path: str) -> bool:
        """Verify that a file is a valid SQLite database."""
        try:
            conn = sqlite3.connect(file_path)
            cursor = conn.cursor()
            
            # Try to execute a simple query
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
            cursor.fetchone()
            
            conn.close()
            return True
            
        except Exception:
            return False
