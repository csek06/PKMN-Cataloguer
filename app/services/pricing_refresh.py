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
from app.models import Card, PriceChartingLink, PriceSnapshot, JobHistory
from app.services.pricecharting_scraper import pricecharting_scraper


logger = get_logger("pricing_refresh")

# Job timeout constants
JOB_TIMEOUT_SECONDS = 300  # 5 minutes max per job
CARD_TIMEOUT_SECONDS = 30  # 30 seconds max per card


class PricingRefreshService:
    """Service for scheduled price refreshes."""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.is_running = False
    
    def start(self):
        """Start the scheduler."""
        if not self.is_running:
            # Schedule daily refresh at 3:00 AM local time
            trigger = CronTrigger(
                hour=3,
                minute=0,
                timezone=settings.local_tz
            )
            
            self.scheduler.add_job(
                self.refresh_prices,
                trigger=trigger,
                id="daily_price_refresh",
                name="Daily Price Refresh",
                max_instances=1,
                coalesce=True
            )
            
            self.scheduler.start()
            self.is_running = True
            
            logger.info(
                "pricing_scheduler_started",
                timezone=settings.local_tz,
                batch_size=settings.price_refresh_batch_size,
                requests_per_sec=settings.price_refresh_requests_per_sec
            )
    
    def stop(self):
        """Stop the scheduler."""
        if self.is_running:
            self.scheduler.shutdown()
            self.is_running = False
            logger.info("pricing_scheduler_stopped")
    
    async def refresh_prices(self):
        """Refresh prices for a batch of cards with timeout protection."""
        try:
            # Wrap the entire job in a timeout
            await asyncio.wait_for(
                self._refresh_prices_impl("scheduled", "daily_prices"),
                timeout=JOB_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            logger.error(
                "price_refresh_timeout",
                job_name="daily_prices",
                timeout_seconds=JOB_TIMEOUT_SECONDS
            )
            # Mark any running job as failed due to timeout
            await self._mark_running_jobs_as_failed("Job timed out")
        except Exception as e:
            logger.error(
                "price_refresh_unexpected_error",
                job_name="daily_prices",
                error=str(e),
                exc_info=True
            )
            await self._mark_running_jobs_as_failed(f"Unexpected error: {str(e)}")

    async def _refresh_prices_impl(self, job_type: str, job_name: str, card_ids: Optional[List[int]] = None):
        """Implementation of price refresh with proper error handling."""
        if not pricecharting_scraper.is_available():
            logger.info("price_refresh_skipped", reason="scraper_unavailable")
            return {"error": "PriceCharting scraper not available"}
        
        start_time = time.time()
        start_datetime = datetime.utcnow()
        processed = 0
        succeeded = 0
        failed = 0
        job_history_id = None
        
        logger.info(
            "price_refresh_start",
            job_name=job_name,
            job_type=job_type,
            batch_size=settings.price_refresh_batch_size if not card_ids else len(card_ids),
            timeout_seconds=JOB_TIMEOUT_SECONDS
        )
        
        try:
            # Create job history record first
            job_history_id = await self._create_job_history(job_type, job_name, start_datetime, card_ids)
            
            # Get cards that need price updates
            cards_to_update = await self._get_cards_for_refresh_async(card_ids)
            
            if not cards_to_update:
                logger.info("price_refresh_no_cards", job_name=job_name)
                return {"processed": 0, "succeeded": 0, "failed": 0, "duration_ms": 0}
            
            # Process cards with rate limiting and timeout protection
            for card, pc_link in cards_to_update:
                processed += 1
                
                try:
                    # Process single card with timeout
                    success = await asyncio.wait_for(
                        self._process_single_card(card, pc_link),
                        timeout=CARD_TIMEOUT_SECONDS
                    )
                    
                    if success:
                        succeeded += 1
                    else:
                        failed += 1
                    
                    # Update job history with current progress for real-time SSE updates
                    if job_history_id:
                        await self._update_job_progress(job_history_id, processed, succeeded, failed)
                    
                    # Implement rate limiting
                    if settings.price_refresh_requests_per_sec > 0:
                        delay = 1.0 / settings.price_refresh_requests_per_sec
                        await asyncio.sleep(delay)
                
                except asyncio.TimeoutError:
                    failed += 1
                    logger.warning(
                        "price_refresh_card_timeout",
                        card_id=card.id,
                        card_name=card.name,
                        timeout_seconds=CARD_TIMEOUT_SECONDS
                    )
                
                except Exception as e:
                    failed += 1
                    logger.error(
                        "price_refresh_card_error",
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
                "price_refresh_job_error",
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
                "price_refresh_complete",
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
    
    def _get_cards_for_refresh(self, session: Session) -> List[tuple]:
        """Get cards that need price updates."""
        # Query for cards with PriceCharting links, ordered by last sync time
        query = (
            select(Card, PriceChartingLink)
            .join(PriceChartingLink)
            .order_by(PriceChartingLink.last_synced_at.asc().nullsfirst())
            .limit(settings.price_refresh_batch_size)
        )
        
        results = session.exec(query).all()
        return results
    
    def _cleanup_old_snapshots(self, session: Session, card_id: int):
        """Remove old price snapshots, keeping only the last 365 days."""
        cutoff_date = date.today().replace(year=date.today().year - 1)
        
        old_snapshots = session.exec(
            select(PriceSnapshot)
            .where(PriceSnapshot.card_id == card_id)
            .where(PriceSnapshot.as_of_date < cutoff_date)
        ).all()
        
        for snapshot in old_snapshots:
            session.delete(snapshot)
    
    async def manual_refresh(self, card_ids: Optional[List[int]] = None) -> dict:
        """Manually trigger a price refresh for specific cards or all cards."""
        try:
            # Wrap the manual job in a timeout
            return await asyncio.wait_for(
                self._refresh_prices_impl("manual", "manual_refresh", card_ids),
                timeout=JOB_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            logger.error(
                "manual_price_refresh_timeout",
                card_ids=card_ids,
                timeout_seconds=JOB_TIMEOUT_SECONDS
            )
            # Mark any running job as failed due to timeout
            await self._mark_running_jobs_as_failed("Manual job timed out")
            return {"error": "Job timed out", "timeout_seconds": JOB_TIMEOUT_SECONDS}
        except Exception as e:
            logger.error(
                "manual_price_refresh_unexpected_error",
                card_ids=card_ids,
                error=str(e),
                exc_info=True
            )
            await self._mark_running_jobs_as_failed(f"Manual job error: {str(e)}")
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
                    job_metadata={"card_ids": card_ids} if card_ids else None
                )
                session.add(job_history)
                session.commit()
                session.refresh(job_history)
                return job_history.id
        except Exception as e:
            logger.error("create_job_history_error", error=str(e), exc_info=True)
            raise

    async def _get_cards_for_refresh_async(self, card_ids: Optional[List[int]] = None) -> List[tuple]:
        """Get cards that need price updates (async version)."""
        try:
            with get_db_session() as session:
                if card_ids:
                    # Refresh specific cards
                    query = (
                        select(Card, PriceChartingLink)
                        .join(PriceChartingLink)
                        .where(Card.id.in_(card_ids))
                    )
                else:
                    # Refresh next batch
                    query = (
                        select(Card, PriceChartingLink)
                        .join(PriceChartingLink)
                        .order_by(PriceChartingLink.last_synced_at.asc().nullsfirst())
                        .limit(settings.price_refresh_batch_size)
                    )
                
                results = session.exec(query).all()
                return results
        except Exception as e:
            logger.error("get_cards_for_refresh_error", error=str(e), exc_info=True)
            return []

    async def _process_single_card(self, card: Card, pc_link: PriceChartingLink) -> bool:
        """Process a single card and return success status."""
        try:
            # Use the offers URL if we have a product ID, otherwise build from card data
            if pc_link.pc_product_id:
                pc_url = f"https://www.pricecharting.com/offers?product={pc_link.pc_product_id}"
            else:
                # Build proper URL using card data and scraper's URL building logic
                card_data = {
                    "name": card.name,
                    "set_name": card.set_name,
                    "number": card.number
                }
                pc_url = pricecharting_scraper._build_card_url(card_data)
            
            if not pc_url:
                logger.warning(
                    "process_card_no_url",
                    card_id=card.id,
                    card_name=card.name,
                    set_name=card.set_name
                )
                return False
            
            # Fetch current prices and final URL using scraper
            scrape_result = await pricecharting_scraper.scrape_product_page_with_url(pc_url)
            
            if scrape_result:
                prices = scrape_result.get("pricing_data")
                final_url = scrape_result.get("final_url")
                
                # Save price snapshot and update game URL in a separate session
                with get_db_session() as session:
                    if prices:
                        snapshot = PriceSnapshot(
                            card_id=card.id,
                            as_of_date=date.today(),
                            ungraded_cents=prices.get("ungraded_cents"),
                            psa9_cents=prices.get("psa9_cents"),
                            psa10_cents=prices.get("psa10_cents"),
                            bgs10_cents=prices.get("bgs10_cents"),
                            source="pricecharting"
                        )
                        session.add(snapshot)
                    
                    # Update PriceCharting link with game URL and last synced timestamp
                    pc_link_record = session.get(PriceChartingLink, pc_link.id)
                    if pc_link_record:
                        pc_link_record.last_synced_at = datetime.utcnow()
                        
                        # Update game URL if we got a different URL (redirect from offers to game page)
                        if final_url and final_url != pc_url and "/game/pokemon-" in final_url:
                            pc_link_record.pc_game_url = final_url
                            logger.debug(
                                "process_card_game_url_updated",
                                card_id=card.id,
                                card_name=card.name,
                                original_url=pc_url,
                                game_url=final_url
                            )
                        
                        session.add(pc_link_record)
                    
                    # Clean up old snapshots (keep last 365 days)
                    if prices:
                        self._cleanup_old_snapshots(session, card.id)
                    
                    session.commit()
                
                logger.debug(
                    "process_card_success",
                    card_id=card.id,
                    card_name=card.name,
                    pc_product_id=pc_link.pc_product_id,
                    has_prices=bool(prices),
                    final_url=final_url
                )
                return True
            else:
                logger.warning(
                    "process_card_no_data",
                    card_id=card.id,
                    card_name=card.name,
                    pc_product_id=pc_link.pc_product_id
                )
                return False
                
        except Exception as e:
            logger.error(
                "process_card_error",
                card_id=card.id,
                card_name=card.name,
                error=str(e),
                exc_info=True
            )
            return False

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
                        "job_progress_updated",
                        job_id=job_history_id,
                        processed=processed,
                        succeeded=succeeded,
                        failed=failed
                    )
                else:
                    logger.error("job_progress_not_found", job_id=job_history_id)
        except Exception as e:
            logger.error("update_job_progress_error", job_id=job_history_id, error=str(e), exc_info=True)

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
                        "job_history_updated",
                        job_id=job_history_id,
                        status=job_record.status,
                        processed=processed,
                        succeeded=succeeded,
                        failed=failed
                    )
                else:
                    logger.error("job_history_not_found", job_id=job_history_id)
        except Exception as e:
            logger.error("update_job_history_error", job_id=job_history_id, error=str(e), exc_info=True)

    async def _mark_running_jobs_as_failed(self, error_message: str):
        """Mark any running jobs as failed."""
        try:
            with get_db_session() as session:
                running_jobs = session.exec(
                    select(JobHistory).where(JobHistory.status == "running")
                ).all()
                
                for job in running_jobs:
                    job.status = "failed"
                    job.completed_at = datetime.utcnow()
                    job.error_message = error_message
                    session.add(job)
                
                if running_jobs:
                    session.commit()
                    logger.info(
                        "marked_running_jobs_as_failed",
                        count=len(running_jobs),
                        error_message=error_message
                    )
        except Exception as e:
            logger.error("mark_running_jobs_failed_error", error=str(e), exc_info=True)


# Global service instance
pricing_refresh_service = PricingRefreshService()
