"""History logger for tracking all agent requests and responses with daily rotation."""

import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from src.config.storage import JSONStorage

logger = logging.getLogger(__name__)


class HistoryLogger:
    """Logs all agent requests and responses with daily file rotation."""
    
    MAX_ENTRIES_PER_FILE = 1000
    
    def __init__(self, base_dir: str | Path):
        """Initialize history logger with daily rotation.
        
        Args:
            base_dir: Base directory for the agent (logs will be in base_dir/logs/)
        """
        self.base_dir = Path(base_dir)
        self.logs_dir = self.base_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        self._current_date = None
        self._current_storage = None
    
    def _get_storage_for_date(self, target_date: date) -> JSONStorage:
        """Get storage for a specific date.
        
        Args:
            target_date: Date for the log file
            
        Returns:
            JSONStorage instance for that date
        """
        filename = f"history_{target_date.isoformat()}.json"
        return JSONStorage(self.logs_dir / filename)
    
    def _get_current_storage(self) -> JSONStorage:
        """Get storage for today, rotating if necessary.
        
        Returns:
            JSONStorage instance for today
        """
        today = date.today()
        
        # Check if we need to rotate (new day)
        if self._current_date != today or self._current_storage is None:
            self._current_date = today
            self._current_storage = self._get_storage_for_date(today)
            
            # Ensure structure exists for new file
            if not self._current_storage.exists():
                self._current_storage.save({
                    "date": today.isoformat(),
                    "max_entries": self.MAX_ENTRIES_PER_FILE,
                    "next_id": 1,
                    "entries": []
                })
        
        return self._current_storage
    
    async def log_job(
        self,
        job_id: str,
        avatar_id: str,
        command: str,
        params: Dict[str, Any],
        success: bool,
        items_count: int = 0,
        filtered_count: int = 0,
        execution_ms: int = 0,
        error: Optional[Dict[str, str]] = None
    ) -> bool:
        """Log a job execution (async wrapper for executor compatibility).
        
        Args:
            job_id: Job identifier
            avatar_id: Avatar used for execution
            command: Command executed
            params: Command parameters
            success: Whether execution was successful
            items_count: Number of items returned
            filtered_count: Number of items filtered
            execution_ms: Execution time in milliseconds
            error: Error information (if failed)
            
        Returns:
            True if successful
        """
        # Convert parameters to log() format
        status = "success" if success else "failed"
        error_msg = error.get("message") if error else None
        
        # Call synchronous log method
        return self.log(
            job_id=job_id,
            avatar_id=avatar_id,
            command=command,
            params=params,
            status=status,
            items_returned=items_count,
            items_filtered=filtered_count,
            error=error_msg,
            execution_ms=execution_ms
        )
    
    def log(
        self,
        job_id: str,
        avatar_id: str,
        command: str,
        params: Dict[str, Any],
        status: str,
        items_returned: int = 0,
        items_filtered: int = 0,
        filter_reasons: Optional[List[Dict[str, Any]]] = None,
        error: Optional[str] = None,
        execution_ms: int = 0
    ) -> bool:
        """Log a request/response (job execution).
        
        Args:
            job_id: Job identifier
            avatar_id: Avatar used for execution
            command: Command executed
            params: Command parameters
            status: Execution status (success, failed)
            items_returned: Number of items returned
            items_filtered: Number of items filtered
            filter_reasons: List of filter reasons
            error: Error message if failed
            execution_ms: Execution time in milliseconds
            
        Returns:
            True if successful
        """
        # Convert to audit event format for unified logging
        details = {
            "command": command,
            "params": params,
            "items_returned": items_returned,
            "items_filtered": items_filtered,
            "execution_ms": execution_ms
        }
        
        if filter_reasons:
            details["filter_reasons"] = filter_reasons
        
        return self.log_audit_event(
            event_type="job_execution",
            actor="user",
            resource_type="job",
            resource_id=job_id,
            action="execute",
            details=details,
            status=status,
            error=error
        )
    
    def log_audit_event(
        self,
        event_type: str,
        actor: str,
        resource_type: str,
        resource_id: str,
        action: str,
        details: Dict[str, Any],
        status: str = "success",
        error: Optional[str] = None
    ) -> bool:
        """Log an audit event.
        
        Args:
            event_type: Type of event (job_execution, avatar_created, etc.)
            actor: Who performed the action (typically "user")
            resource_type: Type of resource affected (avatar, channel, job, etc.)
            resource_id: Identifier of the resource
            action: Action performed (create, update, delete, execute, etc.)
            details: Event-specific details
            status: Event status (success, failed)
            error: Error message if failed
            
        Returns:
            True if successful
        """
        storage = self._get_current_storage()
        
        def updater(data):
            entry = {
                "id": data["next_id"],
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "event_type": event_type,
                "actor": actor,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "action": action,
                "details": details,
                "status": status
            }
            
            if error:
                entry["error"] = error
            
            # Add backward compatibility fields for job_execution events
            if event_type == "job_execution":
                entry["job_id"] = resource_id
                entry["avatar_id"] = details.get("avatar_id", "")
                entry["command"] = details.get("command", "")
                entry["params"] = details.get("params", {})
                entry["items_returned"] = details.get("items_returned", 0)
                entry["items_filtered"] = details.get("items_filtered", 0)
                entry["execution_ms"] = details.get("execution_ms", 0)
                if "filter_reasons" in details:
                    entry["filter_reasons"] = details["filter_reasons"]
            
            # Add entry
            data["entries"].append(entry)
            data["next_id"] += 1
            
            # Trim if over limit (keep most recent)
            if len(data["entries"]) > self.MAX_ENTRIES_PER_FILE:
                data["entries"] = data["entries"][-self.MAX_ENTRIES_PER_FILE:]
            
            return data
        
        success = storage.update(updater)
        if success:
            logger.info(
                f"Logged {event_type}: actor={actor}, resource={resource_type}:{resource_id}, "
                f"action={action}, status={status}"
            )
        return success
    
    def log_avatar_event(
        self,
        action: str,
        avatar_id: str,
        details: Optional[Dict[str, Any]] = None,
        actor: str = "user",
        status: str = "success",
        error: Optional[str] = None
    ) -> bool:
        """Log an avatar-related event.
        
        Args:
            action: Action performed (create, update, delete, query, status_change)
            avatar_id: Avatar identifier
            details: Additional event details
            actor: Who performed the action
            status: Event status
            error: Error message if failed
            
        Returns:
            True if successful
        """
        event_type = f"avatar_{action}"
        return self.log_audit_event(
            event_type=event_type,
            actor=actor,
            resource_type="avatar",
            resource_id=avatar_id,
            action=action,
            details=details or {},
            status=status,
            error=error
        )
    
    def log_channel_event(
        self,
        action: str,
        channel_id: str,
        avatar_id: str,
        details: Optional[Dict[str, Any]] = None,
        actor: str = "user",
        status: str = "success",
        error: Optional[str] = None
    ) -> bool:
        """Log a channel/source-related event.
        
        Args:
            action: Action performed (added, removed, updated, queried)
            channel_id: Channel/source identifier
            avatar_id: Associated avatar identifier
            details: Additional event details
            actor: Who performed the action
            status: Event status
            error: Error message if failed
            
        Returns:
            True if successful
        """
        event_type = f"source_{action}"
        event_details = {"avatar_id": avatar_id}
        if details:
            event_details.update(details)
        
        return self.log_audit_event(
            event_type=event_type,
            actor=actor,
            resource_type="source",
            resource_id=channel_id,
            action=action,
            details=event_details,
            status=status,
            error=error
        )
    
    def log_auth_event(
        self,
        action: str,
        avatar_id: str,
        details: Optional[Dict[str, Any]] = None,
        actor: str = "user",
        status: str = "success",
        error: Optional[str] = None
    ) -> bool:
        """Log an authentication-related event.
        
        Args:
            action: Action performed (started, completed, failed, cancelled)
            avatar_id: Avatar identifier
            details: Additional event details (method, phone, etc.)
            actor: Who performed the action
            status: Event status
            error: Error message if failed
            
        Returns:
            True if successful
        """
        event_type = f"auth_{action}"
        return self.log_audit_event(
            event_type=event_type,
            actor=actor,
            resource_type="auth",
            resource_id=avatar_id,
            action=action,
            details=details or {},
            status=status,
            error=error
        )
    
    def log_system_event(
        self,
        action: str,
        resource_type: str,
        resource_id: str,
        details: Optional[Dict[str, Any]] = None,
        actor: str = "user",
        status: str = "success",
        error: Optional[str] = None
    ) -> bool:
        """Log a system operation event.
        
        Args:
            action: Action performed (queried, listed, synced, etc.)
            resource_type: Type of resource (account, channels, dialogs, config)
            resource_id: Resource identifier
            details: Additional event details
            actor: Who performed the action
            status: Event status
            error: Error message if failed
            
        Returns:
            True if successful
        """
        event_type = f"{resource_type}_{action}"
        return self.log_audit_event(
            event_type=event_type,
            actor=actor,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            details=details or {},
            status=status,
            error=error
        )
    
    def get_recent(self, limit: int = 50, days: int = 7) -> List[Dict[str, Any]]:
        """Get most recent entries from recent days.
        
        Args:
            limit: Maximum number of entries to return
            days: Number of days to look back
            
        Returns:
            List of entries (newest first)
        """
        all_entries = []
        today = date.today()
        
        # Collect entries from recent days
        for i in range(days):
            target_date = today - timedelta(days=i)
            storage = self._get_storage_for_date(target_date)
            
            if storage.exists():
                data = storage.load(default={"entries": []})
                entries = data.get("entries", [])
                all_entries.extend(entries)
        
        # Sort by timestamp (newest first) and limit
        all_entries.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return all_entries[:limit]
    
    def get_by_avatar(self, avatar_id: str, limit: int = 50, days: int = 7) -> List[Dict[str, Any]]:
        """Get entries for specific avatar from recent days.
        
        Args:
            avatar_id: Avatar identifier
            limit: Maximum number of entries to return
            days: Number of days to look back
            
        Returns:
            List of entries (newest first)
        """
        all_entries = []
        today = date.today()
        
        # Collect entries from recent days
        for i in range(days):
            target_date = today - timedelta(days=i)
            storage = self._get_storage_for_date(target_date)
            
            if storage.exists():
                data = storage.load(default={"entries": []})
                entries = data.get("entries", [])
                # Filter by avatar
                filtered = [e for e in entries if e.get("avatar_id") == avatar_id]
                all_entries.extend(filtered)
        
        # Sort by timestamp (newest first) and limit
        all_entries.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return all_entries[:limit]
    
    def get_by_job(self, job_id: str, days: int = 7) -> Optional[Dict[str, Any]]:
        """Get entry for specific job from recent days.
        
        Args:
            job_id: Job identifier
            days: Number of days to look back
            
        Returns:
            Entry data or None
        """
        today = date.today()
        
        # Search recent days
        for i in range(days):
            target_date = today - timedelta(days=i)
            storage = self._get_storage_for_date(target_date)
            
            if storage.exists():
                data = storage.load(default={"entries": []})
                entries = data.get("entries", [])
                
                # Find by job_id
                for entry in reversed(entries):  # Search from newest
                    if entry.get("job_id") == job_id:
                        return entry
        return None
    
    async def query_history(
        self,
        avatar_id: Optional[str] = None,
        job_id: Optional[str] = None,
        date: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Query history with optional filters.
        
        Args:
            avatar_id: Filter by avatar ID
            job_id: Filter by job ID
            date: Filter by date (YYYY-MM-DD format)
            limit: Maximum number of entries to return
            
        Returns:
            List of history entries matching the filters
        """
        from datetime import date as date_class
        
        # If job_id is provided, return that specific job
        if job_id:
            entry = self.get_by_job(job_id, days=30)
            return [entry] if entry else []
        
        # If date is provided, load entries from that specific date
        if date:
            try:
                target_date = date_class.fromisoformat(date)
                storage = self._get_storage_for_date(target_date)
                
                if storage.exists():
                    data = storage.load(default={"entries": []})
                    entries = data.get("entries", [])
                    
                    # Filter by avatar if provided
                    if avatar_id:
                        entries = [e for e in entries if e.get("avatar_id") == avatar_id]
                    
                    # Sort by timestamp (newest first) and limit
                    entries.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
                    return entries[:limit]
                
                return []
            except (ValueError, Exception) as e:
                logger.warning(f"Invalid date format: {date}, {e}")
                return []
        
        # If avatar_id is provided, get entries for that avatar
        if avatar_id:
            return self.get_by_avatar(avatar_id, limit=limit, days=30)
        
        # Otherwise, return recent entries
        return self.get_recent(limit=limit, days=30)
    
    def query_by_event_type(
        self,
        event_type: str,
        limit: int = 50,
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """Query entries by event type.
        
        Args:
            event_type: Event type to filter by
            limit: Maximum number of entries to return
            days: Number of days to look back
            
        Returns:
            List of entries matching the event type (newest first)
        """
        all_entries = []
        today = date.today()
        
        # Collect entries from recent days
        for i in range(days):
            target_date = today - timedelta(days=i)
            storage = self._get_storage_for_date(target_date)
            
            if storage.exists():
                data = storage.load(default={"entries": []})
                entries = data.get("entries", [])
                # Filter by event type
                filtered = [e for e in entries if e.get("event_type") == event_type]
                all_entries.extend(filtered)
        
        # Sort by timestamp (newest first) and limit
        all_entries.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return all_entries[:limit]
    
    def query_by_resource(
        self,
        resource_type: str,
        resource_id: Optional[str] = None,
        limit: int = 50,
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """Query entries by resource type and optionally resource ID.
        
        Args:
            resource_type: Type of resource (avatar, source, job, etc.)
            resource_id: Optional specific resource ID
            limit: Maximum number of entries to return
            days: Number of days to look back
            
        Returns:
            List of entries matching the resource criteria (newest first)
        """
        all_entries = []
        today = date.today()
        
        # Collect entries from recent days
        for i in range(days):
            target_date = today - timedelta(days=i)
            storage = self._get_storage_for_date(target_date)
            
            if storage.exists():
                data = storage.load(default={"entries": []})
                entries = data.get("entries", [])
                
                # Filter by resource type
                filtered = [e for e in entries if e.get("resource_type") == resource_type]
                
                # Further filter by resource_id if provided
                if resource_id:
                    filtered = [e for e in filtered if e.get("resource_id") == resource_id]
                
                all_entries.extend(filtered)
        
        # Sort by timestamp (newest first) and limit
        all_entries.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return all_entries[:limit]
    
    def get_audit_trail(
        self,
        resource_type: str,
        resource_id: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """Get complete audit trail for a specific resource.
        
        Args:
            resource_type: Type of resource (avatar, source, etc.)
            resource_id: Resource identifier
            days: Number of days to look back
            
        Returns:
            List of all events for the resource (chronological order, oldest first)
        """
        entries = self.query_by_resource(resource_type, resource_id, limit=10000, days=days)
        # Return in chronological order (oldest first) for audit trail
        entries.sort(key=lambda x: x.get("timestamp", ""))
        return entries
    
    def get_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get summary statistics from recent days.
        
        Args:
            days: Number of days to include
            
        Returns:
            Statistics dictionary with event type breakdown
        """
        all_entries = []
        today = date.today()
        
        # Collect entries from recent days
        for i in range(days):
            target_date = today - timedelta(days=i)
            storage = self._get_storage_for_date(target_date)
            
            if storage.exists():
                data = storage.load(default={"entries": []})
                entries = data.get("entries", [])
                all_entries.extend(entries)
        
        if not all_entries:
            return {
                "total_events": 0,
                "successful": 0,
                "failed": 0,
                "total_items_returned": 0,
                "total_items_filtered": 0,
                "avg_execution_ms": 0,
                "event_types": {}
            }
        
        successful = sum(1 for e in all_entries if e.get("status") == "success")
        failed = sum(1 for e in all_entries if e.get("status") == "failed")
        total_items = sum(e.get("items_returned", 0) for e in all_entries)
        total_filtered = sum(e.get("items_filtered", 0) for e in all_entries)
        avg_time = sum(e.get("execution_ms", 0) for e in all_entries) / len(all_entries)
        
        # Event type breakdown
        event_types = {}
        for entry in all_entries:
            event_type = entry.get("event_type", "unknown")
            if event_type not in event_types:
                event_types[event_type] = {
                    "count": 0,
                    "successful": 0,
                    "failed": 0
                }
            event_types[event_type]["count"] += 1
            if entry.get("status") == "success":
                event_types[event_type]["successful"] += 1
            elif entry.get("status") == "failed":
                event_types[event_type]["failed"] += 1
        
        return {
            "total_events": len(all_entries),
            "successful": successful,
            "failed": failed,
            "total_items_returned": total_items,
            "total_items_filtered": total_filtered,
            "avg_execution_ms": int(avg_time),
            "event_types": event_types
        }
    
    def list_log_files(self) -> List[str]:
        """List all history log files.
        
        Returns:
            List of log file dates (YYYY-MM-DD format)
        """
        log_files = sorted(self.logs_dir.glob("history_*.json"))
        return [f.stem.replace("history_", "") for f in log_files]
    
    def cleanup_old_logs(self, keep_days: int = 30) -> int:
        """Delete log files older than specified days.
        
        Args:
            keep_days: Number of days to keep
            
        Returns:
            Number of files deleted
        """
        today = date.today()
        deleted = 0
        
        for log_file in self.logs_dir.glob("history_*.json"):
            try:
                # Extract date from filename
                date_str = log_file.stem.replace("history_", "")
                file_date = date.fromisoformat(date_str)
                
                # Check if too old
                if (today - file_date).days > keep_days:
                    log_file.unlink()
                    deleted += 1
                    logger.info(f"Deleted old log file: {log_file.name}")
            except (ValueError, OSError) as e:
                logger.warning(f"Failed to process log file {log_file.name}: {e}")
        
        return deleted
