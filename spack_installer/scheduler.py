"""Intelligent job scheduling algorithms for optimizing installation order."""

import heapq
from typing import List, Dict, Set, Tuple
from datetime import datetime
from .models import InstallationJob, JobPriority, JobStatus


class JobScheduler:
    """Intelligent job scheduler that optimizes installation order."""
    
    def __init__(self):
        """Initialize the job scheduler."""
        self.priority_weights = {
            JobPriority.HIGH: 3.0,
            JobPriority.MEDIUM: 2.0,
            JobPriority.LOW: 1.0
        }
    
    def calculate_job_score(self, job: InstallationJob, dependency_graph: Dict[str, Set[str]]) -> float:
        """Calculate a scheduling score for a job.
        
        Lower scores indicate higher priority for scheduling.
        
        Args:
            job: The job to score
            dependency_graph: Graph of package dependencies
            
        Returns:
            Scheduling score (lower = higher priority)
        """
        score = 0.0
        
        # Priority factor (higher priority = lower score)
        priority_weight = self.priority_weights.get(job.priority, 2.0)
        score += (4.0 - priority_weight) * 100  # Scale priority heavily
        
        # Dependency factor (fewer dependencies = lower score)
        dependencies = job.dependencies_list
        dependency_count = len(dependencies)
        score += dependency_count * 10
        
        # Estimated time factor (shorter jobs get slight preference)
        # But not too much to avoid starving long jobs
        time_factor = min(job.estimated_time / 3600.0, 2.0)  # Cap at 2 hours
        score += time_factor * 5
        
        # Age factor (older jobs get slight preference)
        age_hours = (datetime.utcnow() - job.submitted_at).total_seconds() / 3600.0
        score -= min(age_hours, 24.0) * 2  # Cap at 24 hours
        
        # Dependency chain optimization
        # Jobs that unlock many other jobs get priority
        unlocked_jobs = self._count_unlocked_jobs(job.package_name, dependency_graph)
        score -= unlocked_jobs * 15
        
        return score
    
    def _count_unlocked_jobs(self, package_name: str, dependency_graph: Dict[str, Set[str]]) -> int:
        """Count how many jobs would be unlocked by installing this package."""
        count = 0
        for pkg, deps in dependency_graph.items():
            if package_name in deps:
                count += 1
        return count
    
    def _build_dependency_graph(self, jobs: List[InstallationJob]) -> Dict[str, Set[str]]:
        """Build a dependency graph from the list of jobs."""
        graph = {}
        for job in jobs:
            graph[job.package_name] = set(job.dependencies_list)
        return graph
    
    def _find_ready_jobs(self, jobs: List[InstallationJob], installed_packages: Set[str]) -> List[InstallationJob]:
        """Find jobs that have all their dependencies satisfied."""
        ready_jobs = []
        
        for job in jobs:
            if job.status != JobStatus.PENDING:
                continue
                
            dependencies = set(job.dependencies_list)
            if dependencies.issubset(installed_packages):
                ready_jobs.append(job)
        
        return ready_jobs
    
    def get_next_job(self, jobs: List[InstallationJob], installed_packages: Set[str] = None) -> InstallationJob:
        """Get the next job to execute based on intelligent scheduling.
        
        Args:
            jobs: List of all jobs
            installed_packages: Set of already installed package names
            
        Returns:
            The next job to execute, or None if no jobs are ready
        """
        if installed_packages is None:
            installed_packages = set()
        
        # Filter to only pending jobs
        pending_jobs = [job for job in jobs if job.status == JobStatus.PENDING]
        if not pending_jobs:
            return None
        
        # Find jobs that are ready to run (dependencies satisfied)
        ready_jobs = self._find_ready_jobs(pending_jobs, installed_packages)
        if not ready_jobs:
            return None
        
        # Build dependency graph for scoring
        dependency_graph = self._build_dependency_graph(pending_jobs)
        
        # Score all ready jobs and pick the best one
        scored_jobs = []
        for job in ready_jobs:
            score = self.calculate_job_score(job, dependency_graph)
            heapq.heappush(scored_jobs, (score, job.id, job))
        
        if scored_jobs:
            _, _, best_job = heapq.heappop(scored_jobs)
            return best_job
        
        return None
    
    def optimize_job_order(self, jobs: List[InstallationJob]) -> List[InstallationJob]:
        """Optimize the order of all pending jobs.
        
        Args:
            jobs: List of all jobs
            
        Returns:
            Optimized order of jobs
        """
        pending_jobs = [job for job in jobs if job.status == JobStatus.PENDING]
        if not pending_jobs:
            return []
        
        optimized_order = []
        installed_packages = set()
        remaining_jobs = pending_jobs.copy()
        
        # Iteratively pick the best next job
        while remaining_jobs:
            next_job = self.get_next_job(remaining_jobs, installed_packages)
            if next_job is None:
                # No jobs are ready (circular dependencies or missing external deps)
                # Pick the highest priority job with fewest dependencies
                next_job = min(
                    remaining_jobs,
                    key=lambda j: (
                        -self.priority_weights.get(j.priority, 2.0),
                        len(j.dependencies_list),
                        j.submitted_at
                    )
                )
            
            optimized_order.append(next_job)
            installed_packages.add(next_job.package_name)
            remaining_jobs.remove(next_job)
        
        return optimized_order
    
    def detect_circular_dependencies(self, jobs: List[InstallationJob]) -> List[Tuple[str, str]]:
        """Detect circular dependencies in the job list.
        
        Returns:
            List of tuples representing circular dependency edges
        """
        graph = self._build_dependency_graph(jobs)
        
        def has_cycle_util(node: str, visited: Set[str], rec_stack: Set[str]) -> List[Tuple[str, str]]:
            visited.add(node)
            rec_stack.add(node)
            cycles = []
            
            for neighbor in graph.get(node, set()):
                if neighbor not in visited:
                    cycles.extend(has_cycle_util(neighbor, visited, rec_stack))
                elif neighbor in rec_stack:
                    cycles.append((node, neighbor))
            
            rec_stack.remove(node)
            return cycles
        
        visited = set()
        all_cycles = []
        
        for node in graph:
            if node not in visited:
                all_cycles.extend(has_cycle_util(node, visited, set()))
        
        return all_cycles
    
    def estimate_total_time(self, jobs: List[InstallationJob]) -> float:
        """Estimate total time for all jobs considering parallelization potential.
        
        Args:
            jobs: List of jobs to estimate
            
        Returns:
            Estimated total time in seconds
        """
        if not jobs:
            return 0.0
        
        # For now, assume sequential execution
        # This could be enhanced to consider parallel execution opportunities
        return sum(job.estimated_time for job in jobs if job.status == JobStatus.PENDING)
