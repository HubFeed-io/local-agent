"""
Unit tests for configuration manager.

Tests the ConfigManager class which manages agent configuration,
avatars, and blacklist rules.
"""

import pytest
from unittest.mock import Mock
from pathlib import Path
from datetime import datetime, timedelta, timezone

# Add src to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from config.manager import ConfigManager


@pytest.fixture
def config_manager(tmp_path):
    """Fixture providing a ConfigManager instance with temp directory."""
    return ConfigManager(tmp_path)


class TestConfigManagerInit:
    """Test ConfigManager initialization."""
    
    def test_init_creates_storage_files(self, tmp_path):
        """Should create storage files on initialization."""
        manager = ConfigManager(tmp_path)
        
        assert (tmp_path / "config.json").exists()
        assert (tmp_path / "avatars.json").exists()
        assert (tmp_path / "blacklist.json").exists()
    
    def test_init_with_default_structures(self, config_manager):
        """Should initialize with default data structures."""
        config = config_manager.get_config()
        assert config["token"] is None
        
        avatars = config_manager.get_avatars()
        assert avatars == []
        
        blacklist = config_manager.get_blacklist()
        assert "global" in blacklist
        assert "by_avatar" in blacklist


class TestConfigMethods:
    """Test configuration methods."""
    
    def test_get_config(self, config_manager):
        """Should return current configuration."""
        config = config_manager.get_config()
        assert isinstance(config, dict)
        assert "token" in config
    
    def test_save_config(self, config_manager):
        """Should save complete configuration."""
        new_config = {
            "token": "test_token_123",
            "verified_at": None,
            "platform_config": {}
        }

        success = config_manager.save_config(new_config)
        assert success is True

        loaded = config_manager.get_config()
        assert loaded["token"] == "test_token_123"
    
    def test_update_config(self, config_manager):
        """Should update specific config fields."""
        success = config_manager.update_config(
            token="new_token"
        )
        assert success is True

        config = config_manager.get_config()
        assert config["token"] == "new_token"
    
    def test_is_configured_false(self, config_manager):
        """Should return False when not configured."""
        assert config_manager.is_configured() is False
    
    def test_is_configured_true(self, config_manager):
        """Should return True when configured with token."""
        config_manager.update_config(
            token="test_token"
        )
        assert config_manager.is_configured() is True
    
    def test_is_verified_false_when_no_verification(self, config_manager):
        """Should return False when never verified."""
        assert config_manager.is_verified() is False
    
    def test_is_verified_true_when_recent(self, config_manager):
        """Should return True when verified recently (within 24h)."""
        from datetime import timezone
        recent_time = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        print(config_manager.get_config())
        config_manager.update_config(verified_at=recent_time)
        print(config_manager.get_config())
        assert config_manager.is_verified() is True
    
    def test_is_verified_false_when_old(self, config_manager):
        """Should return False when verification is old (>24h)."""
        old_time = (datetime.utcnow() - timedelta(hours=25)).isoformat() + "Z"
        config_manager.update_config(verified_at=old_time)
        
        assert config_manager.is_verified() is False
    
    def test_get_platform_config(self, config_manager):
        """Should return platform-specific configuration."""
        config_manager.update_config(
            platform_config={
                "telegram": {"api_id": "123", "api_hash": "abc"}
            }
        )
        
        telegram_config = config_manager.get_platform_config("telegram")
        assert telegram_config["api_id"] == "123"
        assert telegram_config["api_hash"] == "abc"
    
    def test_get_platform_config_default(self, config_manager):
        """Should return empty dict for non-existent platform."""
        config = config_manager.get_platform_config("unknown")
        assert config == {}
    
    def test_get_polling_interval_default(self, config_manager):
        """Should return default polling interval of 30 seconds."""
        interval = config_manager.get_polling_interval()
        assert interval == 30
    
    def test_get_polling_interval_custom(self, config_manager):
        """Should return custom polling interval."""
        config_manager.update_config(
            platform_config={"polling_interval_seconds": 60}
        )
        
        interval = config_manager.get_polling_interval()
        assert interval == 60


