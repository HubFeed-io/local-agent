"""Configuration manager that fetches config from SaaS."""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any

from .storage import JSONStorage

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages agent configuration fetched from SaaS."""
    
    def __init__(self, data_dir: str | Path, history_logger=None):
        """Initialize configuration manager.
        
        Args:
            data_dir: Directory for storing configuration files
            history_logger: Optional HistoryLogger instance for audit logging
        """
        self.data_dir = Path(data_dir)
        self.config_storage = JSONStorage(self.data_dir / "config.json")
        self.avatar_storage = JSONStorage(self.data_dir / "avatars.json")
        self.blacklist_storage = JSONStorage(self.data_dir / "blacklist.json")
        self.history_logger = history_logger
        self._status_dirty = False

        # Initialize default structures
        self._ensure_defaults()
    
    def _ensure_defaults(self):
        """Ensure default data structures exist."""
        # Config defaults
        if not self.config_storage.exists():
            self.config_storage.save({
                "token": None,
                "verified_at": None,
                "platform_config": {}
            })
        
        # Avatar defaults
        if not self.avatar_storage.exists():
            self.avatar_storage.save({
                "avatars": []
            })
        
        # Blacklist defaults
        if not self.blacklist_storage.exists():
            self.blacklist_storage.save({
                "global": {
                    "keywords": [],
                    "senders": [],
                    "channels": []
                },
                "by_avatar": {}
            })
    
    # Config methods
    
    def get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return self.config_storage.load(default={})
    
    def save_config(self, config: Dict[str, Any]) -> bool:
        """Save configuration.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            True if successful
        """
        return self.config_storage.save(config)
    
    def update_config(self, **kwargs) -> bool:
        """Update specific config fields.
        
        Args:
            **kwargs: Fields to update
            
        Returns:
            True if successful
        """
        def updater(data):
            data.update(kwargs)
            return data
        
        success = self.config_storage.update(updater)
        
        # Log audit event
        if success and self.history_logger:
            self.history_logger.log_system_event(
                action="updated",
                resource_type="config",
                resource_id="system",
                details={"updates": list(kwargs.keys())}
            )
        
        return success
    
    def is_configured(self) -> bool:
        """Check if agent is configured with token."""
        config = self.get_config()
        return bool(config.get("token"))
    
    def is_verified(self) -> bool:
        """Check if token has been verified recently (within 24h)."""
        config = self.get_config()
        verified_at = config.get("verified_at")

        if not verified_at:
            return False
        
        try:
            verified_time = datetime.fromisoformat(verified_at.replace('Z', '+00:00'))
            return datetime.now(timezone.utc) - verified_time < timedelta(hours=24)
        except (ValueError, TypeError):
            return False
    
    def get_platform_config(self, platform: str = "telegram") -> Dict[str, Any]:
        """Get platform-specific configuration.
        
        Args:
            platform: Platform name
            
        Returns:
            Platform configuration dictionary
        """
        config = self.get_config()
        return config.get("platform_config", {}).get(platform, {})
    
    def get_polling_interval(self) -> int:
        """Get polling interval in seconds (default: 30)."""
        config = self.get_config()
        return config.get("platform_config", {}).get("polling_interval_seconds", 30)
    
    # Avatar methods
    
    def get_avatars(self) -> list:
        """Get all avatars."""
        data = self.avatar_storage.load(default={"avatars": []})
        return data.get("avatars", [])
    
    def get_avatar(self, avatar_id: str) -> Optional[Dict[str, Any]]:
        """Get specific avatar by ID.
        
        Args:
            avatar_id: Avatar identifier
            
        Returns:
            Avatar data or None
        """
        avatars = self.get_avatars()
        for avatar in avatars:
            if avatar.get("id") == avatar_id:
                return avatar
        return None
    
    def save_avatar(self, avatar: Dict[str, Any]) -> bool:
        """Save or update an avatar.
        
        Args:
            avatar: Avatar data (must include 'id' field)
            
        Returns:
            True if successful
        """
        avatar_id = avatar.get("id")
        if not avatar_id:
            logger.error("Avatar must have an 'id' field")
            return False
        
        # Check if this is an update or create
        existing = self.get_avatar(avatar_id)
        is_update = existing is not None
        
        def updater(data):
            avatars = data.get("avatars", [])
            
            # Update existing or append new
            found = False
            for i, existing in enumerate(avatars):
                if existing.get("id") == avatar_id:
                    avatars[i] = avatar
                    found = True
                    break
            
            if not found:
                avatars.append(avatar)
            
            data["avatars"] = avatars
            return data
        
        success = self.avatar_storage.update(updater)
        
        # Log audit event
        if success and self.history_logger:
            action = "updated" if is_update else "created"
            self.history_logger.log_avatar_event(
                action=action,
                avatar_id=avatar_id,
                details={
                    "name": avatar.get("name"),
                    "platform": avatar.get("platform"),
                    "status": avatar.get("status")
                }
            )
        
        return success
    
    def delete_avatar(self, avatar_id: str) -> bool:
        """Delete an avatar.
        
        Args:
            avatar_id: Avatar identifier
            
        Returns:
            True if successful
        """
        # Get avatar info before deletion for audit log
        avatar = self.get_avatar(avatar_id)
        
        def updater(data):
            avatars = data.get("avatars", [])
            data["avatars"] = [a for a in avatars if a.get("id") != avatar_id]
            return data
        
        success = self.avatar_storage.update(updater)
        
        # Log audit event
        if success and self.history_logger and avatar:
            self.history_logger.log_avatar_event(
                action="deleted",
                avatar_id=avatar_id,
                details={
                    "name": avatar.get("name"),
                    "platform": avatar.get("platform")
                }
            )
        
        return success
    
    def get_auth_failure_status(self, avatar_id: str) -> str:
        """Return the appropriate status after an auth failure.

        active → auth_required (backend will retry with a new job)
        auth_required → failed_reauth (backend stops retrying)
        """
        avatar = self.get_avatar(avatar_id)
        if avatar and avatar.get("status") == "auth_required":
            return "failed_reauth"
        return "auth_required"

    def update_avatar_status(self, avatar_id: str, status: str) -> bool:
        """Update avatar status.
        
        Args:
            avatar_id: Avatar identifier
            status: New status (active, inactive, auth_required)
            
        Returns:
            True if successful
        """
        avatar = self.get_avatar(avatar_id)
        if not avatar:
            return False
        
        old_status = avatar.get("status")
        avatar["status"] = status
        avatar["last_used_at"] = datetime.utcnow().isoformat() + "Z"
        success = self.save_avatar(avatar)

        # Mark dirty for immediate sync if status actually changed
        if success and old_status != status:
            self._status_dirty = True

        # Log audit event (in addition to the save_avatar log)
        if success and self.history_logger:
            self.history_logger.log_avatar_event(
                action="status_changed",
                avatar_id=avatar_id,
                details={
                    "old_status": old_status,
                    "new_status": status
                }
            )
        
        return success

    def consume_status_dirty(self) -> bool:
        """Check and reset the status dirty flag.

        Returns:
            True if any avatar status changed since last check
        """
        dirty = self._status_dirty
        self._status_dirty = False
        return dirty

    # Blacklist methods
    
    def get_blacklist(self) -> Dict[str, Any]:
        """Get complete blacklist configuration."""
        return self.blacklist_storage.load(default={
            "global": {"keywords": [], "senders": [], "channels": []},
            "by_avatar": {}
        })
    
    def save_blacklist(self, blacklist: Dict[str, Any]) -> bool:
        """Save blacklist configuration.
        
        Args:
            blacklist: Blacklist configuration
            
        Returns:
            True if successful
        """
        return self.blacklist_storage.save(blacklist)
    
    def get_avatar_blacklist(self, avatar_id: str) -> Dict[str, list]:
        """Get blacklist rules for specific avatar (merged with global).
        
        Args:
            avatar_id: Avatar identifier
            
        Returns:
            Combined blacklist rules
        """
        blacklist = self.get_blacklist()
        global_rules = blacklist.get("global", {})
        avatar_rules = blacklist.get("by_avatar", {}).get(avatar_id, {})
        
        # Merge global and avatar-specific rules
        return {
            "keywords": list(set(
                global_rules.get("keywords", []) + 
                avatar_rules.get("keywords", [])
            )),
            "senders": list(set(
                global_rules.get("senders", []) + 
                avatar_rules.get("senders", [])
            )),
            "channels": list(set(
                global_rules.get("channels", []) + 
                avatar_rules.get("channels", [])
            ))
        }
    
    # Source whitelist methods
    
    # Frequency presets in seconds
    FREQUENCY_PRESETS = {
        "5min": 300,
        "10min": 600,
        "15min": 900,
        "30min": 1800,
        "1h": 3600,
        "2h": 7200,
        "4h": 14400,
        "6h": 21600,
        "12h": 43200,
        "24h": 86400
    }
    DEFAULT_FREQUENCY = 300  # 5 minutes
    
    def get_avatar_sources(self, avatar_id: str) -> Dict[str, Any]:
        """Get sources configuration for an avatar.
        
        Args:
            avatar_id: Avatar identifier
            
        Returns:
            Sources configuration with 'enabled' and 'items' keys
        """
        avatar = self.get_avatar(avatar_id)
        if not avatar:
            return {"enabled": False, "items": []}
        
        return avatar.get("sources", {"enabled": False, "items": []})
    
    def save_avatar_sources(self, avatar_id: str, sources: Dict[str, Any]) -> bool:
        """Save sources configuration for an avatar.
        
        Args:
            avatar_id: Avatar identifier
            sources: Sources configuration with 'enabled' and 'items' keys
            
        Returns:
            True if successful
        """
        avatar = self.get_avatar(avatar_id)
        if not avatar:
            logger.error(f"Avatar not found: {avatar_id}")
            return False
        
        avatar["sources"] = sources
        return self.save_avatar(avatar)
    
    def add_source(self, avatar_id: str, source: Dict[str, Any]) -> bool:
        """Add a source to an avatar's whitelist.
        
        Args:
            avatar_id: Avatar identifier
            source: Source data (id, name, type, frequency_seconds)
            
        Returns:
            True if successful
        """
        sources = self.get_avatar_sources(avatar_id)
        items = sources.get("items", [])
        
        # Check if source already exists
        source_id = source.get("id")
        for existing in items:
            if existing.get("id") == source_id:
                logger.warning(f"Source already exists: {source_id}")
                return False
        
        # Add default values
        new_source = {
            "id": source.get("id"),
            "name": source.get("name", ""),
            "type": source.get("type", "channel"),
            "frequency_seconds": source.get("frequency_seconds", self.DEFAULT_FREQUENCY),
            "last_checked_at": None,
            "last_message_id": None
        }
        if source.get("username"):
            new_source["username"] = source["username"]
        
        items.append(new_source)
        sources["items"] = items
        sources["enabled"] = True  # Enable sources when first one is added
        
        success = self.save_avatar_sources(avatar_id, sources)
        
        # Log audit event
        if success and self.history_logger:
            self.history_logger.log_channel_event(
                action="added",
                channel_id=source_id,
                avatar_id=avatar_id,
                details={
                    "name": new_source.get("name"),
                    "type": new_source.get("type"),
                    "frequency_seconds": new_source.get("frequency_seconds")
                }
            )
        
        return success
    
    def remove_source(self, avatar_id: str, source_id: str) -> bool:
        """Remove a source from an avatar's whitelist.
        
        Args:
            avatar_id: Avatar identifier
            source_id: Source identifier to remove
            
        Returns:
            True if successful
        """
        sources = self.get_avatar_sources(avatar_id)
        items = sources.get("items", [])
        
        # Find source info before removal for audit log
        source_info = None
        for s in items:
            if s.get("id") == source_id:
                source_info = s
                break
        
        sources["items"] = [s for s in items if s.get("id") != source_id]
        
        success = self.save_avatar_sources(avatar_id, sources)
        
        # Log audit event
        if success and self.history_logger and source_info:
            self.history_logger.log_channel_event(
                action="removed",
                channel_id=source_id,
                avatar_id=avatar_id,
                details={
                    "name": source_info.get("name"),
                    "type": source_info.get("type")
                }
            )
        
        return success
    
    def update_source(self, avatar_id: str, source_id: str, updates: Dict[str, Any]) -> bool:
        """Update a source's settings.
        
        Args:
            avatar_id: Avatar identifier
            source_id: Source identifier
            updates: Fields to update (e.g., frequency_seconds)
            
        Returns:
            True if successful
        """
        sources = self.get_avatar_sources(avatar_id)
        items = sources.get("items", [])
        
        for source in items:
            if source.get("id") == source_id:
                source.update(updates)
                success = self.save_avatar_sources(avatar_id, sources)
                
                # Log audit event
                if success and self.history_logger:
                    self.history_logger.log_channel_event(
                        action="updated",
                        channel_id=source_id,
                        avatar_id=avatar_id,
                        details={
                            "updates": updates,
                            "name": source.get("name")
                        }
                    )
                
                return success
        
        logger.error(f"Source not found: {source_id}")
        return False
    
    def update_source_last_checked(self, avatar_id: str, source_id: str, 
                                    last_checked_at: str, last_message_id: Optional[int] = None) -> bool:
        """Update a source's last checked timestamp and message ID.
        
        Args:
            avatar_id: Avatar identifier
            source_id: Source identifier
            last_checked_at: ISO timestamp of last check
            last_message_id: ID of last message seen (optional)
            
        Returns:
            True if successful
        """
        updates = {"last_checked_at": last_checked_at}
        if last_message_id is not None:
            updates["last_message_id"] = last_message_id
        
        return self.update_source(avatar_id, source_id, updates)
    
    def get_sources_due_for_check(self, avatar_id: str) -> list:
        """Get sources that are due for checking based on their frequency.
        
        Args:
            avatar_id: Avatar identifier
            
        Returns:
            List of sources that need to be checked
        """
        sources = self.get_avatar_sources(avatar_id)
        
        if not sources.get("enabled", False):
            return []
        
        due_sources = []
        now = datetime.now(timezone.utc)
        
        for source in sources.get("items", []):
            last_checked = source.get("last_checked_at")
            frequency = source.get("frequency_seconds", self.DEFAULT_FREQUENCY)
            
            if not last_checked:
                # Never checked, it's due
                due_sources.append(source)
            else:
                try:
                    last_time = datetime.fromisoformat(last_checked.replace('Z', '+00:00'))
                    if (now - last_time).total_seconds() >= frequency:
                        due_sources.append(source)
                except (ValueError, TypeError):
                    # Invalid timestamp, consider it due
                    due_sources.append(source)
        
        return due_sources
