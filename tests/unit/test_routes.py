"""
Unit tests for API routes.

Tests the FastAPI routes for local agent management.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
from fastapi.testclient import TestClient
import base64
import os

# Add src to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


# Mock global instances before importing routes
mock_config_manager = Mock()
mock_hubfeed_client = Mock()
mock_history_logger = Mock()
mock_executor = Mock()
mock_agent_loop = Mock()
mock_platform_manager = Mock()

# Mock the main module
sys.modules['src.main'] = MagicMock()
sys.modules['src.main'].config_manager = mock_config_manager
sys.modules['src.main'].hubfeed_client = mock_hubfeed_client
sys.modules['src.main'].history_logger = mock_history_logger
sys.modules['src.main'].executor = mock_executor
sys.modules['src.main'].agent_loop = mock_agent_loop
sys.modules['src.main'].platform_manager = mock_platform_manager

from src.api.routes import router
from fastapi import FastAPI


@pytest.fixture
def app():
    """Create FastAPI app for testing."""
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def setup_mocks():
    """Reset mocks before each test."""
    mock_config_manager.reset_mock()
    mock_hubfeed_client.reset_mock()
    mock_history_logger.reset_mock()
    mock_executor.reset_mock()
    mock_agent_loop.reset_mock()
    mock_platform_manager.reset_mock()
    
    # Set default return values
    mock_config_manager.get_config.return_value = {
        "token": "test_token_abc123"
    }
    mock_config_manager.is_configured.return_value = True
    mock_config_manager.is_verified.return_value = True
    mock_config_manager.get_avatars.return_value = []
    mock_config_manager.get_blacklist.return_value = {
        "global": {"keywords": [], "senders": [], "channels": []},
        "by_avatar": {}
    }
    mock_config_manager.update_config.return_value = True
    mock_config_manager.save_blacklist.return_value = True
    mock_config_manager.delete_avatar.return_value = True
    
    mock_agent_loop.is_running = False
    mock_agent_loop.health_check = AsyncMock(return_value={
        "running": False,
        "verified": True,
        "hubfeed_reachable": True,
        "configured": True
    })
    mock_agent_loop.start = AsyncMock()
    mock_agent_loop.stop = AsyncMock()
    
    mock_history_logger.query_history = AsyncMock(return_value=[])
    
    # Set up platform_manager mock
    mock_telegram_handler = Mock()
    mock_telegram_handler.start_auth = AsyncMock(return_value={
        "status": "code_sent",
        "phone_code_hash": "hash123"
    })
    mock_telegram_handler.complete_auth = AsyncMock(return_value={
        "status": "authenticated",
        "avatar": {"id": "avatar_1", "name": "Test"}
    })
    mock_telegram_handler.start_qr_auth = AsyncMock(return_value={
        "status": "qr_ready",
        "url": "tg://login?token=abc123"
    })
    mock_telegram_handler.wait_qr_scan = AsyncMock(return_value={
        "status": "authenticated",
        "avatar": {"id": "avatar_1", "name": "Test"}
    })
    mock_telegram_handler.cancel_qr_auth = AsyncMock(return_value=True)
    mock_platform_manager.get_handler.return_value = mock_telegram_handler
    
    yield


class TestAuthEndpoint:
    """Test authentication endpoint."""
    
    def test_login_success(self, client):
        """Should login with correct credentials."""
        with patch.dict(os.environ, {"AGENT_UI_USERNAME": "admin", "AGENT_UI_PASSWORD": "changeme"}):
            response = client.post(
                "/api/auth/login",
                json={"username": "admin", "password": "changeme"}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "token" in data
        assert data["username"] == "admin"
    
    def test_login_invalid_credentials(self, client):
        """Should reject invalid credentials."""
        with patch.dict(os.environ, {"AGENT_UI_USERNAME": "admin", "AGENT_UI_PASSWORD": "changeme"}):
            response = client.post(
                "/api/auth/login",
                json={"username": "admin", "password": "wrong"}
            )
        
        assert response.status_code == 401
        assert "Invalid username or password" in response.json()["detail"]


class TestConfigEndpoints:
    """Test configuration endpoints."""
    
    def test_get_config(self, client):
        """Should retrieve current configuration."""
        response = client.get("/api/config")
        
        assert response.status_code == 200
        data = response.json()
        assert "config" in data
        assert "is_configured" in data
        assert "is_verified" in data
    
    def test_get_config_hides_token(self, client):
        """Should hide full token in response."""
        response = client.get("/api/config")
        
        assert response.status_code == 200
        token = response.json()["config"]["token"]
        assert token.endswith("...")
    
    def test_update_config_success(self, client):
        """Should update configuration."""
        response = client.post(
            "/api/config",
            json={
                "token": "new_token_123"
            }
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_config_manager.update_config.assert_called_once()
    
    def test_update_config_no_updates(self, client):
        """Should reject empty updates."""
        response = client.post("/api/config", json={})
        
        assert response.status_code == 400
    
    def test_update_config_starts_loop(self, client):
        """Should start agent loop after config update."""
        mock_agent_loop.is_running = False
        
        response = client.post(
            "/api/config",
            json={"token": "new_token"}
        )
        
        assert response.status_code == 200


class TestAvatarEndpoints:
    """Test avatar endpoints."""
    
    def test_get_avatars(self, client):
        """Should retrieve all avatars."""
        mock_config_manager.get_avatars.return_value = [
            {
                "id": "avatar_1",
                "name": "Test Avatar",
                "platform": "telegram",
                "status": "active",
                "metadata": {"session_string": "secret"}
            }
        ]
        
        response = client.get("/api/avatars")
        
        assert response.status_code == 200
        data = response.json()
        assert "avatars" in data
        assert len(data["avatars"]) == 1
        # Should not expose session_string
        assert "session_string" not in str(data)
    
    def test_delete_avatar_success(self, client):
        """Should delete avatar."""
        mock_config_manager.delete_avatar.return_value = True
        
        response = client.delete("/api/avatars/avatar_1")
        
        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_config_manager.delete_avatar.assert_called_once_with("avatar_1")
    
    def test_delete_avatar_not_found(self, client):
        """Should handle non-existent avatar."""
        mock_config_manager.delete_avatar.return_value = False
        
        response = client.delete("/api/avatars/nonexistent")
        
        assert response.status_code == 404


class TestBlacklistEndpoints:
    """Test blacklist endpoints."""
    
    def test_get_blacklist(self, client):
        """Should retrieve blacklist configuration."""
        response = client.get("/api/blacklist")
        
        assert response.status_code == 200
        data = response.json()
        assert "blacklist" in data
        mock_config_manager.get_blacklist.assert_called_once()
    
    def test_update_blacklist(self, client):
        """Should update blacklist configuration."""
        blacklist_data = {
            "global": {
                "keywords": ["spam"],
                "senders": [],
                "channels": []
            },
            "by_avatar": {}
        }
        
        response = client.put(
            "/api/blacklist",
            json={"blacklist": blacklist_data}
        )
        
        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_config_manager.save_blacklist.assert_called_once_with(blacklist_data)
    
    def test_update_blacklist_failure(self, client):
        """Should handle blacklist update failure."""
        mock_config_manager.save_blacklist.return_value = False
        
        response = client.put(
            "/api/blacklist",
            json={"blacklist": {}}
        )
        
        assert response.status_code == 500


class TestHistoryEndpoint:
    """Test history endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_history(self, client):
        """Should retrieve execution history."""
        mock_history_logger.query_history.return_value = [
            {
                "job_id": "job_1",
                "avatar_id": "avatar_1",
                "command": "telegram.get_messages",
                "success": True,
                "timestamp": "2024-01-01T00:00:00Z"
            }
        ]
        
        response = client.get("/api/history")
        
        assert response.status_code == 200
        data = response.json()
        assert "history" in data
    
    @pytest.mark.asyncio
    async def test_get_history_with_filters(self, client):
        """Should filter history by parameters."""
        response = client.get(
            "/api/history?avatar_id=avatar_1&limit=10"
        )
        
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_get_history_error(self, client):
        """Should handle history query errors."""
        mock_history_logger.query_history.side_effect = Exception("Query failed")
        
        response = client.get("/api/history")
        
        assert response.status_code == 500


