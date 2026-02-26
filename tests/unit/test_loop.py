"""
Unit tests for agent polling loop.

Tests the AgentLoop class which manages the main polling loop
for communicating with Hubfeed backend.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
from datetime import datetime, timedelta
import asyncio

# Add src to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.loop import AgentLoop


@pytest.fixture
def mock_config_manager():
    """Mock ConfigManager for testing."""
    manager = Mock()
    manager.is_configured.return_value = True
    manager.is_verified.return_value = True
    manager.get_avatars.return_value = []
    manager.get_polling_interval.return_value = 30
    manager.get_platform_config.return_value = {}
    return manager


@pytest.fixture
def mock_hubfeed_client():
    """Mock HubfeedClient for testing."""
    client = Mock()
    client.verify_token = AsyncMock(return_value={"user": {"email": "test@example.com"}})
    client.sync_avatars = AsyncMock(return_value={"success": True})
    client.get_tasks = AsyncMock(return_value=[])
    client.submit_result = AsyncMock(return_value={"success": True})
    client.health_check = AsyncMock(return_value=True)
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_executor():
    """Mock JobExecutor for testing."""
    executor = Mock()
    executor.execute_job = AsyncMock(return_value={
        "job_id": "test_job",
        "avatar_id": "avatar_1",
        "success": True,
        "raw_data": [],
        "execution_ms": 100
    })
    executor.cleanup = AsyncMock()
    return executor


@pytest.fixture
def agent_loop(mock_config_manager, mock_hubfeed_client, mock_executor):
    """Fixture providing an AgentLoop instance."""
    return AgentLoop(mock_config_manager, mock_hubfeed_client, mock_executor)


class TestAgentLoopInit:
    """Test AgentLoop initialization."""
    
    def test_init_with_dependencies(
        self, 
        mock_config_manager, 
        mock_hubfeed_client, 
        mock_executor
    ):
        """Should initialize with required dependencies."""
        loop = AgentLoop(mock_config_manager, mock_hubfeed_client, mock_executor)
        
        assert loop.config_manager == mock_config_manager
        assert loop.hubfeed_client == mock_hubfeed_client
        assert loop.executor == mock_executor
        assert loop._running is False
        assert loop._task is None
        assert loop._verified is False
        assert loop._last_avatar_sync is None
    
    def test_is_running_property(self, agent_loop):
        """Should provide is_running property."""
        assert agent_loop.is_running is False
        
        agent_loop._running = True
        assert agent_loop.is_running is True
    
    def test_is_verified_property(self, agent_loop):
        """Should provide is_verified property."""
        assert agent_loop.is_verified is False
        
        agent_loop._verified = True
        assert agent_loop.is_verified is True


class TestStartStop:
    """Test loop start and stop operations."""
    
    @pytest.mark.asyncio
    async def test_start_creates_task(self, agent_loop):
        """Should create and start polling task."""
        with patch.object(agent_loop, '_run', new_callable=AsyncMock) as mock_run:
            await agent_loop.start()
            
            assert agent_loop._running is True
            assert agent_loop._task is not None
            
            # Clean up
            await agent_loop.stop()
    
    @pytest.mark.asyncio
    async def test_start_when_already_running(self, agent_loop):
        """Should not start twice."""
        agent_loop._running = True
        
        await agent_loop.start()
        
        # Should still be running but not create duplicate tasks
        assert agent_loop._running is True
    
    @pytest.mark.asyncio
    async def test_stop_cancels_task(self, agent_loop, mock_executor, mock_hubfeed_client):
        """Should cancel running task and cleanup."""
        # Start the loop
        agent_loop._running = True
        agent_loop._task = asyncio.create_task(asyncio.sleep(10))
        
        await agent_loop.stop()
        
        assert agent_loop._running is False
        mock_executor.cleanup.assert_called_once()
        mock_hubfeed_client.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, agent_loop, mock_executor):
        """Should handle stop when not running."""
        await agent_loop.stop()
        
        # Should not call cleanup if not running
        mock_executor.cleanup.assert_not_called()


class TestTokenVerification:
    """Test token verification logic."""
    
    @pytest.mark.asyncio
    async def test_verify_token_success(
        self, 
        agent_loop, 
        mock_hubfeed_client,
        mock_config_manager
    ):
        """Should verify token successfully."""
        result = await agent_loop._verify_token()
        
        assert result is True
        assert agent_loop._verified is True
        mock_hubfeed_client.verify_token.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_verify_token_not_configured(
        self, 
        agent_loop,
        mock_config_manager,
        mock_hubfeed_client
    ):
        """Should fail if agent not configured."""
        mock_config_manager.is_configured.return_value = False
        
        result = await agent_loop._verify_token()
        
        assert result is False
        assert agent_loop._verified is False
        mock_hubfeed_client.verify_token.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_verify_token_api_error(
        self, 
        agent_loop,
        mock_hubfeed_client
    ):
        """Should handle verification errors."""
        mock_hubfeed_client.verify_token.side_effect = Exception("API Error")
        
        result = await agent_loop._verify_token()
        
        assert result is False
        assert agent_loop._verified is False


class TestAvatarSync:
    """Test avatar synchronization logic."""
    
    @pytest.mark.asyncio
    async def test_sync_avatars_success(
        self, 
        agent_loop,
        mock_config_manager,
        mock_hubfeed_client
    ):
        """Should sync avatars successfully."""
        mock_config_manager.get_avatars.return_value = [
            {"id": "avatar_1", "name": "Test"}
        ]
        
        await agent_loop._sync_avatars()
        
        assert agent_loop._last_avatar_sync is not None
        mock_hubfeed_client.sync_avatars.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_sync_avatars_empty_list(
        self, 
        agent_loop,
        mock_config_manager,
        mock_hubfeed_client
    ):
        """Should handle empty avatar list."""
        mock_config_manager.get_avatars.return_value = []
        
        await agent_loop._sync_avatars()
        
        # Should not call sync for empty list
        mock_hubfeed_client.sync_avatars.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_sync_avatars_error(
        self, 
        agent_loop,
        mock_config_manager,
        mock_hubfeed_client
    ):
        """Should handle sync errors gracefully."""
        mock_config_manager.get_avatars.return_value = [{"id": "test"}]
        mock_hubfeed_client.sync_avatars.side_effect = Exception("Sync failed")
        
        # Should not raise exception
        await agent_loop._sync_avatars()
    
    def test_should_sync_avatars_never_synced(self, agent_loop):
        """Should sync if never synced before."""
        agent_loop._last_avatar_sync = None
        
        assert agent_loop._should_sync_avatars() is True
    
    def test_should_sync_avatars_recent(self, agent_loop):
        """Should not sync if recently synced."""
        agent_loop._last_avatar_sync = datetime.utcnow()
        
        assert agent_loop._should_sync_avatars() is False
    
    def test_should_sync_avatars_old(self, agent_loop):
        """Should sync if last sync was > 5 minutes ago."""
        agent_loop._last_avatar_sync = datetime.utcnow() - timedelta(minutes=6)
        
        assert agent_loop._should_sync_avatars() is True


class TestPollCycle:
    """Test polling cycle logic."""
    
    @pytest.mark.asyncio
    async def test_poll_cycle_no_tasks(
        self, 
        agent_loop,
        mock_hubfeed_client
    ):
        """Should handle poll cycle with no tasks."""
        agent_loop._verified = True
        mock_hubfeed_client.get_tasks.return_value = []
        
        await agent_loop._poll_cycle()
        
        mock_hubfeed_client.get_tasks.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_poll_cycle_with_tasks(
        self, 
        agent_loop,
        mock_hubfeed_client,
        mock_executor
    ):
        """Should execute tasks in poll cycle."""
        agent_loop._verified = True
        agent_loop._running = True
        
        tasks = [
            {
                "job_id": "job_1",
                "avatar_id": "avatar_1",
                "command": "telegram.get_messages",
                "params": {}
            }
        ]
        mock_hubfeed_client.get_tasks.return_value = tasks
        
        mock_executor.execute_job.return_value = {
            "job_id": "job_1",
            "avatar_id": "avatar_1",
            "success": True,
            "raw_data": [],
            "filtered_count": 0,
            "execution_ms": 100
        }

        await agent_loop._poll_cycle()

        mock_executor.execute_job.assert_called_once_with(tasks[0])
        mock_hubfeed_client.submit_result.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_poll_cycle_submit_result_error(
        self, 
        agent_loop,
        mock_hubfeed_client,
        mock_executor
    ):
        """Should handle result submission errors."""
        agent_loop._verified = True
        agent_loop._running = True
        
        tasks = [{"job_id": "job_1", "avatar_id": "avatar_1", "command": "test", "params": {}}]
        mock_hubfeed_client.get_tasks.return_value = tasks

        mock_executor.execute_job.return_value = {
            "job_id": "job_1",
            "avatar_id": "avatar_1",
            "success": True,
            "raw_data": [],
            "execution_ms": 100
        }

        mock_hubfeed_client.submit_result.side_effect = Exception("Submit failed")

        # Should not raise exception
        await agent_loop._poll_cycle()
    
    @pytest.mark.asyncio
    async def test_poll_cycle_reverifies_if_needed(
        self, 
        agent_loop,
        mock_config_manager
    ):
        """Should re-verify token if needed."""
        agent_loop._verified = False
        mock_config_manager.is_verified.return_value = False
        
        with patch.object(agent_loop, '_verify_token', new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = True
            
            await agent_loop._poll_cycle()
            
            mock_verify.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_poll_cycle_syncs_avatars_if_needed(
        self, 
        agent_loop
    ):
        """Should sync avatars periodically."""
        agent_loop._verified = True
        agent_loop._last_avatar_sync = datetime.utcnow() - timedelta(minutes=6)
        
        with patch.object(agent_loop, '_sync_avatars', new_callable=AsyncMock) as mock_sync:
            await agent_loop._poll_cycle()
            
            mock_sync.assert_called_once()


class TestWaitForNextPoll:
    """Test poll interval waiting."""
    
    @pytest.mark.asyncio
    async def test_wait_for_next_poll(self, agent_loop, mock_config_manager):
        """Should wait for configured interval."""
        mock_config_manager.get_polling_interval.return_value = 0.1  # 100ms for testing
        
        start = asyncio.get_event_loop().time()
        await agent_loop._wait_for_next_poll()
        elapsed = asyncio.get_event_loop().time() - start
        
        assert elapsed >= 0.1


class TestHealthCheck:
    """Test health check functionality."""
    
    @pytest.mark.asyncio
    async def test_health_check_all_healthy(
        self, 
        agent_loop,
        mock_config_manager,
        mock_hubfeed_client
    ):
        """Should return healthy status."""
        agent_loop._running = True
        agent_loop._verified = True
        agent_loop._last_avatar_sync = datetime.utcnow()
        
        mock_config_manager.is_configured.return_value = True
        mock_hubfeed_client.health_check.return_value = True
        
        health = await agent_loop.health_check()
        
        assert health["running"] is True
        assert health["verified"] is True
        assert health["configured"] is True
        assert health["hubfeed_reachable"] is True
        assert health["last_avatar_sync"] is not None
    
    @pytest.mark.asyncio
    async def test_health_check_not_running(self, agent_loop):
        """Should report not running status."""
        agent_loop._running = False
        
        health = await agent_loop.health_check()
        
        assert health["running"] is False
    
    @pytest.mark.asyncio
    async def test_health_check_not_verified(self, agent_loop):
        """Should report not verified status."""
        agent_loop._verified = False
        
        health = await agent_loop.health_check()
        
        assert health["verified"] is False
    
    @pytest.mark.asyncio
    async def test_health_check_hubfeed_unreachable(
        self, 
        agent_loop,
        mock_hubfeed_client
    ):
        """Should report Hubfeed unreachable."""
        mock_hubfeed_client.health_check.return_value = False
        
        health = await agent_loop.health_check()
        
        assert health["hubfeed_reachable"] is False


class TestRunLoop:
    """Test main run loop."""
    
    @pytest.mark.asyncio
    async def test_run_verifies_token_initially(self, agent_loop):
        """Should verify token on startup."""
        agent_loop._running = True
        
        with patch.object(agent_loop, '_verify_token', new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = False  # Fail verification to stop loop
            
            await agent_loop._run()
            
            mock_verify.assert_called_once()
            assert agent_loop._running is False
    
    @pytest.mark.asyncio
    async def test_run_syncs_avatars_initially(self, agent_loop):
        """Should sync avatars on startup."""
        agent_loop._running = True
        
        with patch.object(agent_loop, '_verify_token', new_callable=AsyncMock) as mock_verify:
            with patch.object(agent_loop, '_sync_avatars', new_callable=AsyncMock) as mock_sync:
                with patch.object(agent_loop, '_poll_cycle', new_callable=AsyncMock) as mock_poll:
                    with patch.object(agent_loop, '_wait_for_next_poll', new_callable=AsyncMock) as mock_wait:
                        mock_verify.return_value = True
                        
                        # Make the loop stop after one iteration
                        async def stop_after_first():
                            agent_loop._running = False
                        
                        mock_poll.side_effect = stop_after_first
                        
                        await agent_loop._run()
                        
                        mock_sync.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_run_handles_poll_cycle_errors(self, agent_loop):
        """Should handle errors in poll cycle."""
        agent_loop._running = True
        
        with patch.object(agent_loop, '_verify_token', new_callable=AsyncMock) as mock_verify:
            with patch.object(agent_loop, '_sync_avatars', new_callable=AsyncMock):
                with patch.object(agent_loop, '_poll_cycle', new_callable=AsyncMock) as mock_poll:
                    with patch.object(agent_loop, '_wait_for_next_poll', new_callable=AsyncMock):
                        mock_verify.return_value = True
                        
                        call_count = 0
                        async def poll_with_error():
                            nonlocal call_count
                            call_count += 1
                            if call_count == 1:
                                raise Exception("Poll error")
                            else:
                                agent_loop._running = False
                        
                        mock_poll.side_effect = poll_with_error
                        
                        # Should not raise exception
                        await agent_loop._run()
                        
                        assert call_count == 2  # Should continue after error


class TestIntegration:
    """Integration tests for AgentLoop."""
    
    @pytest.mark.asyncio
    async def test_complete_loop_cycle(
        self,
        mock_config_manager,
        mock_hubfeed_client,
        mock_executor
    ):
        """Test complete loop cycle from start to stop."""
        loop = AgentLoop(mock_config_manager, mock_hubfeed_client, mock_executor)
        
        # Setup mocks for a single cycle
        mock_config_manager.get_avatars.return_value = [{"id": "test"}]
        mock_config_manager.get_polling_interval.return_value = 0.01  # 10ms
        
        mock_hubfeed_client.get_tasks.return_value = [
            {"job_id": "test_job", "avatar_id": "avatar_1", "command": "telegram.get_messages", "params": {}}
        ]

        mock_executor.execute_job.return_value = {
            "job_id": "test_job",
            "avatar_id": "avatar_1",
            "success": True,
            "raw_data": [],
            "execution_ms": 100
        }
        
        # Start loop in background
        await loop.start()
        
        # Let it run for a short time
        await asyncio.sleep(0.05)
        
        # Stop loop
        await loop.stop()
        
        # Verify it ran (stop() resets _verified, so check calls instead)
        mock_hubfeed_client.verify_token.assert_called()
        mock_hubfeed_client.sync_avatars.assert_called()
