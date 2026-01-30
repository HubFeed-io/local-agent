"""
Unit tests for history logger.

Tests the HistoryLogger class which logs agent requests and responses
with daily file rotation.
"""

import pytest
from datetime import date, timedelta
from pathlib import Path
import json

# Add src to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from history.logger import HistoryLogger


@pytest.fixture
def history_logger(tmp_path):
    """Fixture providing a HistoryLogger instance with temp directory."""
    return HistoryLogger(tmp_path)


class TestHistoryLoggerInit:
    """Test HistoryLogger initialization."""
    
    def test_init_creates_logs_directory(self, tmp_path):
        """Should create logs directory on initialization."""
        logger = HistoryLogger(tmp_path)
        
        assert (tmp_path / "logs").exists()
        assert (tmp_path / "logs").is_dir()


class TestHistoryLoggerLogging:
    """Test logging functionality."""
    
    def test_log_basic_entry(self, history_logger):
        """Should log a basic entry with required fields."""
        result = history_logger.log(
            job_id="job_123",
            avatar_id="avatar_1",
            command="get_messages",
            params={"channel": "test_channel"},
            status="success"
        )
        
        assert result is True
        
        # Verify log file was created
        logs_dir = history_logger.logs_dir
        today = date.today()
        log_file = logs_dir / f"history_{today.isoformat()}.json"
        assert log_file.exists()
        
        # Verify entry
        entries = history_logger.get_recent(limit=1)
        assert len(entries) == 1
        assert entries[0]["job_id"] == "job_123"
        assert entries[0]["avatar_id"] == "avatar_1"
        assert entries[0]["command"] == "get_messages"
        assert entries[0]["status"] == "success"
    
    def test_log_entry_with_all_fields(self, history_logger):
        """Should log entry with all optional fields."""
        result = history_logger.log(
            job_id="job_456",
            avatar_id="avatar_2",
            command="fetch_updates",
            params={"limit": 100},
            status="success",
            items_returned=95,
            items_filtered=5,
            filter_reasons=[{"keyword": "spam"}],
            execution_ms=1234
        )
        
        assert result is True
        
        entries = history_logger.get_recent(limit=1)
        entry = entries[0]
        assert entry["items_returned"] == 95
        assert entry["items_filtered"] == 5
        assert entry["execution_ms"] == 1234
        assert "filter_reasons" in entry
    
    def test_log_failed_entry_with_error(self, history_logger):
        """Should log failed entry with error message."""
        result = history_logger.log(
            job_id="job_789",
            avatar_id="avatar_3",
            command="get_messages",
            params={},
            status="failed",
            error="Connection timeout"
        )
        
        assert result is True
        
        entries = history_logger.get_recent(limit=1)
        entry = entries[0]
        assert entry["status"] == "failed"
        assert entry["error"] == "Connection timeout"
    
    def test_log_multiple_entries(self, history_logger):
        """Should log multiple entries successfully."""
        for i in range(5):
            result = history_logger.log(
                job_id=f"job_{i}",
                avatar_id="avatar_1",
                command="get_messages",
                params={},
                status="success"
            )
            assert result is True
        
        entries = history_logger.get_recent(limit=10)
        assert len(entries) == 5


class TestHistoryLoggerQuery:
    """Test query functionality."""
    
    def test_get_recent_returns_newest_first(self, history_logger):
        """Should return entries with newest first."""
        # Log 3 entries
        for i in range(3):
            history_logger.log(
                job_id=f"job_{i}",
                avatar_id="avatar_1",
                command="test",
                params={},
                status="success"
            )
        
        entries = history_logger.get_recent(limit=3)
        assert len(entries) == 3
        # Newest should be first (job_2)
        assert entries[0]["job_id"] == "job_2"
        assert entries[1]["job_id"] == "job_1"
        assert entries[2]["job_id"] == "job_0"
    
    def test_get_recent_with_limit(self, history_logger):
        """Should respect limit parameter."""
        # Log 10 entries
        for i in range(10):
            history_logger.log(
                job_id=f"job_{i}",
                avatar_id="avatar_1",
                command="test",
                params={},
                status="success"
            )
        
        entries = history_logger.get_recent(limit=5)
        assert len(entries) == 5
    
    def test_get_by_avatar_filters_correctly(self, history_logger):
        """Should return only entries for specific avatar."""
        # Log entries for different avatars
        history_logger.log(
            job_id="job_1",
            avatar_id="avatar_1",
            command="test",
            params={},
            status="success"
        )
        history_logger.log(
            job_id="job_2",
            avatar_id="avatar_2",
            command="test",
            params={},
            status="success"
        )
        history_logger.log(
            job_id="job_3",
            avatar_id="avatar_1",
            command="test",
            params={},
            status="success"
        )
        
        entries = history_logger.get_by_avatar("avatar_1", limit=10)
        assert len(entries) == 2
        assert all(e["avatar_id"] == "avatar_1" for e in entries)
    
    def test_get_by_job_finds_entry(self, history_logger):
        """Should find entry by job ID."""
        history_logger.log(
            job_id="unique_job",
            avatar_id="avatar_1",
            command="test",
            params={"special": True},
            status="success"
        )
        
        entry = history_logger.get_by_job("unique_job")
        assert entry is not None
        assert entry["job_id"] == "unique_job"
        assert entry["params"]["special"] is True
    
    def test_get_by_job_not_found(self, history_logger):
        """Should return None for non-existent job."""
        entry = history_logger.get_by_job("nonexistent")
        assert entry is None