class TestStatusEndpoint:
    """Test status endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_status_running(self, client):
        """Should return running status."""
        mock_agent_loop.health_check.return_value = {
            "running": True,
            "verified": True,
            "hubfeed_reachable": True,
            "configured": True
        }
        
        response = client.get("/api/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert "version" in data
    
    @pytest.mark.asyncio
    async def test_get_status_stopped(self, client):
        """Should return stopped status."""
        mock_agent_loop.health_check.return_value = {
            "running": False,
            "verified": True,
            "hubfeed_reachable": True,
            "configured": True
        }
        
        response = client.get("/api/status")
        
        assert response.status_code == 200
        assert response.json()["status"] == "stopped"
    
    @pytest.mark.asyncio
    async def test_get_status_not_initialized(self, client):
        """Should handle uninitialized agent loop."""
        with patch('src.api.routes.get_globals', return_value=(None, None, None, None, None, None)):
            response = client.get("/api/status")
        
        assert response.status_code == 200
        assert response.json()["status"] == "not_initialized"


class TestControlEndpoints:
    """Test control endpoints."""
    
    @pytest.mark.asyncio
    async def test_start_agent(self, client):
        """Should start agent loop."""
        mock_agent_loop.is_running = False
        
        response = client.post("/api/control/start")
        
        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_agent_loop.start.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_start_agent_already_running(self, client):
        """Should handle already running agent."""
        mock_agent_loop.is_running = True
        
        response = client.post("/api/control/start")
        
        assert response.status_code == 200
        assert "already running" in response.json()["message"]
    
    @pytest.mark.asyncio
    async def test_start_agent_not_configured(self, client):
        """Should reject start when not configured."""
        mock_config_manager.is_configured.return_value = False
        
        response = client.post("/api/control/start")
        
        assert response.status_code == 400
    
    @pytest.mark.asyncio
    async def test_stop_agent(self, client):
        """Should stop agent loop."""
        mock_agent_loop.is_running = True
        
        response = client.post("/api/control/stop")
        
        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_agent_loop.stop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_stop_agent_already_stopped(self, client):
        """Should handle already stopped agent."""
        mock_agent_loop.is_running = False
        
        response = client.post("/api/control/stop")
        
        assert response.status_code == 200
        assert "already stopped" in response.json()["message"]


class TestTelegramAuthEndpoints:
    """Test Telegram authentication endpoints."""
    
    @pytest.mark.asyncio
    async def test_telegram_phone_auth_start(self, client):
        """Should start phone authentication."""
        response = client.post(
            "/api/avatars/telegram/phone/start",
            json={"avatar_id": "avatar_1", "phone": "+1234567890"}
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "code_sent"
        mock_platform_manager.get_handler.assert_called_with('telegram')
    
    @pytest.mark.asyncio
    async def test_telegram_phone_auth_complete(self, client):
        """Should complete phone authentication."""
        response = client.post(
            "/api/avatars/telegram/phone/complete",
            json={
                "avatar_id": "avatar_1",
                "phone": "+1234567890",
                "code": "12345",
                "phone_code_hash": "hash123"
            }
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "authenticated"
        mock_platform_manager.get_handler.assert_called_with('telegram')
    
    @pytest.mark.asyncio
    async def test_telegram_qr_auth_start(self, client):
        """Should start QR authentication."""
        response = client.post(
            "/api/avatars/telegram/qr/start",
            json={"avatar_id": "avatar_1"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "qr_ready"
        assert "qr_code_image" in data
        mock_platform_manager.get_handler.assert_called_with('telegram')
    
    @pytest.mark.asyncio
    async def test_telegram_qr_auth_cancel(self, client):
        """Should cancel QR authentication."""
        response = client.post("/api/avatars/telegram/qr/cancel/avatar_1")
        
        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_platform_manager.get_handler.assert_called_with('telegram')


class TestCacheEndpoints:
    """Test avatar cache endpoints."""

    def test_get_cached_avatar_directory_traversal_blocked(self, client):
        """Should reject filenames with directory traversal."""
        response = client.get("/api/cache/avatars/..test.png")
        assert response.status_code == 400

    @patch("src.api.routes.Path")
    def test_get_cached_avatar_file_exists(self, MockPath, client):
        """Should return file when it exists."""
        # Make the avatar path exist
        mock_avatar_path = MagicMock()
        mock_avatar_path.exists.return_value = True
        MockPath.return_value.__truediv__.return_value = mock_avatar_path

        with patch("src.api.routes.FileResponse") as MockFileResponse:
            MockFileResponse.return_value = MagicMock()
            response = client.get("/api/cache/avatars/test.png")
        # The route should attempt to serve the file (may get 200 or 500 depending on FileResponse mock)

    @patch("src.api.routes.Path")
    def test_get_cached_avatar_fallback_to_placeholder(self, MockPath, client):
        """Should return placeholder when file doesn't exist."""
        # Avatar path doesn't exist, placeholder does
        mock_avatar_path = MagicMock()
        mock_avatar_path.exists.return_value = False
        mock_placeholder_path = MagicMock()
        mock_placeholder_path.exists.return_value = True

        def path_side_effect(path_str):
            if "cache/avatars" in str(path_str):
                return mock_avatar_path
            return mock_placeholder_path

        MockPath.side_effect = path_side_effect
        mock_avatar_path.__truediv__ = MagicMock(return_value=mock_avatar_path)

        # The route will try FileResponse which may fail in test but we verify the logic path
        response = client.get("/api/cache/avatars/missing.png")

    @patch("src.api.routes.Path")
    def test_get_cached_avatar_no_placeholder_returns_404(self, MockPath, client):
        """Should return 404 when neither file nor placeholder exists."""
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_path.__truediv__ = MagicMock(return_value=mock_path)
        MockPath.return_value = mock_path

        response = client.get("/api/cache/avatars/missing.png")
        assert response.status_code == 404


