import asyncio
import random
import time
from datetime import datetime, date
from typing import List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session, select

from app.config import settings
from app.db import get_db_session
from app.logging import get_logger
from app.models import Card, JobHistory
from app.services.tcgdx_api import tcgdx_api


logger = get_logger("metadata_refresh")

# Job timeout constants
JOB_TIMEOUT_SECONDS = 600  # 10 minutes max per job (longer than pricing due to API searches)
CARD_TIMEOUT_SECONDS = 90  # 90 seconds max per card (increased from 45 for API timeouts)


class MetadataRefreshService:
    """Service for scheduled metadata refreshes from TCGdx API."""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.is_running = False
    
    def start(self):
        """Start the scheduler."""
        if not self.is_running:
            # Schedule weekly refresh on Sundays at 2:00 AM local time
            trigger = CronTrigger(
                day_of_week=6,  # Sunday
                hour=2,
                minute=0,
                timezone=settings.local_tz
            )
            
            self.scheduler.add_job(
                self.refresh_metadata,
                trigger=trigger,
                id="weekly_metadata_refresh",
                name="Weekly Metadata Refresh",
                max_instances=1,
                coalesce=True
            )
            
            self.scheduler.start()
            self.is_running = True
            
            logger.info(
                "metadata_scheduler_started",
                timezone=settings.local_tz,
                batch_size=settings.price_refresh_batch_size  # Reuse batch size setting
            )
    
    def stop(self):
        """Stop the scheduler."""
        if self.is_running:
            self.scheduler.shutdown()
            self.is_running = False
            logger.info("metadata_scheduler_stopped")
    
    async def refresh_metadata(self):
        """Refresh metadata for a batch of cards with timeout protection."""
        try:
            # Wrap the entire job in a timeout
            await asyncio.wait_for(
                self._refresh_metadata_impl("scheduled", "weekly_metadata"),
                timeout=JOB_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            logger.error(
                "metadata_refresh_timeout",
                job_name="weekly_metadata",
                timeout_seconds=JOB_TIMEOUT_SECONDS
            )
            # Mark any running job as failed due to timeout
            await self._mark_running_jobs_as_failed("Job timed out")
        except Exception as e:
            logger.error(
                "metadata_refresh_unexpected_error",
                job_name="weekly_metadata",
                error=str(e),
                exc_info=True
            )
            await self._mark_running_jobs_as_failed(f"Unexpected error: {str(e)}")

    async def _refresh_metadata_impl(self, job_type: str, job_name: str, card_ids: Optional[List[int]] = None):
        """Implementation of metadata refresh with proper error handling."""
        # Check API availability
        logger.info("metadata_refresh_checking_api_availability", job_name=job_name)
        api_available = await tcgdx_api.is_available()
        
        if not api_available:
            error_msg = "TCGdx API is currently unavailable. This may be due to network issues, API downtime, or timeout. The metadata refresh will be skipped until the API is accessible again."
            logger.warning(
                "metadata_refresh_skipped", 
                reason="api_unavailable",
                job_name=job_name,
                message=error_msg
            )
            
            # Create a failed job record to track this attempt
            start_datetime = datetime.utcnow()
            job_history_id = await self._create_job_history(job_type, job_name, start_datetime, card_ids)
            if job_history_id:
                await self._mark_job_as_failed(job_history_id, error_msg)
            
            return {"error": error_msg}
        
        start_time = time.time()
        start_datetime = datetime.utcnow()
        processed = 0
        succeeded = 0
        failed = 0
        job_history_id = None
        
        logger.info(
            "metadata_refresh_start",
            job_name=job_name,
            job_type=job_type,
            batch_size=settings.price_refresh_batch_size if not card_ids else len(card_ids),
            timeout_seconds=JOB_TIMEOUT_SECONDS
        )
        
        try:
            # Create job history record first
            job_history_id = await self._create_job_history(job_type, job_name, start_datetime, card_ids)
            
            # Get cards that need metadata updates
            cards_to_update = await self._get_cards_for_refresh_async(card_ids)
            
            if not cards_to_update:
                logger.info("metadata_refresh_no_cards", job_name=job_name)
                return {"processed": 0, "succeeded": 0, "failed": 0, "duration_ms": 0}
            
            # Process cards with rate limiting and timeout protection
            for card in cards_to_update:
                processed += 1
                
                try:
                    # Process single card with timeout
                    success = await asyncio.wait_for(
                        self._process_single_card(card),
                        timeout=CARD_TIMEOUT_SECONDS
                    )
                    
                    if success:
                        succeeded += 1
                    else:
                        failed += 1
                    
                    # Update job history with current progress for real-time SSE updates
                    if job_history_id:
                        await self._update_job_progress(job_history_id, processed, succeeded, failed)
                    
                    # Implement rate limiting (1 second between requests)
                    await asyncio.sleep(1.0)
                
                except asyncio.TimeoutError:
                    failed += 1
                    logger.warning(
                        "metadata_refresh_card_timeout",
                        card_id=card.id,
                        card_name=card.name,
                        timeout_seconds=CARD_TIMEOUT_SECONDS
                    )
                
                except Exception as e:
                    failed += 1
                    logger.error(
                        "metadata_refresh_card_error",
                        card_id=card.id,
                        card_name=card.name,
                        error=str(e),
                        exc_info=True
                    )
                    
                    # Add exponential backoff with jitter for failed requests
                    backoff_time = min(2 ** min(failed, 6), 30) + random.uniform(0, 1)
                    await asyncio.sleep(backoff_time)
        
        except Exception as e:
            logger.error(
                "metadata_refresh_job_error",
                job_name=job_name,
                error=str(e),
                exc_info=True
            )
            return {"error": str(e)}
        
        finally:
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Update job history record
            if job_history_id:
                await self._update_job_history(
                    job_history_id, processed, succeeded, failed, duration_ms
                )
            
            logger.info(
                "metadata_refresh_complete",
                job_name=job_name,
                processed=processed,
                succeeded=succeeded,
                failed=failed,
                duration_ms=duration_ms
            )
        
        return {
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
            "duration_ms": duration_ms
        }
    
    async def _get_cards_for_refresh_async(self, card_ids: Optional[List[int]] = None) -> List[Card]:
        """Get cards that need metadata updates (async version)."""
        try:
            with get_db_session() as session:
                if card_ids:
                    # Refresh specific cards
                    query = (
                        select(Card)
                        .where(Card.id.in_(card_ids))
                    )
                else:
                    # Refresh cards that need metadata updates
                    # Priority: cards without api_id, then cards with old sync dates
                    query = (
                        select(Card)
                        .where(
                            (Card.api_id.is_(None)) |  # Cards without API ID
                            (Card.api_last_synced_at.is_(None)) |  # Never synced
                            (Card.hp.is_(None))  # Missing basic metadata
                        )
                        .order_by(Card.api_last_synced_at.asc().nullsfirst())
                        .limit(settings.price_refresh_batch_size)
                    )
                
                results = session.exec(query).all()
                return results
        except Exception as e:
            logger.error("get_cards_for_metadata_refresh_error", error=str(e), exc_info=True)
            return []

    async def _process_single_card(self, card: Card) -> bool:
        """Process a single card and return success status."""
        try:
            api_card_data = None
            
            # Phase 1: Try direct lookup if we have API ID
            if card.api_id:
                logger.debug(
                    "metadata_direct_lookup",
                    card_id=card.id,
                    card_name=card.name,
                    api_id=card.api_id
                )
                api_card_data = await tcgdx_api.get_card_by_id(card.api_id)
            
            # Phase 2: Search and find best match if no API ID or direct lookup failed
            if not api_card_data:
                logger.debug(
                    "metadata_search_lookup",
                    card_id=card.id,
                    card_name=card.name,
                    set_name=card.set_name,
                    number=card.number
                )
                api_card_data = await tcgdx_api.search_and_find_best_match(
                    card.name, card.set_name, card.number
                )
            
            if not api_card_data:
                logger.warning(
                    "metadata_no_api_data",
                    card_id=card.id,
                    card_name=card.name,
                    set_name=card.set_name,
                    number=card.number
                )
                return False
            
            # Extract normalized card data
            extracted_data = tcgdx_api.extract_card_data(api_card_data)
            
            if not extracted_data:
                logger.warning(
                    "metadata_extraction_failed",
                    card_id=card.id,
                    card_name=card.name
                )
                return False
            
            # Update card with metadata in a separate session
            with get_db_session() as session:
                card_record = session.get(Card, card.id)
                if card_record:
                    # Update all the metadata fields (allow empty lists, 0, etc.)
                    for field, value in extracted_data.items():
                        if hasattr(card_record, field):
                            setattr(card_record, field, value)
                    
                    # Always update the sync timestamp
                    card_record.api_last_synced_at = datetime.utcnow()
                    card_record.updated_at = datetime.utcnow()
                    
                    session.add(card_record)
                    session.commit()
                    
                    logger.info(
                        "metadata_card_updated",
                        card_id=card.id,
                        card_name=card.name,
                        api_id=extracted_data.get("api_id"),
                        hp=extracted_data.get("hp"),
                        types=extracted_data.get("types"),
                        rarity=extracted_data.get("rarity")
                    )
                    return True
                else:
                    logger.error(
                        "metadata_card_not_found",
                        card_id=card.id
                    )
                    return False
                
        except Exception as e:
            logger.error(
                "metadata_process_card_error",
                card_id=card.id,
                card_name=card.name,
                error=str(e),
                exc_info=True
            )
            return False

    async def manual_refresh(self, card_ids: Optional[List[int]] = None) -> dict:
        """Manually trigger a metadata refresh for specific cards or all cards."""
        try:
            # Wrap the manual job in a timeout
            return await asyncio.wait_for(
                self._refresh_metadata_impl("manual", "manual_metadata_refresh", card_ids),
                timeout=JOB_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            logger.error(
                "manual_metadata_refresh_timeout",
                card_ids=card_ids,
                timeout_seconds=JOB_TIMEOUT_SECONDS
            )
            # Mark any running job as failed due to timeout
            await self._mark_running_jobs_as_failed("Manual metadata job timed out")
            return {"error": "Job timed out", "timeout_seconds": JOB_TIMEOUT_SECONDS}
        except Exception as e:
            logger.error(
                "manual_metadata_refresh_unexpected_error",
                card_ids=card_ids,
                error=str(e),
                exc_info=True
            )
            await self._mark_running_jobs_as_failed(f"Manual metadata job error: {str(e)}")
            return {"error": str(e)}

    async def _create_job_history(self, job_type: str, job_name: str, start_datetime: datetime, card_ids: Optional[List[int]] = None) -> int:
        """Create a job history record and return its ID."""
        try:
            with get_db_session() as session:
                job_history = JobHistory(
                    job_type=job_type,
                    job_name=job_name,
                    started_at=start_datetime,
                    status="running",
                    job_metadata={"card_ids": card_ids, "job_category": "metadata"} if card_ids else {"job_category": "metadata"}
                )
                session.add(job_history)
                session.commit()
                session.refresh(job_history)
                return job_history.id
        except Exception as e:
            logger.error("create_metadata_job_history_error", error=str(e), exc_info=True)
            raise

    async def _update_job_progress(self, job_history_id: int, processed: int, succeeded: int, failed: int):
        """Update job history record with current progress for real-time SSE updates."""
        try:
            with get_db_session() as session:
                job_record = session.get(JobHistory, job_history_id)
                if job_record:
                    job_record.processed = processed
                    job_record.succeeded = succeeded
                    job_record.failed = failed
                    session.add(job_record)
                    session.commit()
                    
                    logger.debug(
                        "metadata_job_progress_updated",
                        job_id=job_history_id,
                        processed=processed,
                        succeeded=succeeded,
                        failed=failed
                    )
                else:
                    logger.error("metadata_job_progress_not_found", job_id=job_history_id)
        except Exception as e:
            logger.error("update_metadata_job_progress_error", job_id=job_history_id, error=str(e), exc_info=True)

    async def _update_job_history(self, job_history_id: int, processed: int, succeeded: int, failed: int, duration_ms: int):
        """Update job history record with completion data."""
        try:
            with get_db_session() as session:
                job_record = session.get(JobHistory, job_history_id)
                if job_record:
                    job_record.completed_at = datetime.utcnow()
                    job_record.status = "completed" if failed == 0 else "completed_with_errors"
                    job_record.processed = processed
                    job_record.succeeded = succeeded
                    job_record.failed = failed
                    job_record.duration_ms = duration_ms
                    session.add(job_record)
                    session.commit()
                    
                    logger.info(
                        "metadata_job_history_updated",
                        job_id=job_history_id,
                        status=job_record.status,
                        processed=processed,
                        succeeded=succeeded,
                        failed=failed
                    )
                else:
                    logger.error("metadata_job_history_not_found", job_id=job_history_id)
        except Exception as e:
            logger.error("update_metadata_job_history_error", job_id=job_history_id, error=str(e), exc_info=True)

    async def _mark_job_as_failed(self, job_history_id: int, error_message: str):
        """Mark a specific job as failed."""
        try:
            with get_db_session() as session:
                job_record = session.get(JobHistory, job_history_id)
                if job_record:
                    job_record.status = "failed"
                    job_record.completed_at = datetime.utcnow()
                    job_record.error_message = error_message
                    job_record.processed = 0
                    job_record.succeeded = 0
                    job_record.failed = 0
                    job_record.duration_ms = 0
                    session.add(job_record)
                    session.commit()
                    
                    logger.info(
                        "metadata_job_marked_as_failed",
                        job_id=job_history_id,
                        error_message=error_message
                    )
                else:
                    logger.error("metadata_job_not_found_for_failure", job_id=job_history_id)
        except Exception as e:
            logger.error("mark_metadata_job_as_failed_error", job_id=job_history_id, error=str(e), exc_info=True)

    async def _mark_running_jobs_as_failed(self, error_message: str):
        """Mark any running metadata jobs as failed."""
        try:
            with get_db_session() as session:
                running_jobs = session.exec(
                    select(JobHistory)
                    .where(JobHistory.status == "running")
                    .where(JobHistory.job_name.like("%metadata%"))
                ).all()
                
                for job in running_jobs:
                    job.status = "failed"
                    job.completed_at = datetime.utcnow()
                    job.error_message = error_message
                    session.add(job)
                
                if running_jobs:
                    session.commit()
                    logger.info(
                        "marked_running_metadata_jobs_as_failed",
                        count=len(running_jobs),
                        error_message=error_message
                    )
        except Exception as e:
            logger.error("mark_running_metadata_jobs_failed_error", error=str(e), exc_info=True)


# Global service instance
metadata_refresh_service = MetadataRefreshService()
