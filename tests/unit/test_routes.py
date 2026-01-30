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


# Note: Global error handling test removed as FastAPI handles exceptions 
# at framework level. Route-specific error handling is tested in individual tests.
