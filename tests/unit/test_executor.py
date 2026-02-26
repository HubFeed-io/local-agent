"""
Unit tests for job executor.

Tests the JobExecutor class which dispatches jobs to platform handlers
and applies blacklist filtering.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
from datetime import datetime

# Add src to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.executor import JobExecutor


@pytest.fixture
def mock_config_manager(tmp_path):
    """Mock ConfigManager for testing."""
    manager = Mock()
    manager.data_dir = str(tmp_path)
    manager.get_avatar_blacklist.return_value = {
        "keywords": [],
        "senders": [],
        "channels": []
    }
    return manager


@pytest.fixture
def mock_history_logger():
    """Mock HistoryLogger for testing."""
    logger = Mock()
    logger.log_job = AsyncMock()
    return logger


@pytest.fixture
def executor(mock_config_manager, mock_history_logger):
    """Fixture providing a JobExecutor instance."""
    return JobExecutor(mock_config_manager, mock_history_logger)


@pytest.fixture
def sample_job():
    """Sample job data."""
    return {
        "job_id": "job_test_123",
        "avatar_id": "avatar_test_456",
        "command": "telegram.get_messages",
        "params": {
            "channel": "@test_channel",
            "limit": 100
        }
    }


@pytest.fixture
def sample_telegram_messages():
    """Sample Telegram message data."""
    return [
        {
            "id": 1001,
            "date": datetime.utcnow().isoformat(),
            "message": "Test message 1",
            "from_id": "user_123"
        },
        {
            "id": 1002,
            "date": datetime.utcnow().isoformat(),
            "message": "Test message 2 with spam",
            "from_id": "user_456"
        },
        {
            "id": 1003,
            "date": datetime.utcnow().isoformat(),
            "message": "Test message 3",
            "from_id": "user_789"
        }
    ]


class TestJobExecutorInit:
    """Test JobExecutor initialization."""
    
    def test_init_creates_handlers(self, mock_config_manager, mock_history_logger):
        """Should initialize with platform handlers and blacklist filter."""
        executor = JobExecutor(mock_config_manager, mock_history_logger)
        
        assert executor.config_manager == mock_config_manager
        assert executor.history_logger == mock_history_logger
        assert executor.telegram_handler is not None
        assert executor.browser_handler is not None
        assert executor.blacklist_filter is not None


class TestExecuteJob:
    """Test job execution."""
    
    @pytest.mark.asyncio
    async def test_execute_job_success(
        self, 
        executor, 
        sample_job, 
        sample_telegram_messages,
        mock_history_logger
    ):
        """Should execute job successfully and return results."""
        # Mock telegram handler
        executor.telegram_handler.execute = AsyncMock(return_value=sample_telegram_messages)
        
        result = await executor.execute_job(sample_job)
        
        assert result["success"] is True
        assert result["job_id"] == "job_test_123"
        assert result["avatar_id"] == "avatar_test_456"
        assert result["command"] == "telegram.get_messages"
        assert result["items_count"] == 3
        assert result["raw_data"] == sample_telegram_messages
        assert result["execution_ms"] >= 0  # Can be 0 for very fast executions
        assert "timestamp" in result
        
        # Verify history was logged
        mock_history_logger.log_job.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_job_with_blacklist_filtering(
        self, 
        executor, 
        sample_job,
        sample_telegram_messages,
        mock_config_manager
    ):
        """Should apply blacklist filtering to results."""
        # Setup blacklist
        mock_config_manager.get_avatar_blacklist.return_value = {
            "keywords": ["spam"],
            "senders": [],
            "channels": []
        }
        
        # Mock telegram handler
        executor.telegram_handler.execute = AsyncMock(return_value=sample_telegram_messages)
        
        result = await executor.execute_job(sample_job)
        
        assert result["success"] is True
        assert result["filtered_count"] == 1  # One message with "spam"
        assert result["items_count"] == 2  # Two messages remaining
        assert len(result["raw_data"]) == 2
    
    @pytest.mark.asyncio
    async def test_execute_job_unknown_command(self, executor, sample_job):
        """Should fail with unknown command platform."""
        sample_job["command"] = "unknown.command"
        
        result = await executor.execute_job(sample_job)
        
        assert result["success"] is False
        assert "error" in result
        assert result["error"]["type"] == "ValueError"
        assert "Unknown command platform" in result["error"]["message"]
    
    @pytest.mark.asyncio
    async def test_execute_job_handler_exception(self, executor, sample_job):
        """Should handle exceptions from platform handlers."""
        # Mock telegram handler to raise exception
        executor.telegram_handler.execute = AsyncMock(
            side_effect=Exception("Connection failed")
        )
        
        result = await executor.execute_job(sample_job)
        
        assert result["success"] is False
        assert "error" in result
        assert result["error"]["type"] == "Exception"
        assert "Connection failed" in result["error"]["message"]
    
    @pytest.mark.asyncio
    async def test_execute_job_non_message_command(self, executor, sample_telegram_messages):
        """Should not apply blacklist to non-message commands."""
        job = {
            "job_id": "job_test_999",
            "avatar_id": "avatar_test_456",
            "command": "telegram.get_channel_info",
            "params": {"channel": "@test"}
        }

        executor.telegram_handler.execute = AsyncMock(return_value=sample_telegram_messages)

        result = await executor.execute_job(job)

        assert result["success"] is True
        assert result["filtered_count"] == 0  # No filtering applied
        assert result["items_count"] == 3  # All messages returned

    @pytest.mark.asyncio
    async def test_execute_job_browser_command(self, executor, mock_history_logger):
        """Should dispatch browser.* commands to browser_handler."""
        job = {
            "job_id": "job_browser_1",
            "avatar_id": "avatar_browser_1",
            "command": "browser.xhr_capture",
            "params": {"url": "https://example.com"}
        }

        mock_data = [{"type": "xhr", "url": "https://api.example.com", "data": {}}]
        executor.browser_handler.execute = AsyncMock(return_value=mock_data)

        result = await executor.execute_job(job)

        assert result["success"] is True
        assert result["job_id"] == "job_browser_1"
        assert result["items_count"] == 1
        executor.browser_handler.execute.assert_called_once_with(
            "avatar_browser_1", "browser.xhr_capture", {"url": "https://example.com"}
        )
        mock_history_logger.log_job.assert_called_once()


class TestBlacklistFiltering:
    """Test blacklist filtering logic."""
    
    def test_apply_blacklist_no_rules(self, executor, sample_telegram_messages):
        """Should return all data when no blacklist rules."""
        filtered, count = executor._apply_blacklist(
            "avatar_123",
            sample_telegram_messages,
            "telegram.get_messages"
        )
        
        assert count == 0
        assert len(filtered) == 3
    
    def test_apply_blacklist_with_keyword_filter(
        self, 
        executor, 
        sample_telegram_messages,
        mock_config_manager
    ):
        """Should filter messages matching keyword rules."""
        mock_config_manager.get_avatar_blacklist.return_value = {
            "keywords": ["spam"],
            "senders": [],
            "channels": []
        }
        
        filtered, count = executor._apply_blacklist(
            "avatar_123",
            sample_telegram_messages,
            "telegram.get_messages"
        )
        
        assert count == 1  # One message filtered
        assert len(filtered) == 2  # Two messages remain
    
    def test_apply_blacklist_non_message_command(self, executor, sample_telegram_messages):
        """Should skip filtering for non-message commands."""
        filtered, count = executor._apply_blacklist(
            "avatar_123",
            sample_telegram_messages,
            "telegram.get_channel_info"  # Not a message command
        )
        
        assert count == 0
        assert len(filtered) == 3  # All data returned


class TestHistoryLogging:
    """Test history logging."""
    
    @pytest.mark.asyncio
    async def test_log_to_history_success(self, executor, sample_job, mock_history_logger):
        """Should log successful execution to history."""
        result = {
            "job_id": "job_test_123",
            "avatar_id": "avatar_test_456",
            "command": "telegram.get_messages",
            "success": True,
            "items_count": 10,
            "filtered_count": 2,
            "execution_ms": 1234
        }
        
        await executor._log_to_history(sample_job, result)
        
        mock_history_logger.log_job.assert_called_once_with(
            job_id="job_test_123",
            avatar_id="avatar_test_456",
            command="telegram.get_messages",
            params=sample_job["params"],
            success=True,
            items_count=10,
            filtered_count=2,
            execution_ms=1234,
            error=None
        )
    
    @pytest.mark.asyncio
    async def test_log_to_history_failure(self, executor, sample_job, mock_history_logger):
        """Should log failed execution to history."""
        result = {
            "job_id": "job_test_123",
            "avatar_id": "avatar_test_456",
            "command": "telegram.get_messages",
            "success": False,
            "error": {
                "type": "Exception",
                "message": "Failed"
            },
            "execution_ms": 500
        }
        
        await executor._log_to_history(sample_job, result)
        
        mock_history_logger.log_job.assert_called_once()
        call_kwargs = mock_history_logger.log_job.call_args[1]
        assert call_kwargs["success"] is False
        assert call_kwargs["error"]["type"] == "Exception"
    
    @pytest.mark.asyncio
    async def test_log_to_history_exception_handling(
        self, 
        executor, 
        sample_job,
        mock_history_logger
    ):
        """Should handle exceptions during history logging gracefully."""
        mock_history_logger.log_job.side_effect = Exception("Logging failed")
        
        result = {
            "job_id": "job_test_123",
            "success": True,
            "items_count": 5,
            "filtered_count": 0,
            "execution_ms": 1000
        }
        
        # Should not raise exception
        await executor._log_to_history(sample_job, result)


class TestCleanup:
    """Test cleanup operations."""
    
    @pytest.mark.asyncio
    async def test_cleanup_disconnects_handlers(self, executor):
        """Should disconnect platform handlers during cleanup."""
        executor.telegram_handler.disconnect_all = AsyncMock()
        executor.browser_handler.disconnect_all = AsyncMock()

        await executor.cleanup()

        executor.telegram_handler.disconnect_all.assert_called_once()
        executor.browser_handler.disconnect_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_handles_exceptions(self, executor):
        """Should handle exceptions during cleanup gracefully."""
        executor.telegram_handler.disconnect_all = AsyncMock(
            side_effect=Exception("Disconnect failed")
        )
        executor.browser_handler.disconnect_all = AsyncMock(
            side_effect=Exception("Browser disconnect failed")
        )

        # Should not raise exception
        await executor.cleanup()


class TestIntegration:
    """Integration tests for JobExecutor."""
    
    @pytest.mark.asyncio
    async def test_complete_job_workflow(
        self, 
        executor,
        sample_telegram_messages,
        mock_config_manager,
        mock_history_logger
    ):
        """Test complete job execution workflow."""
        # Setup
        job = {
            "job_id": "job_integration_test",
            "avatar_id": "avatar_test",
            "command": "telegram.get_messages",
            "params": {"channel": "@test", "limit": 10}
        }
        
        mock_config_manager.get_avatar_blacklist.return_value = {
            "keywords": ["spam"],
            "senders": [],
            "channels": []
        }
        
        executor.telegram_handler.execute = AsyncMock(return_value=sample_telegram_messages)
        
        # Execute
        result = await executor.execute_job(job)
        
        # Verify
        assert result["success"] is True
        assert result["job_id"] == "job_integration_test"
        assert result["filtered_count"] == 1
        assert len(result["raw_data"]) == 2
        
        # Verify history was logged
        mock_history_logger.log_job.assert_called_once()
