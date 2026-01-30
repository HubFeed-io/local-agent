# Agent Test Suite

Comprehensive test suite for the Hubfeed Agent application.

## 📁 Structure

```
tests/
├── __init__.py              # Test package
├── conftest.py              # Shared pytest fixtures
├── pytest.ini               # Pytest configuration
├── README.md                # This file
│
├── unit/                    # Unit tests (isolated)
│   ├── __init__.py
│   ├── test_config_storage.py      # ✅ JSON storage tests
│   ├── test_blacklist_filter.py    # ✅ Blacklist filtering tests
│   ├── test_config_manager.py      # TODO: Config management tests
│   ├── test_history_logger.py      # TODO: History logging tests
│   └── test_auth.py                # TODO: Authentication tests
│
├── integration/             # Integration tests (combined functionality)
│   ├── __init__.py
│   ├── test_api_routes.py          # TODO: API endpoint tests
│   ├── test_executor.py            # TODO: Job executor tests
│   ├── test_loop.py                # TODO: Polling loop tests
│   └── test_hubfeed_client.py      # TODO: HTTP client tests
│
└── e2e/                     # End-to-end tests (full workflows)
    ├── __init__.py
    └── test_full_flow.py           # TODO: Complete agent lifecycle
```

## 🧪 Running Tests

### Install Dependencies

```bash
cd agent
pip install -r requirements.txt
```

### Run All Tests

```bash
pytest
```

### Run Specific Test Categories

```bash
# Run only unit tests
pytest tests/unit

# Run only integration tests
pytest tests/integration

# Run only E2E tests
pytest tests/e2e
```

### Run Specific Test Files

```bash
# Run config storage tests
pytest tests/unit/test_config_storage.py

# Run blacklist filter tests
pytest tests/unit/test_blacklist_filter.py
```

### Run Tests with Coverage

```bash
# Generate coverage report
pytest --cov=src --cov-report=html

# View report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Run Tests with Markers

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run only slow tests
pytest -m slow

# Skip slow tests
pytest -m "not slow"
```

## 📊 Test Coverage

### Completed (✅)

- **Config Storage** (`test_config_storage.py`)
  - ✅ File creation and initialization
  - ✅ Read/write operations
  - ✅ Atomic writes with temp files
  - ✅ Thread-safe concurrent operations
  - ✅ Corrupted JSON handling
  - ✅ Permission errors
  - ✅ Nested data structures
  - ✅ Unicode support
  - ✅ Edge cases (large data, special characters)

- **Blacklist Filter** (`test_blacklist_filter.py`)
  - ✅ Keyword filtering (global + avatar-specific)
  - ✅ Sender filtering
  - ✅ Channel filtering
  - ✅ Case-insensitive matching
  - ✅ Partial keyword matching
  - ✅ Multiple rule matching
  - ✅ Global vs avatar-specific rules
  - ✅ Rule management (add/remove)
  - ✅ Reason tracking
  - ✅ Edge cases (Unicode, regex escaping, whitespace)

### In Progress (🚧)

- **Config Manager** - Avatar CRUD operations
- **History Logger** - Daily rotation and cleanup
- **API Routes** - FastAPI endpoint testing
- **Executor** - Job execution logic
- **Loop** - Polling mechanism
- **Hubfeed Client** - HTTP communication

### Planned (📋)

- **Authentication** - JWT token handling
- **End-to-End** - Full agent lifecycle

## 🛠️ Available Fixtures

From `conftest.py`:

### Data Fixtures
- `temp_data_dir` - Temporary directory for test files
- `mock_config` - Sample configuration data
- `mock_avatar` - Sample avatar data
- `mock_avatars_list` - List of avatars
- `mock_blacklist` - Blacklist rules
- `mock_job` - Job data from SaaS
- `mock_telegram_messages` - Sample Telegram messages

### File Fixtures
- `sample_config_file` - Pre-created config.json
- `sample_avatars_file` - Pre-created avatars.json
- `sample_blacklist_file` - Pre-created blacklist.json
- `sample_history_log` - Pre-created history log

### Client Fixtures
- `test_client` - FastAPI TestClient
- `authenticated_client` - TestClient with auth token

## 📝 Writing New Tests

### Unit Test Example

```python
import pytest
from config.storage import JSONStorage

@pytest.mark.unit
class TestMyModule:
    def test_something(self, temp_data_dir):
        """Test description."""
        # Arrange
        file_path = temp_data_dir / "test.json"
        storage = JSONStorage(file_path, {})
        
        # Act
        storage.write({"key": "value"})
        result = storage.read()
        
        # Assert
        assert result["key"] == "value"
```

### Integration Test Example

```python
import pytest

@pytest.mark.integration
class TestAPIIntegration:
    def test_api_endpoint(self, authenticated_client):
        """Test API endpoint."""
        response = authenticated_client.get("/api/config")
        assert response.status_code == 200
```

## 🎯 Coverage Goals

- **Unit Tests**: 90%+ code coverage
- **Integration Tests**: All critical workflows
- **E2E Tests**: Happy path + error scenarios

## 🐛 Debugging Tests

### Run with verbose output

```bash
pytest -v
```

### Run with print statements

```bash
pytest -s
```

### Run specific test

```bash
pytest tests/unit/test_config_storage.py::TestJSONStorage::test_init_creates_file_if_not_exists
```

### Drop into debugger on failure

```bash
pytest --pdb
```

## 📚 Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Pytest Fixtures](https://docs.pytest.org/en/stable/fixture.html)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [Agent Implementation](../README.md)
