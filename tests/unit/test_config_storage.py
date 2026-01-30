"""
Unit tests for config.storage module.

Tests the JSON file storage system including thread-safe operations,
atomic writes, and error handling.
"""

import pytest
import json
import threading
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from config.storage import JSONStorage


@pytest.mark.unit
class TestJSONStorage:
    """Test cases for JSONStorage class."""
    
    def test_init_creates_directory(self, temp_data_dir):
        """Test that initialization creates parent directory."""
        file_path = temp_data_dir / "nested" / "test.json"
        storage = JSONStorage(file_path)
        
        assert file_path.parent.exists()
    
    def test_load_creates_file_with_default(self, temp_data_dir):
        """Test that load creates file with default data if not exists."""
        file_path = temp_data_dir / "test.json"
        default_data = {"key": "value"}
        
        storage = JSONStorage(file_path)
        data = storage.load(default=default_data)
        
        assert file_path.exists()
        assert data == default_data
    
    def test_load_returns_existing_data(self, temp_data_dir):
        """Test that load returns existing file data."""
        file_path = temp_data_dir / "test.json"
        existing_data = {"existing": "data"}
        
        # Create existing file
        with open(file_path, "w") as f:
            json.dump(existing_data, f)
        
        storage = JSONStorage(file_path)
        data = storage.load(default={"default": "data"})
        
        assert data == existing_data
    
    def test_save_writes_data(self, temp_data_dir):
        """Test saving data to storage."""
        file_path = temp_data_dir / "test.json"
        storage = JSONStorage(file_path)
        
        test_data = {"new": "data", "list": [1, 2, 3]}
        result = storage.save(test_data)
        
        assert result is True
        
        # Verify by reading file directly
        with open(file_path) as f:
            saved_data = json.load(f)
        assert saved_data == test_data
    
    def test_atomic_write_with_temp_file(self, temp_data_dir):
        """Test that writes use atomic temp file strategy."""
        file_path = temp_data_dir / "test.json"
        storage = JSONStorage(file_path)
        
        # Save initial data
        storage.save({"initial": "data"})
        
        # Save new data
        new_data = {"atomic": "write"}
        storage.save(new_data)
        
        # Verify temp file doesn't exist (cleaned up)
        temp_file = file_path.with_suffix('.tmp')
        assert not temp_file.exists()
        
        # Verify final file has correct data
        assert storage.load() == new_data
    
    def test_update_method(self, temp_data_dir):
        """Test update method with updater function."""
        file_path = temp_data_dir / "test.json"
        storage = JSONStorage(file_path)
        
        # Initialize with data
        storage.save({"counter": 0, "name": "test"})
        
        # Update using updater function
        def increment(data):
            data["counter"] += 1
            return data
        
        result = storage.update(increment)
        assert result is True
        
        # Verify update
        data = storage.load()
        assert data["counter"] == 1
        assert data["name"] == "test"
    
    def test_concurrent_updates(self, temp_data_dir):
        """Test thread-safe concurrent updates."""
        file_path = temp_data_dir / "test.json"
        storage = JSONStorage(file_path)
        
        # Initialize
        storage.save({"counter": 0})
        
        def increment_counter(thread_id):
            for _ in range(10):
                def updater(data):
                    data["counter"] += 1
                    data[f"thread_{thread_id}"] = True
                    return data
                storage.update(updater)
        
        # Run multiple threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=increment_counter, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # Verify final state
        final_data = storage.load()
        assert final_data["counter"] == 50  # 5 threads * 10 increments
        assert all(f"thread_{i}" in final_data for i in range(5))
    
    def test_corrupted_json_returns_default(self, temp_data_dir):
        """Test that corrupted JSON returns default data."""
        file_path = temp_data_dir / "test.json"
        default_data = {"default": "data"}
        
        # Create corrupted JSON file
        with open(file_path, "w") as f:
            f.write("{invalid json content")
        
        storage = JSONStorage(file_path)
        data = storage.load(default=default_data)
        
        assert data == default_data
    
    def test_exists_method(self, temp_data_dir):
        """Test exists method."""
        file_path = temp_data_dir / "test.json"
        storage = JSONStorage(file_path)
        
        assert storage.exists() is False
        
        storage.save({"test": "data"})
        assert storage.exists() is True
    
    def test_delete_method(self, temp_data_dir):
        """Test delete method."""
        file_path = temp_data_dir / "test.json"
        storage = JSONStorage(file_path)
        
        # Create file
        storage.save({"test": "data"})
        assert file_path.exists()
        
        # Delete
        result = storage.delete()
        assert result is True
        assert not file_path.exists()
    
    def test_delete_nonexistent_file(self, temp_data_dir):
        """Test deleting non-existent file."""
        file_path = temp_data_dir / "nonexistent.json"
        storage = JSONStorage(file_path)
        
        result = storage.delete()
        assert result is True
    
    def test_nested_data_structures(self, temp_data_dir):
        """Test handling of nested data structures."""
        file_path = temp_data_dir / "test.json"
        complex_data = {
            "users": [
                {"id": 1, "name": "Alice", "tags": ["admin", "active"]},
                {"id": 2, "name": "Bob", "tags": ["user"]}
            ],
            "config": {
                "nested": {
                    "deeply": {
                        "value": 42
                    }
                }
            }
        }
        
        storage = JSONStorage(file_path)
        storage.save(complex_data)
        result = storage.load()
        
        assert result == complex_data
        assert result["config"]["nested"]["deeply"]["value"] == 42
    
    def test_empty_data(self, temp_data_dir):
        """Test handling of empty data."""
        file_path = temp_data_dir / "test.json"
        storage = JSONStorage(file_path)
        
        storage.save({})
        result = storage.load()
        
        assert result == {}
    
    def test_unicode_data(self, temp_data_dir):
        """Test handling of Unicode characters."""
        file_path = temp_data_dir / "test.json"
        unicode_data = {
            "emoji": "🎉🚀💡",
            "chinese": "你好世界",
            "arabic": "مرحبا بالعالم",
            "russian": "Привет мир"
        }
        
        storage = JSONStorage(file_path)
        storage.save(unicode_data)
        result = storage.load()
        
        assert result == unicode_data