class TestAvatarMethods:
    """Test avatar management methods."""
    
    def test_get_avatars_empty(self, config_manager):
        """Should return empty list when no avatars."""
        avatars = config_manager.get_avatars()
        assert avatars == []
    
    def test_save_avatar_new(self, config_manager):
        """Should save new avatar."""
        avatar = {
            "id": "avatar_1",
            "name": "Test Avatar",
            "platform": "telegram",
            "status": "active"
        }
        
        success = config_manager.save_avatar(avatar)
        assert success is True
        
        avatars = config_manager.get_avatars()
        assert len(avatars) == 1
        assert avatars[0]["id"] == "avatar_1"
    
    def test_save_avatar_update_existing(self, config_manager):
        """Should update existing avatar with same ID."""
        avatar1 = {"id": "avatar_1", "name": "Original Name", "status": "active"}
        config_manager.save_avatar(avatar1)
        
        avatar2 = {"id": "avatar_1", "name": "Updated Name", "status": "inactive"}
        config_manager.save_avatar(avatar2)
        
        avatars = config_manager.get_avatars()
        assert len(avatars) == 1
        assert avatars[0]["name"] == "Updated Name"
        assert avatars[0]["status"] == "inactive"
    
    def test_save_avatar_without_id(self, config_manager):
        """Should fail when avatar has no ID."""
        avatar = {"name": "No ID Avatar"}
        success = config_manager.save_avatar(avatar)
        assert success is False
    
    def test_get_avatar_by_id(self, config_manager):
        """Should retrieve specific avatar by ID."""
        avatar = {"id": "avatar_1", "name": "Test"}
        config_manager.save_avatar(avatar)
        
        retrieved = config_manager.get_avatar("avatar_1")
        assert retrieved is not None
        assert retrieved["id"] == "avatar_1"
        assert retrieved["name"] == "Test"
    
    def test_get_avatar_not_found(self, config_manager):
        """Should return None for non-existent avatar."""
        avatar = config_manager.get_avatar("nonexistent")
        assert avatar is None
    
    def test_delete_avatar(self, config_manager):
        """Should delete avatar by ID."""
        avatar = {"id": "avatar_1", "name": "To Delete"}
        config_manager.save_avatar(avatar)
        
        success = config_manager.delete_avatar("avatar_1")
        assert success is True
        
        avatars = config_manager.get_avatars()
        assert len(avatars) == 0
    
    def test_delete_nonexistent_avatar(self, config_manager):
        """Should return True even when deleting non-existent avatar."""
        success = config_manager.delete_avatar("nonexistent")
        assert success is True
    
    def test_update_avatar_status(self, config_manager):
        """Should update avatar status and last_used_at."""
        avatar = {"id": "avatar_1", "status": "active"}
        config_manager.save_avatar(avatar)
        
        success = config_manager.update_avatar_status("avatar_1", "inactive")
        assert success is True
        
        updated = config_manager.get_avatar("avatar_1")
        assert updated["status"] == "inactive"
        assert "last_used_at" in updated
    
    def test_update_status_nonexistent_avatar(self, config_manager):
        """Should return False when updating non-existent avatar."""
        success = config_manager.update_avatar_status("nonexistent", "active")
        assert success is False
    
    def test_multiple_avatars(self, config_manager):
        """Should handle multiple avatars correctly."""
        avatar1 = {"id": "avatar_1", "name": "First"}
        avatar2 = {"id": "avatar_2", "name": "Second"}
        avatar3 = {"id": "avatar_3", "name": "Third"}
        
        config_manager.save_avatar(avatar1)
        config_manager.save_avatar(avatar2)
        config_manager.save_avatar(avatar3)
        
        avatars = config_manager.get_avatars()
        assert len(avatars) == 3