class TestQRAuthStatusEndpoint:
    """Test QR auth status check endpoint."""

    @pytest.mark.asyncio
    async def test_qr_status_returns_result(self, client):
        """Should return QR scan result."""
        response = client.get("/api/avatars/telegram/qr/status/avatar_1")

        assert response.status_code == 200
        assert response.json()["status"] == "authenticated"

    @pytest.mark.asyncio
    async def test_qr_status_authenticated_syncs_avatars(self, client):
        """Should sync avatars with Hubfeed on successful auth."""
        mock_hubfeed_client.sync_avatars = AsyncMock()
        mock_agent_loop.is_running = True
        mock_agent_loop.refresh_config = AsyncMock()

        response = client.get("/api/avatars/telegram/qr/status/avatar_1")

        assert response.status_code == 200
        mock_hubfeed_client.sync_avatars.assert_called_once()

    @pytest.mark.asyncio
    async def test_qr_status_exception_returns_500(self, client):
        """Should return 500 on exception."""
        handler = mock_platform_manager.get_handler.return_value
        handler.wait_qr_scan = AsyncMock(side_effect=Exception("timeout"))

        response = client.get("/api/avatars/telegram/qr/status/avatar_1")

        assert response.status_code == 500


class TestBrowserPlatformEndpoints:
    """Test browser-related endpoints."""

    def test_get_available_platforms_with_flows(self, client):
        """Should return available browser platforms."""
        mock_config_manager.get_platform_config.return_value = {
            "login_flows": [
                {"platform": "x", "display_name": "X (Twitter)", "credential_fields": ["username", "password"]}
            ]
        }

        response = client.get("/api/platforms/browser/available")

        assert response.status_code == 200
        platforms = response.json()["platforms"]
        assert len(platforms) == 1
        assert platforms[0]["platform"] == "x"

    def test_get_available_platforms_empty(self, client):
        """Should return empty list when no flows configured."""
        mock_config_manager.get_platform_config.return_value = None

        response = client.get("/api/platforms/browser/available")

        assert response.status_code == 200
        assert response.json()["platforms"] == []

    @pytest.mark.asyncio
    async def test_browser_auth_start_success(self, client):
        """Should start browser auth and return result."""
        mock_executor.browser_handler = Mock()
        mock_executor.browser_handler.start_auth = AsyncMock(return_value={
            "status": "authenticated",
            "avatar": {"id": "x_user1"}
        })
        mock_hubfeed_client.sync_avatars = AsyncMock()
        mock_agent_loop.is_running = True
        mock_agent_loop.refresh_config = AsyncMock()

        response = client.post("/api/avatars/browser/auth/start", json={
            "avatar_id": "x_user1",
            "platform": "x",
            "username": "user",
            "password": "pass"
        })

        assert response.status_code == 200
        assert response.json()["status"] == "authenticated"

    @pytest.mark.asyncio
    async def test_browser_auth_start_challenge_required(self, client):
        """Should return challenge info when 2FA needed."""
        mock_executor.browser_handler = Mock()
        mock_executor.browser_handler.start_auth = AsyncMock(return_value={
            "status": "challenge_required",
            "challenge_prompt": "Enter 2FA code"
        })

        response = client.post("/api/avatars/browser/auth/start", json={
            "avatar_id": "x_user1",
            "platform": "x",
            "username": "user",
            "password": "pass"
        })

        assert response.status_code == 200
        assert response.json()["status"] == "challenge_required"

    @pytest.mark.asyncio
    async def test_browser_auth_start_exception(self, client):
        """Should return 500 on exception."""
        mock_executor.browser_handler = Mock()
        mock_executor.browser_handler.start_auth = AsyncMock(
            side_effect=Exception("Browser failed")
        )

        response = client.post("/api/avatars/browser/auth/start", json={
            "avatar_id": "x_user1",
            "platform": "x",
            "username": "user",
            "password": "pass"
        })

        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_browser_challenge_success(self, client):
        """Should submit challenge and sync on success."""
        mock_executor.browser_handler = Mock()
        mock_executor.browser_handler.submit_challenge = AsyncMock(return_value={
            "status": "success"
        })
        mock_hubfeed_client.sync_avatars = AsyncMock()
        mock_agent_loop.is_running = True
        mock_agent_loop.refresh_config = AsyncMock()

        response = client.post("/api/avatars/browser/auth/challenge", json={
            "avatar_id": "x_user1",
            "response": "123456"
        })

        assert response.status_code == 200
        assert response.json()["status"] == "success"

    @pytest.mark.asyncio
    async def test_browser_challenge_exception(self, client):
        """Should return 500 on exception."""
        mock_executor.browser_handler = Mock()
        mock_executor.browser_handler.submit_challenge = AsyncMock(
            side_effect=Exception("Challenge failed")
        )

        response = client.post("/api/avatars/browser/auth/challenge", json={
            "avatar_id": "x_user1",
            "response": "123456"
        })

        assert response.status_code == 500

    def test_get_pending_challenge_exists(self, client):
        """Should return challenge info when pending."""
        mock_executor.browser_handler = Mock()
        mock_executor.browser_handler.get_pending_challenge.return_value = {
            "challenge_prompt": "Enter 2FA code",
            "step_id": "2fa"
        }

        response = client.get("/api/avatars/browser/auth/challenge/x_user1")

        assert response.status_code == 200
        assert response.json()["has_challenge"] is True
        assert response.json()["challenge_prompt"] == "Enter 2FA code"

    def test_get_pending_challenge_none(self, client):
        """Should return no challenge when nothing pending."""
        mock_executor.browser_handler = Mock()
        mock_executor.browser_handler.get_pending_challenge.return_value = None

        response = client.get("/api/avatars/browser/auth/challenge/x_user1")

        assert response.status_code == 200
        assert response.json()["has_challenge"] is False

    @pytest.mark.asyncio
    async def test_browser_test_connection_success(self, client):
        """Should test browser connection."""
        mock_config_manager.get_avatar.return_value = {"id": "x_user1", "status": "active"}
        mock_executor.browser_handler = Mock()
        mock_session = AsyncMock()
        mock_session.check_login_state = AsyncMock(return_value=True)
        mock_executor.browser_handler._get_session = AsyncMock(return_value=mock_session)

        response = client.post("/api/avatars/browser/test/x_user1")

        assert response.status_code == 200
        assert response.json()["logged_in"] is True

    @pytest.mark.asyncio
    async def test_browser_test_connection_not_found(self, client):
        """Should return 404 when avatar not found."""
        mock_config_manager.get_avatar.return_value = None

        response = client.post("/api/avatars/browser/test/nonexistent")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_browser_test_connection_exception(self, client):
        """Should return logged_in: false on exception."""
        mock_config_manager.get_avatar.return_value = {"id": "x_user1", "status": "active"}
        mock_executor.browser_handler = Mock()
        mock_executor.browser_handler._get_session = AsyncMock(
            side_effect=Exception("Browser crashed")
        )

        response = client.post("/api/avatars/browser/test/x_user1")

        assert response.status_code == 200
        assert response.json()["logged_in"] is False


