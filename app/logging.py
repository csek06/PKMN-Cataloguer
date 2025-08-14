import logging
import logging.config
import logging.handlers
import os
import sys
import uuid
from typing import Any, Dict

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.config import settings


def redact_url(url: str) -> str:
    """Redact sensitive query parameters from URLs for logging."""
    if "t=" in url:
        # Simple redaction for PriceCharting token
        import re
        return re.sub(r'([?&])t=[^&]*', r'\1t=REDACTED', url)
    return url


def configure_logging():
    """Configure structured logging with both console and file output."""
    # Ensure logs directory exists
    logs_dir = settings.logs_dir
    os.makedirs(logs_dir, exist_ok=True)
    
    # Clear any existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    
    # Set root logger level
    log_level = getattr(logging, settings.log_level.upper())
    root_logger.setLevel(log_level)
    
    # Create formatters
    console_formatter = logging.Formatter("%(message)s")
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Console handler (for Docker logs and development)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # File handlers with rotation and compression
    # Main application log (all levels)
    app_handler = logging.handlers.RotatingFileHandler(
        filename=os.path.join(logs_dir, "app.log"),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    app_handler.setLevel(log_level)
    app_handler.setFormatter(file_formatter)
    root_logger.addHandler(app_handler)
    
    # Error-only log file
    error_handler = logging.handlers.RotatingFileHandler(
        filename=os.path.join(logs_dir, "error.log"),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_formatter)
    root_logger.addHandler(error_handler)
    
    # Access log handler (for HTTP requests)
    access_handler = logging.handlers.RotatingFileHandler(
        filename=os.path.join(logs_dir, "access.log"),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    access_handler.setLevel(logging.INFO)
    access_handler.setFormatter(file_formatter)
    
    # External API calls log handler
    external_handler = logging.handlers.RotatingFileHandler(
        filename=os.path.join(logs_dir, "external.log"),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    external_handler.setLevel(logging.INFO)
    external_handler.setFormatter(file_formatter)
    
    # Configure specific loggers
    access_logger = logging.getLogger("access")
    access_logger.addHandler(access_handler)
    access_logger.setLevel(logging.INFO)
    access_logger.propagate = False  # Don't propagate to root logger
    
    external_logger = logging.getLogger("external")
    external_logger.addHandler(external_handler)
    external_logger.setLevel(logging.INFO)
    external_logger.propagate = False  # Don't propagate to root logger
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add unique request ID to each request."""
    
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        # Add request ID to structlog context
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        
        response = await call_next(request)
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Log HTTP requests with structured data."""
    
    def __init__(self, app):
        super().__init__(app)
        self.logger = structlog.get_logger("access")
    
    async def dispatch(self, request: Request, call_next):
        import time
        start_time = time.time()
        
        response = await call_next(request)
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Get client IP
        client_ip = request.client.host if request.client else "unknown"
        
        # Get user agent
        user_agent = request.headers.get("user-agent", "unknown")
        
        # Get route pattern if available
        route = getattr(request, "route", None)
        route_path = route.path if route else request.url.path
        
        self.logger.info(
            "http_request",
            method=request.method,
            path=str(request.url.path),
            status=response.status_code,
            duration_ms=duration_ms,
            client_ip=client_ip,
            user_agent=user_agent,
            route=f"{request.method} {route_path}",
            request_id=getattr(request.state, "request_id", "unknown")
        )
        
        return response


def get_logger(name: str = None) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


class ExternalCallLogger:
    """Context manager for logging external API calls."""
    
    def __init__(self, service: str, url: str, request_id: str = None):
        self.service = service
        self.url = redact_url(url)
        self.request_id = request_id
        self.logger = get_logger("external")
        self.start_time = None
    
    def __enter__(self):
        import time
        self.start_time = time.time()
        self.logger.info(
            "external_call_start",
            service=self.service,
            url=self.url,
            request_id=self.request_id
        )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        duration_ms = int((time.time() - self.start_time) * 1000)
        
        if exc_type is None:
            self.logger.info(
                "external_call_success",
                service=self.service,
                url=self.url,
                duration_ms=duration_ms,
                request_id=self.request_id
            )
        else:
            self.logger.error(
                "external_call_error",
                service=self.service,
                url=self.url,
                duration_ms=duration_ms,
                error=str(exc_val),
                request_id=self.request_id,
                exc_info=True
            )
