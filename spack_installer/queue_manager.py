"""Queue manager for handling job submission and management with improved architecture."""

import getpass
from datetime import datetime
from typing import List, Optional, Dict, Any
from .database import get_db_manager
from .models import JobStatus, JobPriority
from .scheduler import JobScheduler


class QueueManager:
    """Manages the job queue with improved data access patterns."""
    
    def __init__(self):
        """Initialize the queue manager."""
        self.scheduler = JobScheduler()
        self.db = get_db_manager()
    
    def submit_job(
        self,
        package_name: str,
        priority: JobPriority = JobPriority.MEDIUM,
        dependencies: List[str] = None,
        estimated_time: float = 300.0,
        spack_command: str = None,
        resource_requirements: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Submit a new installation job to the queue.
        
        Args:
            package_name: Name of the package to install
            priority: Job priority
            dependencies: List of dependency package names
            estimated_time: Estimated installation time in seconds
            spack_command: Custom spack command to run
            resource_requirements: Dict of resource requirements
            
        Returns:
            Dict with job information
        """
        return self.db.create_job(
            package_name=package_name,
            priority=priority,
            estimated_time=estimated_time,
            submitted_by=getpass.getuser(),
            spack_command=spack_command,
            dependencies=dependencies,
            resource_requirements=resource_requirements
        )
    
    def get_job(self, job_id: int) -> Optional[Dict[str, Any]]:
        """Get a job by ID."""
        return self.db.get_job_by_id(job_id)
    
    def get_all_jobs(self, status: JobStatus = None) -> List[Dict[str, Any]]:
        """Get all jobs, optionally filtered by status."""
        return self.db.get_all_jobs(status)
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get comprehensive queue status information."""
        # Get status counts
        status_counts = self.db.get_status_counts()
        
        # Get worker status
        worker_status = self.db.get_worker_status()
        is_worker_active = worker_status['is_active'] if worker_status else False
        current_job_id = worker_status['current_job_id'] if worker_status else None
        
        # Get pending jobs for next job calculation
        pending_jobs = self.get_all_jobs(JobStatus.PENDING)
        installed_packages = self.db.get_completed_package_names()
        
        # Convert pending job dicts to objects for scheduler compatibility
        pending_job_objects = [self._dict_to_job_object(job) for job in pending_jobs]
        next_job = self.scheduler.get_next_job(pending_job_objects, installed_packages)
        
        # Estimate total time
        total_estimated_time = self.scheduler.estimate_total_time(pending_job_objects)
        
        return {
            "status_counts": status_counts,
            "worker_active": is_worker_active,
            "current_job_id": current_job_id,
            "next_job_id": next_job.id if next_job else None,
            "total_pending": status_counts.get("pending", 0),
            "estimated_total_time": total_estimated_time,
            "queue_length": len(pending_jobs)
        }
    
    def cancel_job(self, job_id: int) -> bool:
        """Cancel a pending job."""
        job = self.get_job(job_id)
        if not job or job['status'] != 'pending':
            return False
        
        return self.db.update_job_status(
            job_id=job_id,
            status=JobStatus.CANCELLED,
            completed_at=datetime.utcnow()
        )
    
    def get_next_job_to_run(self) -> Optional[Dict[str, Any]]:
        """Get the next job that should be executed."""
        pending_jobs = self.get_all_jobs(JobStatus.PENDING)
        if not pending_jobs:
            return None
        
        installed_packages = self.db.get_completed_package_names()
        
        # Convert to objects for scheduler
        pending_job_objects = [self._dict_to_job_object(job) for job in pending_jobs]
        next_job_obj = self.scheduler.get_next_job(pending_job_objects, installed_packages)
        
        if next_job_obj:
            # Find the corresponding dict
            for job_dict in pending_jobs:
                if job_dict['id'] == next_job_obj.id:
                    return job_dict
        
        return None
    
    def mark_job_running(self, job_id: int) -> bool:
        """Mark a job as running."""
        job = self.get_job(job_id)
        if not job or job['status'] != 'pending':
            return False
        
        return self.db.update_job_status(
            job_id=job_id,
            status=JobStatus.RUNNING,
            started_at=datetime.utcnow()
        )
    
    def mark_job_completed(self, job_id: int, success: bool = True, error_message: str = None) -> bool:
        """Mark a job as completed or failed."""
        job = self.get_job(job_id)
        if not job or job['status'] != 'running':
            return False
        
        completed_at = datetime.utcnow()
        actual_time = None
        if job['started_at']:
            actual_time = (completed_at - job['started_at']).total_seconds()
        
        return self.db.update_job_status(
            job_id=job_id,
            status=JobStatus.COMPLETED if success else JobStatus.FAILED,
            completed_at=completed_at,
            actual_time=actual_time,
            error_message=error_message
        )
    
    def create_retry_job(self, original_job_id: int) -> Optional[Dict[str, Any]]:
        """Create a retry job for a failed job.
        
        Args:
            original_job_id: The ID of the original failed job
            
        Returns:
            Dictionary of the new retry job, or None if retry not possible
        """
        return self.db.create_retry_job(original_job_id)
    
    def cleanup_completed_jobs(self, keep_days: int = 7) -> int:
        """Clean up old completed/failed jobs."""
        return self.db.cleanup_old_jobs(keep_days)
    
    def get_job_logs(self, job_id: int) -> List[Dict[str, Any]]:
        """Get logs for a specific job."""
        return self.db.get_job_logs(job_id)
    
    def get_optimized_queue_order(self) -> List[Dict[str, Any]]:
        """Get the optimized order for all pending jobs."""
        pending_jobs = self.get_all_jobs(JobStatus.PENDING)
        pending_job_objects = [self._dict_to_job_object(job) for job in pending_jobs]
        optimized_objects = self.scheduler.optimize_job_order(pending_job_objects)
        
        # Convert back to dictionaries
        optimized_dicts = []
        for obj in optimized_objects:
            for job_dict in pending_jobs:
                if job_dict['id'] == obj.id:
                    optimized_dicts.append(job_dict)
                    break
        
        return optimized_dicts
    
    def detect_dependency_issues(self) -> Dict[str, Any]:
        """Detect potential dependency issues in the queue."""
        pending_jobs = self.get_all_jobs(JobStatus.PENDING)
        pending_job_objects = [self._dict_to_job_object(job) for job in pending_jobs]
        
        # Detect circular dependencies
        circular_deps = self.scheduler.detect_circular_dependencies(pending_job_objects)
        
        # Find jobs with unsatisfied dependencies
        installed_packages = self.db.get_completed_package_names()
        
        unsatisfied_deps = []
        for job in pending_jobs:
            missing_deps = set(job['dependencies_list'] or []) - installed_packages
            if missing_deps:
                # Check if missing deps are in pending jobs
                pending_packages = {j['package_name'] for j in pending_jobs}
                external_deps = missing_deps - pending_packages
                if external_deps:
                    unsatisfied_deps.append({
                        "job_id": job['id'],
                        "package": job['package_name'],
                        "missing_external_deps": list(external_deps)
                    })
        
        return {
            "circular_dependencies": circular_deps,
            "unsatisfied_dependencies": unsatisfied_deps
        }
    
    def _dict_to_job_object(self, job_dict: Dict[str, Any]):
        """Convert job dictionary to a simple object for scheduler compatibility."""
        from types import SimpleNamespace
        
        # Create a simple object with the necessary attributes
        obj = SimpleNamespace()
        obj.id = job_dict['id']
        obj.package_name = job_dict['package_name']
        
        # Convert string priority back to enum
        priority_str = job_dict['priority']
        if priority_str == 'high':
            obj.priority = JobPriority.HIGH
        elif priority_str == 'medium':
            obj.priority = JobPriority.MEDIUM
        elif priority_str == 'low':
            obj.priority = JobPriority.LOW
        else:
            obj.priority = JobPriority.MEDIUM  # Default fallback
        
        obj.estimated_time = job_dict['estimated_time']
        obj.dependencies_list = job_dict['dependencies_list'] or []
        
        # Add submitted_at for age calculation in scheduler
        obj.submitted_at = job_dict['submitted_at']
        
        # Add status as enum
        status_str = job_dict['status']
        if status_str == 'pending':
            obj.status = JobStatus.PENDING
        elif status_str == 'running':
            obj.status = JobStatus.RUNNING
        elif status_str == 'completed':
            obj.status = JobStatus.COMPLETED
        elif status_str == 'failed':
            obj.status = JobStatus.FAILED
        elif status_str == 'cancelled':
            obj.status = JobStatus.CANCELLED
        else:
            obj.status = JobStatus.PENDING  # Default fallback
        
        return obj