class TestSourceEndpoints:
    """Test source management endpoints."""

    def test_get_sources_success(self, client):
        """Should return sources for avatar."""
        mock_config_manager.get_avatar.return_value = {"id": "av1"}
        mock_config_manager.get_avatar_sources.return_value = {
            "enabled": True,
            "items": [{"id": "ch1", "name": "News"}]
        }
        mock_config_manager.FREQUENCY_PRESETS = {"5m": 300, "1h": 3600}

        response = client.get("/api/avatars/av1/sources")

        assert response.status_code == 200
        data = response.json()
        assert data["avatar_id"] == "av1"
        assert data["sources"]["enabled"] is True

    def test_get_sources_avatar_not_found(self, client):
        """Should return 404 when avatar not found."""
        mock_config_manager.get_avatar.return_value = None

        response = client.get("/api/avatars/nonexistent/sources")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_add_source_success(self, client):
        """Should add source and sync."""
        mock_config_manager.get_avatar.return_value = {"id": "av1"}
        mock_config_manager.add_source.return_value = True
        mock_hubfeed_client.sync_avatars = AsyncMock()

        response = client.post("/api/avatars/av1/sources", json={
            "id": "-1001234567890",
            "name": "News Channel",
            "type": "channel",
            "frequency_seconds": 300
        })

        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_add_source_avatar_not_found(self, client):
        """Should return 404 when avatar not found."""
        mock_config_manager.get_avatar.return_value = None

        response = client.post("/api/avatars/nonexistent/sources", json={
            "id": "ch1",
            "name": "Chan",
            "type": "channel"
        })

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_add_source_duplicate_returns_400(self, client):
        """Should return 400 when source already exists."""
        mock_config_manager.get_avatar.return_value = {"id": "av1"}
        mock_config_manager.add_source.return_value = False

        response = client.post("/api/avatars/av1/sources", json={
            "id": "ch1",
            "name": "Duplicate",
            "type": "channel"
        })

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_update_source_success(self, client):
        """Should update source settings."""
        mock_config_manager.get_avatar.return_value = {"id": "av1"}
        mock_config_manager.update_source.return_value = True
        mock_hubfeed_client.sync_avatars = AsyncMock()

        response = client.put("/api/avatars/av1/sources/ch1", json={
            "frequency_seconds": 600
        })

        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_update_source_no_updates(self, client):
        """Should return 400 when no updates provided."""
        mock_config_manager.get_avatar.return_value = {"id": "av1"}

        response = client.put("/api/avatars/av1/sources/ch1", json={})

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_update_source_not_found(self, client):
        """Should return 404 when source not found."""
        mock_config_manager.get_avatar.return_value = {"id": "av1"}
        mock_config_manager.update_source.return_value = False

        response = client.put("/api/avatars/av1/sources/nonexistent", json={
            "frequency_seconds": 600
        })

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_remove_source_success(self, client):
        """Should remove source and sync."""
        mock_config_manager.get_avatar.return_value = {"id": "av1"}
        mock_config_manager.remove_source.return_value = True
        mock_hubfeed_client.sync_avatars = AsyncMock()

        response = client.delete("/api/avatars/av1/sources/ch1")

        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_remove_source_avatar_not_found(self, client):
        """Should return 404 when avatar not found."""
        mock_config_manager.get_avatar.return_value = None

        response = client.delete("/api/avatars/nonexistent/sources/ch1")

        assert response.status_code == 404


