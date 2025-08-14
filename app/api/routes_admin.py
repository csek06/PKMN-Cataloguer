from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, Request, HTTPException, Header
from fastapi.responses import JSONResponse
from sqlmodel import Session

from app.config import settings
from app.db import get_session, health_check
from app.logging import get_logger
from app.schemas import HealthResponse
from app.services.pricing_refresh import pricing_refresh_service


router = APIRouter(prefix="/api", tags=["admin"])
logger = get_logger("admin_api")


def verify_admin_token(authorization: Optional[str] = Header(None)):
    """Verify admin authorization for protected endpoints."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    # Simple token verification - in production, use proper JWT or similar
    if authorization != f"Bearer {settings.secret_key}":
        raise HTTPException(status_code=403, detail="Invalid authorization token")


@router.get("/healthz")
async def health_check_endpoint(request: Request):
    """Health check endpoint."""
    try:
        request_id = getattr(request.state, "request_id", None)
        
        # Check database connectivity
        db_healthy = health_check()
        
        status = "healthy" if db_healthy else "unhealthy"
        
        response = HealthResponse(
            status=status,
            database=db_healthy,
            timestamp=datetime.utcnow()
        )
        
        logger.info(
            "health_check",
            status=status,
            database=db_healthy,
            request_id=request_id
        )
        
        status_code = 200 if db_healthy else 503
        return JSONResponse(
            content=response.dict(),
            status_code=status_code
        )
    
    except Exception as e:
        logger.error(
            "health_check_error",
            error=str(e),
            request_id=getattr(request.state, "request_id", None),
            exc_info=True
        )
        
        return JSONResponse(
            content={
                "status": "error",
                "database": False,
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e)
            },
            status_code=503
        )


@router.post("/refresh-prices")
async def manual_price_refresh(
    request: Request,
    card_ids: Optional[List[int]] = None,
    session: Session = Depends(get_session),
    _: None = Depends(verify_admin_token)
):
    """Manually trigger a price refresh."""
    try:
        request_id = getattr(request.state, "request_id", None)
        
        logger.info(
            "manual_price_refresh_request",
            card_ids=card_ids,
            card_count=len(card_ids) if card_ids else None,
            request_id=request_id
        )
        
        # Trigger the refresh
        result = await pricing_refresh_service.manual_refresh(card_ids)
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        logger.info(
            "manual_price_refresh_complete",
            result=result,
            request_id=request_id
        )
        
        return JSONResponse(content={
            "success": True,
            "message": "Price refresh completed",
            **result
        })
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "manual_price_refresh_error",
            card_ids=card_ids,
            error=str(e),
            request_id=getattr(request.state, "request_id", None),
            exc_info=True
        )
        
        raise HTTPException(
            status_code=500,
            detail="Price refresh failed"
        )


@router.get("/scheduler/status")
async def get_scheduler_status(
    request: Request,
    _: None = Depends(verify_admin_token)
):
    """Get scheduler status."""
    try:
        request_id = getattr(request.state, "request_id", None)
        
        is_running = pricing_refresh_service.is_running
        
        # Get job info if scheduler is running
        job_info = None
        if is_running and pricing_refresh_service.scheduler:
            job = pricing_refresh_service.scheduler.get_job("daily_price_refresh")
            if job:
                job_info = {
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                    "trigger": str(job.trigger)
                }
        
        response = {
            "scheduler_running": is_running,
            "job": job_info,
            "timezone": settings.local_tz,
            "batch_size": settings.price_refresh_batch_size,
            "requests_per_sec": settings.price_refresh_requests_per_sec,
            "pricecharting_available": bool(settings.pc_token)
        }
        
        logger.info(
            "scheduler_status_request",
            scheduler_running=is_running,
            has_job=bool(job_info),
            request_id=request_id
        )
        
        return JSONResponse(content=response)
    
    except Exception as e:
        logger.error(
            "scheduler_status_error",
            error=str(e),
            request_id=getattr(request.state, "request_id", None),
            exc_info=True
        )
        
        raise HTTPException(
            status_code=500,
            detail="Failed to get scheduler status"
        )


@router.post("/scheduler/start")
async def start_scheduler(
    request: Request,
    _: None = Depends(verify_admin_token)
):
    """Start the price refresh scheduler."""
    try:
        request_id = getattr(request.state, "request_id", None)
        
        if pricing_refresh_service.is_running:
            return JSONResponse(content={
                "success": True,
                "message": "Scheduler is already running"
            })
        
        pricing_refresh_service.start()
        
        logger.info(
            "scheduler_started",
            request_id=request_id
        )
        
        return JSONResponse(content={
            "success": True,
            "message": "Scheduler started successfully"
        })
    
    except Exception as e:
        logger.error(
            "scheduler_start_error",
            error=str(e),
            request_id=getattr(request.state, "request_id", None),
            exc_info=True
        )
        
        raise HTTPException(
            status_code=500,
            detail="Failed to start scheduler"
        )


@router.post("/scheduler/stop")
async def stop_scheduler(
    request: Request,
    _: None = Depends(verify_admin_token)
):
    """Stop the price refresh scheduler."""
    try:
        request_id = getattr(request.state, "request_id", None)
        
        if not pricing_refresh_service.is_running:
            return JSONResponse(content={
                "success": True,
                "message": "Scheduler is already stopped"
            })
        
        pricing_refresh_service.stop()
        
        logger.info(
            "scheduler_stopped",
            request_id=request_id
        )
        
        return JSONResponse(content={
            "success": True,
            "message": "Scheduler stopped successfully"
        })
    
    except Exception as e:
        logger.error(
            "scheduler_stop_error",
            error=str(e),
            request_id=getattr(request.state, "request_id", None),
            exc_info=True
        )
        
        raise HTTPException(
            status_code=500,
            detail="Failed to stop scheduler"
        )
