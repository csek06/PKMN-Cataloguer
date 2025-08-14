import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.db import init_db
from app.logging import (
    configure_logging,
    RequestIDMiddleware,
    AccessLogMiddleware,
    get_logger
)
from app.api import routes_search, routes_collection, routes_cards, routes_admin, routes_settings
from app.ui import pages
from app.services.pricing_refresh import pricing_refresh_service


# Configure logging first
configure_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("application_startup")
    
    try:
        # Initialize database
        init_db()
        logger.info("database_initialized")
        
        # Start pricing refresh scheduler
        pricing_refresh_service.start()
        logger.info("pricing_scheduler_started")
        
    except Exception as e:
        logger.error("startup_error", error=str(e), exc_info=True)
        raise
    
    yield
    
    # Shutdown
    logger.info("application_shutdown")
    
    try:
        # Stop pricing refresh scheduler
        pricing_refresh_service.stop()
        logger.info("pricing_scheduler_stopped")
        
    except Exception as e:
        logger.error("shutdown_error", error=str(e), exc_info=True)


# Create FastAPI app
app = FastAPI(
    title="Pokémon Card Cataloguer",
    description="A single-user Pokémon card collection manager with pricing integration",
    version="1.0.0",
    lifespan=lifespan
)

# Add middleware
app.add_middleware(RequestIDMiddleware)
app.add_middleware(AccessLogMiddleware)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(pages.router)
app.include_router(routes_search.router)
app.include_router(routes_collection.router)
app.include_router(routes_cards.router)
app.include_router(routes_admin.router)
app.include_router(routes_settings.router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with structured logging."""
    request_id = getattr(request.state, "request_id", "unknown")
    
    logger.warning(
        "http_exception",
        status_code=exc.status_code,
        detail=exc.detail,
        path=str(request.url.path),
        method=request.method,
        request_id=request_id
    )
    
    # Return JSON for API endpoints, HTML for pages
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "request_id": request_id}
        )
    else:
        # For page requests, return HTML error page
        templates = Jinja2Templates(directory="templates")
        return templates.TemplateResponse(
            "base.html",
            {
                "request": request,
                "error": exc.detail,
                "status_code": exc.status_code
            },
            status_code=exc.status_code
        )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions with structured logging."""
    request_id = getattr(request.state, "request_id", "unknown")
    
    logger.error(
        "unhandled_exception",
        error=str(exc),
        path=str(request.url.path),
        method=request.method,
        request_id=request_id,
        exc_info=True
    )
    
    # Return JSON for API endpoints, HTML for pages
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "request_id": request_id
            }
        )
    else:
        # For page requests, return HTML error page
        templates = Jinja2Templates(directory="templates")
        return templates.TemplateResponse(
            "base.html",
            {
                "request": request,
                "error": "An unexpected error occurred",
                "status_code": 500
            },
            status_code=500
        )


if __name__ == "__main__":
    import uvicorn
    
    # Run with uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # Set to True for development
        log_config=None,  # Disable uvicorn's default logging
        access_log=False  # We handle access logging with our middleware
    )
