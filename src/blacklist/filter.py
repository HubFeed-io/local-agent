"""Blacklist filter for local content filtering before sending to HubFeed."""

import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    """Result of blacklist filtering."""
    data: List[Dict[str, Any]]
    filtered_count: int
    reasons: List[Dict[str, Any]]


class BlacklistFilter:
    """Applies local blacklist rules to filter content before sending to HubFeed."""
    
    def __init__(self, config_manager):
        """Initialize blacklist filter.
        
        Args:
            config_manager: ConfigManager instance
        """
        self.config_manager = config_manager
    
    def filter(self, data: List[Dict[str, Any]], avatar_id: str) -> FilterResult:
        """Apply blacklist rules to data.
        
        Args:
            data: List of items to filter (e.g., Telegram messages)
            avatar_id: Avatar ID for avatar-specific rules
            
        Returns:
            FilterResult with filtered data and metadata
        """
        # Get combined rules for this avatar
        rules = self.config_manager.get_avatar_blacklist(avatar_id)
        
        filtered_data = []
        reasons = []
        
        for i, item in enumerate(data):
            reason = self._check_item(item, rules)
            if reason:
                reasons.append({
                    "index": i,
                    "reason": reason,
                    "item_id": self._get_item_id(item)
                })
                logger.debug(f"Filtered item {i}: {reason}")
            else:
                filtered_data.append(item)
        
        logger.info(
            f"Filtered {len(reasons)} of {len(data)} items for avatar {avatar_id}"
        )
        
        return FilterResult(
            data=filtered_data,
            filtered_count=len(reasons),
            reasons=reasons
        )
    
    def _check_item(self, item: Dict[str, Any], rules: Dict[str, List[str]]) -> Optional[str]:
        """Check if item matches any blacklist rule.
        
        Args:
            item: Item to check
            rules: Blacklist rules
            
        Returns:
            Filter reason or None if item passes
        """
        # Check keywords
        text = self._get_text(item)
        for keyword in rules.get("keywords", []):
            if keyword.lower() in text.lower():
                return f"keyword:{keyword}"
        
        # Check sender
        sender = self._get_sender(item)
        if sender:
            for blocked_sender in rules.get("senders", []):
                if self._match_sender(sender, blocked_sender):
                    return f"sender:{blocked_sender}"
        
        # Check channel
        channel = self._get_channel(item)
        if channel:
            for blocked_channel in rules.get("channels", []):
                if str(channel) == str(blocked_channel):
                    return f"channel:{blocked_channel}"
        
        return None
    
    def _get_text(self, item: Dict[str, Any]) -> str:
        """Extract text content from item.
        
        Supports Telegram message format.
        
        Args:
            item: Item to extract text from
            
        Returns:
            Text content (empty string if none)
        """
        # Telegram message format
        if "message" in item:
            return item.get("message", "") or ""
        
        # Telegram media caption
        if "media" in item and isinstance(item["media"], dict):
            caption = item["media"].get("caption")
            if caption:
                return caption
        
        return ""
    
    def _get_sender(self, item: Dict[str, Any]) -> Optional[str]:
        """Extract sender identifier from item.
        
        Supports Telegram message format.
        
        Args:
            item: Item to extract sender from
            
        Returns:
            Sender identifier or None
        """
        # Telegram message format
        from_id = item.get("from_id")
        if from_id:
            if isinstance(from_id, dict):
                # User ID format: {"_": "PeerUser", "user_id": 123456}
                user_id = from_id.get("user_id")
                if user_id:
                    return str(user_id)
                
                # Channel ID format: {"_": "PeerChannel", "channel_id": 123456}
                channel_id = from_id.get("channel_id")
                if channel_id:
                    return str(channel_id)
            else:
                return str(from_id)
        
        return None
    
    def _get_channel(self, item: Dict[str, Any]) -> Optional[str]:
        """Extract channel identifier from item.
        
        Supports Telegram message format.
        
        Args:
            item: Item to extract channel from
            
        Returns:
            Channel identifier or None
        """
        # Telegram message format
        peer_id = item.get("peer_id")
        if peer_id and isinstance(peer_id, dict):
            # Channel format: {"_": "PeerChannel", "channel_id": 123456}
            channel_id = peer_id.get("channel_id")
            if channel_id:
                return str(channel_id)
            
            # Chat format: {"_": "PeerChat", "chat_id": 123456}
            chat_id = peer_id.get("chat_id")
            if chat_id:
                return str(chat_id)
        
        return None
    
    def _get_item_id(self, item: Dict[str, Any]) -> Optional[str]:
        """Get unique identifier for item (for logging).
        
        Args:
            item: Item to get ID from
            
        Returns:
            Item ID or None
        """
        # Telegram message ID
        msg_id = item.get("id")
        if msg_id:
            return str(msg_id)
        
        return None
    
    def _match_sender(self, sender: str, pattern: str) -> bool:
        """Check if sender matches pattern.
        
        Supports:
        - Exact ID match: "123456"
        - Username match: "@username" or "username"
        
        Args:
            sender: Sender identifier
            pattern: Pattern to match
            
        Returns:
            True if matches
        """
        # Exact match
        if sender == pattern:
            return True
        
        # Username match (with or without @)
        if pattern.startswith("@"):
            # Pattern has @, sender might not
            return sender == pattern[1:] or sender == pattern
        else:
            # Pattern doesn't have @, sender might
            return sender == pattern or sender == f"@{pattern}"
        
        return False