@pytest.mark.unit
class TestJSONStorageEdgeCases:
    """Edge cases and error handling for JSONStorage."""
    
    def test_nonexistent_directory_created(self, temp_data_dir):
        """Test that parent directories are created automatically."""
        file_path = temp_data_dir / "nested" / "dir" / "test.json"
        storage = JSONStorage(file_path)
        
        storage.save({"test": "data"})
        
        assert file_path.exists()
        assert storage.load() == {"test": "data"}
    
    def test_large_data(self, temp_data_dir):
        """Test handling of large data structures."""
        file_path = temp_data_dir / "test.json"
        large_data = {
            "items": [{"id": i, "data": f"item_{i}"} for i in range(1000)]
        }
        
        storage = JSONStorage(file_path)
        storage.save(large_data)
        result = storage.load()
        
        assert len(result["items"]) == 1000
        assert result["items"][500]["id"] == 500
    
    def test_special_characters_in_keys(self, temp_data_dir):
        """Test keys with special characters."""
        file_path = temp_data_dir / "test.json"
        special_data = {
            "key.with.dots": "value1",
            "key-with-dashes": "value2",
            "key_with_underscores": "value3",
            "key with spaces": "value4"
        }
        
        storage = JSONStorage(file_path)
        storage.save(special_data)
        result = storage.load()
        
        assert result == special_data
    
    def test_reentrant_lock_allows_nested_calls(self, temp_data_dir):
        """Test that RLock allows nested method calls."""
        file_path = temp_data_dir / "test.json"
        storage = JSONStorage(file_path)
        
        # This should not deadlock thanks to RLock
        def updater(data):
            # update() calls load() and save() which also acquire the lock
            data["updated"] = True
            return data
        
        result = storage.update(updater)
        assert result is True
        
        data = storage.load()
        assert data["updated"] is True