class TestBlacklistMethods:
    """Test blacklist management methods."""
    
    def test_get_blacklist_default(self, config_manager):
        """Should return default blacklist structure."""
        blacklist = config_manager.get_blacklist()
        
        assert "global" in blacklist
        assert "by_avatar" in blacklist
        assert blacklist["global"]["keywords"] == []
        assert blacklist["global"]["senders"] == []
        assert blacklist["global"]["channels"] == []
    
    def test_save_blacklist(self, config_manager):
        """Should save blacklist configuration."""
        blacklist = {
            "global": {
                "keywords": ["spam", "test"],
                "senders": ["123"],
                "channels": ["456"]
            },
            "by_avatar": {}
        }
        
        success = config_manager.save_blacklist(blacklist)
        assert success is True
        
        loaded = config_manager.get_blacklist()
        assert loaded["global"]["keywords"] == ["spam", "test"]
        assert loaded["global"]["senders"] == ["123"]
    
    def test_get_avatar_blacklist_global_only(self, config_manager):
        """Should return global rules when no avatar-specific rules."""
        blacklist = {
            "global": {
                "keywords": ["spam"],
                "senders": ["123"],
                "channels": ["456"]
            },
            "by_avatar": {}
        }
        config_manager.save_blacklist(blacklist)
        
        rules = config_manager.get_avatar_blacklist("avatar_1")
        assert "spam" in rules["keywords"]
        assert "123" in rules["senders"]
        assert "456" in rules["channels"]
    
    def test_get_avatar_blacklist_merged(self, config_manager):
        """Should merge global and avatar-specific rules."""
        blacklist = {
            "global": {
                "keywords": ["spam"],
                "senders": ["123"],
                "channels": ["456"]
            },
            "by_avatar": {
                "avatar_1": {
                    "keywords": ["test"],
                    "senders": ["789"],
                    "channels": ["999"]
                }
            }
        }
        config_manager.save_blacklist(blacklist)
        
        rules = config_manager.get_avatar_blacklist("avatar_1")
        
        # Should contain both global and avatar-specific rules
        assert "spam" in rules["keywords"]
        assert "test" in rules["keywords"]
        assert "123" in rules["senders"]
        assert "789" in rules["senders"]
        assert "456" in rules["channels"]
        assert "999" in rules["channels"]
    
    def test_get_avatar_blacklist_deduplication(self, config_manager):
        """Should deduplicate rules when merging."""
        blacklist = {
            "global": {
                "keywords": ["spam", "test"],
                "senders": ["123"],
                "channels": ["456"]
            },
            "by_avatar": {
                "avatar_1": {
                    "keywords": ["test", "duplicate"],  # "test" duplicates global
                    "senders": ["123", "789"],  # "123" duplicates global
                    "channels": ["456", "999"]  # "456" duplicates global
                }
            }
        }
        config_manager.save_blacklist(blacklist)
        
        rules = config_manager.get_avatar_blacklist("avatar_1")
        
        # Should have deduplicated lists
        assert len(rules["keywords"]) == 3  # spam, test, duplicate
        assert len(rules["senders"]) == 2  # 123, 789
        assert len(rules["channels"]) == 2  # 456, 999


class TestConfigManagerIntegration:
    """Test integrated scenarios."""
    
    def test_complete_setup_workflow(self, config_manager):
        """Test a complete agent setup workflow."""
        # 1. Configure agent
        config_manager.update_config(
            token="test_token_123"
        )
        assert config_manager.is_configured() is True
        
        # 2. Add avatar
        avatar = {
            "id": "telegram_1",
            "name": "My Telegram",
            "platform": "telegram",
            "status": "active"
        }
        config_manager.save_avatar(avatar)
        
        # 3. Configure blacklist
        blacklist = {
            "global": {
                "keywords": ["spam"],
                "senders": [],
                "channels": []
            },
            "by_avatar": {
                "telegram_1": {
                    "keywords": ["personal"],
                    "senders": [],
                    "channels": []
                }
            }
        }
        config_manager.save_blacklist(blacklist)
        
        # 4. Verify everything
        assert len(config_manager.get_avatars()) == 1
        rules = config_manager.get_avatar_blacklist("telegram_1")
        assert "spam" in rules["keywords"]
        assert "personal" in rules["keywords"]
    
    def test_persistence_across_instances(self, tmp_path):
        """Configuration should persist across manager instances."""
        # Create first instance and save data
        manager1 = ConfigManager(tmp_path)
        manager1.update_config(token="test_token_persist")
        manager1.save_avatar({"id": "avatar_1", "name": "Test"})

        # Create second instance and verify data persists
        manager2 = ConfigManager(tmp_path)
        config = manager2.get_config()
        assert config["token"] == "test_token_persist"

        avatars = manager2.get_avatars()
        assert len(avatars) == 1
        assert avatars[0]["name"] == "Test"


