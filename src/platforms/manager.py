"""Platform Manager - Manages platform-specific handlers."""

import logging
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class PlatformManager:
    """Manages platform-specific handlers (Telegram, Discord, etc.)."""
    
    def __init__(self, config_manager):
        """Initialize Platform Manager.
        
        Args:
            config_manager: ConfigManager instance
        """
        self.config_manager = config_manager
        self._handlers: Dict[str, Any] = {}
        logger.info("Platform Manager initialized")
    
    def get_handler(self, platform: str) -> Optional[Any]:
        """Get or create handler for a platform.
        
        Args:
            platform: Platform name (e.g., 'telegram', 'discord')
            
        Returns:
            Platform handler instance or None if platform not supported
        """
        # Create handler if it doesn't exist
        if platform not in self._handlers:
            if platform == 'telegram':
                from .telegram import TelegramHandler
                self._handlers[platform] = TelegramHandler(self.config_manager)
                logger.info("Telegram handler created")
            elif platform == 'discord':
                # Future: Discord handler
                logger.warning(f"Discord platform not yet implemented")
                return None
            # Add more platforms here as needed
            else:
                logger.warning(f"Unknown platform: {platform}")
                return None
        
        return self._handlers.get(platform)
    
    async def disconnect_all(self):
        """Disconnect all platform handlers."""
        logger.info("Disconnecting all platform handlers...")
        
        for platform, handler in list(self._handlers.items()):
            try:
                if hasattr(handler, 'disconnect_all'):
                    await handler.disconnect_all()
                    logger.info(f"Disconnected {platform} handler")
            except Exception as e:
                logger.error(f"Error disconnecting {platform} handler: {e}")
        
        self._handlers.clear()
        logger.info("All platform handlers disconnected")
