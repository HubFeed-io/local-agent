"""Main polling loop for agent-Hubfeed communication."""

import logging
import asyncio
from typing import Optional
from datetime import datetime

from .hubfeed_client import HubfeedClient
from .executor import JobExecutor

try:
    from config import ConfigManager
    from history import HistoryLogger
except ImportError:
    from ..config import ConfigManager
    from ..history import HistoryLogger

logger = logging.getLogger(__name__)


class AgentLoop:
    """Main agent polling loop."""
    
    def __init__(
        self,
        config_manager: ConfigManager,
        hubfeed_client: HubfeedClient,
        executor: JobExecutor
    ):
        """Initialize agent loop.
        
        Args:
            config_manager: ConfigManager instance
            hubfeed_client: HubfeedClient instance
            executor: JobExecutor instance
        """
        self.config_manager = config_manager
        self.hubfeed_client = hubfeed_client
        self.executor = executor
        
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._verified = False
        self._last_avatar_sync: Optional[datetime] = None
        
        logger.info("Agent loop initialized")
    
    async def start(self):
        """Start the polling loop."""
        if self._running:
            logger.warning("Loop already running")
            return
        
        logger.info("Starting agent polling loop...")
        self._running = True
        self._task = asyncio.create_task(self._run())
    
    async def stop(self):
        """Stop the polling loop."""
        if not self._running:
            return
        
        logger.info("Stopping agent polling loop...")
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        # Cleanup
        await self.executor.cleanup()
        await self.hubfeed_client.close()
        
        logger.info("Agent polling loop stopped")
    
    async def _run(self):
        """Main polling loop."""
        try:
            # Initial verification
            if not await self._verify_token():
                logger.error("Token verification failed. Agent will not poll.")
                self._running = False
                return
            
            # Initial avatar sync
            await self._sync_avatars()
            
            # Main loop
            while self._running:
                try:
                    await self._poll_cycle()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in poll cycle: {e}", exc_info=True)
                
                # Wait before next poll
                await self._wait_for_next_poll()
            
        except asyncio.CancelledError:
            logger.info("Polling loop cancelled")
        except Exception as e:
            logger.error(f"Fatal error in polling loop: {e}", exc_info=True)
            self._running = False
    
    async def _verify_token(self) -> bool:
        """Verify token with Hubfeed backend.
        
        Returns:
            True if verification successful
        """
        if not self.config_manager.is_configured():
            logger.warning("Agent not configured. Please set Hubfeed URL and token.")
            return False
        
        try:
            logger.info("Verifying token with Hubfeed...")
            result = await self.hubfeed_client.verify_token()
            
            self._verified = True
            logger.info(f"Token verified successfully for user: {result.get('user', {}).get('email')}")
            return True
            
        except Exception as e:
            logger.error(f"Token verification failed: {e}")
            self._verified = False
            return False
    
    async def _sync_avatars(self):
        """Sync avatars with Hubfeed backend."""
        try:
            avatars = self.config_manager.get_avatars()
            
            if not avatars:
                logger.info("No avatars to sync")
                return
            
            logger.info(f"Syncing {len(avatars)} avatars...")
            await self.hubfeed_client.sync_avatars(avatars)
            
            self._last_avatar_sync = datetime.utcnow()
            logger.info("Avatars synced successfully")
            
        except Exception as e:
            logger.error(f"Avatar sync failed: {e}")
    
    async def _poll_cycle(self):
        """Execute one poll cycle."""
        # Re-verify token periodically (every hour or if not verified)
        if not self._verified or not self.config_manager.is_verified():
            if not await self._verify_token():
                return
        
        # Sync avatars periodically (every 5 minutes)
        if self._should_sync_avatars():
            await self._sync_avatars()
        
        # Poll for tasks
        try:
            tasks = await self.hubfeed_client.get_tasks()
            
            if not tasks:
                logger.debug("No pending tasks")
                return
            
            logger.info(f"Received {len(tasks)} task(s)")
            
            # Execute tasks sequentially
            for task in tasks:
                if not self._running:
                    break
                
                result = await self.executor.execute_job(task)
                
                # Submit result back to Hubfeed
                try:
                    await self.hubfeed_client.submit_result(
                        job_id=result["job_id"],
                        avatar_id=result["avatar_id"],
                        success=result["success"],
                        raw_data=result.get("raw_data"),
                        filtered_count=result.get("filtered_count", 0),
                        error=result.get("error"),
                        execution_ms=result["execution_ms"]
                    )
                except Exception as e:
                    logger.error(f"Failed to submit result for job {result['job_id']}: {e}")
        
        except Exception as e:
            logger.error(f"Error polling for tasks: {e}")
    
    def _should_sync_avatars(self) -> bool:
        """Check if avatars should be synced.
        
        Returns:
            True if sync is needed
        """
        if self._last_avatar_sync is None:
            return True
        
        # Sync every 5 minutes
        elapsed = (datetime.utcnow() - self._last_avatar_sync).total_seconds()
        return elapsed > 300  # 5 minutes
    
    async def _wait_for_next_poll(self):
        """Wait for next poll interval."""
        interval = self.config_manager.get_polling_interval()
        
        logger.debug(f"Waiting {interval}s before next poll")
        await asyncio.sleep(interval)
    
    @property
    def is_running(self) -> bool:
        """Check if loop is running."""
        return self._running
    
    @property
    def is_verified(self) -> bool:
        """Check if token is verified."""
        return self._verified
    
    async def health_check(self) -> dict:
        """Get loop health status.
        
        Returns:
            Health status dictionary
        """
        hubfeed_reachable = await self.hubfeed_client.health_check()
        
        return {
            "running": self._running,
            "verified": self._verified,
            "hubfeed_reachable": hubfeed_reachable,
            "configured": self.config_manager.is_configured(),
            "last_avatar_sync": self._last_avatar_sync.isoformat() + "Z" if self._last_avatar_sync else None
        }
