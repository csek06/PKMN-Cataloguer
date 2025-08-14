from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.db import get_session
from app.logging import get_logger
from app.services.pricecharting_scraper import pricecharting_scraper


router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="templates")
logger = get_logger("ui_pages")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, session: Session = Depends(get_session)):
    """Main application page."""
    try:
        request_id = getattr(request.state, "request_id", None)
        
        logger.info(
            "index_page_request",
            request_id=request_id
        )
        
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "has_pricing": pricecharting_scraper.is_available()
            }
        )
    
    except Exception as e:
        logger.error(
            "index_page_error",
            error=str(e),
            request_id=getattr(request.state, "request_id", None),
            exc_info=True
        )
        
        # Return a basic error page
        return templates.TemplateResponse(
            "base.html",
            {
                "request": request,
                "error": "Failed to load application"
            },
            status_code=500
        )


@router.get("/settings", response_class=HTMLResponse)
async def settings(request: Request):
    """Settings page."""
    try:
        request_id = getattr(request.state, "request_id", None)
        
        logger.info(
            "settings_page_request",
            request_id=request_id
        )
        
        return templates.TemplateResponse(
            "settings.html",
            {
                "request": request,
                "has_pricing": pricecharting_scraper.is_available()
            }
        )
    
    except Exception as e:
        logger.error(
            "settings_page_error",
            error=str(e),
            request_id=getattr(request.state, "request_id", None),
            exc_info=True
        )
        
        # Return a basic error page
        return templates.TemplateResponse(
            "base.html",
            {
                "request": request,
                "error": "Failed to load settings page"
            },
            status_code=500
        )