class TestSourceManagement:
    """Test source whitelist methods."""

    def test_get_avatar_sources_empty_default(self, config_manager):
        """Should return disabled empty sources when avatar has none."""
        config_manager.save_avatar({"id": "av1", "name": "Test"})
        sources = config_manager.get_avatar_sources("av1")
        assert sources == {"enabled": False, "items": []}

    def test_get_avatar_sources_returns_saved(self, config_manager):
        """Should return saved sources config."""
        config_manager.save_avatar({
            "id": "av1", "name": "Test",
            "sources": {"enabled": True, "items": [{"id": "ch1", "name": "Chan"}]}
        })
        sources = config_manager.get_avatar_sources("av1")
        assert sources["enabled"] is True
        assert len(sources["items"]) == 1

    def test_get_avatar_sources_avatar_not_found(self, config_manager):
        """Should return disabled empty sources when avatar not found."""
        sources = config_manager.get_avatar_sources("nonexistent")
        assert sources == {"enabled": False, "items": []}

    def test_save_avatar_sources_success(self, config_manager):
        """Should save sources config to avatar."""
        config_manager.save_avatar({"id": "av1", "name": "Test"})
        result = config_manager.save_avatar_sources("av1", {
            "enabled": True,
            "items": [{"id": "ch1", "name": "Chan"}]
        })
        assert result is True
        sources = config_manager.get_avatar_sources("av1")
        assert sources["enabled"] is True

    def test_save_avatar_sources_avatar_not_found(self, config_manager):
        """Should return False when avatar not found."""
        result = config_manager.save_avatar_sources("nonexistent", {"enabled": True, "items": []})
        assert result is False

    def test_add_source_success(self, config_manager):
        """Should add a source to avatar's whitelist."""
        config_manager.save_avatar({"id": "av1", "name": "Test"})
        result = config_manager.add_source("av1", {
            "id": "-1001234567890",
            "name": "News Channel",
            "type": "channel"
        })
        assert result is True

        sources = config_manager.get_avatar_sources("av1")
        assert len(sources["items"]) == 1
        assert sources["items"][0]["id"] == "-1001234567890"
        assert sources["items"][0]["name"] == "News Channel"

    def test_add_source_duplicate_returns_false(self, config_manager):
        """Should return False when source already exists."""
        config_manager.save_avatar({"id": "av1", "name": "Test"})
        config_manager.add_source("av1", {"id": "ch1", "name": "Chan"})
        result = config_manager.add_source("av1", {"id": "ch1", "name": "Chan duplicate"})
        assert result is False

    def test_add_source_sets_defaults(self, config_manager):
        """Should set default values for optional fields."""
        config_manager.save_avatar({"id": "av1", "name": "Test"})
        config_manager.add_source("av1", {"id": "ch1"})

        sources = config_manager.get_avatar_sources("av1")
        item = sources["items"][0]
        assert item["name"] == ""
        assert item["type"] == "channel"
        assert item["frequency_seconds"] == ConfigManager.DEFAULT_FREQUENCY
        assert item["last_checked_at"] is None
        assert item["last_message_id"] is None

    def test_add_source_enables_sources(self, config_manager):
        """Should enable sources when first source is added."""
        config_manager.save_avatar({"id": "av1", "name": "Test"})
        config_manager.add_source("av1", {"id": "ch1", "name": "Chan"})

        sources = config_manager.get_avatar_sources("av1")
        assert sources["enabled"] is True

    def test_remove_source_success(self, config_manager):
        """Should remove source from whitelist."""
        config_manager.save_avatar({"id": "av1", "name": "Test"})
        config_manager.add_source("av1", {"id": "ch1", "name": "Chan"})
        config_manager.add_source("av1", {"id": "ch2", "name": "Chan 2"})

        result = config_manager.remove_source("av1", "ch1")
        assert result is True

        sources = config_manager.get_avatar_sources("av1")
        assert len(sources["items"]) == 1
        assert sources["items"][0]["id"] == "ch2"

    def test_remove_source_nonexistent(self, config_manager):
        """Should succeed even when removing nonexistent source."""
        config_manager.save_avatar({"id": "av1", "name": "Test"})
        result = config_manager.remove_source("av1", "nonexistent")
        assert result is True

    def test_update_source_success(self, config_manager):
        """Should update source settings."""
        config_manager.save_avatar({"id": "av1", "name": "Test"})
        config_manager.add_source("av1", {"id": "ch1", "name": "Chan", "frequency_seconds": 300})

        result = config_manager.update_source("av1", "ch1", {"frequency_seconds": 600})
        assert result is True

        sources = config_manager.get_avatar_sources("av1")
        assert sources["items"][0]["frequency_seconds"] == 600

    def test_update_source_not_found(self, config_manager):
        """Should return False when source not found."""
        config_manager.save_avatar({"id": "av1", "name": "Test"})
        result = config_manager.update_source("av1", "nonexistent", {"frequency_seconds": 600})
        assert result is False

    def test_update_source_last_checked(self, config_manager):
        """Should update last_checked_at timestamp."""
        config_manager.save_avatar({"id": "av1", "name": "Test"})
        config_manager.add_source("av1", {"id": "ch1", "name": "Chan"})

        now = datetime.now(timezone.utc).isoformat()
        result = config_manager.update_source_last_checked("av1", "ch1", now)
        assert result is True

        sources = config_manager.get_avatar_sources("av1")
        assert sources["items"][0]["last_checked_at"] == now

    def test_update_source_last_checked_with_message_id(self, config_manager):
        """Should update both last_checked_at and last_message_id."""
        config_manager.save_avatar({"id": "av1", "name": "Test"})
        config_manager.add_source("av1", {"id": "ch1", "name": "Chan"})

        now = datetime.now(timezone.utc).isoformat()
        result = config_manager.update_source_last_checked("av1", "ch1", now, last_message_id=12345)
        assert result is True

        sources = config_manager.get_avatar_sources("av1")
        assert sources["items"][0]["last_message_id"] == 12345


