"""
Unit tests for blacklist filter.

Tests the BlacklistFilter class which filters content locally
before sending to the SaaS platform.
"""

import pytest
from unittest.mock import Mock

# Add src to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from blacklist.filter import BlacklistFilter, FilterResult


class TestBlacklistFilterInit:
    """Test BlacklistFilter initialization."""
    
    def test_init_with_config_manager(self):
        """Should initialize with config manager."""
        mock_config = Mock()
        filter_obj = BlacklistFilter(mock_config)
        assert filter_obj.config_manager is mock_config


class TestBlacklistFilterBasicFiltering:
    """Test basic filtering functionality."""
    
    def test_filter_empty_data(self):
        """Should handle empty data list."""
        mock_config = Mock()
        mock_config.get_avatar_blacklist.return_value = {
            "keywords": [],
            "senders": [],
            "channels": []
        }
        
        filter_obj = BlacklistFilter(mock_config)
        result = filter_obj.filter([], "avatar_1")
        
        assert isinstance(result, FilterResult)
        assert result.data == []
        assert result.filtered_count == 0
        assert result.reasons == []
    
    def test_filter_no_rules(self):
        """Should pass all items when no rules exist."""
        mock_config = Mock()
        mock_config.get_avatar_blacklist.return_value = {
            "keywords": [],
            "senders": [],
            "channels": []
        }
        
        data = [
            {"id": 1, "message": "Hello"},
            {"id": 2, "message": "World"}
        ]
        
        filter_obj = BlacklistFilter(mock_config)
        result = filter_obj.filter(data, "avatar_1")
        
        assert len(result.data) == 2
        assert result.filtered_count == 0
    
    def test_filter_by_keyword(self):
        """Should filter messages containing blacklisted keywords."""
        mock_config = Mock()
        mock_config.get_avatar_blacklist.return_value = {
            "keywords": ["spam", "advertisement"],
            "senders": [],
            "channels": []
        }
        
        data = [
            {"id": 1, "message": "Normal message"},
            {"id": 2, "message": "This is spam content"},
            {"id": 3, "message": "Check this advertisement"}
        ]
        
        filter_obj = BlacklistFilter(mock_config)
        result = filter_obj.filter(data, "avatar_1")
        
        assert len(result.data) == 1
        assert result.data[0]["id"] == 1
        assert result.filtered_count == 2
        assert len(result.reasons) == 2
    
    def test_filter_by_sender(self):
        """Should filter messages from blacklisted senders."""
        mock_config = Mock()
        mock_config.get_avatar_blacklist.return_value = {
            "keywords": [],
            "senders": ["123456"],
            "channels": []
        }
        
        data = [
            {"id": 1, "message": "From good user", "from_id": {"user_id": 789}},
            {"id": 2, "message": "From blocked user", "from_id": {"user_id": 123456}}
        ]
        
        filter_obj = BlacklistFilter(mock_config)
        result = filter_obj.filter(data, "avatar_1")
        
        assert len(result.data) == 1
        assert result.data[0]["id"] == 1
        assert result.filtered_count == 1
    
    def test_filter_by_channel(self):
        """Should filter messages from blacklisted channels."""
        mock_config = Mock()
        mock_config.get_avatar_blacklist.return_value = {
            "keywords": [],
            "senders": [],
            "channels": ["999"]
        }
        
        data = [
            {"id": 1, "message": "From channel 1", "peer_id": {"channel_id": 888}},
            {"id": 2, "message": "From blocked channel", "peer_id": {"channel_id": 999}}
        ]
        
        filter_obj = BlacklistFilter(mock_config)
        result = filter_obj.filter(data, "avatar_1")
        
        assert len(result.data) == 1
        assert result.data[0]["id"] == 1
        assert result.filtered_count == 1


class TestBlacklistFilterKeywordMatching:
    """Test keyword matching behavior."""
    
    def test_case_insensitive_keyword_matching(self):
        """Keywords should match case-insensitively."""
        mock_config = Mock()
        mock_config.get_avatar_blacklist.return_value = {
            "keywords": ["SPAM"],
            "senders": [],
            "channels": []
        }
        
        data = [
            {"id": 1, "message": "This is spam"},
            {"id": 2, "message": "This is SPAM"},
            {"id": 3, "message": "This is SpAm"}
        ]
        
        filter_obj = BlacklistFilter(mock_config)
        result = filter_obj.filter(data, "avatar_1")
        
        assert len(result.data) == 0
        assert result.filtered_count == 3
    
    def test_partial_keyword_matching(self):
        """Keywords should match as substrings."""
        mock_config = Mock()
        mock_config.get_avatar_blacklist.return_value = {
            "keywords": ["test"],
            "senders": [],
            "channels": []
        }
        
        data = [
            {"id": 1, "message": "This is a test"},
            {"id": 2, "message": "testing this feature"},
            {"id": 3, "message": "unrelated message"}
        ]
        
        filter_obj = BlacklistFilter(mock_config)
        result = filter_obj.filter(data, "avatar_1")
        
        assert len(result.data) == 1
        assert result.data[0]["id"] == 3
        assert result.filtered_count == 2
    
    def test_media_caption_filtering(self):
        """Should filter based on media captions."""
        mock_config = Mock()
        mock_config.get_avatar_blacklist.return_value = {
            "keywords": ["spam"],
            "senders": [],
            "channels": []
        }
        
        data = [
            {"id": 1, "media": {"caption": "spam content"}},
            {"id": 2, "media": {"caption": "normal content"}}
        ]
        
        filter_obj = BlacklistFilter(mock_config)
        result = filter_obj.filter(data, "avatar_1")
        
        assert len(result.data) == 1
        assert result.data[0]["id"] == 2


