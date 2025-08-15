import asyncio
import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, desc

from app.db import get_db_session
from app.models import JobHistory, AppSettings
from app.services.pricing_refresh import pricing_refresh_service
from app.services.metadata_refresh import metadata_refresh_service
from app.config import settings
from app.schemas import AppSettingsResponse, UpdateAppSettingsRequest

templates = Jinja2Templates(directory="templates")


router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/pricing", response_class=HTMLResponse)
async def get_pricing_settings(request: Request):
    """Get current pricing refresh settings and status."""
    
    # Get scheduler status
    scheduler_running = pricing_refresh_service.is_running
    
    # Get next scheduled run time
    next_run = None
    if scheduler_running and pricing_refresh_service.scheduler.get_jobs():
        job = pricing_refresh_service.scheduler.get_job("daily_price_refresh")
        if job:
            next_run = job.next_run_time.isoformat() if job.next_run_time else None
    
    # Get last job history
    last_job = None
    with get_db_session() as session:
        last_job_record = session.exec(
            select(JobHistory)
            .where(JobHistory.job_type == "scheduled")
            .order_by(desc(JobHistory.started_at))
            .limit(1)
        ).first()
        
        if last_job_record:
            last_job = last_job_record
    
    # Get current running job
    current_job = None
    with get_db_session() as session:
        running_job = session.exec(
            select(JobHistory)
            .where(JobHistory.status == "running")
            .order_by(desc(JobHistory.started_at))
            .limit(1)
        ).first()
        
        if running_job:
            current_job = running_job
    
    return templates.TemplateResponse(
        "_pricing_status.html",
        {
            "request": request,
            "scheduler_running": scheduler_running,
            "next_run": next_run,
            "batch_size": settings.price_refresh_batch_size,
            "requests_per_sec": settings.price_refresh_requests_per_sec,
            "timezone": settings.local_tz,
            "last_job": last_job,
            "current_job": current_job
        }
    )


