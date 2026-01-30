"""HTTP client for communicating with Hubfeed backend API."""

import logging
import os
from typing import List, Dict, Any, Optional
import httpx
from datetime import datetime

try:
    from __version__ import __version__
except ImportError:
    from ..__version__ import __version__

logger = logging.getLogger(__name__)


class HubfeedClient:
    """Client for Hubfeed backend API communication."""
    
    def __init__(self, config_manager):
        """Initialize Hubfeed client.
        
        Args:
            config_manager: ConfigManager instance
        """
        self.config_manager = config_manager
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client.
        
        Returns:
            Configured httpx.AsyncClient
        """
        if self._client is None or self._client.is_closed:
            config = self.config_manager.get_config()
            base_url = os.environ.get("HUBFEED_API_URL", "https://hubfeed.io")
            token = config.get("token")
            
            headers = {
                "User-Agent": f"HubfeedAgent/{__version__}",
                "X-Agent-Version": __version__,
                "X-Agent-Capabilities": "telegram",
            }
            
            if token:
                headers["Authorization"] = f"Bearer {token}"
            
            self._client = httpx.AsyncClient(
                base_url=base_url,
                headers=headers,
                timeout=30.0,
                follow_redirects=True
            )
        
        return self._client
    
    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    async def verify_token(self) -> Dict[str, Any]:
        """Verify agent token and fetch configuration.
        
        Returns:
            Response with config and user info
            
        Raises:
            httpx.HTTPError: If verification fails
        """
        client = await self._get_client()
        
        # Prepare capabilities payload
        capabilities = {
            "version": __version__,
            "platforms": ["telegram"],
            "commands": {
                "telegram": [
                    "telegram.get_messages",
                    "telegram.get_channel_info",
                    "telegram.list_dialogs",
                    "telegram.search_messages"
                ]
            }
        }
        
        try:
            response = await client.post("/api/agent/verify", json={
                "capabilities": capabilities
            })
            response.raise_for_status()
            data = response.json()
            
            # Update local config with received platform config
            if "config" in data:
                self.config_manager.update_config(
                    platform_config=data["config"],
                    verified_at=datetime.utcnow().isoformat() + "Z"
                )
            
            logger.info("Token verified successfully")
            return data
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.error("Token verification failed: Invalid token")
            elif e.response.status_code == 403:
                logger.error("Token verification failed: Token revoked")
            else:
                logger.error(f"Token verification failed: {e}")
            raise
        except httpx.HTTPError as e:
            logger.error(f"Token verification failed: {e}")
            raise
    
    async def sync_avatars(self, avatars: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Sync avatar list with Hubfeed backend.
        
        Args:
            avatars: List of avatar data
            
        Returns:
            Sync response
            
        Raises:
            httpx.HTTPError: If sync fails
        """
        client = await self._get_client()
        
        # Prepare avatar data (exclude sensitive session info)
        sync_data = []
        for avatar in avatars:
            # Get nested metadata from avatar
            avatar_metadata = avatar.get("metadata", {})
            
            # Get sources (allowed channels) - only include essential fields
            sources = avatar.get("sources", {})
            sources_items = []
            for source in sources.get("items", []):
                sources_items.append({
                    "id": source.get("id"),
                    "name": source.get("name"),
                    "type": source.get("type"),
                    "frequency_seconds": source.get("frequency_seconds")
                })
            
            sync_data.append({
                "id": avatar.get("id"),
                "name": avatar.get("name"),
                "platform": avatar.get("platform"),
                "status": avatar.get("status"),
                "metadata": {
                    "phone": avatar.get("phone"),
                    "created_at": avatar.get("created_at"),
                    "last_used_at": avatar.get("last_used_at"),
                    "user_id": avatar_metadata.get("user_id"),  # Telegram user ID
                    "username": avatar_metadata.get("username"),  # Telegram username
                    "sources_enabled": sources.get("enabled", False),
                    "sources": sources_items  # Allowed channels/sources
                }
            })
        
        try:
            response = await client.post("/api/agent/avatars/sync", json={
                "avatars": sync_data
            })
            response.raise_for_status()
            data = response.json()
            
            logger.info(f"Synced {len(sync_data)} avatars with Hubfeed")
            return data
            
        except httpx.HTTPError as e:
            logger.error(f"Avatar sync failed: {e}")
            raise
    
    async def get_tasks(self) -> List[Dict[str, Any]]:
        """Poll for pending tasks from Hubfeed.
        
        Returns:
            List of pending tasks/jobs
            
        Raises:
            httpx.HTTPError: If polling fails
        """
        client = await self._get_client()
        
        try:
            response = await client.get("/api/agent/tasks")
            response.raise_for_status()
            data = response.json()
            
            tasks = data.get("tasks", [])
            if tasks:
                logger.info(f"Received {len(tasks)} tasks from Hubfeed")
            
            # Check for upgrade requirement
            upgrade_required = response.headers.get("X-Upgrade-Required")
            if upgrade_required == "true":
                logger.warning(
                    f"Agent version {__version__} is outdated. Please upgrade."
                )
            
            return tasks
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.error("Authentication failed. Token may be invalid or revoked.")
            else:
                logger.error(f"Task polling failed: {e}")
            raise
        except httpx.HTTPError as e:
            logger.error(f"Task polling failed: {e}")
            raise
    
    async def submit_result(
        self,
        job_id: str,
        avatar_id: str,
        success: bool,
        raw_data: Optional[List[Dict[str, Any]]] = None,
        filtered_count: int = 0,
        error: Optional[Dict[str, str]] = None,
        execution_ms: int = 0
    ) -> Dict[str, Any]:
        """Submit job execution result to Hubfeed.
        
        Args:
            job_id: Job identifier
            avatar_id: Avatar ID that executed the job
            success: Whether execution was successful
            raw_data: Raw data returned (if successful)
            filtered_count: Number of items filtered locally
            error: Error information (if failed)
            execution_ms: Execution time in milliseconds
            
        Returns:
            Submission response
            
        Raises:
            httpx.HTTPError: If submission fails
        """
        client = await self._get_client()
        
        payload = {
            "job_id": job_id,
            "avatar_id": avatar_id,
            "success": success,
            "execution_time_ms": execution_ms
        }
        
        if success and raw_data is not None:
            payload["raw_data"] = raw_data
            payload["filtered_count"] = filtered_count
            payload["items_count"] = len(raw_data)
        
        if error:
            payload["error"] = error
        
        try:
            response = await client.post("/api/agent/results", json=payload)
            response.raise_for_status()
            data = response.json()
            
            logger.info(f"Submitted result for job {job_id}: {success}")
            return data
            
        except httpx.HTTPError as e:
            logger.error(f"Result submission failed for job {job_id}: {e}")
            raise
    
    async def health_check(self) -> bool:
        """Check connectivity to Hubfeed backend.
        
        Returns:
            True if backend is reachable
        """
        try:
            client = await self._get_client()
            response = await client.get("/health", timeout=5.0)
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            return False
