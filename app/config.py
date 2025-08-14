import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Data directory - these remain environment-only as they're needed before DB connection
    data_dir: str = "/data"
    
    @property
    def db_path(self) -> str:
        """Database path within the data directory."""
        return f"{self.data_dir}/app.db"
    
    @property
    def logs_dir(self) -> str:
        """Logs directory within the data directory."""
        return f"{self.data_dir}/logs"
    
    # Security - this remains environment-only for security
    secret_key: str = "change-me"
    
    # Application settings - these will be loaded from database with env fallbacks
    sql_echo: bool = False
    log_level: str = "INFO"
    local_tz: str = "America/New_York"
    price_refresh_batch_size: int = 200
    price_refresh_requests_per_sec: int = 1
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Base settings from environment variables
_base_settings = Settings()

class DatabaseSettings:
    """Settings manager that loads from database with environment fallbacks."""
    
    def __init__(self):
        self._cached_settings = None
        self._cache_time = None
        
    def _get_db_settings(self):
        """Load settings from database with caching."""
        import time
        from datetime import datetime
        
        # Cache for 30 seconds to avoid constant DB queries
        current_time = time.time()
        if (self._cached_settings is not None and 
            self._cache_time is not None and 
            current_time - self._cache_time < 30):
            return self._cached_settings
        
        try:
            from sqlmodel import Session, create_engine, select
            from app.models import AppSettings
            
            # Create database connection
            db_path = _base_settings.db_path
            if not db_path.startswith('sqlite:///'):
                db_path = f"sqlite:///{db_path}"
            
            engine = create_engine(db_path, echo=False)
            
            with Session(engine) as session:
                db_settings = session.exec(select(AppSettings)).first()
                
                if db_settings:
                    self._cached_settings = db_settings
                    self._cache_time = current_time
                    return db_settings
                    
        except Exception:
            # If database is not available or settings don't exist, use environment defaults
            pass
        
        return None
    
    @property
    def data_dir(self):
        """Data directory - always from environment."""
        return _base_settings.data_dir
    
    @property
    def db_path(self):
        """Database path - always from environment."""
        return _base_settings.db_path
    
    @property
    def logs_dir(self):
        """Logs directory - always from environment."""
        return _base_settings.logs_dir
    
    @property
    def secret_key(self):
        """Secret key - always from environment for security."""
        return _base_settings.secret_key
    
    @property
    def sql_echo(self):
        """SQL echo setting - from database or environment fallback."""
        db_settings = self._get_db_settings()
        return db_settings.sql_echo if db_settings else _base_settings.sql_echo
    
    @property
    def log_level(self):
        """Log level - from database or environment fallback."""
        db_settings = self._get_db_settings()
        return db_settings.log_level if db_settings else _base_settings.log_level
    
    @property
    def local_tz(self):
        """Local timezone - from database or environment fallback."""
        db_settings = self._get_db_settings()
        return db_settings.local_tz if db_settings else _base_settings.local_tz
    
    @property
    def price_refresh_batch_size(self):
        """Price refresh batch size - from database or environment fallback."""
        db_settings = self._get_db_settings()
        return db_settings.price_refresh_batch_size if db_settings else _base_settings.price_refresh_batch_size
    
    @property
    def price_refresh_requests_per_sec(self):
        """Price refresh requests per second - from database or environment fallback."""
        db_settings = self._get_db_settings()
        return db_settings.price_refresh_requests_per_sec if db_settings else _base_settings.price_refresh_requests_per_sec
    
    def invalidate_cache(self):
        """Invalidate the settings cache to force reload from database."""
        self._cached_settings = None
        self._cache_time = None


settings = DatabaseSettings()
