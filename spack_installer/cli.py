"""Command Line Interface for the Spack Installer API."""

import click
import os
import sys
import os
from datetime import datetime
from tabulate import tabulate
from colorama import init, Fore, Style
from .queue_manager import QueueManager
from .models import JobPriority, JobStatus
from .worker import start_worker, stop_worker, get_worker_status
from .config import config

# Initialize colorama for cross-platform colored output
init()

# Global queue manager instance
queue_manager = QueueManager()


def format_duration(seconds: float) -> str:
    """Format duration in a human-readable way."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"


def format_timestamp(timestamp: datetime) -> str:
    """Format timestamp in a readable way."""
    if not timestamp:
        return "N/A"
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


def format_status(status: JobStatus) -> str:
    """Format job status with colors."""
    colors = {
        JobStatus.PENDING: Fore.YELLOW,
        JobStatus.RUNNING: Fore.BLUE,
        JobStatus.COMPLETED: Fore.GREEN,
        JobStatus.FAILED: Fore.RED,
        JobStatus.CANCELLED: Fore.MAGENTA
    }
    color = colors.get(status, "")
    return f"{color}{status.value.upper()}{Style.RESET_ALL}"


def format_status_string(status_str: str) -> str:
    """Format job status string with colors."""
    colors = {
        "pending": Fore.YELLOW,
        "running": Fore.BLUE,
        "completed": Fore.GREEN,
        "failed": Fore.RED,
        "cancelled": Fore.MAGENTA
    }
    color = colors.get(status_str, "")
    return f"{color}{status_str.upper()}{Style.RESET_ALL}"


@click.group()
@click.version_option(version="1.0.0")
def main():
    """Spack Installer API - A queuing system for Spack package installations."""
    pass


@main.command()
@click.argument("package_name")
@click.option("--priority", "-p", 
              type=click.Choice(["high", "medium", "low"], case_sensitive=False),
              default="medium",
              help="Job priority (default: medium)")
@click.option("--dependencies", "-d",
              help="Comma-separated list of dependencies")
@click.option("--estimated-time", "-t",
              type=float,
              default=300.0,
              help="Estimated installation time in seconds (default: 300)")
@click.option("--spack-command", "-c",
              help="Custom spack command to run (overrides default)")
@click.option("--spack-setup", "-s",
              help="Path to spack setup script (overrides default)")
def submit(package_name, priority, dependencies, estimated_time, spack_command, spack_setup):
    """Submit a new package installation job to the queue."""
    try:
        # Handle custom spack setup path
        if spack_setup:
            # If a custom spack setup is provided, modify the command to use it
            import os
            if not os.path.isfile(spack_setup):
                click.echo(f"{Fore.RED}✗{Style.RESET_ALL} Spack setup script not found: {spack_setup}", err=True)
                sys.exit(1)
            
            if spack_command:
                # User provided both custom setup and custom command
                spack_command = f"source {spack_setup} && {spack_command}"
            else:
                # User provided custom setup but not custom command
                spack_command = f"source {spack_setup} && spack install {package_name}"
        
        # Parse priority
        job_priority = JobPriority(priority.lower())
        
        # Parse dependencies
        deps_list = []
        if dependencies:
            deps_list = [dep.strip() for dep in dependencies.split(",") if dep.strip()]
        
        # Submit job
        job_info = queue_manager.submit_job(
            package_name=package_name,
            priority=job_priority,
            dependencies=deps_list,
            estimated_time=estimated_time,
            spack_command=spack_command
        )
        
        click.echo(f"{Fore.GREEN}✓{Style.RESET_ALL} Job submitted successfully!")
        click.echo(f"Job ID: {job_info['id']}")
        click.echo(f"Package: {job_info['package_name']}")
        click.echo(f"Priority: {job_info['priority']}")
        click.echo(f"Estimated time: {format_duration(job_info['estimated_time'])}")
        if deps_list:
            click.echo(f"Dependencies: {', '.join(deps_list)}")
        
    except ValueError as e:
        click.echo(f"{Fore.RED}✗{Style.RESET_ALL} Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"{Fore.RED}✗{Style.RESET_ALL} Unexpected error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option("--status", "-s",
              type=click.Choice(["pending", "running", "completed", "failed", "cancelled"]),
              help="Filter jobs by status")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
def status(status, verbose):
    """Show current queue status and job information."""
    try:
        # Get queue status
        queue_status = queue_manager.get_queue_status()
        
        # Display queue summary
        click.echo(f"\n{Fore.CYAN}=== Queue Status ==={Style.RESET_ALL}")
        click.echo(f"Worker Active: {Fore.GREEN if queue_status['worker_active'] else Fore.RED}"
                  f"{'Yes' if queue_status['worker_active'] else 'No'}{Style.RESET_ALL}")
        
        if queue_status['current_job_id']:
            click.echo(f"Current Job: {queue_status['current_job_id']}")
        
        if queue_status['next_job_id']:
            click.echo(f"Next Job: {queue_status['next_job_id']}")
        
        click.echo(f"Pending Jobs: {queue_status['total_pending']}")
        click.echo(f"Estimated Total Time: {format_duration(queue_status['estimated_total_time'])}")
        
        # Job counts by status
        click.echo(f"\n{Fore.CYAN}=== Job Counts ==={Style.RESET_ALL}")
        for job_status, count in queue_status['status_counts'].items():
            click.echo(f"{job_status.capitalize()}: {count}")
        
        # Get jobs
        if status:
            filter_status = JobStatus(status)
            jobs = queue_manager.get_all_jobs(filter_status)
        else:
            jobs = queue_manager.get_all_jobs()
        
        if not jobs:
            click.echo(f"\n{Fore.YELLOW}No jobs found.{Style.RESET_ALL}")
            return
        
        # Display jobs table
        click.echo(f"\n{Fore.CYAN}=== Jobs ==={Style.RESET_ALL}")
        
        if verbose:
            headers = ["ID", "Package", "Status", "Priority", "Est. Time", "Actual Time", 
                      "Submitted", "Started", "Completed", "Dependencies"]
            rows = []
            for job in jobs:
                deps = ", ".join(job['dependencies_list']) if job['dependencies_list'] else "None"
                rows.append([
                    job['id'],
                    job['package_name'],
                    format_status_string(job['status']),
                    job['priority'],
                    format_duration(job['estimated_time']),
                    format_duration(job['actual_time']) if job['actual_time'] else "N/A",
                    format_timestamp(job['submitted_at']),
                    format_timestamp(job['started_at']),
                    format_timestamp(job['completed_at']),
                    deps[:30] + "..." if len(deps) > 30 else deps
                ])
        else:
            headers = ["ID", "Package", "Status", "Priority", "Est. Time", "Submitted", "Submitted By"]
            rows = []
            for job in jobs:
                rows.append([
                    job['id'],
                    job['package_name'],
                    format_status_string(job['status']),
                    job['priority'],
                    format_duration(job['estimated_time']),
                    format_timestamp(job['submitted_at']),
                    job['submitted_by']
                ])
        
        click.echo(tabulate(rows, headers=headers, tablefmt="grid"))
        
    except Exception as e:
        click.echo(f"{Fore.RED}✗{Style.RESET_ALL} Error getting status: {e}", err=True)
        sys.exit(1)


@main.group()
def worker():
    """Worker management commands."""
    pass


@worker.command()
def start():
    """Start the worker daemon."""
    try:
        click.echo("Starting worker daemon...")
        start_worker()
    except KeyboardInterrupt:
        click.echo(f"\n{Fore.YELLOW}Worker stopped by user.{Style.RESET_ALL}")
    except Exception as e:
        click.echo(f"{Fore.RED}✗{Style.RESET_ALL} Error starting worker: {e}", err=True)
        sys.exit(1)


@worker.command()
def stop():
    """Stop the worker daemon."""
    try:
        if stop_worker():
            click.echo(f"{Fore.GREEN}✓{Style.RESET_ALL} Worker stopped successfully.")
        else:
            click.echo(f"{Fore.YELLOW}No active worker found.{Style.RESET_ALL}")
    except Exception as e:
        click.echo(f"{Fore.RED}✗{Style.RESET_ALL} Error stopping worker: {e}", err=True)
        sys.exit(1)


@worker.command()
def info():
    """Show worker status information."""
    try:
        worker_status = get_worker_status()
        
        click.echo(f"\n{Fore.CYAN}=== Worker Status ==={Style.RESET_ALL}")
        click.echo(f"Active: {Fore.GREEN if worker_status['active'] else Fore.RED}"
                  f"{'Yes' if worker_status['active'] else 'No'}{Style.RESET_ALL}")
        
        if worker_status['current_job_id']:
            click.echo(f"Current Job ID: {worker_status['current_job_id']}")
        
        if worker_status['started_at']:
            click.echo(f"Started At: {worker_status['started_at']}")
        
        if worker_status['last_heartbeat']:
            click.echo(f"Last Heartbeat: {worker_status['last_heartbeat']}")
        
        if worker_status['process_id']:
            click.echo(f"Process ID: {worker_status['process_id']}")
            
    except Exception as e:
        click.echo(f"{Fore.RED}✗{Style.RESET_ALL} Error getting worker status: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("job_id", type=int)
def cancel(job_id):
    """Cancel a pending job."""
    try:
        if queue_manager.cancel_job(job_id):
            click.echo(f"{Fore.GREEN}✓{Style.RESET_ALL} Job {job_id} cancelled successfully.")
        else:
            click.echo(f"{Fore.YELLOW}Could not cancel job {job_id}. "
                      f"Job may not exist or may not be in pending status.{Style.RESET_ALL}")
    except Exception as e:
        click.echo(f"{Fore.RED}✗{Style.RESET_ALL} Error cancelling job: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option("--keep-days", "-k", type=int, default=7,
              help="Number of days to keep completed jobs (default: 7)")
def cleanup(keep_days):
    """Clean up old completed jobs."""
    try:
        deleted_count = queue_manager.cleanup_completed_jobs(keep_days)
        click.echo(f"{Fore.GREEN}✓{Style.RESET_ALL} Cleaned up {deleted_count} old jobs.")
    except Exception as e:
        click.echo(f"{Fore.RED}✗{Style.RESET_ALL} Error during cleanup: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("job_id", type=int)
def logs(job_id):
    """Show logs for a specific job."""
    try:
        job = queue_manager.get_job(job_id)
        if not job:
            click.echo(f"{Fore.RED}✗{Style.RESET_ALL} Job {job_id} not found.", err=True)
            sys.exit(1)
        
        job_logs = queue_manager.get_job_logs(job_id)
        
        click.echo(f"\n{Fore.CYAN}=== Logs for Job {job_id} ({job['package_name']}) ==={Style.RESET_ALL}")
        
        if not job_logs:
            click.echo(f"{Fore.YELLOW}No logs found for this job.{Style.RESET_ALL}")
            return
        
        for log in job_logs:
            color = {
                "INFO": Fore.GREEN,
                "WARNING": Fore.YELLOW,
                "ERROR": Fore.RED
            }.get(log['level'], "")
            
            click.echo(f"{format_timestamp(log['timestamp'])} "
                      f"{color}[{log['level']}]{Style.RESET_ALL} {log['message']}")
            
    except Exception as e:
        click.echo(f"{Fore.RED}✗{Style.RESET_ALL} Error getting logs: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("job_id", type=int)
def retry(job_id):
    """Retry a failed job with the same configuration."""
    try:
        # Get the original job
        original_job = queue_manager.get_job(job_id)
        if not original_job:
            click.echo(f"{Fore.RED}✗{Style.RESET_ALL} Job {job_id} not found.", err=True)
            sys.exit(1)
        
        # Check if job is failed
        if original_job['status'] != 'failed':
            click.echo(f"{Fore.RED}✗{Style.RESET_ALL} Job {job_id} is not failed (status: {original_job['status']}). Only failed jobs can be retried.", err=True)
            sys.exit(1)
        
        # Check if job has retries remaining
        if original_job['retry_count'] >= original_job['max_retries']:
            click.echo(f"{Fore.RED}✗{Style.RESET_ALL} Job {job_id} has exhausted all retry attempts ({original_job['retry_count']}/{original_job['max_retries']}).", err=True)
            sys.exit(1)
        
        # Create retry job using the queue manager method
        retry_job = queue_manager.create_retry_job(job_id)
        
        if not retry_job:
            click.echo(f"{Fore.RED}✗{Style.RESET_ALL} Failed to create retry job for job {job_id}.", err=True)
            sys.exit(1)
        
        click.echo(f"{Fore.GREEN}✓{Style.RESET_ALL} Retry job created successfully!")
        click.echo(f"New Job ID: {retry_job['id']}")
        click.echo(f"Package: {retry_job['package_name']}")
        click.echo(f"Retry attempt: {retry_job['retry_count']}/{retry_job['max_retries']}")
        click.echo(f"Original job ID: {original_job['id']}")
        click.echo(f"Priority: {retry_job['priority']}")
        click.echo(f"Estimated time: {format_duration(retry_job['estimated_time'])}")
        if retry_job['dependencies_list']:
            click.echo(f"Dependencies: {', '.join(retry_job['dependencies_list'])}")
        
        # Show when the retry will be eligible to run
        if retry_job.get('last_retry_at'):
            from datetime import datetime, timedelta
            next_eligible = retry_job['last_retry_at'] + timedelta(seconds=retry_job['retry_delay'])
            current_time = datetime.utcnow()
            if next_eligible > current_time:
                wait_time = (next_eligible - current_time).total_seconds()
                click.echo(f"Next retry eligible in: {format_duration(wait_time)}")
            else:
                click.echo(f"{Fore.GREEN}Job is eligible to run immediately{Style.RESET_ALL}")
        
    except Exception as e:
        click.echo(f"{Fore.RED}✗{Style.RESET_ALL} Error creating retry job: {e}", err=True)
        sys.exit(1)


@main.command()
def failed():
    """Show all failed jobs and their retry status."""
    try:
        # Get all failed jobs
        failed_jobs = queue_manager.get_all_jobs(JobStatus.FAILED)
        
        if not failed_jobs:
            click.echo(f"\n{Fore.GREEN}No failed jobs found.{Style.RESET_ALL}")
            return
        
        click.echo(f"\n{Fore.CYAN}=== Failed Jobs ==={Style.RESET_ALL}")
        
        headers = ["ID", "Package", "User", "Failed At", "Error", "Retries", "Can Retry"]
        rows = []
        
        for job in failed_jobs:
            # Truncate error message for display
            error_msg = job.get('error_message', 'No error message')
            if len(error_msg) > 50:
                error_msg = error_msg[:47] + "..."
            
            # Check if job can be retried
            can_retry = job['retry_count'] < job['max_retries']
            retry_status = f"{job['retry_count']}/{job['max_retries']}"
            can_retry_display = f"{Fore.GREEN}Yes{Style.RESET_ALL}" if can_retry else f"{Fore.RED}No{Style.RESET_ALL}"
            
            rows.append([
                job['id'],
                job['package_name'],
                job['submitted_by'],
                format_timestamp(job.get('completed_at')),
                error_msg,
                retry_status,
                can_retry_display
            ])
        
        click.echo(tabulate(rows, headers=headers, tablefmt="grid"))
        
        # Show retry instructions
        retryable_jobs = [job for job in failed_jobs if job['retry_count'] < job['max_retries']]
        if retryable_jobs:
            click.echo(f"\n{Fore.CYAN}To retry a failed job, use:{Style.RESET_ALL}")
            click.echo(f"  spack-installer retry <job-id>")
            click.echo(f"\nExample: spack-installer retry {retryable_jobs[0]['id']}")
        
    except Exception as e:
        click.echo(f"{Fore.RED}✗{Style.RESET_ALL} Error getting failed jobs: {e}", err=True)
        sys.exit(1)


@main.command()
def config_check():
    """Check spack configuration and system requirements."""
    try:
        click.echo(f"\n{Fore.CYAN}=== Spack Configuration Check ==={Style.RESET_ALL}")
        
        # Check spack setup script
        spack_script = config.get_spack_setup_script()
        click.echo(f"Spack setup script: {spack_script}")
        
        if config.validate_spack_setup():
            click.echo(f"{Fore.GREEN}✓{Style.RESET_ALL} Spack setup script found")
        else:
            click.echo(f"{Fore.RED}✗{Style.RESET_ALL} Spack setup script not found")
            click.echo(f"{Fore.YELLOW}  Set SPACK_SETUP_SCRIPT environment variable to specify location{Style.RESET_ALL}")
        
        # Check database configuration
        click.echo(f"\n{Fore.CYAN}=== Database Configuration ==={Style.RESET_ALL}")
        click.echo(f"Database type: {config.get_database_type()}")
        click.echo(f"Database path: {config.get_database_path()}")
        if config.get_database_url():
            click.echo(f"Database URL: {config.get_database_url()}")
        
        # Check if database file exists and is accessible
        db_path = config.get_database_path()
        if os.path.exists(db_path):
            click.echo(f"{Fore.GREEN}✓{Style.RESET_ALL} Database file exists")
            try:
                # Test database access
                from .database import get_db_manager
                db = get_db_manager()
                status_counts = db.get_status_counts()
                total_jobs = sum(status_counts.values())
                click.echo(f"  Total jobs in database: {total_jobs}")
            except Exception as e:
                click.echo(f"{Fore.RED}✗{Style.RESET_ALL} Error accessing database: {e}")
        else:
            click.echo(f"{Fore.YELLOW}⚠{Style.RESET_ALL} Database file will be created on first use")
        
        # Show other configuration values
        click.echo(f"\n{Fore.CYAN}=== Worker Configuration ==={Style.RESET_ALL}")
        click.echo(f"Check interval: {config.WORKER_CHECK_INTERVAL}s")
        click.echo(f"Heartbeat interval: {config.WORKER_HEARTBEAT_INTERVAL}s")
        click.echo(f"Job timeout multiplier: {config.DEFAULT_JOB_TIMEOUT_MULTIPLIER}x")
        click.echo(f"Max heartbeat age: {config.MAX_WORKER_HEARTBEAT_AGE}s")
        
        # Test spack availability (if setup script exists)
        if config.validate_spack_setup():
            click.echo(f"\n{Fore.CYAN}=== Testing Spack Availability ==={Style.RESET_ALL}")
            import subprocess
            try:
                test_command = f"source {spack_script} && spack --version"
                result = subprocess.run(
                    test_command,
                    shell=True,
                    executable="/bin/bash",
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    version = result.stdout.strip()
                    click.echo(f"{Fore.GREEN}✓{Style.RESET_ALL} Spack is available: {version}")
                else:
                    click.echo(f"{Fore.RED}✗{Style.RESET_ALL} Failed to run spack: {result.stderr}")
                    
            except subprocess.TimeoutExpired:
                click.echo(f"{Fore.YELLOW}⚠{Style.RESET_ALL} Spack test timed out")
            except Exception as e:
                click.echo(f"{Fore.RED}✗{Style.RESET_ALL} Error testing spack: {e}")
        
    except Exception as e:
        click.echo(f"{Fore.RED}✗{Style.RESET_ALL} Error checking configuration: {e}", err=True)
        sys.exit(1)


@main.command()
def optimize():
    """Show optimized queue order and dependency analysis."""
    try:
        # Get optimized order
        optimized_jobs = queue_manager.get_optimized_queue_order()
        
        click.echo(f"\n{Fore.CYAN}=== Optimized Queue Order ==={Style.RESET_ALL}")
        
        if not optimized_jobs:
            click.echo(f"{Fore.YELLOW}No pending jobs to optimize.{Style.RESET_ALL}")
        else:
            headers = ["Order", "ID", "Package", "Priority", "Est. Time", "Dependencies"]
            rows = []
            for i, job in enumerate(optimized_jobs, 1):
                deps = ", ".join(job['dependencies_list']) if job['dependencies_list'] else "None"
                rows.append([
                    i,
                    job['id'],
                    job['package_name'],
                    job['priority'],
                    format_duration(job['estimated_time']),
                    deps[:30] + "..." if len(deps) > 30 else deps
                ])
            
            click.echo(tabulate(rows, headers=headers, tablefmt="grid"))
        
        # Check for dependency issues
        issues = queue_manager.detect_dependency_issues()
        
        if issues['circular_dependencies']:
            click.echo(f"\n{Fore.RED}=== Circular Dependencies Detected ==={Style.RESET_ALL}")
            for dep1, dep2 in issues['circular_dependencies']:
                click.echo(f"{Fore.RED}✗{Style.RESET_ALL} {dep1} ↔ {dep2}")
        
        if issues['unsatisfied_dependencies']:
            click.echo(f"\n{Fore.YELLOW}=== Unsatisfied External Dependencies ==={Style.RESET_ALL}")
            for issue in issues['unsatisfied_dependencies']:
                click.echo(f"{Fore.YELLOW}⚠{Style.RESET_ALL} Job {issue['job_id']} ({issue['package']}) "
                          f"needs: {', '.join(issue['missing_external_deps'])}")
        
        if not issues['circular_dependencies'] and not issues['unsatisfied_dependencies']:
            click.echo(f"\n{Fore.GREEN}✓{Style.RESET_ALL} No dependency issues detected.")
            
    except Exception as e:
        click.echo(f"{Fore.RED}✗{Style.RESET_ALL} Error optimizing queue: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
