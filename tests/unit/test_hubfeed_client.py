"""
Unit tests for Hubfeed HTTP client.

Tests the HubfeedClient class which communicates with the Hubfeed backend API.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
from datetime import datetime
import httpx

# Add src to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.hubfeed_client import HubfeedClient


@pytest.fixture
def mock_config_manager():
    """Mock ConfigManager for testing."""
    manager = Mock()
    manager.get_config.return_value = {
        "token": "test_token_abc123"
    }
    manager.update_config = Mock(return_value=True)
    return manager


@pytest.fixture
def client(mock_config_manager):
    """Fixture providing a HubfeedClient instance."""
    return HubfeedClient(mock_config_manager)


@pytest.fixture
def mock_http_response():
    """Factory for creating mock HTTP responses."""
    def _create_response(status_code=200, json_data=None, headers=None):
        response = Mock(spec=httpx.Response)
        response.status_code = status_code
        response.json.return_value = json_data or {}
        response.headers = headers or {}
        response.raise_for_status = Mock()
        
        if status_code >= 400:
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                message=f"HTTP {status_code}",
                request=Mock(),
                response=response
            )
        
        return response
    return _create_response


class TestHubfeedClientInit:
    """Test HubfeedClient initialization."""
    
    def test_init_with_config_manager(self, mock_config_manager):
        """Should initialize with config manager."""
        client = HubfeedClient(mock_config_manager)
        
        assert client.config_manager == mock_config_manager
        assert client._client is None


class TestGetClient:
    """Test HTTP client creation and management."""
    
    @pytest.mark.asyncio
    async def test_get_client_creates_new_client(self, client, mock_config_manager):
        """Should create new HTTP client with proper configuration."""
        http_client = await client._get_client()

        assert http_client is not None
        assert isinstance(http_client, httpx.AsyncClient)
        assert str(http_client.base_url) == "https://hubfeed.io"
        assert "Authorization" in http_client.headers
        assert http_client.headers["Authorization"] == "Bearer test_token_abc123"

    @pytest.mark.asyncio
    async def test_get_client_uses_env_var(self, client):
        """Should use HUBFEED_API_URL env var when set."""
        import os
        with patch.dict(os.environ, {"HUBFEED_API_URL": "https://custom.hubfeed.io"}):
            # Force new client creation
            client._client = None
            http_client = await client._get_client()

        assert str(http_client.base_url) == "https://custom.hubfeed.io"
    
    @pytest.mark.asyncio
    async def test_get_client_reuses_existing_client(self, client):
        """Should reuse existing HTTP client if not closed."""
        client1 = await client._get_client()
        client2 = await client._get_client()
        
        assert client1 is client2
    
    @pytest.mark.asyncio
    async def test_get_client_includes_user_agent(self, client):
        """Should include user agent and version headers."""
        http_client = await client._get_client()
        
        assert "User-Agent" in http_client.headers
        assert "HubfeedAgent" in http_client.headers["User-Agent"]
        assert "X-Agent-Version" in http_client.headers
        assert "X-Agent-Capabilities" in http_client.headers
    
    @pytest.mark.asyncio
    async def test_close_client(self, client):
        """Should close HTTP client properly."""
        http_client = await client._get_client()
        await client.close()
        
        assert client._client is None


class TestVerifyToken:
    """Test token verification."""
    
    @pytest.mark.asyncio
    async def test_verify_token_success(self, client, mock_http_response, mock_config_manager):
        """Should verify token successfully."""
        response_data = {
            "success": True,
            "user": {
                "email": "test@example.com",
                "id": "user_123"
            },
            "config": {
                "polling_interval_seconds": 30
            }
        }
        
        mock_response = mock_http_response(200, response_data)
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            result = await client.verify_token()
        
        assert result["success"] is True
        assert result["user"]["email"] == "test@example.com"
        
        # Should update local config
        mock_config_manager.update_config.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_verify_token_invalid_token(self, client, mock_http_response):
        """Should handle 401 unauthorized error."""
        mock_response = mock_http_response(401, {"error": "Invalid token"})
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            with pytest.raises(httpx.HTTPStatusError):
                await client.verify_token()
    
    @pytest.mark.asyncio
    async def test_verify_token_revoked(self, client, mock_http_response):
        """Should handle 403 forbidden error."""
        mock_response = mock_http_response(403, {"error": "Token revoked"})
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            with pytest.raises(httpx.HTTPStatusError):
                await client.verify_token()
    
    @pytest.mark.asyncio
    async def test_verify_token_network_error(self, client):
        """Should handle network errors."""
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection failed")
            )
            mock_get_client.return_value = mock_http_client
            
            with pytest.raises(httpx.ConnectError):
                await client.verify_token()


class TestSyncAvatars:
    """Test avatar synchronization."""
    
    @pytest.mark.asyncio
    async def test_sync_avatars_success(self, client, mock_http_response):
        """Should sync avatars successfully."""
        avatars = [
            {
                "id": "avatar_1",
                "name": "Test Avatar 1",
                "platform": "telegram",
                "status": "active",
                "phone": "+1234567890",
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "id": "avatar_2",
                "name": "Test Avatar 2",
                "platform": "telegram",
                "status": "inactive",
                "created_at": datetime.utcnow().isoformat()
            }
        ]
        
        response_data = {
            "success": True,
            "synced": 2
        }
        
        mock_response = mock_http_response(200, response_data)
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            result = await client.sync_avatars(avatars)
        
        assert result["success"] is True
        assert result["synced"] == 2
        
        # Verify the call was made with sanitized data (no session_string)
        call_args = mock_http_client.post.call_args
        sent_data = call_args[1]["json"]
        assert len(sent_data["avatars"]) == 2
        assert "session_string" not in str(sent_data)
    
    @pytest.mark.asyncio
    async def test_sync_avatars_empty_list(self, client, mock_http_response):
        """Should handle empty avatar list."""
        response_data = {"success": True, "synced": 0}
        mock_response = mock_http_response(200, response_data)
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            result = await client.sync_avatars([])
        
        assert result["success"] is True
    
    @pytest.mark.asyncio
    async def test_sync_avatars_network_error(self, client):
        """Should handle network errors during sync."""
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection failed")
            )
            mock_get_client.return_value = mock_http_client
            
            with pytest.raises(httpx.ConnectError):
                await client.sync_avatars([{"id": "test"}])


class TestGetTasks:
    """Test task polling."""
    
    @pytest.mark.asyncio
    async def test_get_tasks_with_tasks(self, client, mock_http_response):
        """Should retrieve pending tasks."""
        tasks_data = [
            {
                "job_id": "job_1",
                "avatar_id": "avatar_1",
                "command": "telegram.get_messages",
                "params": {"channel": "@test", "limit": 100}
            },
            {
                "job_id": "job_2",
                "avatar_id": "avatar_2",
                "command": "telegram.get_channel_info",
                "params": {"channel": "@test"}
            }
        ]
        
        response_data = {"tasks": tasks_data}
        mock_response = mock_http_response(200, response_data)
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            result = await client.get_tasks()
        
        assert len(result) == 2
        assert result[0]["job_id"] == "job_1"
        assert result[1]["job_id"] == "job_2"
    
    @pytest.mark.asyncio
    async def test_get_tasks_empty(self, client, mock_http_response):
        """Should handle empty task list."""
        response_data = {"tasks": []}
        mock_response = mock_http_response(200, response_data)
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            result = await client.get_tasks()
        
        assert result == []
    
    @pytest.mark.asyncio
    async def test_get_tasks_upgrade_required(self, client, mock_http_response):
        """Should detect upgrade requirement from headers."""
        response_data = {"tasks": []}
        mock_response = mock_http_response(
            200, 
            response_data,
            headers={"X-Upgrade-Required": "true"}
        )
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            result = await client.get_tasks()
        
        # Should still return tasks
        assert result == []
    
    @pytest.mark.asyncio
    async def test_get_tasks_unauthorized(self, client, mock_http_response):
        """Should handle unauthorized error."""
        mock_response = mock_http_response(401, {"error": "Unauthorized"})
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            with pytest.raises(httpx.HTTPStatusError):
                await client.get_tasks()


class TestSubmitResult:
    """Test result submission."""
    
    @pytest.mark.asyncio
    async def test_submit_result_success(self, client, mock_http_response):
        """Should submit successful job result."""
        raw_data = [
            {"id": 1, "message": "Test 1"},
            {"id": 2, "message": "Test 2"}
        ]
        
        response_data = {"success": True, "received": True}
        mock_response = mock_http_response(200, response_data)
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            result = await client.submit_result(
                job_id="job_123",
                success=True,
                raw_data=raw_data,
                filtered_count=1,
                execution_ms=1234
            )
        
        assert result["success"] is True
        
        # Verify payload structure
        call_args = mock_http_client.post.call_args
        payload = call_args[1]["json"]
        assert payload["job_id"] == "job_123"
        assert payload["success"] is True
        assert payload["items_count"] == 2
        assert payload["filtered_count"] == 1
        assert payload["execution_ms"] == 1234
        assert "timestamp" in payload
    
    @pytest.mark.asyncio
    async def test_submit_result_failure(self, client, mock_http_response):
        """Should submit failed job result."""
        error = {
            "type": "ValueError",
            "message": "Invalid command"
        }
        
        response_data = {"success": True}
        mock_response = mock_http_response(200, response_data)
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            result = await client.submit_result(
                job_id="job_456",
                success=False,
                error=error,
                execution_ms=500
            )
        
        # Verify error is included in payload
        call_args = mock_http_client.post.call_args
        payload = call_args[1]["json"]
        assert payload["success"] is False
        assert payload["error"]["type"] == "ValueError"
    
    @pytest.mark.asyncio
    async def test_submit_result_network_error(self, client):
        """Should handle network errors during submission."""
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(
                side_effect=httpx.TimeoutException("Request timed out")
            )
            mock_get_client.return_value = mock_http_client
            
            with pytest.raises(httpx.TimeoutException):
                await client.submit_result(
                    job_id="job_789",
                    success=True,
                    raw_data=[],
                    execution_ms=5000
                )


class TestHealthCheck:
    """Test health check."""
    
    @pytest.mark.asyncio
    async def test_health_check_success(self, client, mock_http_response):
        """Should return True when backend is reachable."""
        mock_response = mock_http_response(200, {"status": "ok"})
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client
            
            result = await client.health_check()
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_health_check_failure(self, client):
        """Should return False when backend is unreachable."""
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_get_client.return_value = mock_http_client
            
            result = await client.health_check()
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_health_check_timeout(self, client):
        """Should return False on timeout."""
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(
                side_effect=httpx.TimeoutException("Timeout")
            )
            mock_get_client.return_value = mock_http_client
            
            result = await client.health_check()
        
        assert result is False


class TestIntegration:
    """Integration tests for HubfeedClient."""
    
    @pytest.mark.asyncio
    async def test_complete_workflow(self, client, mock_http_response):
        """Test complete client workflow."""
        # 1. Verify token
        verify_response = mock_http_response(200, {
            "success": True,
            "user": {"email": "test@example.com"}
        })
        
        # 2. Sync avatars
        sync_response = mock_http_response(200, {"success": True, "synced": 1})
        
        # 3. Get tasks
        tasks_response = mock_http_response(200, {
            "tasks": [{"job_id": "job_1", "command": "test"}]
        })
        
        # 4. Submit result
        submit_response = mock_http_response(200, {"success": True})
        
        with patch.object(client, '_get_client') as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(
                side_effect=[verify_response, sync_response, submit_response]
            )
            mock_http_client.get = AsyncMock(return_value=tasks_response)
            mock_get_client.return_value = mock_http_client
            
            # Execute workflow
            await client.verify_token()
            await client.sync_avatars([{"id": "test"}])
            tasks = await client.get_tasks()
            await client.submit_result("job_1", True, raw_data=[], execution_ms=100)
            
            assert len(tasks) == 1
