"""JSON-based database implementation for the Spack installer queue system."""

import os
import json
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any, Generator
from contextlib import contextmanager
from .models import JobStatus, JobPriority
from .config import config

# Default database path from config
DEFAULT_DB_PATH = config.get_database_path()


class JSONDatabase:
    """JSON-based database for storing job and worker information."""
    
    def __init__(self, db_path: str = None):
        """Initialize the JSON database.
        
        Args:
            db_path: Path to JSON file. If None, uses default path.
        """
        self.db_path = db_path or DEFAULT_DB_PATH
        
        # Ensure directory exists
        db_dir = os.path.dirname(self.db_path)
        os.makedirs(db_dir, exist_ok=True)
        
        # Thread lock for concurrent access
        self._lock = threading.RLock()
        
        # Initialize database if it doesn't exist
        self._initialize_db()
    
    def _initialize_db(self):
        """Initialize the database file if it doesn't exist."""
        if not os.path.exists(self.db_path):
            initial_data = {
                "jobs": [],
                "logs": [],
                "worker_status": None,
                "next_job_id": 1
            }
            self._write_data(initial_data)
    
    def _read_data(self) -> Dict[str, Any]:
        """Read data from JSON file."""
        try:
            with open(self.db_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # If file doesn't exist or is corrupted, reinitialize
            self._initialize_db()
            with open(self.db_path, 'r') as f:
                return json.load(f)
    
    def _write_data(self, data: Dict[str, Any]):
        """Write data to JSON file."""
        with open(self.db_path, 'w') as f:
            json.dump(data, f, indent=2, default=self._json_serializer)
    
    def _json_serializer(self, obj):
        """Custom JSON serializer for datetime objects."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    def _parse_datetime(self, dt_str: str) -> Optional[datetime]:
        """Parse datetime string back to datetime object."""
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str)
        except (ValueError, TypeError):
            return None
    
    @contextmanager
    def _transaction(self):
        """Context manager for thread-safe database operations."""
        with self._lock:
            data = self._read_data()
            try:
                yield data
                self._write_data(data)
            except Exception:
                # Don't save if there's an error
                raise
    
    def create_job(
        self,
        package_name: str,
        priority: JobPriority,
        estimated_time: float,
        submitted_by: str,
        spack_command: str = None,
        dependencies: List[str] = None,
        resource_requirements: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Create a new job and return its data as a dictionary."""
        with self._transaction() as data:
            # Check if package is already queued or installed
            existing_job = None
            for job in data["jobs"]:
                if (job["package_name"] == package_name and 
                    job["status"] in ["pending", "running"]):
                    existing_job = job
                    break
            
            if existing_job:
                raise ValueError(f"Package '{package_name}' is already queued or being installed (Job ID: {existing_job['id']})")
            
            # Create new job
            job_id = data["next_job_id"]
            data["next_job_id"] += 1
            
            job = {
                'id': job_id,
                'package_name': package_name,
                'priority': priority.value,
                'status': JobStatus.PENDING.value,
                'estimated_time': estimated_time,
                'actual_time': None,
                'submitted_by': submitted_by,
                'submitted_at': datetime.utcnow(),
                'started_at': None,
                'completed_at': None,
                'spack_command': spack_command,
                'error_message': None,
                'dependencies_list': dependencies or [],
                'resource_requirements_dict': resource_requirements or {}
            }
            
            data["jobs"].append(job)
            
            # Add log entry
            log_entry = {
                'id': len(data["logs"]) + 1,
                'job_id': job_id,
                'timestamp': datetime.utcnow(),
                'level': "INFO",
                'message': f"Job submitted for package '{package_name}'"
            }
            data["logs"].append(log_entry)
            
            # Return a copy with parsed datetimes for consistency
            job_copy = job.copy()
            job_copy['submitted_at'] = job['submitted_at']
            job_copy['started_at'] = self._parse_datetime(job['started_at'])
            job_copy['completed_at'] = self._parse_datetime(job['completed_at'])
            
            return job_copy
    
    def get_job_by_id(self, job_id: int) -> Optional[Dict[str, Any]]:
        """Get a job by ID, returning a dictionary."""
        with self._transaction() as data:
            for job in data["jobs"]:
                if job["id"] == job_id:
                    job_copy = job.copy()
                    job_copy['submitted_at'] = self._parse_datetime(job['submitted_at'])
                    job_copy['started_at'] = self._parse_datetime(job['started_at'])
                    job_copy['completed_at'] = self._parse_datetime(job['completed_at'])
                    
                    # Add retry fields for backward compatibility
                    if 'retry_count' not in job_copy:
                        job_copy['retry_count'] = 0
                    if 'max_retries' not in job_copy:
                        job_copy['max_retries'] = config.DEFAULT_MAX_RETRIES
                    if 'last_retry_at' not in job_copy:
                        job_copy['last_retry_at'] = None
                    if 'retry_delay' not in job_copy:
                        job_copy['retry_delay'] = config.DEFAULT_RETRY_DELAY
                    if 'is_retry' not in job_copy:
                        job_copy['is_retry'] = False
                    if 'original_job_id' not in job_copy:
                        job_copy['original_job_id'] = None
                    else:
                        job_copy['last_retry_at'] = self._parse_datetime(job['last_retry_at'])
                    
                    return job_copy
            return None
    
    def get_all_jobs(self, status: Optional[JobStatus] = None) -> List[Dict[str, Any]]:
        """Get all jobs, optionally filtered by status, returning dictionaries."""
        with self._transaction() as data:
            jobs = []
            for job in data["jobs"]:
                if status is None or job["status"] == status.value:
                    job_copy = job.copy()
                    job_copy['submitted_at'] = self._parse_datetime(job['submitted_at'])
                    job_copy['started_at'] = self._parse_datetime(job['started_at'])
                    job_copy['completed_at'] = self._parse_datetime(job['completed_at'])
                    
                    # Add retry fields for backward compatibility
                    if 'retry_count' not in job_copy:
                        job_copy['retry_count'] = 0
                    if 'max_retries' not in job_copy:
                        job_copy['max_retries'] = config.DEFAULT_MAX_RETRIES
                    if 'last_retry_at' not in job_copy:
                        job_copy['last_retry_at'] = None
                    if 'retry_delay' not in job_copy:
                        job_copy['retry_delay'] = config.DEFAULT_RETRY_DELAY
                    if 'is_retry' not in job_copy:
                        job_copy['is_retry'] = False
                    if 'original_job_id' not in job_copy:
                        job_copy['original_job_id'] = None
                    else:
                        job_copy['last_retry_at'] = self._parse_datetime(job['last_retry_at'])
                    
                    jobs.append(job_copy)
            
            # Sort by submitted_at descending
            jobs.sort(key=lambda x: x['submitted_at'] or datetime.min, reverse=True)
            return jobs
    
    def update_job_status(
        self,
        job_id: int,
        status: JobStatus,
        started_at=None,
        completed_at=None,
        actual_time=None,
        error_message=None
    ) -> bool:
        """Update job status and related fields."""
        with self._transaction() as data:
            job = None
            for j in data["jobs"]:
                if j["id"] == job_id:
                    job = j
                    break
            
            if not job:
                return False
            
            job["status"] = status.value
            if started_at is not None:
                job["started_at"] = started_at
            if completed_at is not None:
                job["completed_at"] = completed_at
            if actual_time is not None:
                job["actual_time"] = actual_time
            if error_message is not None:
                job["error_message"] = error_message
            
            # Add log entry
            log_message = f"Job status changed to {status.value}"
            if error_message:
                log_message += f": {error_message}"
            
            log_entry = {
                'id': len(data["logs"]) + 1,
                'job_id': job_id,
                'timestamp': datetime.utcnow(),
                'level': "ERROR" if status == JobStatus.FAILED else "INFO",
                'message': log_message
            }
            data["logs"].append(log_entry)
            
            return True
    
    def get_job_logs(self, job_id: int) -> List[Dict[str, Any]]:
        """Get logs for a specific job."""
        with self._transaction() as data:
            logs = []
            for log in data["logs"]:
                if log["job_id"] == job_id:
                    log_copy = log.copy()
                    log_copy['timestamp'] = self._parse_datetime(log['timestamp'])
                    logs.append(log_copy)
            
            # Sort by timestamp
            logs.sort(key=lambda x: x['timestamp'] or datetime.min)
            return logs
    
    def add_job_log(self, job_id: int, level: str, message: str) -> bool:
        """Add a log entry for a specific job."""
        with self._transaction() as data:
            log_entry = {
                'id': len(data["logs"]) + 1,
                'job_id': job_id,
                'timestamp': datetime.utcnow().isoformat(),
                'level': level,
                'message': message
            }
            
            data["logs"].append(log_entry)
            return True
    
    def get_status_counts(self) -> Dict[str, int]:
        """Get count of jobs by status."""
        with self._transaction() as data:
            status_counts = {}
            for status in JobStatus:
                status_counts[status.value] = 0
            
            for job in data["jobs"]:
                status = job["status"]
                if status in status_counts:
                    status_counts[status] += 1
            
            return status_counts
    
    def get_completed_package_names(self) -> set:
        """Get set of package names that have been completed successfully."""
        with self._transaction() as data:
            package_names = set()
            for job in data["jobs"]:
                if job["status"] == JobStatus.COMPLETED.value:
                    package_names.add(job["package_name"])
            return package_names
    
    def cleanup_old_jobs(self, keep_days: int) -> int:
        """Clean up old completed/failed jobs."""
        from datetime import timedelta
        
        with self._transaction() as data:
            cutoff_date = datetime.utcnow() - timedelta(days=keep_days)
            
            jobs_to_keep = []
            deleted_count = 0
            
            for job in data["jobs"]:
                if (job["status"] in [JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value] and
                    job["completed_at"]):
                    completed_at = self._parse_datetime(job["completed_at"])
                    if completed_at and completed_at < cutoff_date:
                        deleted_count += 1
                        continue
                jobs_to_keep.append(job)
            
            data["jobs"] = jobs_to_keep
            
            # Also clean up logs for deleted jobs
            job_ids = {job["id"] for job in jobs_to_keep}
            data["logs"] = [log for log in data["logs"] if log["job_id"] in job_ids]
            
            return deleted_count
    
    def create_retry_job(self, original_job_id: int) -> Optional[Dict[str, Any]]:
        """Create a retry job for a failed job.
        
        Args:
            original_job_id: The ID of the original failed job
            
        Returns:
            Dictionary of the new retry job, or None if retry not possible
        """
        with self._transaction() as data:
            # Find the original job
            original_job = None
            for job in data["jobs"]:
                if job["id"] == original_job_id:
                    original_job = job
                    break
            
            if not original_job:
                return None
            
            # Check if job is eligible for retry
            if original_job["status"] != JobStatus.FAILED.value:
                return None
            
            # Add retry fields to existing jobs if they don't exist (backward compatibility)
            if 'retry_count' not in original_job:
                original_job['retry_count'] = 0
            if 'max_retries' not in original_job:
                original_job['max_retries'] = config.DEFAULT_MAX_RETRIES
            if 'last_retry_at' not in original_job:
                original_job['last_retry_at'] = None
            if 'retry_delay' not in original_job:
                original_job['retry_delay'] = config.DEFAULT_RETRY_DELAY
            if 'is_retry' not in original_job:
                original_job['is_retry'] = False
            if 'original_job_id' not in original_job:
                original_job['original_job_id'] = None
            
            # Check if we've exceeded max retries
            if original_job["retry_count"] >= original_job["max_retries"]:
                return None
            
            # Calculate retry delay with exponential backoff
            retry_count = original_job["retry_count"] + 1
            retry_delay = original_job["retry_delay"] * (config.RETRY_BACKOFF_FACTOR ** (retry_count - 1))
            
            # Create new retry job
            job_id = data["next_job_id"]
            data["next_job_id"] += 1
            
            retry_job = {
                'id': job_id,
                'package_name': original_job['package_name'],
                'priority': original_job['priority'],
                'status': JobStatus.PENDING.value,
                'estimated_time': original_job['estimated_time'],
                'actual_time': None,
                'submitted_by': original_job['submitted_by'],
                'submitted_at': datetime.utcnow(),
                'started_at': None,
                'completed_at': None,
                'spack_command': original_job['spack_command'],
                'error_message': None,
                'dependencies_list': original_job.get('dependencies_list', []),
                'resource_requirements_dict': original_job.get('resource_requirements_dict', {}),
                'retry_count': retry_count,
                'max_retries': original_job['max_retries'],
                'last_retry_at': datetime.utcnow(),
                'retry_delay': retry_delay,
                'is_retry': True,
                'original_job_id': original_job.get('original_job_id', original_job_id)
            }
            
            data["jobs"].append(retry_job)
            
            # Update original job to increment retry count
            original_job["retry_count"] = retry_count
            original_job["last_retry_at"] = datetime.utcnow()
            
            # Add log entries
            retry_log = {
                'id': len(data["logs"]) + 1,
                'job_id': job_id,
                'timestamp': datetime.utcnow(),
                'level': "INFO",
                'message': f"Retry job created (attempt {retry_count}/{original_job['max_retries']}) for original job {original_job_id}"
            }
            data["logs"].append(retry_log)
            
            original_log = {
                'id': len(data["logs"]) + 1,
                'job_id': original_job_id,
                'timestamp': datetime.utcnow(),
                'level': "INFO",
                'message': f"Retry attempt {retry_count} created as job {job_id}, next retry delay: {retry_delay:.1f}s"
            }
            data["logs"].append(original_log)
            
            # Return a copy with parsed datetimes
            retry_job_copy = retry_job.copy()
            retry_job_copy['submitted_at'] = retry_job['submitted_at']
            retry_job_copy['last_retry_at'] = retry_job['last_retry_at']
            
            return retry_job_copy
    
    def get_jobs_eligible_for_retry(self) -> List[Dict[str, Any]]:
        """Get failed jobs that are eligible for retry.
        
        Returns:
            List of job dictionaries that can be retried
        """
        with self._transaction() as data:
            eligible_jobs = []
            current_time = datetime.utcnow()
            
            for job in data["jobs"]:
                # Add retry fields if missing (backward compatibility)
                if 'retry_count' not in job:
                    job['retry_count'] = 0
                if 'max_retries' not in job:
                    job['max_retries'] = config.DEFAULT_MAX_RETRIES
                if 'last_retry_at' not in job:
                    job['last_retry_at'] = None
                if 'retry_delay' not in job:
                    job['retry_delay'] = config.DEFAULT_RETRY_DELAY
                if 'is_retry' not in job:
                    job['is_retry'] = False
                if 'original_job_id' not in job:
                    job['original_job_id'] = None
                    
                if (job["status"] == JobStatus.FAILED.value and 
                    job["retry_count"] < job["max_retries"]):
                    
                    # Check if enough time has passed since last retry
                    if job.get("last_retry_at"):
                        last_retry = self._parse_datetime(job["last_retry_at"])
                        if last_retry:
                            time_since_retry = (current_time - last_retry).total_seconds()
                            if time_since_retry < job["retry_delay"]:
                                continue  # Not enough time has passed
                    
                    job_copy = job.copy()
                    job_copy['submitted_at'] = self._parse_datetime(job['submitted_at'])
                    job_copy['started_at'] = self._parse_datetime(job['started_at'])
                    job_copy['completed_at'] = self._parse_datetime(job['completed_at'])
                    job_copy['last_retry_at'] = self._parse_datetime(job['last_retry_at'])
                    eligible_jobs.append(job_copy)
            
            return eligible_jobs

    def get_worker_status(self) -> Optional[Dict[str, Any]]:
        """Get worker status information."""
        with self._transaction() as data:
            worker = data.get("worker_status")
            if not worker:
                return None
            
            worker_copy = worker.copy()
            worker_copy['started_at'] = self._parse_datetime(worker.get('started_at'))
            worker_copy['last_heartbeat'] = self._parse_datetime(worker.get('last_heartbeat'))
            return worker_copy
    
    def update_worker_status(
        self,
        is_active: bool,
        current_job_id: Optional[int] = None,
        started_at=None,
        process_id: Optional[int] = None
    ) -> None:
        """Update worker status."""
        with self._transaction() as data:
            if not data["worker_status"]:
                data["worker_status"] = {}
            
            worker = data["worker_status"]
            worker["is_active"] = is_active
            worker["current_job_id"] = current_job_id
            worker["last_heartbeat"] = datetime.utcnow()
            
            if started_at is not None:
                worker["started_at"] = started_at
            if process_id is not None:
                worker["process_id"] = process_id
            
            if not is_active:
                worker["started_at"] = None
                worker["current_job_id"] = None
                worker["process_id"] = None


# Global database manager instance
_db_manager: Optional[JSONDatabase] = None


def get_db_manager(db_path: str = None) -> JSONDatabase:
    """Get the global database manager instance."""
    global _db_manager
    if _db_manager is None:
        # Use config-specified path if no explicit path provided
        db_path = db_path or config.get_database_path()
        _db_manager = JSONDatabase(db_path)
    return _db_manager


def reset_db_manager():
    """Reset the global database manager (for testing)."""
    global _db_manager
    _db_manager = None