@router.post("/pricing/run", response_class=HTMLResponse)
async def trigger_manual_refresh(request: Request, card_ids: Optional[List[int]] = None):
    """Trigger a manual price refresh."""
    
    # Check if there's already a job running
    with get_db_session() as session:
        running_job = session.exec(
            select(JobHistory)
            .where(JobHistory.status == "running")
        ).first()
        
        if running_job:
            raise HTTPException(
                status_code=409,
                detail="A price refresh job is already running"
            )
    
    # Start the manual refresh using FastAPI BackgroundTasks
    from fastapi import BackgroundTasks
    import asyncio
    
    try:
        # Create a wrapper function for the background task
        def run_manual_refresh():
            """Wrapper to run the async manual refresh in a new event loop."""
            import asyncio
            
            async def _run():
                try:
                    result = await pricing_refresh_service.manual_refresh(card_ids)
                    print(f"Background job completed: {result}")
                except Exception as e:
                    print(f"Background job failed: {e}")
                    # Mark any running jobs as failed
                    await pricing_refresh_service._mark_running_jobs_as_failed(f"Background job error: {str(e)}")
            
            # Create new event loop for the background task
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_run())
            finally:
                loop.close()
        
        # Start the background task using threading to avoid blocking
        import threading
        thread = threading.Thread(target=run_manual_refresh)
        thread.daemon = True
        thread.start()
        
        # Give it a moment to start and create the job record
        await asyncio.sleep(0.2)
        
        # Return the updated status template
        scheduler_running = pricing_refresh_service.is_running
        
        # Get next scheduled run time
        next_run = None
        if scheduler_running and pricing_refresh_service.scheduler.get_jobs():
            job = pricing_refresh_service.scheduler.get_job("daily_price_refresh")
            if job:
                next_run = job.next_run_time.isoformat() if job.next_run_time else None
        
        # Get last completed job
        last_job = None
        with get_db_session() as session:
            last_job_record = session.exec(
                select(JobHistory)
                .where(JobHistory.status.in_(["completed", "completed_with_errors"]))
                .order_by(desc(JobHistory.started_at))
                .limit(1)
            ).first()
            
            if last_job_record:
                last_job = last_job_record
        
        # Get current running job (should be the one we just started)
        current_job = None
        with get_db_session() as session:
            running_job = session.exec(
                select(JobHistory)
                .where(JobHistory.status == "running")
                .order_by(desc(JobHistory.started_at))
                .limit(1)
            ).first()
            
            if running_job:
                current_job = running_job
        
        return templates.TemplateResponse(
            "_pricing_status.html",
            {
                "request": request,
                "scheduler_running": scheduler_running,
                "next_run": next_run,
                "batch_size": settings.price_refresh_batch_size,
                "requests_per_sec": settings.price_refresh_requests_per_sec,
                "timezone": settings.local_tz,
                "last_job": last_job,
                "current_job": current_job
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start manual refresh: {str(e)}"
        )


@router.get("/pricing/history", response_class=HTMLResponse)
async def get_pricing_history(request: Request, limit: int = 20, offset: int = 0):
    """Get pricing refresh job history."""
    
    with get_db_session() as session:
        # Get total count
        total_query = select(JobHistory)
        total_count = len(session.exec(total_query).all())
        
        # Get paginated results
        history_query = (
            select(JobHistory)
            .order_by(desc(JobHistory.started_at))
            .offset(offset)
            .limit(limit)
        )
        
        history_records = session.exec(history_query).all()
        
        return templates.TemplateResponse(
            "_job_history.html",
            {
                "request": request,
                "history": history_records,
                "total": total_count,
                "limit": limit,
                "offset": offset
            }
        )


@router.get("/pricing/events")
async def pricing_events(request: Request):
    """Server-Side Events endpoint for real-time pricing job updates."""
    
    async def event_generator():
        """Generate SSE events for job status updates."""
        last_job_id = None
        last_status = None
        
        while True:
            try:
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                
                # Get current job status
                current_job = None
                with get_db_session() as session:
                    running_job = session.exec(
                        select(JobHistory)
                        .where(JobHistory.status == "running")
                        .order_by(desc(JobHistory.started_at))
                        .limit(1)
                    ).first()
                    
                    if running_job:
                        current_job = {
                            "id": running_job.id,
                            "job_name": running_job.job_name,
                            "job_type": running_job.job_type,
                            "status": running_job.status,
                            "started_at": running_job.started_at.isoformat(),
                            "processed": running_job.processed or 0,
                            "succeeded": running_job.succeeded or 0,
                            "failed": running_job.failed or 0
                        }
                
                # Check for job status changes
                current_job_id = current_job["id"] if current_job else None
                current_status = current_job["status"] if current_job else "idle"
                
                # Send event if job status changed or job is running
                if (current_job_id != last_job_id or 
                    current_status != last_status or 
                    current_status == "running"):
                    
                    event_data = {
                        "type": "job_status",
                        "timestamp": datetime.utcnow().isoformat(),
                        "job": current_job,
                        "scheduler_running": pricing_refresh_service.is_running
                    }
                    
                    # Send SSE event
                    yield f"data: {json.dumps(event_data)}\n\n"
                    
                    last_job_id = current_job_id
                    last_status = current_status
                
                # If no job is running, check less frequently
                sleep_duration = 1.0 if current_status == "running" else 3.0
                await asyncio.sleep(sleep_duration)
                
            except Exception as e:
                # Send error event
                error_event = {
                    "type": "error",
                    "timestamp": datetime.utcnow().isoformat(),
                    "message": str(e)
                }
                yield f"data: {json.dumps(error_event)}\n\n"
                await asyncio.sleep(5.0)  # Wait longer on error
    
    return StreamingResponse(
        event_generator(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
        }
    )


@router.get("/pricing/stats", response_class=HTMLResponse)
async def get_pricing_stats(request: Request):
    """Get pricing refresh statistics."""
    
    with get_db_session() as session:
        # Get recent job statistics (all completed jobs, not just this month)
        recent_jobs = session.exec(
            select(JobHistory)
            .where(JobHistory.status.in_(["completed", "completed_with_errors", "failed"]))
        ).all()
        
        if not recent_jobs:
            stats = {
                "total_jobs": 0,
                "success_rate": 0,
                "avg_duration_ms": 0,
                "total_cards_processed": 0,
                "total_cards_succeeded": 0,
                "total_cards_failed": 0
            }
        else:
            total_jobs = len(recent_jobs)
            successful_jobs = len([j for j in recent_jobs if j.status == "completed"])
            success_rate = (successful_jobs / total_jobs) * 100 if total_jobs > 0 else 0
            
            total_duration = sum(j.duration_ms or 0 for j in recent_jobs)
            avg_duration = total_duration / total_jobs if total_jobs > 0 else 0
            
            total_processed = sum(j.processed for j in recent_jobs)
            total_succeeded = sum(j.succeeded for j in recent_jobs)
            total_failed = sum(j.failed for j in recent_jobs)
            
            stats = {
                "total_jobs": total_jobs,
                "success_rate": round(success_rate, 1),
                "avg_duration_ms": round(avg_duration),
                "total_cards_processed": total_processed,
                "total_cards_succeeded": total_succeeded,
                "total_cards_failed": total_failed
            }
        
        return templates.TemplateResponse(
            "_pricing_stats.html",
            {
                "request": request,
                **stats
            }
        )


@router.get("/app", response_model=AppSettingsResponse)
async def get_app_settings():
    """Get current application settings."""
    
    with get_db_session() as session:
        app_settings = session.exec(select(AppSettings)).first()
        
        if not app_settings:
            raise HTTPException(
                status_code=404,
                detail="Application settings not found. Please run migration."
            )
        
        return app_settings


@router.put("/app", response_model=AppSettingsResponse)
async def update_app_settings(request: UpdateAppSettingsRequest):
    """Update application settings."""
    
    with get_db_session() as session:
        app_settings = session.exec(select(AppSettings)).first()
        
        if not app_settings:
            raise HTTPException(
                status_code=404,
                detail="Application settings not found. Please run migration."
            )
        
        # Update only provided fields
        update_data = request.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(app_settings, field, value)
        
        # Update timestamp
        app_settings.updated_at = datetime.utcnow()
        
        session.add(app_settings)
        session.commit()
        session.refresh(app_settings)
        
        # Invalidate settings cache to force reload
        settings.invalidate_cache()
        
        return app_settings


@router.get("/app/form", response_class=HTMLResponse)
async def get_app_settings_form(request: Request):
    """Get application settings form for the settings page."""
    
    with get_db_session() as session:
        app_settings = session.exec(select(AppSettings)).first()
        
        if not app_settings:
            # Create default settings if they don't exist
            app_settings = AppSettings()
            session.add(app_settings)
            session.commit()
            session.refresh(app_settings)
        
        # Define setting descriptions
        setting_descriptions = {
            "log_level": "Controls the verbosity of application logging. DEBUG shows all messages, INFO shows general information, WARNING shows only warnings and errors, ERROR shows only errors.",
            "local_tz": "The timezone used for displaying dates and scheduling background jobs. Use standard timezone names like 'America/New_York' or 'Europe/London'.",
            "price_refresh_batch_size": "Number of cards to process in each batch during price refresh jobs. Larger batches are faster but use more memory. Recommended: 100-500.",
            "price_refresh_requests_per_sec": "Rate limit for PriceCharting requests to avoid being blocked. Lower values are safer but slower. Recommended: 1-2 requests per second.",
            "sql_echo": "Enable detailed SQL query logging for debugging database issues. Only enable when troubleshooting as it creates verbose logs."
        }
        
        return templates.TemplateResponse(
            "_app_settings_form.html",
            {
                "request": request,
                "settings": app_settings,
                "descriptions": setting_descriptions
            }
        )


# Metadata refresh endpoints
@router.get("/metadata", response_class=HTMLResponse)
async def get_metadata_settings(request: Request):
    """Get current metadata refresh settings and status."""
    
    # Get scheduler status
    scheduler_running = metadata_refresh_service.is_running
    
    # Get next scheduled run time
    next_run = None
    if scheduler_running and metadata_refresh_service.scheduler.get_jobs():
        job = metadata_refresh_service.scheduler.get_job("weekly_metadata_refresh")
        if job:
            next_run = job.next_run_time.isoformat() if job.next_run_time else None
    
    # Get last job history
    last_job = None
    with get_db_session() as session:
        last_job_record = session.exec(
            select(JobHistory)
            .where(JobHistory.job_name.like("%metadata%"))
            .where(JobHistory.job_type == "scheduled")
            .order_by(desc(JobHistory.started_at))
            .limit(1)
        ).first()
        
        if last_job_record:
            last_job = last_job_record
    
    # Get current running metadata job
    current_job = None
    with get_db_session() as session:
        running_job = session.exec(
            select(JobHistory)
            .where(JobHistory.status == "running")
            .where(JobHistory.job_name.like("%metadata%"))
            .order_by(desc(JobHistory.started_at))
            .limit(1)
        ).first()
        
        if running_job:
            current_job = running_job
    
    return templates.TemplateResponse(
        "_metadata_status.html",
        {
            "request": request,
            "scheduler_running": scheduler_running,
            "next_run": next_run,
            "batch_size": settings.price_refresh_batch_size,  # Reuse batch size setting
            "timezone": settings.local_tz,
            "last_job": last_job,
            "current_job": current_job
        }
    )


@router.post("/metadata/run", response_class=HTMLResponse)
async def trigger_manual_metadata_refresh(request: Request, card_ids: Optional[List[int]] = None):
    """Trigger a manual metadata refresh."""
    
    # Check if there's already a metadata job running
    with get_db_session() as session:
        running_job = session.exec(
            select(JobHistory)
            .where(JobHistory.status == "running")
            .where(JobHistory.job_name.like("%metadata%"))
        ).first()
        
        if running_job:
            raise HTTPException(
                status_code=409,
                detail="A metadata refresh job is already running"
            )
    
    try:
        # Create a wrapper function for the background task
        def run_manual_metadata_refresh():
            """Wrapper to run the async manual metadata refresh in a new event loop."""
            import asyncio
            
            async def _run():
                try:
                    result = await metadata_refresh_service.manual_refresh(card_ids)
                    print(f"Background metadata job completed: {result}")
                except Exception as e:
                    print(f"Background metadata job failed: {e}")
                    # Mark any running jobs as failed
                    await metadata_refresh_service._mark_running_jobs_as_failed(f"Background job error: {str(e)}")
            
            # Create new event loop for the background task
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_run())
            finally:
                loop.close()
        
        # Start the background task using threading to avoid blocking
        import threading
        thread = threading.Thread(target=run_manual_metadata_refresh)
        thread.daemon = True
        thread.start()
        
        # Give it a moment to start and create the job record
        await asyncio.sleep(0.2)
        
        # Return the updated status template
        scheduler_running = metadata_refresh_service.is_running
        
        # Get next scheduled run time
        next_run = None
        if scheduler_running and metadata_refresh_service.scheduler.get_jobs():
            job = metadata_refresh_service.scheduler.get_job("weekly_metadata_refresh")
            if job:
                next_run = job.next_run_time.isoformat() if job.next_run_time else None
        
        # Get last completed job
        last_job = None
        with get_db_session() as session:
            last_job_record = session.exec(
                select(JobHistory)
                .where(JobHistory.job_name.like("%metadata%"))
                .where(JobHistory.status.in_(["completed", "completed_with_errors"]))
                .order_by(desc(JobHistory.started_at))
                .limit(1)
            ).first()
            
            if last_job_record:
                last_job = last_job_record
        
        # Get current running job (should be the one we just started)
        current_job = None
        with get_db_session() as session:
            running_job = session.exec(
                select(JobHistory)
                .where(JobHistory.status == "running")
                .where(JobHistory.job_name.like("%metadata%"))
                .order_by(desc(JobHistory.started_at))
                .limit(1)
            ).first()
            
            if running_job:
                current_job = running_job
        
        return templates.TemplateResponse(
            "_metadata_status.html",
            {
                "request": request,
                "scheduler_running": scheduler_running,
                "next_run": next_run,
                "batch_size": settings.price_refresh_batch_size,
                "timezone": settings.local_tz,
                "last_job": last_job,
                "current_job": current_job
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start manual metadata refresh: {str(e)}"
        )


@router.get("/metadata/history", response_class=HTMLResponse)
async def get_metadata_history(request: Request, limit: int = 10, offset: int = 0):
    """Get metadata refresh job history."""
    
    with get_db_session() as session:
        # Get total count for metadata jobs
        total_query = (
            select(JobHistory)
            .where(JobHistory.job_name.like("%metadata%"))
        )
        total_count = len(session.exec(total_query).all())
        
        # Get paginated results for metadata jobs
        history_query = (
            select(JobHistory)
            .where(JobHistory.job_name.like("%metadata%"))
            .order_by(desc(JobHistory.started_at))
            .offset(offset)
            .limit(limit)
        )
        
        history_records = session.exec(history_query).all()
        
        return templates.TemplateResponse(
            "_job_history.html",
            {
                "request": request,
                "history": history_records,
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "job_type": "metadata"
            }
        )


@router.get("/metadata/events")
async def metadata_events(request: Request):
    """Server-Side Events endpoint for real-time metadata job updates."""
    
    async def event_generator():
        """Generate SSE events for metadata job status updates."""
        last_job_id = None
        last_status = None
        
        while True:
            try:
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                
                # Get current metadata job status
                current_job = None
                with get_db_session() as session:
                    running_job = session.exec(
                        select(JobHistory)
                        .where(JobHistory.status == "running")
                        .where(JobHistory.job_name.like("%metadata%"))
                        .order_by(desc(JobHistory.started_at))
                        .limit(1)
                    ).first()
                    
                    if running_job:
                        current_job = {
                            "id": running_job.id,
                            "job_name": running_job.job_name,
                            "job_type": running_job.job_type,
                            "status": running_job.status,
                            "started_at": running_job.started_at.isoformat(),
                            "processed": running_job.processed or 0,
                            "succeeded": running_job.succeeded or 0,
                            "failed": running_job.failed or 0
                        }
                
                # Check for job status changes
                current_job_id = current_job["id"] if current_job else None
                current_status = current_job["status"] if current_job else "idle"
                
                # Send event if job status changed or job is running
                if (current_job_id != last_job_id or 
                    current_status != last_status or 
                    current_status == "running"):
                    
                    event_data = {
                        "type": "job_status",
                        "timestamp": datetime.utcnow().isoformat(),
                        "job": current_job,
                        "scheduler_running": metadata_refresh_service.is_running
                    }
                    
                    # Send SSE event
                    yield f"data: {json.dumps(event_data)}\n\n"
                    
                    last_job_id = current_job_id
                    last_status = current_status
                
                # If no job is running, check less frequently
                sleep_duration = 1.0 if current_status == "running" else 3.0
                await asyncio.sleep(sleep_duration)
                
            except Exception as e:
                # Send error event
                error_event = {
                    "type": "error",
                    "timestamp": datetime.utcnow().isoformat(),
                    "message": str(e)
                }
                yield f"data: {json.dumps(error_event)}\n\n"
                await asyncio.sleep(5.0)  # Wait longer on error
    
    return StreamingResponse(
        event_generator(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
        }
    )


@router.get("/metadata/stats", response_class=HTMLResponse)
async def get_metadata_stats(request: Request):
    """Get metadata refresh statistics."""
    
    with get_db_session() as session:
        # Get recent metadata job statistics
        recent_jobs = session.exec(
            select(JobHistory)
            .where(JobHistory.job_name.like("%metadata%"))
            .where(JobHistory.status.in_(["completed", "completed_with_errors", "failed"]))
        ).all()
        
        if not recent_jobs:
            stats = {
                "total_jobs": 0,
                "success_rate": 0,
                "avg_duration_ms": 0,
                "total_cards_processed": 0,
                "total_cards_succeeded": 0,
                "total_cards_failed": 0
            }
        else:
            total_jobs = len(recent_jobs)
            successful_jobs = len([j for j in recent_jobs if j.status == "completed"])
            success_rate = (successful_jobs / total_jobs) * 100 if total_jobs > 0 else 0
            
            total_duration = sum(j.duration_ms or 0 for j in recent_jobs)
            avg_duration = total_duration / total_jobs if total_jobs > 0 else 0
            
            total_processed = sum(j.processed for j in recent_jobs)
            total_succeeded = sum(j.succeeded for j in recent_jobs)
            total_failed = sum(j.failed for j in recent_jobs)
            
            stats = {
                "total_jobs": total_jobs,
                "success_rate": round(success_rate, 1),
                "avg_duration_ms": round(avg_duration),
                "total_cards_processed": total_processed,
                "total_cards_succeeded": total_succeeded,
                "total_cards_failed": total_failed
            }
        
        return templates.TemplateResponse(
            "_metadata_stats.html",
            {
                "request": request,
                **stats
            }
        )