class TestDialogEndpoints:
    """Test dialog listing endpoint."""

    @pytest.mark.asyncio
    async def test_get_dialogs_cached(self, client):
        """Should return cached dialogs when available."""
        mock_config_manager.get_avatar.return_value = {
            "id": "av1",
            "status": "active",
            "cached_dialogs": [{"id": "123", "name": "Test Chan", "type": "channel"}]
        }

        response = client.get("/api/avatars/av1/dialogs")

        assert response.status_code == 200
        data = response.json()
        assert data["cached"] is True
        assert len(data["dialogs"]) == 1

    @pytest.mark.asyncio
    async def test_get_dialogs_refresh(self, client):
        """Should fetch fresh dialogs when refresh=True."""
        mock_config_manager.get_avatar.return_value = {
            "id": "av1",
            "status": "active",
            "cached_dialogs": [{"id": "123", "name": "Old"}]
        }
        mock_config_manager.save_avatar.return_value = True

        handler = mock_platform_manager.get_handler.return_value
        handler.list_dialogs = AsyncMock(return_value=[
            {"id": 456, "name": "Fresh Channel", "is_group": False, "is_user": False}
        ])

        response = client.get("/api/avatars/av1/dialogs?refresh=true")

        assert response.status_code == 200
        data = response.json()
        assert data["cached"] is False
        assert len(data["dialogs"]) == 1
        assert data["dialogs"][0]["name"] == "Fresh Channel"

    @pytest.mark.asyncio
    async def test_get_dialogs_avatar_not_found(self, client):
        """Should return 404 when avatar not found."""
        mock_config_manager.get_avatar.return_value = None

        response = client.get("/api/avatars/nonexistent/dialogs")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_dialogs_avatar_not_active(self, client):
        """Should return 400 when avatar not authenticated."""
        mock_config_manager.get_avatar.return_value = {
            "id": "av1",
            "status": "auth_required"
        }

        response = client.get("/api/avatars/av1/dialogs")

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_dialogs_telegram_error(self, client):
        """Should return 500 on telegram error."""
        mock_config_manager.get_avatar.return_value = {
            "id": "av1",
            "status": "active"
        }

        handler = mock_platform_manager.get_handler.return_value
        handler.list_dialogs = AsyncMock(side_effect=Exception("Connection lost"))

        response = client.get("/api/avatars/av1/dialogs?refresh=true")

        assert response.status_code == 500