class TestGetSourcesDueForCheck:
    """Test source frequency checking logic."""

    def test_returns_empty_when_disabled(self, config_manager):
        """Should return empty list when sources are disabled."""
        config_manager.save_avatar({
            "id": "av1", "name": "Test",
            "sources": {"enabled": False, "items": [{"id": "ch1"}]}
        })
        result = config_manager.get_sources_due_for_check("av1")
        assert result == []

    def test_returns_never_checked_sources(self, config_manager):
        """Should return sources that have never been checked."""
        config_manager.save_avatar({"id": "av1", "name": "Test"})
        config_manager.add_source("av1", {"id": "ch1", "name": "Chan"})

        result = config_manager.get_sources_due_for_check("av1")
        assert len(result) == 1
        assert result[0]["id"] == "ch1"

    def test_returns_sources_past_frequency(self, config_manager):
        """Should return sources whose check interval has elapsed."""
        config_manager.save_avatar({"id": "av1", "name": "Test"})
        config_manager.add_source("av1", {"id": "ch1", "name": "Chan", "frequency_seconds": 60})

        # Set last_checked to 2 minutes ago
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        config_manager.update_source_last_checked("av1", "ch1", old_time)

        result = config_manager.get_sources_due_for_check("av1")
        assert len(result) == 1

    def test_skips_recently_checked_sources(self, config_manager):
        """Should not return sources checked within their frequency."""
        config_manager.save_avatar({"id": "av1", "name": "Test"})
        config_manager.add_source("av1", {"id": "ch1", "name": "Chan", "frequency_seconds": 3600})

        # Set last_checked to 1 minute ago (well within 1 hour frequency)
        recent_time = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        config_manager.update_source_last_checked("av1", "ch1", recent_time)

        result = config_manager.get_sources_due_for_check("av1")
        assert len(result) == 0

    def test_handles_invalid_timestamp(self, config_manager):
        """Should treat sources with invalid timestamps as due."""
        config_manager.save_avatar({
            "id": "av1", "name": "Test",
            "sources": {
                "enabled": True,
                "items": [{
                    "id": "ch1", "name": "Chan",
                    "frequency_seconds": 300,
                    "last_checked_at": "not-a-date",
                    "last_message_id": None
                }]
            }
        })
        result = config_manager.get_sources_due_for_check("av1")
        assert len(result) == 1

    def test_mixed_due_and_not_due(self, config_manager):
        """Should correctly filter mixed due/not-due sources."""
        config_manager.save_avatar({"id": "av1", "name": "Test"})
        config_manager.add_source("av1", {"id": "ch1", "name": "Due", "frequency_seconds": 60})
        config_manager.add_source("av1", {"id": "ch2", "name": "Not due", "frequency_seconds": 3600})

        old_time = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        recent_time = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        config_manager.update_source_last_checked("av1", "ch1", old_time)
        config_manager.update_source_last_checked("av1", "ch2", recent_time)

        result = config_manager.get_sources_due_for_check("av1")
        assert len(result) == 1
        assert result[0]["id"] == "ch1"


