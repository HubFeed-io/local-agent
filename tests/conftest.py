"""
Shared pytest fixtures for agent tests.

This module provides common fixtures used across all test modules.
"""

import pytest
import tempfile
import shutil
import json
from pathlib import Path
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from typing import Dict, Any


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory for tests."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_config() -> Dict[str, Any]:
    """Mock configuration data."""
    return {
        "token": "test_token_abc123",
        "verified": True,
        "polling_interval": 30
    }


@pytest.fixture
def mock_avatar() -> Dict[str, Any]:
    """Mock avatar data."""
    return {
        "id": "tg_test_12345",
        "name": "Test Telegram Avatar",
        "platform": "telegram",
        "status": "active",
        "created_at": datetime.utcnow().isoformat()
    }


@pytest.fixture
def mock_avatars_list(mock_avatar) -> list:
    """Mock list of avatars."""
    return [
        mock_avatar,
        {
            "id": "tg_test_67890",
            "name": "Another Test Avatar",
            "platform": "telegram",
            "status": "inactive",
            "created_at": datetime.utcnow().isoformat()
        }
    ]


@pytest.fixture
def mock_blacklist() -> Dict[str, Any]:
    """Mock blacklist configuration."""
    return {
        "global": {
            "keywords": ["spam", "scam"],
            "senders": ["@baduser"],
            "channels": []
        },
        "tg_test_12345": {
            "keywords": ["crypto", "pump"],
            "senders": [],
            "channels": ["@blacklisted_channel"]
        }
    }


@pytest.fixture
def mock_job() -> Dict[str, Any]:
    """Mock job data from SaaS."""
    return {
        "job_id": "job_test_999",
        "avatar_id": "tg_test_12345",
        "command": "telegram.get_messages",
        "params": {
            "channel": "@test_channel",
            "limit": 100
        }
    }


@pytest.fixture
def mock_telegram_messages() -> list:
    """Mock Telegram messages for testing."""
    return [
        {
            "id": 1001,
            "date": datetime.utcnow().isoformat(),
            "message": "Test message 1",
            "from_id": "user_123",
            "to_id": "channel_456"
        },
        {
            "id": 1002,
            "date": datetime.utcnow().isoformat(),
            "message": "Test message with spam keyword",
            "from_id": "user_789",
            "to_id": "channel_456"
        },
        {
            "id": 1003,
            "date": datetime.utcnow().isoformat(),
            "message": "Clean test message 3",
            "from_id": "user_123",
            "to_id": "channel_456"
        }
    ]


@pytest.fixture
def test_client():
    """FastAPI test client."""
    # Import here to avoid circular imports
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    
    from main import app
    return TestClient(app)


@pytest.fixture
def authenticated_client(test_client):
    """FastAPI test client with authentication."""
    # Login to get token
    response = test_client.post(
        "/api/login",
        json={"username": "admin", "password": "changeme"}
    )
    token = response.json()["token"]
    
    # Add auth header to client
    test_client.headers["Authorization"] = f"Bearer {token}"
    return test_client


@pytest.fixture
def sample_config_file(temp_data_dir, mock_config):
    """Create a sample config.json file."""
    config_path = temp_data_dir / "config.json"
    with open(config_path, "w") as f:
        json.dump(mock_config, f)
    return config_path


@pytest.fixture
def sample_avatars_file(temp_data_dir, mock_avatars_list):
    """Create a sample avatars.json file."""
    avatars_path = temp_data_dir / "avatars.json"
    with open(avatars_path, "w") as f:
        json.dump(mock_avatars_list, f)
    return avatars_path


@pytest.fixture
def sample_blacklist_file(temp_data_dir, mock_blacklist):
    """Create a sample blacklist.json file."""
    blacklist_path = temp_data_dir / "blacklist.json"
    with open(blacklist_path, "w") as f:
        json.dump(mock_blacklist, f)
    return blacklist_path


@pytest.fixture
def sample_history_log(temp_data_dir):
    """Create a sample history log file."""
    logs_dir = temp_data_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    
    log_file = logs_dir / f"history_{datetime.utcnow().strftime('%Y-%m-%d')}.json"
    log_data = [
        {
            "timestamp": datetime.utcnow().isoformat(),
            "job_id": "job_001",
            "avatar_id": "tg_test_12345",
            "command": "telegram.get_messages",
            "status": "success",
            "execution_time_ms": 1234,
            "items_count": 10
        },
        {
            "timestamp": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
            "job_id": "job_002",
            "avatar_id": "tg_test_12345",
            "command": "telegram.get_channel_info",
            "status": "success",
            "execution_time_ms": 567,
            "items_count": 1
        }
    ]
    
    with open(log_file, "w") as f:
        for entry in log_data:
            f.write(json.dumps(entry) + "\n")
    
    return log_file


@pytest.fixture(autouse=True)
def reset_globals():
    """Reset global state between tests."""
    # Import and reset globals if needed
    yield
    # Cleanup after test
