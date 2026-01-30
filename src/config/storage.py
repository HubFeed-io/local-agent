"""JSON file storage with thread-safe operations."""

import json
import threading
from pathlib import Path
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


class JSONStorage:
    """Thread-safe JSON file storage."""
    
    def __init__(self, file_path: str | Path):
        """Initialize storage for a JSON file.
        
        Args:
            file_path: Path to the JSON file
        """
        self.file_path = Path(file_path)
        self._lock = threading.RLock()
        self._ensure_directory()
    
    def _ensure_directory(self):
        """Create parent directory if it doesn't exist."""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
    
    def load(self, default: Optional[Any] = None) -> Any:
        """Load data from JSON file.
        
        Args:
            default: Default value if file doesn't exist
            
        Returns:
            Loaded data or default value
        """
        with self._lock:
            if not self.file_path.exists():
                if default is not None:
                    self.save(default)
                    return default
                return None
            
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from {self.file_path}: {e}")
                return default
            except Exception as e:
                logger.error(f"Failed to load {self.file_path}: {e}")
                return default
    
    def save(self, data: Any) -> bool:
        """Save data to JSON file.
        
        Args:
            data: Data to save (must be JSON serializable)
            
        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            try:
                # Write to temporary file first
                temp_path = self.file_path.with_suffix('.tmp')
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, default=str, ensure_ascii=False)
                
                # Atomic rename
                temp_path.replace(self.file_path)
                return True
            except Exception as e:
                logger.error(f"Failed to save {self.file_path}: {e}")
                return False
    
    def update(self, updater: callable) -> bool:
        """Update data with a function.
        
        Args:
            updater: Function that takes current data and returns updated data
            
        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            data = self.load(default={})
            updated_data = updater(data)
            return self.save(updated_data)
    
    def exists(self) -> bool:
        """Check if file exists."""
        return self.file_path.exists()
    
    def delete(self) -> bool:
        """Delete the file.
        
        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            try:
                if self.file_path.exists():
                    self.file_path.unlink()
                return True
            except Exception as e:
                logger.error(f"Failed to delete {self.file_path}: {e}")
                return False
