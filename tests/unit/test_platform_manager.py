"""
Unit tests for PlatformManager.

Tests handler creation, caching, browser platform detection, and cleanup.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path

# Add src to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

# Pre-inject mock modules so handler imports don't fail
mock_telethon = MagicMock()
mock_nodriver = MagicMock()
sys.modules.setdefault('telethon', mock_telethon)
sys.modules.setdefault('telethon.sessions', MagicMock())
sys.modules.setdefault('telethon.errors', MagicMock())
sys.modules.setdefault('telethon.tl', MagicMock())
sys.modules.setdefault('telethon.tl.functions', MagicMock())
sys.modules.setdefault('telethon.tl.functions.auth', MagicMock())
sys.modules.setdefault('nodriver', mock_nodriver)

from platforms.manager import PlatformManager


class TestPlatformManagerInit:
    """Test PlatformManager initialization."""

    def test_init_stores_config_manager(self):
        """Should store config_manager reference."""
        config_manager = Mock()
        pm = PlatformManager(config_manager)
        assert pm.config_manager is config_manager

    def test_init_empty_handlers(self):
        """Should start with empty handlers dict."""
        pm = PlatformManager(Mock())
        assert pm._handlers == {}


class TestGetHandler:
    """Test handler creation and caching."""

    @patch("platforms.telegram.TelegramHandler")
    def test_get_telegram_handler(self, MockTelegramHandler):
        """Should create TelegramHandler for 'telegram' platform."""
        config_manager = Mock()
        pm = PlatformManager(config_manager)

        handler = pm.get_handler("telegram")

        MockTelegramHandler.assert_called_once_with(config_manager)
        assert handler is MockTelegramHandler.return_value

    @patch("platforms.telegram.TelegramHandler")
    def test_get_telegram_handler_cached(self, MockTelegramHandler):
        """Should return cached handler on second call."""
        pm = PlatformManager(Mock())

        handler1 = pm.get_handler("telegram")
        handler2 = pm.get_handler("telegram")

        assert handler1 is handler2
        MockTelegramHandler.assert_called_once()

    @patch("platforms.browser.BrowserHandler")
    def test_get_browser_handler(self, MockBrowserHandler):
        """Should create BrowserHandler for 'browser' platform."""
        config_manager = Mock()
        config_manager.get_platform_config.return_value = None
        pm = PlatformManager(config_manager)

        handler = pm.get_handler("browser")

        MockBrowserHandler.assert_called_once_with(config_manager)
        assert handler is MockBrowserHandler.return_value

    @patch("platforms.browser.BrowserHandler")
    def test_get_browser_handler_loads_login_flows(self, MockBrowserHandler):
        """Should load login flows from config when available."""
        config_manager = Mock()
        login_flows = [{"platform": "x", "steps": []}]
        config_manager.get_platform_config.return_value = {"login_flows": login_flows}
        pm = PlatformManager(config_manager)

        pm.get_handler("browser")

        MockBrowserHandler.return_value.update_login_flows.assert_called_once_with(login_flows)

    @patch("platforms.browser.BrowserHandler")
    def test_get_browser_handler_no_login_flows(self, MockBrowserHandler):
        """Should not call update_login_flows when no flows in config."""
        config_manager = Mock()
        config_manager.get_platform_config.return_value = {}
        pm = PlatformManager(config_manager)

        pm.get_handler("browser")

        MockBrowserHandler.return_value.update_login_flows.assert_not_called()

    @patch("platforms.browser.BrowserHandler")
    def test_get_browser_platform_by_name(self, MockBrowserHandler):
        """Should create BrowserHandler when platform is in login_flows config."""
        config_manager = Mock()
        config_manager.get_platform_config.return_value = {
            "login_flows": [{"platform": "x"}]
        }
        pm = PlatformManager(config_manager)

        handler = pm.get_handler("x")

        MockBrowserHandler.assert_called_once_with(config_manager)
        assert handler is MockBrowserHandler.return_value

    @patch("platforms.browser.BrowserHandler")
    def test_get_browser_platform_registers_browser_key(self, MockBrowserHandler):
        """Should also register under 'browser' key for generic access."""
        config_manager = Mock()
        config_manager.get_platform_config.return_value = {
            "login_flows": [{"platform": "x"}]
        }
        pm = PlatformManager(config_manager)

        pm.get_handler("x")

        assert pm._handlers.get("browser") is MockBrowserHandler.return_value

    @patch("platforms.browser.BrowserHandler")
    def test_get_browser_platform_does_not_overwrite_existing_browser(self, MockBrowserHandler):
        """Should not overwrite existing 'browser' handler."""
        config_manager = Mock()
        config_manager.get_platform_config.return_value = {
            "login_flows": [{"platform": "x"}]
        }
        pm = PlatformManager(config_manager)
        existing_handler = Mock()
        pm._handlers["browser"] = existing_handler

        pm.get_handler("x")

        assert pm._handlers["browser"] is existing_handler

    def test_get_unknown_platform_returns_none(self):
        """Should return None for unknown platforms."""
        config_manager = Mock()
        config_manager.get_platform_config.return_value = None
        pm = PlatformManager(config_manager)

        result = pm.get_handler("discord")

        assert result is None

    @patch("platforms.browser.BrowserHandler")
    def test_get_handler_cached_browser_platform(self, MockBrowserHandler):
        """Should return cached handler for browser platforms."""
        config_manager = Mock()
        config_manager.get_platform_config.return_value = {
            "login_flows": [{"platform": "x"}]
        }
        pm = PlatformManager(config_manager)

        handler1 = pm.get_handler("x")
        handler2 = pm.get_handler("x")

        assert handler1 is handler2
        MockBrowserHandler.assert_called_once()


class TestIsBrowserPlatform:
    """Test browser platform detection."""

    def test_returns_true_when_platform_in_flows(self):
        """Should return True when platform found in login_flows."""
        config_manager = Mock()
        config_manager.get_platform_config.return_value = {
            "login_flows": [{"platform": "x"}]
        }
        pm = PlatformManager(config_manager)

        assert pm._is_browser_platform("x") is True

    def test_returns_false_when_platform_not_in_flows(self):
        """Should return False when platform not in login_flows."""
        config_manager = Mock()
        config_manager.get_platform_config.return_value = {
            "login_flows": [{"platform": "x"}]
        }
        pm = PlatformManager(config_manager)

        assert pm._is_browser_platform("facebook") is False

    def test_returns_false_when_no_browser_config(self):
        """Should return False when no browser config exists."""
        config_manager = Mock()
        config_manager.get_platform_config.return_value = None
        pm = PlatformManager(config_manager)

        assert pm._is_browser_platform("x") is False

    def test_returns_false_when_no_login_flows(self):
        """Should return False when config has no login_flows key."""
        config_manager = Mock()
        config_manager.get_platform_config.return_value = {}
        pm = PlatformManager(config_manager)

        assert pm._is_browser_platform("x") is False


class TestDisconnectAll:
    """Test handler cleanup."""

    @pytest.mark.asyncio
    async def test_disconnect_calls_all_handlers(self):
        """Should call disconnect_all on each handler."""
        pm = PlatformManager(Mock())
        handler1 = AsyncMock()
        handler2 = AsyncMock()
        pm._handlers = {"telegram": handler1, "browser": handler2}

        await pm.disconnect_all()

        handler1.disconnect_all.assert_awaited_once()
        handler2.disconnect_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_clears_handlers(self):
        """Should clear handlers dict after disconnect."""
        pm = PlatformManager(Mock())
        pm._handlers = {"telegram": AsyncMock()}

        await pm.disconnect_all()

        assert pm._handlers == {}

    @pytest.mark.asyncio
    async def test_disconnect_handles_exception(self):
        """Should continue disconnecting even if one handler fails."""
        pm = PlatformManager(Mock())
        handler1 = AsyncMock()
        handler1.disconnect_all.side_effect = Exception("connection error")
        handler2 = AsyncMock()
        pm._handlers = {"telegram": handler1, "browser": handler2}

        await pm.disconnect_all()

        handler2.disconnect_all.assert_awaited_once()
        assert pm._handlers == {}

    @pytest.mark.asyncio
    async def test_disconnect_skips_handler_without_method(self):
        """Should skip handlers without disconnect_all method."""
        pm = PlatformManager(Mock())
        handler = Mock(spec=[])  # No attributes
        pm._handlers = {"custom": handler}

        await pm.disconnect_all()

        assert pm._handlers == {}

    @pytest.mark.asyncio
    async def test_disconnect_empty_handlers(self):
        """Should handle empty handlers dict gracefully."""
        pm = PlatformManager(Mock())

        await pm.disconnect_all()

        assert pm._handlers == {}
