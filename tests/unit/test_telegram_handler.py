"""
Unit tests for TelegramHandler.

Tests credential management, client lifecycle, auth flows, command dispatch,
and cleanup. Uses sys.modules injection to mock telethon.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from pathlib import Path
from datetime import datetime

# Add src to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

# Pre-inject mock telethon modules before importing TelegramHandler
mock_telethon = MagicMock()
mock_sessions = MagicMock()
mock_errors = MagicMock()

# Create real exception classes for testing
class MockSessionPasswordNeededError(Exception):
    pass

class MockPhoneCodeInvalidError(Exception):
    pass

class MockPhoneCodeExpiredError(Exception):
    pass

mock_errors.SessionPasswordNeededError = MockSessionPasswordNeededError
mock_errors.PhoneCodeInvalidError = MockPhoneCodeInvalidError
mock_errors.PhoneCodeExpiredError = MockPhoneCodeExpiredError

sys.modules.setdefault('telethon', mock_telethon)
sys.modules.setdefault('telethon.sessions', mock_sessions)
sys.modules.setdefault('telethon.tl', MagicMock())
sys.modules.setdefault('telethon.tl.functions', MagicMock())
sys.modules.setdefault('telethon.tl.functions.auth', MagicMock())

# Force error classes onto whatever mock is in sys.modules (may have been set by other tests)
_errors_mod = sys.modules.get('telethon.errors', mock_errors)
_errors_mod.SessionPasswordNeededError = MockSessionPasswordNeededError
_errors_mod.PhoneCodeInvalidError = MockPhoneCodeInvalidError
_errors_mod.PhoneCodeExpiredError = MockPhoneCodeExpiredError
sys.modules['telethon.errors'] = _errors_mod

mock_telethon.TelegramClient = MagicMock()
mock_sessions.StringSession = MagicMock()

from platforms.telegram import TelegramHandler

# Patch error classes on the already-imported module (in case it imported before us)
import platforms.telegram as _tg_module
_tg_module.SessionPasswordNeededError = MockSessionPasswordNeededError
_tg_module.PhoneCodeInvalidError = MockPhoneCodeInvalidError
_tg_module.PhoneCodeExpiredError = MockPhoneCodeExpiredError


@pytest.fixture
def mock_config_manager():
    """ConfigManager mock with Telegram credentials."""
    manager = Mock()
    manager.get_platform_config.return_value = {
        "telegram_api_id": "12345",
        "telegram_api_hash": "abc123hash"
    }
    manager.get_avatar.return_value = {
        "id": "telegram_99",
        "platform": "telegram",
        "session_string": "valid_session",
        "status": "active"
    }
    manager.update_avatar_status = Mock(return_value=True)
    manager.save_avatar = Mock(return_value=True)
    manager.history_logger = Mock()
    manager.history_logger.log_auth_event = Mock(return_value=True)
    manager.history_logger.log_system_event = Mock(return_value=True)
    return manager


@pytest.fixture
def handler(mock_config_manager):
    """TelegramHandler instance with mocked config."""
    return TelegramHandler(mock_config_manager)


class TestTelegramHandlerInit:
    """Test TelegramHandler initialization."""

    def test_init_stores_config_manager(self, mock_config_manager):
        """Should store config_manager reference."""
        handler = TelegramHandler(mock_config_manager)
        assert handler.config_manager is mock_config_manager

    def test_init_empty_clients(self, handler):
        """Should start with empty client dicts."""
        assert handler._clients == {}
        assert handler._pending_auth == {}


class TestSerializeDatetime:
    """Test _serialize_datetime static method (pure function)."""

    def test_datetime_to_isoformat(self):
        """Should convert datetime to ISO format string."""
        dt = datetime(2024, 1, 15, 10, 30, 0)
        result = TelegramHandler._serialize_datetime(dt)
        assert result == "2024-01-15T10:30:00"

    def test_dict_with_datetime(self):
        """Should recursively convert datetime in dicts."""
        dt = datetime(2024, 1, 15)
        data = {"date": dt, "name": "test"}
        result = TelegramHandler._serialize_datetime(data)
        assert result["date"] == "2024-01-15T00:00:00"
        assert result["name"] == "test"

    def test_list_with_datetime(self):
        """Should convert datetime in lists."""
        dt = datetime(2024, 1, 15)
        data = [dt, "text", 42]
        result = TelegramHandler._serialize_datetime(data)
        assert result[0] == "2024-01-15T00:00:00"
        assert result[1] == "text"
        assert result[2] == 42

    def test_bytes_to_base64(self):
        """Should convert bytes to base64 string."""
        data = b"hello"
        result = TelegramHandler._serialize_datetime(data)
        import base64
        assert result == base64.b64encode(b"hello").decode('utf-8')

    def test_primitives_pass_through(self):
        """Should pass through primitive types unchanged."""
        assert TelegramHandler._serialize_datetime(42) == 42
        assert TelegramHandler._serialize_datetime("text") == "text"
        assert TelegramHandler._serialize_datetime(None) is None
        assert TelegramHandler._serialize_datetime(True) is True

    def test_nested_mixed_types(self):
        """Should handle deeply nested mixed types."""
        dt = datetime(2024, 1, 15)
        data = {
            "messages": [
                {"date": dt, "content": "test", "media": b"\x00\x01"},
                {"date": dt, "nested": {"inner_date": dt}}
            ],
            "count": 2
        }
        result = TelegramHandler._serialize_datetime(data)
        assert result["messages"][0]["date"] == "2024-01-15T00:00:00"
        assert isinstance(result["messages"][0]["media"], str)
        assert result["messages"][1]["nested"]["inner_date"] == "2024-01-15T00:00:00"
        assert result["count"] == 2


class TestGetCredentials:
    """Test _get_credentials method."""

    def test_returns_api_id_and_hash(self, handler):
        """Should return (api_id, api_hash) tuple."""
        api_id, api_hash = handler._get_credentials()
        assert api_id == 12345
        assert api_hash == "abc123hash"

    def test_converts_api_id_to_int(self, handler):
        """Should convert api_id to int."""
        api_id, _ = handler._get_credentials()
        assert isinstance(api_id, int)

    def test_raises_when_api_id_missing(self, mock_config_manager):
        """Should raise ValueError when api_id not configured."""
        mock_config_manager.get_platform_config.return_value = {
            "telegram_api_hash": "abc123hash"
        }
        handler = TelegramHandler(mock_config_manager)
        with pytest.raises(ValueError, match="credentials not configured"):
            handler._get_credentials()

    def test_raises_when_api_hash_missing(self, mock_config_manager):
        """Should raise ValueError when api_hash not configured."""
        mock_config_manager.get_platform_config.return_value = {
            "telegram_api_id": "12345"
        }
        handler = TelegramHandler(mock_config_manager)
        with pytest.raises(ValueError, match="credentials not configured"):
            handler._get_credentials()

    def test_raises_when_empty_config(self, mock_config_manager):
        """Should raise ValueError when platform config is empty."""
        mock_config_manager.get_platform_config.return_value = {}
        handler = TelegramHandler(mock_config_manager)
        with pytest.raises(ValueError):
            handler._get_credentials()


class TestGetClient:
    """Test _get_client async method."""

    @pytest.mark.asyncio
    async def test_returns_cached_connected_client(self, handler):
        """Should return existing client if connected."""
        mock_client = AsyncMock()
        mock_client.is_connected = Mock(return_value=True)
        handler._clients["telegram_99"] = mock_client

        result = await handler._get_client("telegram_99")
        assert result is mock_client

    @pytest.mark.asyncio
    async def test_raises_for_missing_avatar(self, handler):
        """Should raise ValueError when avatar not found."""
        handler.config_manager.get_avatar.return_value = None
        with pytest.raises(ValueError, match="Avatar not found"):
            await handler._get_client("nonexistent")

    @pytest.mark.asyncio
    async def test_raises_for_non_telegram_avatar(self, handler):
        """Should raise ValueError for non-telegram avatars."""
        handler.config_manager.get_avatar.return_value = {
            "id": "x_user1", "platform": "x"
        }
        with pytest.raises(ValueError, match="not a Telegram avatar"):
            await handler._get_client("x_user1")

    @pytest.mark.asyncio
    async def test_raises_for_avatar_without_session(self, handler):
        """Should raise ValueError when no session string."""
        handler.config_manager.get_avatar.return_value = {
            "id": "telegram_99", "platform": "telegram", "session_string": None
        }
        with pytest.raises(ValueError, match="no session"):
            await handler._get_client("telegram_99")

    @pytest.mark.asyncio
    @patch("platforms.telegram.TelegramClient")
    @patch("platforms.telegram.StringSession")
    async def test_creates_new_client_from_session(self, MockStringSession, MockTelegramClient, handler):
        """Should create and connect new client from session string."""
        mock_client = AsyncMock()
        mock_client.is_user_authorized = AsyncMock(return_value=True)
        MockTelegramClient.return_value = mock_client

        result = await handler._get_client("telegram_99")

        MockTelegramClient.assert_called_once()
        mock_client.connect.assert_awaited_once()
        mock_client.is_user_authorized.assert_awaited_once()
        assert handler._clients["telegram_99"] is mock_client

    @pytest.mark.asyncio
    @patch("platforms.telegram.TelegramClient")
    @patch("platforms.telegram.StringSession")
    async def test_disconnects_unauthorized_client(self, MockStringSession, MockTelegramClient, handler):
        """Should disconnect and raise when client not authorized."""
        mock_client = AsyncMock()
        mock_client.is_user_authorized = AsyncMock(return_value=False)
        MockTelegramClient.return_value = mock_client

        with pytest.raises(Exception, match="requires re-authentication"):
            await handler._get_client("telegram_99")

        mock_client.disconnect.assert_awaited_once()
        handler.config_manager.get_auth_failure_status.assert_called_with("telegram_99")
        handler.config_manager.update_avatar_status.assert_called_with(
            "telegram_99",
            handler.config_manager.get_auth_failure_status.return_value
        )


class TestExecuteDispatch:
    """Test execute command dispatcher."""

    @pytest.mark.asyncio
    async def test_dispatches_get_messages(self, handler):
        """Should route telegram.get_messages to _get_messages."""
        mock_client = AsyncMock()
        handler._get_client = AsyncMock(return_value=mock_client)
        handler._get_messages = AsyncMock(return_value=[{"id": 1}])

        result = await handler.execute("av1", "telegram.get_messages", {"channel": "test"})

        handler._get_messages.assert_awaited_once_with(mock_client, {"channel": "test"})
        assert result == [{"id": 1}]

    @pytest.mark.asyncio
    async def test_dispatches_get_channel_info(self, handler):
        """Should route telegram.get_channel_info to _get_channel_info."""
        mock_client = AsyncMock()
        handler._get_client = AsyncMock(return_value=mock_client)
        handler._get_channel_info = AsyncMock(return_value=[{"id": 123}])

        result = await handler.execute("av1", "telegram.get_channel_info", {"channel": "test"})

        handler._get_channel_info.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dispatches_list_dialogs(self, handler):
        """Should route telegram.list_dialogs to _list_dialogs."""
        mock_client = AsyncMock()
        handler._get_client = AsyncMock(return_value=mock_client)
        handler._list_dialogs = AsyncMock(return_value=[])

        await handler.execute("av1", "telegram.list_dialogs", {})

        handler._list_dialogs.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dispatches_search_messages(self, handler):
        """Should route telegram.search_messages to _search_messages."""
        mock_client = AsyncMock()
        handler._get_client = AsyncMock(return_value=mock_client)
        handler._search_messages = AsyncMock(return_value=[])

        await handler.execute("av1", "telegram.search_messages", {"query": "test"})

        handler._search_messages.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_for_unknown_command(self, handler):
        """Should raise ValueError for unknown commands."""
        handler._get_client = AsyncMock(return_value=AsyncMock())

        with pytest.raises(ValueError, match="Unknown command"):
            await handler.execute("av1", "telegram.unknown", {})


class TestStartAuth:
    """Test start_auth phone authentication flow."""

    @pytest.mark.asyncio
    @patch("platforms.telegram.TelegramClient")
    @patch("platforms.telegram.StringSession")
    async def test_start_auth_sends_code(self, MockStringSession, MockTelegramClient, handler):
        """Should send code and return phone_code_hash."""
        mock_client = AsyncMock()
        mock_sent = Mock()
        mock_sent.phone_code_hash = "hash123"
        mock_client.send_code_request = AsyncMock(return_value=mock_sent)
        MockTelegramClient.return_value = mock_client

        result = await handler.start_auth("av1", "+1234567890")

        assert result["status"] == "code_sent"
        assert result["phone_code_hash"] == "hash123"
        assert "av1" in handler._pending_auth

    @pytest.mark.asyncio
    @patch("platforms.telegram.TelegramClient")
    @patch("platforms.telegram.StringSession")
    async def test_start_auth_logs_audit_event(self, MockStringSession, MockTelegramClient, handler):
        """Should log audit event on success."""
        mock_client = AsyncMock()
        mock_sent = Mock()
        mock_sent.phone_code_hash = "hash123"
        mock_client.send_code_request = AsyncMock(return_value=mock_sent)
        MockTelegramClient.return_value = mock_client

        await handler.start_auth("av1", "+1234567890")

        handler.config_manager.history_logger.log_auth_event.assert_called_once()

    @pytest.mark.asyncio
    @patch("platforms.telegram.TelegramClient")
    @patch("platforms.telegram.StringSession")
    async def test_start_auth_cleans_up_on_failure(self, MockStringSession, MockTelegramClient, handler):
        """Should disconnect and clean up on failure."""
        mock_client = AsyncMock()
        mock_client.send_code_request = AsyncMock(side_effect=Exception("Network error"))
        mock_client.connect = AsyncMock()
        MockTelegramClient.return_value = mock_client

        with pytest.raises(Exception, match="Network error"):
            await handler.start_auth("av1", "+1234567890")

        assert "av1" not in handler._pending_auth


class TestCompleteAuth:
    """Test complete_auth phone authentication flow."""

    @pytest.mark.asyncio
    async def test_complete_auth_no_pending_raises(self, handler):
        """Should raise when no pending auth exists."""
        with pytest.raises(ValueError, match="No pending authentication"):
            await handler.complete_auth("av1", "+123", "12345", "hash123")

    @pytest.mark.asyncio
    async def test_complete_auth_success(self, handler):
        """Should complete auth and save avatar."""
        mock_client = AsyncMock()
        mock_me = Mock()
        mock_me.id = 12345
        mock_me.username = "testuser"
        mock_me.first_name = "Test"
        mock_me.last_name = "User"
        mock_client.get_me = AsyncMock(return_value=mock_me)
        mock_client.sign_in = AsyncMock()
        mock_client.session.save.return_value = "saved_session_string"
        handler._pending_auth["av1"] = mock_client

        result = await handler.complete_auth("av1", "+123", "12345", "hash123")

        assert result["status"] == "authenticated"
        assert result["avatar"]["id"] == "telegram_12345"
        handler.config_manager.save_avatar.assert_called_once()
        assert "av1" not in handler._pending_auth
        assert "telegram_12345" in handler._clients

    @pytest.mark.asyncio
    async def test_complete_auth_2fa_required(self, handler):
        """Should return password_required when 2FA is enabled."""
        mock_client = AsyncMock()
        mock_client.sign_in = AsyncMock(side_effect=MockSessionPasswordNeededError())
        handler._pending_auth["av1"] = mock_client

        result = await handler.complete_auth("av1", "+123", "12345", "hash123")

        assert result["status"] == "password_required"
        # Client should still be in pending_auth for password retry
        assert "av1" in handler._pending_auth

    @pytest.mark.asyncio
    async def test_complete_auth_invalid_code(self, handler):
        """Should raise for invalid code."""
        mock_client = AsyncMock()
        mock_client.sign_in = AsyncMock(side_effect=MockPhoneCodeInvalidError())
        handler._pending_auth["av1"] = mock_client

        with pytest.raises(Exception, match="Invalid verification code"):
            await handler.complete_auth("av1", "+123", "wrong", "hash123")

        assert "av1" not in handler._pending_auth

    @pytest.mark.asyncio
    async def test_complete_auth_expired_code(self, handler):
        """Should raise for expired code."""
        mock_client = AsyncMock()
        mock_client.sign_in = AsyncMock(side_effect=MockPhoneCodeExpiredError())
        handler._pending_auth["av1"] = mock_client

        with pytest.raises(Exception, match="Verification code expired"):
            await handler.complete_auth("av1", "+123", "12345", "hash123")


class TestQRAuth:
    """Test QR code authentication flow."""

    @pytest.mark.asyncio
    @patch("platforms.telegram.TelegramClient")
    @patch("platforms.telegram.StringSession")
    async def test_start_qr_auth_returns_url(self, MockStringSession, MockTelegramClient, handler):
        """Should return QR URL and token."""
        mock_client = AsyncMock()
        mock_qr = Mock()
        mock_qr.url = "tg://login?token=abc123"
        mock_qr.token = b"\x01\x02\x03"
        mock_qr.expires = datetime(2024, 12, 31)
        mock_client.qr_login = AsyncMock(return_value=mock_qr)
        MockTelegramClient.return_value = mock_client

        result = await handler.start_qr_auth("av1")

        assert result["status"] == "qr_ready"
        assert result["url"] == "tg://login?token=abc123"
        assert "av1" in handler._pending_auth

    @pytest.mark.asyncio
    async def test_wait_qr_scan_no_pending_raises(self, handler):
        """Should raise when no pending QR auth."""
        with pytest.raises(ValueError, match="No pending QR authentication"):
            await handler.wait_qr_scan("av1")

    @pytest.mark.asyncio
    async def test_wait_qr_scan_timeout(self, handler):
        """Should return timeout status on timeout."""
        mock_client = AsyncMock()
        mock_qr = AsyncMock()
        mock_qr.wait = AsyncMock(side_effect=asyncio.TimeoutError())
        handler._pending_auth["av1"] = {
            'client': mock_client,
            'qr_login': mock_qr,
            'method': 'qr'
        }

        result = await handler.wait_qr_scan("av1", timeout=1)

        assert result["status"] == "timeout"
        assert "av1" not in handler._pending_auth
        mock_client.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancel_qr_auth_success(self, handler):
        """Should cancel and clean up QR auth."""
        mock_client = AsyncMock()
        mock_client.is_connected = Mock(return_value=True)
        handler._pending_auth["av1"] = {
            'client': mock_client,
            'qr_login': Mock(),
            'method': 'qr'
        }

        result = await handler.cancel_qr_auth("av1")

        assert result is True
        assert "av1" not in handler._pending_auth
        mock_client.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancel_qr_auth_no_pending(self, handler):
        """Should return False when no pending QR auth."""
        result = await handler.cancel_qr_auth("nonexistent")
        assert result is False


class TestTestConnection:
    """Test test_connection method."""

    @pytest.mark.asyncio
    async def test_returns_true_on_success(self, handler):
        """Should return True when connection works."""
        mock_client = AsyncMock()
        mock_me = Mock()
        mock_me.first_name = "Test"
        mock_client.get_me = AsyncMock(return_value=mock_me)
        handler._get_client = AsyncMock(return_value=mock_client)

        result = await handler.test_connection("av1")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self, handler):
        """Should return False when connection fails."""
        handler._get_client = AsyncMock(side_effect=Exception("Disconnected"))

        result = await handler.test_connection("av1")
        assert result is False


class TestDisconnectAll:
    """Test disconnect_all cleanup."""

    @pytest.mark.asyncio
    async def test_disconnects_active_clients(self, handler):
        """Should disconnect all active clients."""
        client1 = AsyncMock()
        client1.is_connected = Mock(return_value=True)
        client2 = AsyncMock()
        client2.is_connected = Mock(return_value=True)
        handler._clients = {"av1": client1, "av2": client2}

        await handler.disconnect_all()

        client1.disconnect.assert_awaited_once()
        client2.disconnect.assert_awaited_once()
        assert handler._clients == {}

    @pytest.mark.asyncio
    async def test_disconnects_pending_auth(self, handler):
        """Should disconnect pending auth clients."""
        client = AsyncMock()
        client.is_connected = Mock(return_value=True)
        handler._pending_auth = {"av1": client}

        await handler.disconnect_all()

        client.disconnect.assert_awaited_once()
        assert handler._pending_auth == {}

    @pytest.mark.asyncio
    async def test_handles_disconnect_errors(self, handler):
        """Should continue even if disconnect fails."""
        client1 = AsyncMock()
        client1.is_connected = Mock(return_value=True)
        client1.disconnect = AsyncMock(side_effect=Exception("error"))
        client2 = AsyncMock()
        client2.is_connected = Mock(return_value=True)
        handler._clients = {"av1": client1, "av2": client2}

        await handler.disconnect_all()

        assert handler._clients == {}
        client2.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clears_both_dicts(self, handler):
        """Should clear both clients and pending_auth."""
        client1 = AsyncMock()
        client1.is_connected = Mock(return_value=False)
        client2 = AsyncMock()
        client2.is_connected = Mock(return_value=False)
        handler._clients = {"av1": client1}
        handler._pending_auth = {"av2": client2}

        await handler.disconnect_all()

        assert handler._clients == {}
        assert handler._pending_auth == {}
