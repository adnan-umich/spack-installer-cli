#!/usr/bin/env python3
"""
Example script showing how to use the Spack Installer API programmatically.
"""

from spack_installer.queue_manager import QueueManager
from spack_installer.models import JobPriority
import time

def main():
    """Example usage of the queue manager."""
    queue = QueueManager()
    
    print("=== Spack Installer API Example ===")
    
    # Submit some example jobs
    jobs = [
        ("cmake", JobPriority.HIGH, ["gcc"], 180),
        ("boost", JobPriority.MEDIUM, ["cmake"], 600),
        ("python", JobPriority.HIGH, [], 300),
        ("numpy", JobPriority.MEDIUM, ["python"], 240),
        ("scipy", JobPriority.LOW, ["python", "numpy"], 480),
    ]
    
    print("\n1. Submitting example jobs...")
    submitted_jobs = []
    
    for package, priority, deps, est_time in jobs:
        try:
            job = queue.submit_job(
                package_name=package,
                priority=priority,
                dependencies=deps,
                estimated_time=est_time
            )
            submitted_jobs.append(job)
            print(f"   ✓ Submitted {package} (ID: {job.id})")
        except ValueError as e:
            print(f"   ✗ Failed to submit {package}: {e}")
    
    # Show queue status
    print("\n2. Current queue status:")
    status = queue.get_queue_status()
    print(f"   Pending jobs: {status['total_pending']}")
    print(f"   Estimated total time: {status['estimated_total_time']:.1f} seconds")
    
    # Show optimized order
    print("\n3. Optimized execution order:")
    optimized = queue.get_optimized_queue_order()
    for i, job in enumerate(optimized, 1):
        deps = ", ".join(job.dependencies_list) if job.dependencies_list else "none"
        print(f"   {i}. {job.package_name} (deps: {deps})")
    
    # Check for issues
    print("\n4. Dependency analysis:")
    issues = queue.detect_dependency_issues()
    if issues['circular_dependencies']:
        print("   ✗ Circular dependencies found:")
        for dep1, dep2 in issues['circular_dependencies']:
            print(f"     {dep1} ↔ {dep2}")
    else:
        print("   ✓ No circular dependencies")
    
    if issues['unsatisfied_dependencies']:
        print("   ⚠ Unsatisfied external dependencies:")
        for issue in issues['unsatisfied_dependencies']:
            print(f"     {issue['package']}: {', '.join(issue['missing_external_deps'])}")
    else:
        print("   ✓ All dependencies can be satisfied")
    
    print("\n=== Example completed ===")
    print("Use 'spack-installer worker start' to begin processing jobs")
    print("Use 'spack-installer status' to monitor progress")

if __name__ == "__main__":
    main()
