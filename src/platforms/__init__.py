"""Platform handlers for different data sources."""

from src.platforms.telegram import TelegramHandler
from src.platforms.manager import PlatformManager

__all__ = ["TelegramHandler", "PlatformManager"]