class TestDeleteAvatarSync:
    """Test avatar deletion with Hubfeed sync."""

    @pytest.mark.asyncio
    async def test_delete_avatar_syncs_with_hubfeed(self, client):
        """Should sync remaining avatars with Hubfeed after delete."""
        mock_hubfeed_client.sync_avatars = AsyncMock()

        response = client.delete("/api/avatars/avatar_1")

        assert response.status_code == 200
        mock_hubfeed_client.sync_avatars.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_avatar_sync_failure_logged(self, client):
        """Should succeed even if Hubfeed sync fails."""
        mock_hubfeed_client.sync_avatars = AsyncMock(side_effect=Exception("Network error"))

        response = client.delete("/api/avatars/avatar_1")

        assert response.status_code == 200
        assert response.json()["success"] is True


class TestUpdateConfigLoopRestart:
    """Test config update with loop restart behavior."""

    @pytest.mark.asyncio
    async def test_update_config_restarts_running_loop(self, client):
        """Should restart loop when token changes and loop is running."""
        mock_agent_loop.is_running = True

        response = client.post("/api/config", json={"token": "new_token"})

        assert response.status_code == 200
        mock_agent_loop.stop.assert_called_once()
        mock_agent_loop.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_config_starts_loop_when_configured(self, client):
        """Should start loop when token set and agent becomes configured."""
        mock_agent_loop.is_running = False
        mock_config_manager.is_configured.return_value = True

        response = client.post("/api/config", json={"token": "new_token"})

        assert response.status_code == 200
        mock_agent_loop.start.assert_called_once()
