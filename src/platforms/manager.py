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
            elif platform == 'browser' or self._is_browser_platform(platform):
                from .browser import BrowserHandler
                handler = BrowserHandler(self.config_manager)
                # Load login flows from config
                browser_config = self.config_manager.get_platform_config("browser")
                if browser_config and browser_config.get("login_flows"):
                    handler.update_login_flows(browser_config["login_flows"])
                self._handlers[platform] = handler
                # Also register under 'browser' key for generic access
                if platform != 'browser' and 'browser' not in self._handlers:
                    self._handlers['browser'] = handler
                logger.info(f"Browser handler created for platform: {platform}")
            else:
                logger.warning(f"Unknown platform: {platform}")
                return None
        
        return self._handlers.get(platform)
    
    def _is_browser_platform(self, platform: str) -> bool:
        """Check if a platform is browser-based by looking at loaded config."""
        browser_config = self.config_manager.get_platform_config("browser")
        if browser_config and browser_config.get("login_flows"):
            known_platforms = [f.get("platform") for f in browser_config["login_flows"]]
            return platform in known_platforms
        return False

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