class TestStatusDirty:
    """Test status dirty flag lifecycle."""

    def test_consume_returns_false_initially(self, config_manager):
        """Should return False when no status has changed."""
        assert config_manager.consume_status_dirty() is False

    def test_consume_returns_true_after_status_change(self, config_manager):
        """Should return True after avatar status changes."""
        config_manager.save_avatar({"id": "av1", "status": "active"})
        config_manager.update_avatar_status("av1", "inactive")
        assert config_manager.consume_status_dirty() is True

    def test_consume_resets_after_consume(self, config_manager):
        """Should reset to False after consuming."""
        config_manager.save_avatar({"id": "av1", "status": "active"})
        config_manager.update_avatar_status("av1", "inactive")
        config_manager.consume_status_dirty()  # First consume
        assert config_manager.consume_status_dirty() is False  # Second should be False

    def test_same_status_does_not_set_dirty(self, config_manager):
        """Should not set dirty when status doesn't actually change."""
        config_manager.save_avatar({"id": "av1", "status": "active"})
        config_manager.update_avatar_status("av1", "active")  # Same status
        assert config_manager.consume_status_dirty() is False


class TestAuditLogging:
    """Test that operations log audit events when history_logger is set."""

    @pytest.fixture
    def manager_with_logger(self, tmp_path):
        """ConfigManager with a mock history_logger."""
        mock_logger = Mock()
        mock_logger.log_system_event = Mock(return_value=True)
        mock_logger.log_avatar_event = Mock(return_value=True)
        mock_logger.log_channel_event = Mock(return_value=True)
        return ConfigManager(tmp_path, history_logger=mock_logger)

    def test_add_source_logs_channel_event(self, manager_with_logger):
        """Should log channel event when adding a source."""
        manager_with_logger.save_avatar({"id": "av1", "name": "Test"})
        manager_with_logger.add_source("av1", {"id": "ch1", "name": "News"})

        manager_with_logger.history_logger.log_channel_event.assert_called_once_with(
            action="added",
            channel_id="ch1",
            avatar_id="av1",
            details={
                "name": "News",
                "type": "channel",
                "frequency_seconds": ConfigManager.DEFAULT_FREQUENCY
            }
        )

    def test_remove_source_logs_channel_event(self, manager_with_logger):
        """Should log channel event when removing a source."""
        manager_with_logger.save_avatar({"id": "av1", "name": "Test"})
        manager_with_logger.add_source("av1", {"id": "ch1", "name": "News", "type": "channel"})
        manager_with_logger.history_logger.log_channel_event.reset_mock()

        manager_with_logger.remove_source("av1", "ch1")

        manager_with_logger.history_logger.log_channel_event.assert_called_once_with(
            action="removed",
            channel_id="ch1",
            avatar_id="av1",
            details={
                "name": "News",
                "type": "channel"
            }
        )

    def test_update_source_logs_channel_event(self, manager_with_logger):
        """Should log channel event when updating a source."""
        manager_with_logger.save_avatar({"id": "av1", "name": "Test"})
        manager_with_logger.add_source("av1", {"id": "ch1", "name": "News"})
        manager_with_logger.history_logger.log_channel_event.reset_mock()

        manager_with_logger.update_source("av1", "ch1", {"frequency_seconds": 600})

        manager_with_logger.history_logger.log_channel_event.assert_called_once()
        call_kwargs = manager_with_logger.history_logger.log_channel_event.call_args[1]
        assert call_kwargs["action"] == "updated"
        assert call_kwargs["channel_id"] == "ch1"
        assert call_kwargs["details"]["updates"] == {"frequency_seconds": 600}

    def test_update_avatar_status_logs_event(self, manager_with_logger):
        """Should log avatar status_changed event when status changes."""
        manager_with_logger.save_avatar({"id": "av1", "status": "active"})
        manager_with_logger.history_logger.log_avatar_event.reset_mock()

        manager_with_logger.update_avatar_status("av1", "inactive")

        # update_avatar_status calls save_avatar (which logs 'updated') and then logs 'status_changed'
        calls = manager_with_logger.history_logger.log_avatar_event.call_args_list
        status_calls = [c for c in calls if c[1].get("action") == "status_changed"]
        assert len(status_calls) == 1
        call_kwargs = status_calls[0][1]
        assert call_kwargs["avatar_id"] == "av1"
        assert call_kwargs["details"]["old_status"] == "active"
        assert call_kwargs["details"]["new_status"] == "inactive"
