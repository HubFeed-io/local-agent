"""Platform handlers for different data sources."""

try:
    from platforms.telegram import TelegramHandler
    from platforms.browser import BrowserHandler
    from platforms.manager import PlatformManager
except ImportError:
    from src.platforms.telegram import TelegramHandler
    from src.platforms.browser import BrowserHandler
    from src.platforms.manager import PlatformManager

__all__ = ["TelegramHandler", "BrowserHandler", "PlatformManager"]
