"""Multi-user worker daemon for executing installation jobs."""

import os
import sys
import time
import signal
import subprocess
import threading
from datetime import datetime
from typing import Optional
from .database import get_db_manager
from .queue_manager import QueueManager
from .config import config


class InstallationWorker:
    """Multi-user worker daemon that executes installation jobs sequentially."""
    
    def __init__(self, check_interval: float = None, use_system_database: bool = True):
        """Initialize the worker.
        
        Args:
            check_interval: Seconds between queue checks (uses config default if None)
            use_system_database: Whether to use system-wide database for multi-user support
        """
        self.check_interval = check_interval or config.WORKER_CHECK_INTERVAL
        self.use_system_database = use_system_database
        
        # Use system database path for multi-user mode
        if use_system_database:
            # Override database path to use system-wide location
            original_db_path = config.DATABASE_PATH
            config.DATABASE_PATH = config.get_multi_user_database_path()
            print(f"Worker using multi-user database: {config.DATABASE_PATH}")
        
        self.queue_manager = QueueManager()
        self.db = get_db_manager()
        self.running = False
        self.current_job_id = None
        self.current_job_user = None
        self.heartbeat_thread = None
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        print(f"\nReceived signal {signum}, shutting down gracefully...")
        self.stop()
    
    def start(self):
        """Start the worker daemon."""
        print("Starting Spack installation worker (multi-user mode)...")
        
        # Ensure system database directory exists and has proper permissions
        if self.use_system_database:
            self._ensure_system_database_setup()
        
        # Update worker status in database
        self._update_worker_status(True)
        
        self.running = True
        
        # Start heartbeat thread
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()
        
        try:
            self._main_loop()
        except Exception as e:
            print(f"Worker error: {e}")
        finally:
            self.stop()
    
    def _ensure_system_database_setup(self):
        """Ensure the system database directory exists with proper permissions."""
        db_path = config.get_multi_user_database_path()
        db_dir = os.path.dirname(db_path)
        
        # Create directory if it doesn't exist
        if not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir, mode=0o755, exist_ok=True)
                print(f"Created system database directory: {db_dir}")
            except PermissionError:
                print(f"Warning: Could not create system database directory: {db_dir}")
                print("Please run 'sudo mkdir -p {db_dir}' and 'sudo chmod 755 {db_dir}'")
        
        # Check if database file exists and is writable
        if os.path.exists(db_path):
            if not os.access(db_path, os.W_OK):
                print(f"Warning: Database file is not writable: {db_path}")
        else:
            # Try to create the database file
            try:
                # Touch the file to create it
                with open(db_path, 'a'):
                    pass
                # Set permissions so all users can read/write
                os.chmod(db_path, 0o666)
                print(f"Created system database file: {db_path}")
            except PermissionError:
                print(f"Warning: Could not create database file: {db_path}")
                print("Please ensure the worker has write permissions to the database directory")
    
    def stop(self):
        """Stop the worker daemon."""
        print("Stopping worker...")
        self.running = False
        
        # Update worker status in database
        self._update_worker_status(False)
        
        print("Worker stopped.")
    
    def is_running(self) -> bool:
        """Check if a worker is currently running."""
        worker_status = self.db.get_worker_status()
        if not worker_status:
            return False
        
        # Check if worker is marked as active and heartbeat is recent
        if not worker_status['is_active']:
            return False
        
        # Consider worker dead if no heartbeat for configured time
        if worker_status['last_heartbeat']:
            time_diff = (datetime.utcnow() - worker_status['last_heartbeat']).total_seconds()
            return time_diff < config.MAX_WORKER_HEARTBEAT_AGE
        
        return False
    
    def _main_loop(self):
        """Main worker loop."""
        print("Multi-user worker is running. Checking for jobs from all users...")
        
        while self.running:
            try:
                # Get next job to execute (from any user)
                job = self.queue_manager.get_next_job_to_run()
                
                if job:
                    user = job.get('submitted_by', 'unknown')
                    print(f"Starting installation of {job['package_name']} (Job ID: {job['id']}) for user: {user}")
                    self._execute_job(job)
                else:
                    # No jobs available, wait before checking again
                    time.sleep(self.check_interval)
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error in worker loop: {e}")
                time.sleep(self.check_interval)
    
    def _execute_job(self, job):
        """Execute a single installation job."""
        job_id = job['id']
        self.current_job_id = job_id
        self.current_job_user = job.get('submitted_by', 'unknown')
        
        try:
            # Mark job as running
            if not self.queue_manager.mark_job_running(job_id):
                print(f"Failed to mark job {job_id} as running")
                return
            
            # Update worker status with current job
            self._update_worker_status(True, job_id)
            
            # Log job start with user information
            self._log_message(job_id, "INFO", f"Starting installation for user: {self.current_job_user}")
            
            # First, run spack spec to get package information
            self._run_spack_spec(job)
            
            # Execute the installation
            success, error_message = self._run_spack_install(job)
            
            # Mark job as completed
            self.queue_manager.mark_job_completed(job_id, success, error_message)
            
            if success:
                print(f"Successfully installed {job['package_name']} for user {self.current_job_user}")
                self._log_message(job_id, "INFO", f"Installation completed successfully for user: {self.current_job_user}")
            else:
                print(f"Failed to install {job['package_name']} for user {self.current_job_user}: {error_message}")
                self._log_message(job_id, "ERROR", f"Installation failed for user {self.current_job_user}: {error_message}")
                
        except Exception as e:
            print(f"Error executing job {job_id} for user {self.current_job_user}: {e}")
            self.queue_manager.mark_job_completed(job_id, False, str(e))
        finally:
            self.current_job_id = None
            self.current_job_user = None
            self._update_worker_status(True, None)
    
    def _run_spack_spec(self, job):
        """Run spack spec command to get package information and log it.
        
        Args:
            job: The installation job
        """
        job_id = job['id']
        package_name = job['package_name']
        
        try:
            # Get spack setup script
            spack_setup_script = config.get_spack_setup_script()
            
            if not config.validate_spack_setup():
                self._log_message(job_id, "WARNING", f"Spack setup script not found, skipping spec command: {spack_setup_script}")
                return
            
            # Build the spack spec command
            spec_command = f"spack spec {package_name}"
            full_command = f"source {spack_setup_script} && {spec_command}"
            
            # Log the command being executed
            self._log_message(job_id, "INFO", f"Getting package specification: {spec_command}")
            print(f"Running spack spec for {package_name}")
            
            # Run the spec command with streaming (but shorter timeout)
            success, error_msg = self._run_command_with_streaming(job_id, full_command, 60)
            
            if success:
                self._log_message(job_id, "INFO", "Package specification retrieved successfully")
            else:
                self._log_message(job_id, "WARNING", f"Spec command failed: {error_msg}, but continuing with installation")
                
        except Exception as e:
            self._log_message(job_id, "WARNING", f"Error running spec command: {str(e)}, continuing with installation")
    
    def _run_spack_install(self, job) -> tuple[bool, Optional[str]]:
        """Run the actual spack installation command with real-time logging.
        
        Args:
            job: The installation job to execute
            
        Returns:
            Tuple of (success, error_message)
        """
        job_id = job['id']
        
        try:
            # Determine the spack command to run
            if job['spack_command']:
                # Use custom command if provided
                spack_command = job['spack_command']
                
                # Check if the custom command already includes sourcing
                if "source " in spack_command and "setup-env.sh" in spack_command:
                    # Custom command already handles spack setup
                    full_command = spack_command
                else:
                    # Add spack setup to custom command
                    spack_setup_script = config.get_spack_setup_script()
                    if not config.validate_spack_setup():
                        error_msg = f"Spack setup script not found at: {spack_setup_script}"
                        self._log_message(job_id, "ERROR", error_msg)
                        return False, error_msg
                    full_command = f"source {spack_setup_script} && {spack_command}"
            else:
                # Default spack install command
                spack_setup_script = config.get_spack_setup_script()
                
                # Validate that the setup script exists
                if not config.validate_spack_setup():
                    error_msg = f"Spack setup script not found at: {spack_setup_script}"
                    self._log_message(job_id, "ERROR", error_msg)
                    return False, error_msg
                
                spack_command = f"spack install {job['package_name']}"
                full_command = f"source {spack_setup_script} && {spack_command}"
            
            # Log the command being executed
            self._log_message(job_id, "INFO", f"Executing command: {full_command}")
            print(f"Executing: {full_command}")
            
            # Run the command with real-time output streaming
            return self._run_command_with_streaming(job_id, full_command, job['estimated_time'])
                
        except Exception as e:
            error_msg = f"Execution error: {str(e)}"
            self._log_message(job_id, "ERROR", error_msg)
            return False, error_msg
    
    def _run_command_with_streaming(self, job_id: int, command: str, estimated_time: float) -> tuple[bool, Optional[str]]:
        """Run a command with real-time output streaming and logging.
        
        Args:
            job_id: The job ID for logging
            command: The command to execute
            estimated_time: Estimated time for timeout calculation
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Start the process
            process = subprocess.Popen(
                command,
                shell=True,
                executable="/bin/bash",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Merge stderr into stdout for unified streaming
                text=True,
                bufsize=1,  # Line buffered
                universal_newlines=True
            )
            
            # Track the process start time for timeout
            start_time = time.time()
            timeout_seconds = estimated_time * config.DEFAULT_JOB_TIMEOUT_MULTIPLIER
            
            stdout_lines = []
            
            # Read output line by line in real-time
            while True:
                # Check for timeout
                elapsed_time = time.time() - start_time
                if elapsed_time > timeout_seconds:
                    process.terminate()
                    try:
                        process.wait(timeout=5)  # Wait up to 5 seconds for graceful termination
                    except subprocess.TimeoutExpired:
                        process.kill()  # Force kill if it doesn't terminate gracefully
                    
                    timeout_msg = f"Installation timed out after {timeout_seconds:.1f} seconds"
                    self._log_message(job_id, "ERROR", timeout_msg)
                    return False, timeout_msg
                
                # Read a line from stdout
                line = process.stdout.readline()
                
                if line:
                    # Remove trailing newline and log the line immediately
                    line_content = line.rstrip('\n\r')
                    if line_content:  # Only log non-empty lines
                        self._log_message(job_id, "INFO", f"INSTALL: {line_content}")
                        stdout_lines.append(line_content)
                        
                        # Also print to console for immediate feedback with user context
                        print(f"[Job {job_id}|{self.current_job_user}] {line_content}")
                
                # Check if process has finished
                if process.poll() is not None:
                    # Process has finished, read any remaining output
                    remaining_output = process.stdout.read()
                    if remaining_output:
                        for remaining_line in remaining_output.strip().split('\n'):
                            if remaining_line.strip():
                                self._log_message(job_id, "INFO", f"INSTALL: {remaining_line}")
                                stdout_lines.append(remaining_line)
                                print(f"[Job {job_id}|{self.current_job_user}] {remaining_line}")
                    break
                
                # Small sleep to prevent excessive CPU usage
                time.sleep(0.1)
            
            # Get the return code
            return_code = process.returncode
            
            # Log the completion
            self._log_message(job_id, "INFO", f"Command completed with exit code: {return_code}")
            
            if return_code == 0:
                self._log_message(job_id, "INFO", "Installation completed successfully")
                print(f"[Job {job_id}|{self.current_job_user}] Installation completed successfully")
                return True, None
            else:
                error_msg = f"Command failed with exit code {return_code}"
                self._log_message(job_id, "ERROR", error_msg)
                
                # Create a summary error message for the job status
                summary_error = f"Exit code {return_code}"
                
                # Look for error patterns in the last few lines of output
                if stdout_lines:
                    # Get last few lines that might contain error information
                    last_lines = stdout_lines[-5:]
                    for line in reversed(last_lines):
                        if any(keyword in line.lower() for keyword in ['error', 'failed', 'cannot', 'unable']):
                            # Include first 100 chars of the error line
                            summary_error += f": {line[:100]}"
                            break
                
                return False, summary_error
                
        except Exception as e:
            error_msg = f"Process execution error: {str(e)}"
            self._log_message(job_id, "ERROR", error_msg)
            return False, error_msg
    
    def _log_message(self, job_id: int, level: str, message: str):
        """Log a message for a specific job."""
        try:
            # Add log entry directly to database manager
            self.db.add_job_log(job_id, level, message)
        except Exception as e:
            # If database logging fails, at least print to console
            print(f"Failed to log message: {e}")
            user_context = f"|{self.current_job_user}" if self.current_job_user else ""
            print(f"[{level}] Job {job_id}{user_context}: {message}")
    
    def _update_worker_status(self, is_active: bool, current_job_id: Optional[int] = None):
        """Update worker status in the database."""
        started_at = datetime.utcnow() if is_active else None
        process_id = os.getpid() if is_active else None
        
        self.db.update_worker_status(
            is_active=is_active,
            current_job_id=current_job_id,
            started_at=started_at,
            process_id=process_id
        )
    
    def _heartbeat_loop(self):
        """Heartbeat loop to update worker status."""
        while self.running:
            try:
                self._update_worker_status(True, self.current_job_id)
                time.sleep(config.WORKER_HEARTBEAT_INTERVAL)
            except Exception as e:
                print(f"Heartbeat error: {e}")
                time.sleep(config.WORKER_HEARTBEAT_INTERVAL)


def start_worker(use_system_database: bool = True):
    """Start the worker daemon.
    
    Args:
        use_system_database: Whether to use system-wide database for multi-user support
    """
    worker = InstallationWorker(use_system_database=use_system_database)
    
    # Check if another worker is already running
    if worker.is_running():
        print("Another worker is already running. Exiting.")
        sys.exit(1)
    
    worker.start()


def stop_worker():
    """Stop the worker daemon."""
    db = get_db_manager()
    worker_status = db.get_worker_status()
    
    if not worker_status or not worker_status['is_active']:
        print("No active worker found.")
        return False
    
    if worker_status['process_id']:
        try:
            import psutil
            if psutil.pid_exists(worker_status['process_id']):
                process = psutil.Process(worker_status['process_id'])
                process.terminate()
                print(f"Sent termination signal to worker process {worker_status['process_id']}")
                return True
        except ImportError:
            print("psutil not available. Cannot send signal to worker process.")
        except Exception as e:
            print(f"Error stopping worker: {e}")
    
    # Mark worker as inactive in database
    db.update_worker_status(
        is_active=False,
        current_job_id=None,
        process_id=None
    )
    
    print("Marked worker as inactive in database.")
    return True


def get_worker_status() -> dict:
    """Get current worker status."""
    db = get_db_manager()
    worker_status = db.get_worker_status()
    
    if not worker_status:
        return {
            "active": False,
            "current_job_id": None,
            "started_at": None,
            "last_heartbeat": None,
            "process_id": None
        }
    
    return {
        "active": worker_status['is_active'],
        "current_job_id": worker_status['current_job_id'],
        "started_at": worker_status['started_at'].isoformat() if worker_status['started_at'] else None,
        "last_heartbeat": worker_status['last_heartbeat'].isoformat() if worker_status['last_heartbeat'] else None,
        "process_id": worker_status['process_id']
    }
