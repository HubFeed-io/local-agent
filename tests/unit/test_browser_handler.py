"""
Unit tests for BrowserHandler and BrowserSession.

Tests session management, login flows, auth, command dispatch, and cleanup.
Uses sys.modules injection to mock nodriver.
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from pathlib import Path

# Add src to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

# Pre-inject mock nodriver modules before importing
sys.modules.setdefault('nodriver', MagicMock())
sys.modules.setdefault('nodriver.cdp', MagicMock())

from platforms.browser import BrowserHandler, BrowserSession, PLATFORM_CSRF_COOKIES


MOCK_LOGIN_FLOW = {
    "platform": "x",
    "display_name": "X (Twitter)",
    "login_url": "https://x.com/login",
    "success_url_pattern": "x.com/home",
    "credential_fields": ["username", "password"],
    "steps": [
        {"id": "username", "type": "input", "selector": "input[name='text']",
         "credential_field": "username", "press_enter": True, "wait_seconds": 2},
        {"id": "password", "type": "input", "selector": "input[name='password']",
         "credential_field": "password", "press_enter": True, "wait_seconds": 3},
    ]
}


@pytest.fixture
def mock_config_manager(tmp_path):
    """ConfigManager mock for browser tests."""
    manager = Mock()
    manager.data_dir = str(tmp_path)
    manager.get_avatar.return_value = {
        "id": "x_user1",
        "platform": "x",
        "credentials": {"username": "user", "password": "pass"},
        "status": "active",
        "metadata": {"profile_dir": "x_user1"}
    }
    manager.save_avatar = Mock(return_value=True)
    manager.update_avatar_status = Mock(return_value=True)
    manager.history_logger = Mock()
    return manager


@pytest.fixture
def browser_handler(mock_config_manager):
    """BrowserHandler with mock config and login flows."""
    handler = BrowserHandler(mock_config_manager)
    handler._login_flows = {"x": MOCK_LOGIN_FLOW}
    return handler


class TestBrowserSessionInit:
    """Test BrowserSession initialization."""

    def test_stores_attributes(self, tmp_path):
        """Should store all constructor parameters."""
        session = BrowserSession("av1", "x", tmp_path / "profile", MOCK_LOGIN_FLOW)
        assert session.avatar_id == "av1"
        assert session.platform == "x"
        assert session.profile_path == tmp_path / "profile"
        assert session.login_flow is MOCK_LOGIN_FLOW

    def test_initial_browser_and_tab_are_none(self, tmp_path):
        """Should have browser and tab as None initially."""
        session = BrowserSession("av1", "x", tmp_path / "profile", MOCK_LOGIN_FLOW)
        assert session._browser is None
        assert session._tab is None


class TestBrowserSessionIsAlive:
    """Test BrowserSession.is_alive method."""

    def test_returns_false_when_browser_none(self, tmp_path):
        """Should return False when browser not launched."""
        session = BrowserSession("av1", "x", tmp_path, MOCK_LOGIN_FLOW)
        assert session.is_alive() is False

    def test_returns_false_when_tab_none(self, tmp_path):
        """Should return False when tab is None."""
        session = BrowserSession("av1", "x", tmp_path, MOCK_LOGIN_FLOW)
        session._browser = Mock()
        session._tab = None
        assert session.is_alive() is False

    def test_returns_false_when_process_exited(self, tmp_path):
        """Should return False when browser process has exited."""
        session = BrowserSession("av1", "x", tmp_path, MOCK_LOGIN_FLOW)
        session._browser = Mock()
        session._browser._process = Mock()
        session._browser._process.returncode = 1  # Exited
        session._tab = Mock()
        assert session.is_alive() is False

    def test_returns_true_when_running(self, tmp_path):
        """Should return True when browser is running."""
        session = BrowserSession("av1", "x", tmp_path, MOCK_LOGIN_FLOW)
        session._browser = Mock()
        session._browser._process = Mock()
        session._browser._process.returncode = None  # Still running
        session._tab = Mock()
        assert session.is_alive() is True


class TestBrowserSessionClose:
    """Test BrowserSession.close method."""

    @pytest.mark.asyncio
    async def test_close_stops_browser(self, tmp_path):
        """Should stop browser on close."""
        session = BrowserSession("av1", "x", tmp_path, MOCK_LOGIN_FLOW)
        mock_browser = Mock()
        session._browser = mock_browser
        session._tab = Mock()

        await session.close()

        mock_browser.stop.assert_called_once()
        assert session._browser is None
        assert session._tab is None

    @pytest.mark.asyncio
    async def test_close_handles_exception(self, tmp_path):
        """Should handle stop() exception gracefully."""
        session = BrowserSession("av1", "x", tmp_path, MOCK_LOGIN_FLOW)
        mock_browser = Mock()
        mock_browser.stop.side_effect = Exception("Already closed")
        session._browser = mock_browser

        await session.close()

        assert session._browser is None

    @pytest.mark.asyncio
    async def test_close_when_no_browser(self, tmp_path):
        """Should handle close when browser was never launched."""
        session = BrowserSession("av1", "x", tmp_path, MOCK_LOGIN_FLOW)
        await session.close()  # Should not raise


class TestBrowserHandlerInit:
    """Test BrowserHandler initialization."""

    def test_creates_profiles_dir(self, mock_config_manager, tmp_path):
        """Should create browser profiles directory."""
        handler = BrowserHandler(mock_config_manager)
        profiles_dir = Path(mock_config_manager.data_dir) / "browser_profiles"
        assert profiles_dir.exists()

    def test_stores_config_manager(self, mock_config_manager):
        """Should store config_manager reference."""
        handler = BrowserHandler(mock_config_manager)
        assert handler.config_manager is mock_config_manager

    def test_empty_sessions_and_flows(self, mock_config_manager):
        """Should start with empty sessions and flows."""
        handler = BrowserHandler(mock_config_manager)
        assert handler._sessions == {}
        assert handler._login_flows == {}
        assert handler._pending_auth == {}


class TestUpdateLoginFlows:
    """Test update_login_flows method."""

    def test_update_from_dict_list(self, browser_handler):
        """Should accept list of dict flows."""
        flows = [
            {"platform": "x", "display_name": "X", "steps": []},
            {"platform": "reddit", "display_name": "Reddit", "steps": []}
        ]
        browser_handler.update_login_flows(flows)
        assert "x" in browser_handler._login_flows
        assert "reddit" in browser_handler._login_flows

    def test_update_from_pydantic_models(self, browser_handler):
        """Should accept pydantic model-like objects."""
        mock_flow = Mock()
        mock_flow.model_dump.return_value = {"platform": "x", "display_name": "X"}
        browser_handler.update_login_flows([mock_flow])
        assert "x" in browser_handler._login_flows

    def test_overwrites_previous_flows(self, browser_handler):
        """Should clear previous flows on update."""
        browser_handler._login_flows = {"old_platform": {}}
        browser_handler.update_login_flows([{"platform": "new", "steps": []}])
        assert "old_platform" not in browser_handler._login_flows
        assert "new" in browser_handler._login_flows


class TestGetAvailablePlatforms:
    """Test get_available_platforms method."""

    def test_returns_platform_list(self, browser_handler):
        """Should return list of available platforms."""
        platforms = browser_handler.get_available_platforms()
        assert len(platforms) == 1
        assert platforms[0]["platform"] == "x"
        assert platforms[0]["display_name"] == "X (Twitter)"

    def test_returns_empty_when_no_flows(self, mock_config_manager):
        """Should return empty list when no flows configured."""
        handler = BrowserHandler(mock_config_manager)
        assert handler.get_available_platforms() == []


class TestGetPendingChallenge:
    """Test get_pending_challenge method."""

    def test_returns_challenge_when_pending(self, browser_handler):
        """Should return challenge info when pending."""
        challenge = {"challenge_prompt": "Enter 2FA code", "step_id": "2fa"}
        browser_handler._pending_auth["av1"] = {
            "session": Mock(),
            "challenge": challenge
        }
        result = browser_handler.get_pending_challenge("av1")
        assert result == challenge

    def test_returns_none_when_no_pending(self, browser_handler):
        """Should return None when no pending challenge."""
        result = browser_handler.get_pending_challenge("nonexistent")
        assert result is None


class TestBrowserHandlerExecute:
    """Test execute command dispatch."""

    @pytest.mark.asyncio
    async def test_dispatches_xhr_capture(self, browser_handler):
        """Should route browser.xhr_capture to _xhr_capture."""
        mock_session = AsyncMock()
        mock_session.capture_xhr = AsyncMock(return_value=[{"url": "test"}])
        browser_handler._get_session = AsyncMock(return_value=mock_session)

        result = await browser_handler.execute("av1", "browser.xhr_capture", {
            "navigate_url": "https://x.com/home",
            "xhr_targets": ["api/timeline"]
        })

        mock_session.capture_xhr.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_for_unknown_command(self, browser_handler):
        """Should raise ValueError for unknown commands."""
        browser_handler._get_session = AsyncMock(return_value=AsyncMock())
        with pytest.raises(ValueError, match="Unknown browser command"):
            await browser_handler.execute("av1", "browser.unknown", {})


class TestXhrCapture:
    """Test _xhr_capture parameter validation."""

    @pytest.mark.asyncio
    async def test_raises_when_missing_navigate_url(self, browser_handler):
        """Should raise when navigate_url is missing."""
        mock_session = Mock()
        with pytest.raises(ValueError, match="navigate_url and xhr_targets are required"):
            await browser_handler._xhr_capture(mock_session, {"xhr_targets": ["test"]})

    @pytest.mark.asyncio
    async def test_raises_when_missing_xhr_targets(self, browser_handler):
        """Should raise when xhr_targets is empty."""
        mock_session = Mock()
        with pytest.raises(ValueError, match="navigate_url and xhr_targets are required"):
            await browser_handler._xhr_capture(mock_session, {"navigate_url": "https://test.com"})


class TestGetSession:
    """Test _get_session method."""

    @pytest.mark.asyncio
    async def test_raises_when_challenge_pending(self, browser_handler):
        """Should raise when a challenge is pending."""
        browser_handler._pending_auth["av1"] = {"session": Mock(), "challenge": {}}
        with pytest.raises(Exception, match="challenge pending"):
            await browser_handler._get_session("av1")

    @pytest.mark.asyncio
    async def test_returns_alive_cached_session(self, browser_handler):
        """Should return cached session if alive."""
        mock_session = Mock()
        mock_session.is_alive.return_value = True
        browser_handler._sessions["av1"] = mock_session

        result = await browser_handler._get_session("av1")
        assert result is mock_session

    @pytest.mark.asyncio
    async def test_raises_for_missing_avatar(self, browser_handler):
        """Should raise when avatar not found."""
        browser_handler.config_manager.get_avatar.return_value = None
        with pytest.raises(ValueError, match="Avatar not found"):
            await browser_handler._get_session("nonexistent")

    @pytest.mark.asyncio
    async def test_raises_for_missing_login_flow(self, browser_handler):
        """Should raise when no login flow for platform."""
        browser_handler.config_manager.get_avatar.return_value = {
            "id": "fb_user1", "platform": "facebook", "metadata": {}
        }
        with pytest.raises(ValueError, match="No login flow"):
            await browser_handler._get_session("fb_user1")


class TestStartAuth:
    """Test start_auth method."""

    @pytest.mark.asyncio
    async def test_raises_for_unknown_platform(self, browser_handler):
        """Should raise for unsupported platform."""
        with pytest.raises(ValueError, match="No login flow"):
            await browser_handler.start_auth("av1", "facebook", {"username": "u", "password": "p"})

    @pytest.mark.asyncio
    @patch("platforms.browser.BrowserSession")
    async def test_challenge_required_saves_avatar(self, MockSession, browser_handler):
        """Should save avatar and store pending when challenge required."""
        mock_session = AsyncMock()
        mock_session.execute_login = AsyncMock(return_value={
            "status": "challenge_required",
            "challenge_prompt": "Enter 2FA code"
        })
        MockSession.return_value = mock_session

        result = await browser_handler.start_auth("av1", "x", {"username": "u", "password": "p"})

        assert result["status"] == "challenge_required"
        assert "av1" in browser_handler._pending_auth
        browser_handler.config_manager.save_avatar.assert_called_once()

    @pytest.mark.asyncio
    @patch("platforms.browser.BrowserSession")
    async def test_success_extracts_identity(self, MockSession, browser_handler):
        """Should extract platform identity and save avatar on success."""
        mock_session = AsyncMock()
        mock_session.execute_login = AsyncMock(return_value={"status": "success"})
        mock_session.extract_platform_identity = AsyncMock(return_value={"platform_user_id": "12345"})
        MockSession.return_value = mock_session

        result = await browser_handler.start_auth("av1", "x", {"username": "testuser", "password": "pass"})

        assert result["status"] == "authenticated"
        assert result["avatar_id"] == "x_12345"
        browser_handler.config_manager.save_avatar.assert_called_once()

    @pytest.mark.asyncio
    @patch("platforms.browser.BrowserSession")
    async def test_failed_login_closes_session(self, MockSession, browser_handler):
        """Should close session on failed login."""
        mock_session = AsyncMock()
        mock_session.execute_login = AsyncMock(return_value={"status": "failed", "error": "Bad creds"})
        MockSession.return_value = mock_session

        result = await browser_handler.start_auth("av1", "x", {"username": "u", "password": "p"})

        assert result["status"] == "failed"
        mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("platforms.browser.BrowserSession")
    async def test_success_without_identity_uses_username(self, MockSession, browser_handler):
        """Should fallback to username-based ID when identity extraction fails."""
        mock_session = AsyncMock()
        mock_session.execute_login = AsyncMock(return_value={"status": "success"})
        mock_session.extract_platform_identity = AsyncMock(return_value=None)
        MockSession.return_value = mock_session

        result = await browser_handler.start_auth("av1", "x", {"username": "testuser", "password": "pass"})

        assert result["avatar_id"] == "x_testuser"


class TestSubmitChallenge:
    """Test submit_challenge method."""

    @pytest.mark.asyncio
    async def test_raises_when_no_pending(self, browser_handler):
        """Should raise when no pending challenge."""
        with pytest.raises(ValueError, match="No pending challenge"):
            await browser_handler.submit_challenge("nonexistent", "123456")

    @pytest.mark.asyncio
    async def test_success_updates_avatar(self, browser_handler):
        """Should update avatar status on success."""
        mock_session = AsyncMock()
        mock_session.platform = "x"
        mock_session.submit_challenge_response = AsyncMock(return_value={"status": "success"})
        mock_session.extract_platform_identity = AsyncMock(return_value={"platform_user_id": "12345"})
        browser_handler._pending_auth["av1"] = {
            "session": mock_session,
            "challenge": {"challenge_selector": "input", "submit_text": "Submit"},
            "credentials": {"username": "testuser"},
            "profile_dir_name": "x_av1"
        }
        browser_handler.config_manager.get_avatar.return_value = {
            "id": "av1", "platform": "x", "metadata": {}
        }

        result = await browser_handler.submit_challenge("av1", "123456")

        assert result["status"] == "success"
        assert result["avatar_id"] == "x_12345"
        assert "av1" not in browser_handler._pending_auth
        browser_handler.config_manager.save_avatar.assert_called()

    @pytest.mark.asyncio
    async def test_failure_keeps_pending(self, browser_handler):
        """Should keep pending auth on failure."""
        mock_session = AsyncMock()
        mock_session.submit_challenge_response = AsyncMock(return_value={"status": "failed", "error": "Wrong code"})
        browser_handler._pending_auth["av1"] = {
            "session": mock_session,
            "challenge": {"challenge_selector": "input"},
            "credentials": {},
            "profile_dir_name": "x_av1"
        }

        result = await browser_handler.submit_challenge("av1", "wrong")

        assert result["status"] == "failed"
        # Pending auth stays for retry
        assert "av1" in browser_handler._pending_auth


class TestDisconnectAll:
    """Test disconnect_all cleanup."""

    @pytest.mark.asyncio
    async def test_closes_all_sessions(self, browser_handler):
        """Should close all active sessions."""
        session1 = AsyncMock()
        session2 = AsyncMock()
        browser_handler._sessions = {"av1": session1, "av2": session2}

        await browser_handler.disconnect_all()

        session1.close.assert_awaited_once()
        session2.close.assert_awaited_once()
        assert browser_handler._sessions == {}

    @pytest.mark.asyncio
    async def test_closes_pending_auth_sessions(self, browser_handler):
        """Should close pending auth sessions."""
        mock_session = AsyncMock()
        browser_handler._pending_auth = {"av1": {"session": mock_session}}

        await browser_handler.disconnect_all()

        mock_session.close.assert_awaited_once()
        assert browser_handler._pending_auth == {}

    @pytest.mark.asyncio
    async def test_handles_close_exception(self, browser_handler):
        """Should continue even if close fails."""
        session1 = AsyncMock()
        session1.close = AsyncMock(side_effect=Exception("error"))
        session2 = AsyncMock()
        browser_handler._sessions = {"av1": session1, "av2": session2}

        await browser_handler.disconnect_all()

        assert browser_handler._sessions == {}
        session2.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clears_both_dicts(self, browser_handler):
        """Should clear both sessions and pending_auth."""
        browser_handler._sessions = {"av1": AsyncMock()}
        browser_handler._pending_auth = {"av2": {"session": AsyncMock()}}

        await browser_handler.disconnect_all()

        assert browser_handler._sessions == {}
        assert browser_handler._pending_auth == {}


class TestClearCsrfCookies:
    """Test BrowserSession._clear_csrf_cookies method."""

    @pytest.mark.asyncio
    async def test_clears_ct0_for_x_platform(self, tmp_path):
        """Should delete ct0 cookie for both .x.com and .twitter.com domains."""
        session = BrowserSession("av1", "x", tmp_path, MOCK_LOGIN_FLOW)
        session._tab = AsyncMock()

        await session._clear_csrf_cookies()

        assert session._tab.send.call_count == 2

    @pytest.mark.asyncio
    async def test_clears_ct0_for_twitter_platform(self, tmp_path):
        """Should also work when platform is 'twitter' (legacy)."""
        session = BrowserSession("av1", "twitter", tmp_path, MOCK_LOGIN_FLOW)
        session._tab = AsyncMock()

        await session._clear_csrf_cookies()

        assert session._tab.send.call_count == 2

    @pytest.mark.asyncio
    async def test_noop_for_unknown_platform(self, tmp_path):
        """Should do nothing for platforms without CSRF cookies configured."""
        session = BrowserSession("av1", "facebook", tmp_path, MOCK_LOGIN_FLOW)
        session._tab = AsyncMock()

        await session._clear_csrf_cookies()

        session._tab.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_cdp_exception_gracefully(self, tmp_path):
        """Should not raise even if CDP delete_cookies fails."""
        session = BrowserSession("av1", "x", tmp_path, MOCK_LOGIN_FLOW)
        session._tab = AsyncMock()
        session._tab.send = AsyncMock(side_effect=Exception("CDP error"))

        await session._clear_csrf_cookies()  # Should not raise


class TestCaptureXhrCsrfClearing:
    """Test that capture_xhr clears CSRF cookies before navigation."""

    @pytest.mark.asyncio
    async def test_calls_clear_csrf_cookies_before_navigation(self, tmp_path):
        """Should call _clear_csrf_cookies before navigating."""
        session = BrowserSession("av1", "x", tmp_path, MOCK_LOGIN_FLOW)
        session._tab = AsyncMock()
        session._tab.add_handler = Mock()
        session._clear_csrf_cookies = AsyncMock()

        await session.capture_xhr(
            url="https://x.com/home",
            targets=["HomeTimeline"],
            wait_seconds=1,
        )

        session._clear_csrf_cookies.assert_awaited_once()
