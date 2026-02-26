"""Job executor - dispatches jobs to platform handlers."""

import logging
from typing import Dict, Any, List
from datetime import datetime
import time

try:
    from platforms import TelegramHandler
    from platforms.browser import BrowserHandler
    from blacklist import BlacklistFilter
    from history import HistoryLogger
except ImportError:
    from ..platforms import TelegramHandler
    from ..platforms.browser import BrowserHandler
    from ..blacklist import BlacklistFilter
    from ..history import HistoryLogger

logger = logging.getLogger(__name__)


class JobExecutor:
    """Executes jobs by dispatching to appropriate platform handlers."""
    
    def __init__(self, config_manager, history_logger: HistoryLogger):
        """Initialize job executor.
        
        Args:
            config_manager: ConfigManager instance
            history_logger: HistoryLogger instance
        """
        self.config_manager = config_manager
        self.history_logger = history_logger
        
        # Initialize platform handlers
        self.telegram_handler = TelegramHandler(config_manager)
        self.browser_handler = BrowserHandler(config_manager)

        # Initialize blacklist filter
        self.blacklist_filter = BlacklistFilter(config_manager)
        
        logger.info("Job executor initialized")
    
    async def execute_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single job.
        
        Args:
            job: Job specification from Hubfeed
            
        Returns:
            Execution result with raw_data or error
        """
        job_id = job.get("job_id")
        avatar_id = job.get("avatar_id")
        command = job.get("command")
        params = job.get("params", {})
        
        logger.info(f"Executing job {job_id}: {command} on avatar {avatar_id}")
        
        start_time = time.time()
        result = {
            "job_id": job_id,
            "avatar_id": avatar_id,
            "command": command,
            "success": False,
            "execution_ms": 0,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        try:
            # Dispatch to appropriate platform handler
            if command.startswith("telegram."):
                raw_data = await self.telegram_handler.execute(avatar_id, command, params)
            elif command.startswith("browser."):
                raw_data = await self.browser_handler.execute(avatar_id, command, params)
            else:
                raise ValueError(f"Unknown command platform: {command}")
            
            # Apply local blacklist filtering
            filtered_data, filtered_count = self._apply_blacklist(
                avatar_id, 
                raw_data, 
                command
            )
            
            # Calculate execution time
            execution_ms = int((time.time() - start_time) * 1000)
            
            # Prepare result
            result.update({
                "success": True,
                "raw_data": filtered_data,
                "items_count": len(filtered_data),
                "filtered_count": filtered_count,
                "execution_ms": execution_ms
            })
            
            logger.info(
                f"Job {job_id} completed successfully: "
                f"{len(filtered_data)} items ({filtered_count} filtered) in {execution_ms}ms"
            )
            
        except Exception as e:
            execution_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)
            
            logger.error(f"Job {job_id} failed: {error_msg}", exc_info=True)
            
            result.update({
                "success": False,
                "error": {
                    "type": type(e).__name__,
                    "message": error_msg
                },
                "execution_ms": execution_ms
            })
        
        # Log to history
        await self._log_to_history(job, result)
        
        return result
    
    def _apply_blacklist(
        self, 
        avatar_id: str, 
        raw_data: List[Dict[str, Any]],
        command: str
    ) -> tuple[List[Dict[str, Any]], int]:
        """Apply blacklist filtering to raw data.
        
        Args:
            avatar_id: Avatar identifier
            raw_data: Raw data from platform handler
            command: Command that was executed
            
        Returns:
            Tuple of (filtered_data, filtered_count)
        """
        # Only filter message-like data
        if not command.endswith(("get_messages", "search_messages")):
            return raw_data, 0
        
        # Use BlacklistFilter to filter data
        result = self.blacklist_filter.filter(raw_data, avatar_id)
        
        if result.filtered_count > 0:
            logger.info(f"Blacklist filtered {result.filtered_count} items for avatar {avatar_id}")
        
        return result.data, result.filtered_count
    
    async def _log_to_history(self, job: Dict[str, Any], result: Dict[str, Any]):
        """Log job execution to history.
        
        Args:
            job: Job specification
            result: Execution result
        """
        try:
            await self.history_logger.log_job(
                job_id=job.get("job_id"),
                avatar_id=job.get("avatar_id"),
                command=job.get("command"),
                params=job.get("params", {}),
                success=result.get("success", False),
                items_count=result.get("items_count", 0),
                filtered_count=result.get("filtered_count", 0),
                execution_ms=result.get("execution_ms", 0),
                error=result.get("error")
            )
        except Exception as e:
            logger.warning(f"Failed to log job to history: {e}")
    
    async def cleanup(self):
        """Clean up resources."""
        logger.info("Cleaning up job executor...")

        # Disconnect platform handlers
        try:
            await self.telegram_handler.disconnect_all()
        except Exception as e:
            logger.error(f"Error during Telegram cleanup: {e}")

        try:
            await self.browser_handler.disconnect_all()
        except Exception as e:
            logger.error(f"Error during browser cleanup: {e}")

        logger.info("Job executor cleanup complete")