class TestBlacklistFilterSenderMatching:
    """Test sender matching behavior."""
    
    def test_sender_exact_id_match(self):
        """Should match sender by exact ID."""
        mock_config = Mock()
        mock_config.get_avatar_blacklist.return_value = {
            "keywords": [],
            "senders": ["123456"],
            "channels": []
        }
        
        data = [
            {"id": 1, "from_id": {"user_id": 123456}},
            {"id": 2, "from_id": {"user_id": 789}}
        ]
        
        filter_obj = BlacklistFilter(mock_config)
        result = filter_obj.filter(data, "avatar_1")
        
        assert len(result.data) == 1
        assert result.filtered_count == 1
    
    def test_sender_channel_id_format(self):
        """Should handle channel ID format in from_id."""
        mock_config = Mock()
        mock_config.get_avatar_blacklist.return_value = {
            "keywords": [],
            "senders": ["999"],
            "channels": []
        }
        
        data = [
            {"id": 1, "from_id": {"channel_id": 999}},
            {"id": 2, "from_id": {"channel_id": 888}}
        ]
        
        filter_obj = BlacklistFilter(mock_config)
        result = filter_obj.filter(data, "avatar_1")
        
        assert len(result.data) == 1
        assert result.filtered_count == 1


class TestBlacklistFilterEdgeCases:
    """Test edge cases and error handling."""
    
    def test_messages_without_text(self):
        """Should handle messages without text fields."""
        mock_config = Mock()
        mock_config.get_avatar_blacklist.return_value = {
            "keywords": ["test"],
            "senders": [],
            "channels": []
        }
        
        data = [
            {"id": 1},  # No message field
            {"id": 2, "message": None}  # None message
        ]
        
        filter_obj = BlacklistFilter(mock_config)
        result = filter_obj.filter(data, "avatar_1")
        
        # Should not crash, should pass items without text
        assert len(result.data) == 2
    
    def test_multiple_rules_match(self):
        """When multiple rules match, should record first match."""
        mock_config = Mock()
        mock_config.get_avatar_blacklist.return_value = {
            "keywords": ["spam", "test"],
            "senders": ["123"],
            "channels": []
        }
        
        data = [
            {"id": 1, "message": "spam and test", "from_id": {"user_id": 123}}
        ]
        
        filter_obj = BlacklistFilter(mock_config)
        result = filter_obj.filter(data, "avatar_1")
        
        assert result.filtered_count == 1
        assert len(result.reasons) == 1
        # Should record first matching rule
        assert "keyword:spam" in result.reasons[0]["reason"]
    
    def test_unicode_in_keywords(self):
        """Should handle Unicode in keywords."""
        mock_config = Mock()
        mock_config.get_avatar_blacklist.return_value = {
            "keywords": ["émoji", "🚀"],
            "senders": [],
            "channels": []
        }
        
        data = [
            {"id": 1, "message": "Message with émoji"},
            {"id": 2, "message": "Rocket 🚀 message"}
        ]
        
        filter_obj = BlacklistFilter(mock_config)
        result = filter_obj.filter(data, "avatar_1")
        
        assert result.filtered_count == 2


class TestBlacklistFilterResult:
    """Test FilterResult dataclass."""
    
    def test_filter_result_structure(self):
        """FilterResult should have correct structure."""
        mock_config = Mock()
        mock_config.get_avatar_blacklist.return_value = {
            "keywords": ["test"],
            "senders": [],
            "channels": []
        }
        
        data = [
            {"id": 1, "message": "normal"},
            {"id": 2, "message": "test message"}
        ]
        
        filter_obj = BlacklistFilter(mock_config)
        result = filter_obj.filter(data, "avatar_1")
        
        assert hasattr(result, 'data')
        assert hasattr(result, 'filtered_count')
        assert hasattr(result, 'reasons')
        assert isinstance(result.data, list)
        assert isinstance(result.filtered_count, int)
        assert isinstance(result.reasons, list)
    
    def test_reason_tracking(self):
        """Should track detailed reasons for filtering."""
        mock_config = Mock()
        mock_config.get_avatar_blacklist.return_value = {
            "keywords": ["spam"],
            "senders": [],
            "channels": []
        }
        
        data = [
            {"id": 123, "message": "spam content"}
        ]
        
        filter_obj = BlacklistFilter(mock_config)
        result = filter_obj.filter(data, "avatar_1")
        
        assert len(result.reasons) == 1
        reason = result.reasons[0]
        assert "index" in reason
        assert "reason" in reason
        assert "item_id" in reason
        assert reason["index"] == 0
        assert "spam" in reason["reason"]
        assert reason["item_id"] == "123"
