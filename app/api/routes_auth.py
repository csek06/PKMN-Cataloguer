from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session
from pydantic import BaseModel

from app.db import get_session
from app.services.auth import auth_service
from app.middleware.auth import get_current_user, check_setup_required
from app.models import User
from app.logging import get_logger

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="templates")
logger = get_logger("auth_routes")


class SetupRequest(BaseModel):
    username: str
    password: str
    confirm_password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str


@router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request, session: Session = Depends(get_session)):
    """Initial setup page for creating the first user."""
    # Check if setup is actually required
    if not auth_service.is_setup_required(session):
        return RedirectResponse(url="/", status_code=302)
    
    logger.info("setup_page_accessed")
    
    return templates.TemplateResponse(
        "auth/setup.html",
        {"request": request}
    )


@router.post("/setup")
async def setup_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    session: Session = Depends(get_session)
):
    """Create the initial user account."""
    try:
        # Check if setup is actually required
        if not auth_service.is_setup_required(session):
            return RedirectResponse(url="/", status_code=302)
        
        # Validate passwords match
        if password != confirm_password:
            return templates.TemplateResponse(
                "auth/setup.html",
                {
                    "request": request,
                    "error": "Passwords do not match",
                    "username": username
                }
            )
        
        # Validate password length
        if len(password) < 6:
            return templates.TemplateResponse(
                "auth/setup.html",
                {
                    "request": request,
                    "error": "Password must be at least 6 characters long",
                    "username": username
                }
            )
        
        # Create user
        user = auth_service.create_user(username, password, session)
        
        # Create access token and set cookie
        access_token = auth_service.create_access_token(user.username)
        
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax",
            max_age=60 * 60 * 24 * 7  # 7 days
        )
        
        logger.info("setup_completed", username=username)
        return response
        
    except Exception as e:
        logger.error("setup_error", error=str(e), exc_info=True)
        return templates.TemplateResponse(
            "auth/setup.html",
            {
                "request": request,
                "error": "An error occurred during setup. Please try again.",
                "username": username
            }
        )


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, session: Session = Depends(get_session)):
    """Login page."""
    # Check if setup is required first
    if auth_service.is_setup_required(session):
        return RedirectResponse(url="/setup", status_code=302)
    
    logger.info("login_page_accessed")
    
    return templates.TemplateResponse(
        "auth/login.html",
        {"request": request}
    )


@router.post("/login")
async def login_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session)
):
    """Authenticate user and create session."""
    try:
        # Check if setup is required first
        if auth_service.is_setup_required(session):
            return RedirectResponse(url="/setup", status_code=302)
        
        # Check for admin reset password first
        if auth_service.check_admin_reset_password(username, password):
            logger.info("admin_reset_login", username=username)
            
            # Create access token
            access_token = auth_service.create_access_token(username)
            
            response = RedirectResponse(url="/change-password?force=true", status_code=302)
            response.set_cookie(
                key="access_token",
                value=access_token,
                httponly=True,
                secure=False,  # Set to True in production with HTTPS
                samesite="lax",
                max_age=60 * 60 * 24 * 7  # 7 days
            )
            return response
        
        # Regular authentication
        user = auth_service.authenticate_user(username, password, session)
        if not user:
            return templates.TemplateResponse(
                "auth/login.html",
                {
                    "request": request,
                    "error": "Invalid username or password",
                    "username": username
                }
            )
        
        # Create access token and set cookie
        access_token = auth_service.create_access_token(user.username)
        
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax",
            max_age=60 * 60 * 24 * 7  # 7 days
        )
        
        logger.info("login_successful", username=username)
        return response
        
    except Exception as e:
        logger.error("login_error", error=str(e), exc_info=True)
        return templates.TemplateResponse(
            "auth/login.html",
            {
                "request": request,
                "error": "An error occurred during login. Please try again.",
                "username": username
            }
        )


@router.get("/logout")
async def logout_user(request: Request):
    """Logout user by clearing session cookie."""
    logger.info("logout_requested")
    
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(key="access_token")
    
    return response


@router.get("/change-password", response_class=HTMLResponse)
async def change_password_page(
    request: Request,
    force: bool = False,
    current_user: User = Depends(get_current_user)
):
    """Change password page."""
    logger.info("change_password_page_accessed", username=current_user.username, force=force)
    
    return templates.TemplateResponse(
        "auth/change_password.html",
        {
            "request": request,
            "force": force,
            "username": current_user.username
        }
    )


@router.post("/change-password")
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    force: bool = Form(False),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Change user password."""
    try:
        # Validate new passwords match
        if new_password != confirm_password:
            return templates.TemplateResponse(
                "auth/change_password.html",
                {
                    "request": request,
                    "error": "New passwords do not match",
                    "force": force,
                    "username": current_user.username
                }
            )
        
        # Validate password length
        if len(new_password) < 6:
            return templates.TemplateResponse(
                "auth/change_password.html",
                {
                    "request": request,
                    "error": "Password must be at least 6 characters long",
                    "force": force,
                    "username": current_user.username
                }
            )
        
        # For forced password change (admin reset), skip current password check
        if force:
            success = auth_service.force_password_change(current_user.username, new_password, session)
        else:
            success = auth_service.change_password(current_user.username, current_password, new_password, session)
        
        if not success:
            return templates.TemplateResponse(
                "auth/change_password.html",
                {
                    "request": request,
                    "error": "Current password is incorrect" if not force else "Failed to change password",
                    "force": force,
                    "username": current_user.username
                }
            )
        
        logger.info("password_changed_successfully", username=current_user.username)
        
        # Redirect to main page with success message
        response = RedirectResponse(url="/?password_changed=true", status_code=302)
        return response
        
    except Exception as e:
        logger.error("change_password_error", error=str(e), username=current_user.username, exc_info=True)
        return templates.TemplateResponse(
            "auth/change_password.html",
            {
                "request": request,
                "error": "An error occurred while changing password. Please try again.",
                "force": force,
                "username": current_user.username
            }
        )


@router.get("/api/auth/status")
async def auth_status(current_user: User = Depends(get_current_user)):
    """Get current authentication status."""
    return {
        "authenticated": True,
        "username": current_user.username,
        "setup_complete": current_user.is_setup_complete
    }
