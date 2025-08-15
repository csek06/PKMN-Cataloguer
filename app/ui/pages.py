from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.db import get_session
from app.logging import get_logger
from app.services.pricecharting_scraper import pricecharting_scraper
from app.services.auth import auth_service
from app.middleware.auth import get_current_user, check_setup_required
from app.models import User


router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="templates")
logger = get_logger("ui_pages")


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request, 
    session: Session = Depends(get_session)
):
    """Main application page."""
    try:
        request_id = getattr(request.state, "request_id", None)
        
        # Check if setup is required
        if auth_service.is_setup_required(session):
            return RedirectResponse(url="/setup", status_code=302)
        
        # Check authentication
        current_user = await get_current_user(request, session)
        if not current_user:
            return RedirectResponse(url="/login", status_code=302)
        
        logger.info(
            "index_page_request",
            request_id=request_id,
            username=current_user.username
        )
        
        # Check for password change success message
        password_changed = request.query_params.get("password_changed") == "true"
        
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "has_pricing": pricecharting_scraper.is_available(),
                "current_user": current_user,
                "password_changed": password_changed
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
async def settings(
    request: Request,
    session: Session = Depends(get_session)
):
    """Settings page."""
    try:
        request_id = getattr(request.state, "request_id", None)
        
        # Check if setup is required
        if auth_service.is_setup_required(session):
            return RedirectResponse(url="/setup", status_code=302)
        
        # Check authentication
        current_user = await get_current_user(request, session)
        if not current_user:
            return RedirectResponse(url="/login", status_code=302)
        
        logger.info(
            "settings_page_request",
            request_id=request_id,
            username=current_user.username
        )
        
        return templates.TemplateResponse(
            "settings.html",
            {
                "request": request,
                "has_pricing": pricecharting_scraper.is_available(),
                "current_user": current_user
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
