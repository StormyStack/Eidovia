"""
Scheduler Service Module
Background ETL tasks and session state refresh using APScheduler.
"""

import logging
import asyncio
import json
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import redis.asyncio as aioredis
from typing import Optional

import config_prod as config

logger = logging.getLogger(__name__)

# ============================================================
# SCHEDULER SERVICE
# ============================================================

class SchedulerService:
    """
    Background job scheduler using APScheduler.
    Manages ETL refresh, session state updates, and periodic maintenance.
    """
    
    def __init__(self):
        """Initialize scheduler."""
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.redis_client: Optional[aioredis.Redis] = None
        self.running = False
    
    async def initialize(self) -> None:
        """
        Initialize scheduler and Redis connection.
        
        Raises:
            RuntimeError: If initialization fails
        """
        try:
            # Initialize scheduler
            self.scheduler = AsyncIOScheduler()
            
            # Initialize Redis connection
            self.redis_client = await aioredis.from_url(
                config.REDIS_URL,
                decode_responses=True,
                retry_on_timeout=True
            )
            
            # Test Redis connection
            await self.redis_client.ping()
            
            logger.info("✅ Scheduler and Redis initialized")
            
        except Exception as e:
            logger.error(f"❌ Scheduler initialization failed: {e}")
            raise RuntimeError(f"Scheduler init error: {e}")
    
    async def start(self) -> None:
        """
        Start background job scheduler.
        
        Raises:
            RuntimeError: If scheduler not initialized
        """
        if not self.scheduler or not self.redis_client:
            raise RuntimeError("Scheduler not initialized. Call initialize() first.")
        
        try:
            # Add background jobs
            self.scheduler.add_job(
                self._etl_refresh_job,
                trigger=IntervalTrigger(seconds=config.ETL_REFRESH_INTERVAL),
                id="etl_refresh",
                name="ETL Refresh Session States",
                replace_existing=True
            )
            
            self.scheduler.start()
            self.running = True
            
            logger.info(
                f"✅ Scheduler started with ETL refresh every {config.ETL_REFRESH_INTERVAL}s"
            )
            
        except Exception as e:
            logger.error(f"❌ Scheduler failed to start: {e}")
            raise RuntimeError(f"Scheduler start error: {e}")
    
    async def stop(self) -> None:
        """Stop scheduler and close Redis connection."""
        if self.scheduler:
            self.scheduler.shutdown()
            self.running = False
        
        if self.redis_client:
            await self.redis_client.close()
        
        logger.info("Scheduler stopped")
    
    async def _etl_refresh_job(self) -> None:
        """
        Background ETL job: refresh active session states.
        Updates user state vectors in Redis based on recent events.
        """
        lock_key = f"{config.REDIS_ETL_LOCK_PREFIX}:job"
        
        try:
            # Acquire distributed lock to prevent concurrent runs
            lock_acquired = await self.redis_client.set(
                lock_key,
                "1",
                ex=config.ETL_LOCK_TTL,
                nx=True  # Only set if not exists
            )
            
            if not lock_acquired:
                logger.debug("ETL job already running (lock held)")
                return
            
            logger.info("🔄 ETL refresh job started")
            
            # Get all active sessions
            pattern = f"{config.REDIS_SESSION_STATE_PREFIX}:*:state"
            cursor = 0
            refreshed_count = 0
            
            while True:
                cursor, keys = await self.redis_client.scan(
                    cursor,
                    match=pattern,
                    count=100
                )
                
                for key in keys:
                    try:
                        state_json = await self.redis_client.get(key)
                        if state_json:
                            state = json.loads(state_json)
                            
                            # Refresh state vector (e.g., decay engagement)
                            refreshed_state = self._compute_state_vector(state)
                            
                            await self.redis_client.setex(
                                key,
                                config.REDIS_TTL_SESSION_STATE,
                                json.dumps(refreshed_state)
                            )
                            
                            refreshed_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to refresh state {key}: {e}")
                
                if cursor == 0:
                    break
            
            logger.info(f"✅ ETL refresh completed: {refreshed_count} sessions")
            
        except Exception as e:
            logger.error(f"❌ ETL refresh failed: {e}")
        finally:
            # Release lock
            await self.redis_client.delete(lock_key)
    
    def _compute_state_vector(self, current_state: dict) -> dict:
        """
        Compute refreshed state vector (8D).
        Updates engagement decay and time metrics.
        
        State vector: [correctness, response_time, difficulty, topic_match,
                       engagement, question_count, error_rate, time_spent]
        
        Args:
            current_state: Current state dictionary
            
        Returns:
            Refreshed state dictionary
        """
        state = current_state.copy()
        
        # Decay engagement over time (exponential decay)
        decay_factor = 0.95
        if "engagement" in state:
            state["engagement"] = float(state["engagement"]) * decay_factor
        
        # Update last_refresh timestamp
        state["last_refresh"] = datetime.utcnow().isoformat()
        
        return state
    
    async def get_job_status(self) -> dict:
        """
        Get scheduler job status.
        
        Returns:
            Status dictionary
        """
        if not self.scheduler:
            return {"status": "not_initialized"}
        
        jobs = self.scheduler.get_jobs()
        return {
            "running": self.running,
            "job_count": len(jobs),
            "jobs": [
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": str(job.next_run_time)
                }
                for job in jobs
            ]
        }


# Global scheduler instance
scheduler = SchedulerService()