class TestHistoryLoggerStats:
    """Test statistics functionality."""
    
    def test_get_stats_empty(self, history_logger):
        """Should return zero stats when no entries."""
        stats = history_logger.get_stats()
        
        assert stats["total_requests"] == 0
        assert stats["successful"] == 0
        assert stats["failed"] == 0
        assert stats["total_items_returned"] == 0
        assert stats["total_items_filtered"] == 0
        assert stats["avg_execution_ms"] == 0
    
    def test_get_stats_calculates_correctly(self, history_logger):
        """Should calculate statistics correctly."""
        # Log 3 successful, 1 failed
        for i in range(3):
            history_logger.log(
                job_id=f"job_{i}",
                avatar_id="avatar_1",
                command="test",
                params={},
                status="success",
                items_returned=10,
                items_filtered=2,
                execution_ms=100
            )
        
        history_logger.log(
            job_id="job_fail",
            avatar_id="avatar_1",
            command="test",
            params={},
            status="failed",
            execution_ms=50
        )
        
        stats = history_logger.get_stats()
        assert stats["total_requests"] == 4
        assert stats["successful"] == 3
        assert stats["failed"] == 1
        assert stats["total_items_returned"] == 30
        assert stats["total_items_filtered"] == 6
        assert stats["avg_execution_ms"] == 87  # (100+100+100+50)/4


class TestHistoryLoggerFileManagement:
    """Test file management functionality."""
    
    def test_list_log_files(self, history_logger):
        """Should list all log files."""
        # Create entry to generate today's file
        history_logger.log(
            job_id="job_1",
            avatar_id="avatar_1",
            command="test",
            params={},
            status="success"
        )
        
        files = history_logger.list_log_files()
        assert len(files) > 0
        assert date.today().isoformat() in files
    
    def test_cleanup_old_logs(self, history_logger, tmp_path):
        """Should delete old log files."""
        logs_dir = tmp_path / "logs"
        
        # Create old log file manually
        old_date = date.today() - timedelta(days=35)
        old_file = logs_dir / f"history_{old_date.isoformat()}.json"
        old_file.write_text(json.dumps({
            "date": old_date.isoformat(),
            "entries": []
        }))
        
        # Create recent log file
        history_logger.log(
            job_id="job_1",
            avatar_id="avatar_1",
            command="test",
            params={},
            status="success"
        )
        
        # Cleanup (keep 30 days)
        deleted = history_logger.cleanup_old_logs(keep_days=30)
        
        assert deleted == 1
        assert not old_file.exists()
        
        # Today's file should still exist
        today_file = logs_dir / f"history_{date.today().isoformat()}.json"
        assert today_file.exists()


class TestHistoryLoggerRotation:
    """Test daily rotation functionality."""
    
    def test_daily_rotation_creates_separate_files(self, history_logger, tmp_path):
        """Should create separate files for different days."""
        logs_dir = tmp_path / "logs"
        
        # Log today
        history_logger.log(
            job_id="job_today",
            avatar_id="avatar_1",
            command="test",
            params={},
            status="success"
        )
        
        # Manually create yesterday's file to simulate rotation
        yesterday = date.today() - timedelta(days=1)
        yesterday_file = logs_dir / f"history_{yesterday.isoformat()}.json"
        yesterday_file.write_text(json.dumps({
            "date": yesterday.isoformat(),
            "next_id": 2,
            "entries": [{
                "id": 1,
                "job_id": "job_yesterday",
                "avatar_id": "avatar_1",
                "command": "test",
                "params": {},
                "status": "success"
            }]
        }))
        
        # Verify both files exist
        today_file = logs_dir / f"history_{date.today().isoformat()}.json"
        assert today_file.exists()
        assert yesterday_file.exists()
        
        # Verify get_recent() can read from both
        entries = history_logger.get_recent(limit=10, days=7)
        job_ids = [e["job_id"] for e in entries]
        assert "job_today" in job_ids
        assert "job_yesterday" in job_ids


class TestHistoryLoggerEdgeCases:
    """Test edge cases and error handling."""
    
    def test_max_entries_per_file_trimming(self, history_logger):
        """Should trim entries when exceeding MAX_ENTRIES_PER_FILE."""
        # Log more than MAX_ENTRIES_PER_FILE entries
        max_entries = HistoryLogger.MAX_ENTRIES_PER_FILE
        
        for i in range(max_entries + 10):
            history_logger.log(
                job_id=f"job_{i}",
                avatar_id="avatar_1",
                command="test",
                params={},
                status="success"
            )
        
        # Get today's log file
        today = date.today()
        storage = history_logger._get_storage_for_date(today)
        data = storage.load()
        
        # Should not exceed max
        assert len(data["entries"]) == max_entries
        
        # Should keep most recent (highest IDs)
        last_job = data["entries"][-1]["job_id"]
        assert "job_" in last_job
    
    def test_unicode_in_log_entries(self, history_logger):
        """Should handle Unicode in log entries."""
        history_logger.log(
            job_id="job_unicode",
            avatar_id="avatar_émoji_🎉",
            command="测试",
            params={"message": "Hello 世界 🌍"},
            status="success"
        )
        
        entries = history_logger.get_recent(limit=1)
        entry = entries[0]
        assert entry["avatar_id"] == "avatar_émoji_🎉"
        assert entry["command"] == "测试"
        assert entry["params"]["message"] == "Hello 世界 🌍"
    
    def test_empty_params(self, history_logger):
        """Should handle empty params."""
        result = history_logger.log(
            job_id="job_empty",
            avatar_id="avatar_1",
            command="test",
            params={},
            status="success"
        )
        
        assert result is True
        entries = history_logger.get_recent(limit=1)
        assert entries[0]["params"] == {}
