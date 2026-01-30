"""
Unit tests for configuration manager.

Tests the ConfigManager class which manages agent configuration,
avatars, and blacklist rules.
"""

import pytest
from pathlib import Path
from datetime import datetime, timedelta

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
