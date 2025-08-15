from typing import Optional
from fastapi import Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.db import get_session
from app.services.auth import auth_service
from app.models import User
from app.logging import get_logger

logger = get_logger("auth_middleware")


async def get_current_user(
    request: Request,
    session: Session = Depends(get_session)
) -> Optional[User]:
    """Get the current authenticated user from session cookie."""
    # Get the access token from cookies
    access_token = request.cookies.get("access_token")
    if not access_token:
        return None
    
    username = auth_service.verify_token(access_token)
    if not username:
        return None
    
    user = auth_service.get_user_by_username(username, session)
    if not user:
        return None
    
    # Store user in request state for easy access
    request.state.current_user = user
    return user


async def require_auth(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user)
) -> User:
    """Require authentication, redirect to login if not authenticated."""
    # Check if setup is required first
    if not current_user:
        # For API endpoints, return 401
        if request.url.path.startswith("/api/"):
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # For page requests, redirect to login
        return RedirectResponse(url="/login", status_code=302)
    
    return current_user


async def check_setup_required(
    request: Request,
    session: Session = Depends(get_session)
) -> bool:
    """Check if initial setup is required."""
    setup_required = auth_service.is_setup_required(session)
    
    # If setup is required and we're not on setup page, redirect
    if setup_required and not request.url.path.startswith("/setup"):
        if request.url.path.startswith("/api/"):
            raise HTTPException(status_code=403, detail="Setup required")
        return RedirectResponse(url="/setup", status_code=302)
    
    return setup_required


async def optional_auth(
    request: Request,
    session: Session = Depends(get_session)
) -> Optional[User]:
    """Optional authentication for pages that work with or without auth."""
    # Check if setup is required first
    setup_required = auth_service.is_setup_required(session)
    if setup_required:
        return None
    
    # Get the access token from cookies
    access_token = request.cookies.get("access_token")
    if not access_token:
        return None
    
    username = auth_service.verify_token(access_token)
    if not username:
        return None
    
    user = auth_service.get_user_by_username(username, session)
    if user:
        request.state.current_user = user
    
    return user
