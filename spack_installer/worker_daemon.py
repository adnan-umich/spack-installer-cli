#!/usr/bin/env python3
"""
Standalone multi-user worker daemon for Spack Installer.

This script can be run as a system service to handle installation jobs
from multiple users on the same machine.
"""

import os
import sys
import argparse
import signal
import logging
import socket
import threading
import json
import socketserver
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

# Custom JSON encoder to handle datetime objects
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

# Add the package to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from spack_installer.worker import InstallationWorker
from spack_installer.config import config
from spack_installer.queue_manager import QueueManager
from spack_installer.models import JobPriority
from spack_installer.database import get_db_manager

# Global worker instance and server instance
_worker_instance = None
_server_instance = None


class SpackJobHandler(socketserver.BaseRequestHandler):
    """Request handler for processing job submission requests via socket."""
    
    def __init__(self, *args, **kwargs):
        self.queue_manager = QueueManager()
        super().__init__(*args, **kwargs)
    
    def handle(self):
        """Handle incoming socket requests."""
        try:
            # Receive request data
            data = b''
            while True:
                chunk = self.request.recv(4096)
                if not chunk:
                    break
                data += chunk
            
            if not data:
                self._send_error("No data received")
                return
            
            # Parse request
            try:
                request = json.loads(data.decode('utf-8'))
            except json.JSONDecodeError as e:
                self._send_error(f"Invalid JSON: {e}")
                return
            
            # Process request
            action = request.get('action')
            if action == 'submit_job':
                self._handle_submit_job(request.get('params', {}))
            elif action == 'get_status':
                self._handle_get_status(request.get('params', {}))
            elif action == 'get_jobs':
                self._handle_get_jobs(request.get('params', {}))
            elif action == 'cancel_job':
                self._handle_cancel_job(request.get('params', {}))
            elif action == 'get_job_logs':
                self._handle_get_job_logs(request.get('params', {}))
            else:
                self._send_error(f"Unknown action: {action}")
                
        except Exception as e:
            logging.exception(f"Error handling request: {e}")
            self._send_error(f"Server error: {e}")
    
    def _send_response(self, data: Dict[str, Any]):
        """Send successful response."""
        response = {
            'success': True,
            'data': data
        }
        self._send_json(response)
    
    def _send_error(self, message: str):
        """Send error response."""
        response = {
            'success': False,
            'error': message
        }
        self._send_json(response)
    
    def _send_json(self, data: Dict[str, Any]):
        """Send JSON response."""
        try:
            response_json = json.dumps(data, cls=DateTimeEncoder).encode('utf-8')
            self.request.sendall(response_json)
        except (BrokenPipeError, ConnectionResetError):
            # Client disconnected, ignore silently
            pass
        except Exception as e:
            logging.exception(f"Error sending response: {e}")
    
    def _handle_submit_job(self, params: Dict[str, Any]):
        """Handle job submission."""
        try:
            package_name = params.get('package_name')
            priority = params.get('priority', 'medium')
            dependencies = params.get('dependencies', [])
            estimated_time = params.get('estimated_time', 7200.0)
            spack_command = params.get('spack_command')
            
            if not package_name:
                self._send_error("Missing package_name parameter")
                return
            
            # Parse priority
            try:
                job_priority = JobPriority(priority.lower())
            except ValueError:
                self._send_error(f"Invalid priority: {priority}")
                return
            
            # Submit job
            job_info = self.queue_manager.submit_job(
                package_name=package_name,
                priority=job_priority,
                dependencies=dependencies,
                estimated_time=estimated_time,
                spack_command=spack_command
            )
            
            self._send_response(job_info)
            
        except Exception as e:
            logging.exception(f"Error submitting job: {e}")
            self._send_error(f"Error submitting job: {e}")
    
    def _handle_get_status(self, params: Dict[str, Any]):
        """Handle status request."""
        try:
            print("DEBUG: Handling get_status request")
            status = self.queue_manager.get_queue_status()
            print(f"DEBUG: Got status: {status}")
            self._send_response(status)
            print("DEBUG: Sent response")
        except Exception as e:
            print(f"DEBUG: Error in get_status: {e}")
            logging.exception(f"Error getting status: {e}")
            self._send_error(f"Error getting status: {e}")
    
    def _handle_get_jobs(self, params: Dict[str, Any]):
        """Handle get jobs request."""
        try:
            filter_status = params.get('status')
            if filter_status:
                from spack_installer.models import JobStatus
                jobs = self.queue_manager.get_all_jobs(JobStatus(filter_status))
            else:
                jobs = self.queue_manager.get_all_jobs()
            self._send_response({'jobs': jobs})
        except Exception as e:
            logging.exception(f"Error getting jobs: {e}")
            self._send_error(f"Error getting jobs: {e}")
    
    def _handle_cancel_job(self, params: Dict[str, Any]):
        """Handle job cancellation."""
        try:
            job_id = params.get('job_id')
            if not job_id:
                self._send_error("Missing job_id parameter")
                return
            
            success = self.queue_manager.cancel_job(job_id)
            self._send_response({'cancelled': success})
        except Exception as e:
            logging.exception(f"Error cancelling job: {e}")
            self._send_error(f"Error cancelling job: {e}")
    
    def _handle_get_job_logs(self, params: Dict[str, Any]):
        """Handle get job logs request."""
        try:
            job_id = params.get('job_id')
            if not job_id:
                self._send_error("Missing job_id parameter")
                return
            
            logs = self.queue_manager.get_job_logs(job_id)
            self._send_response({'logs': logs})
        except Exception as e:
            logging.exception(f"Error getting job logs: {e}")
            self._send_error(f"Error getting job logs: {e}")


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """Threaded TCP server for handling multiple connections."""
    allow_reuse_address = True
    daemon_threads = True


class ThreadedUnixStreamServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    """Threaded Unix socket server for handling multiple connections."""
    allow_reuse_address = True
    daemon_threads = True


def start_socket_server():
    """Start the socket server for handling client requests."""
    global _server_instance
    
    try:
        if config.USE_UNIX_SOCKET:
            # Create directory for socket if it doesn't exist
            socket_dir = os.path.dirname(config.SERVER_SOCKET_PATH)
            os.makedirs(socket_dir, exist_ok=True)
            
            # Remove socket file if it exists
            if os.path.exists(config.SERVER_SOCKET_PATH):
                os.unlink(config.SERVER_SOCKET_PATH)
            
            # Create Unix socket server
            _server_instance = ThreadedUnixStreamServer(
                config.SERVER_SOCKET_PATH, 
                SpackJobHandler
            )
            logging.info(f"Starting Unix socket server on {config.SERVER_SOCKET_PATH}")
        else:
            # Create TCP server
            _server_instance = ThreadedTCPServer(
                (config.SERVER_HOST, config.SERVER_PORT),
                SpackJobHandler
            )
            logging.info(f"Starting TCP server on {config.SERVER_HOST}:{config.SERVER_PORT}")
        
        # Start server in a separate thread
        server_thread = threading.Thread(target=_server_instance.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        
        logging.info("Socket server started successfully")
        return True
        
    except Exception as e:
        logging.exception(f"Failed to start socket server: {e}")
        return False


def stop_socket_server():
    """Stop the socket server."""
    global _server_instance
    
    if _server_instance:
        try:
            logging.info("Shutting down socket server...")
            _server_instance.shutdown()
            _server_instance.server_close()
            
            # Clean up Unix socket file
            if config.USE_UNIX_SOCKET and os.path.exists(config.SERVER_SOCKET_PATH):
                os.unlink(config.SERVER_SOCKET_PATH)
            
            _server_instance = None
            logging.info("Socket server stopped successfully")
            return True
        except Exception as e:
            logging.exception(f"Failed to stop socket server: {e}")
            return False
    return True


def daemonize():
    """Properly daemonize the process."""
    try:
        # First fork
        pid = os.fork()
        if pid > 0:
            # Exit parent process
            sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"Fork #1 failed: {e}\n")
        sys.exit(1)
    
    # Decouple from parent environment
    os.chdir("/")
    os.setsid()
    os.umask(0)
    
    # Second fork
    try:
        pid = os.fork()
        if pid > 0:
            # Exit parent process
            sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"Fork #2 failed: {e}\n")
        sys.exit(1)
    
    # Redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()
    
    # Redirect stdin, stdout, stderr to /dev/null
    with open('/dev/null', 'r') as f:
        os.dup2(f.fileno(), sys.stdin.fileno())
    with open('/dev/null', 'w') as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
        os.dup2(f.fileno(), sys.stderr.fileno())


def start_worker_server(args=None):
    """Start the combined worker server (socket server + job processor)."""
    global _worker_instance
    
    # Daemonize if requested
    if args and getattr(args, 'daemon', False):
        daemonize()
        # Setup logging again after daemonization
        setup_logging(
            log_level=getattr(args, 'log_level', 'INFO'),
            log_file=getattr(args, 'log_file', None)
        )
    
    logging.info("Starting Spack Installer Worker Server...")
    
    # Start socket server
    if not start_socket_server():
        logging.error("Failed to start socket server")
        sys.exit(1)
    
    # Start worker
    try:
        check_interval = getattr(args, 'check_interval', None) if args else None
        _worker_instance = InstallationWorker(
            check_interval=check_interval,
            use_system_database=True
        )
        
        # Check if another worker is running
        if _worker_instance.is_running():
            logging.error("Another worker is already running. Exiting.")
            stop_socket_server()
            sys.exit(1)
        
        logging.info("Worker server started successfully")
        logging.info(f"Socket type: {'Unix socket' if config.USE_UNIX_SOCKET else 'TCP'}")
        if config.USE_UNIX_SOCKET:
            logging.info(f"Socket path: {config.SERVER_SOCKET_PATH}")
        else:
            logging.info(f"Server address: {config.SERVER_HOST}:{config.SERVER_PORT}")
        
        # Start the worker
        _worker_instance.start()
        
    except KeyboardInterrupt:
        logging.info("Shutdown requested by user")
    except Exception as e:
        logging.exception(f"Worker error: {e}")
    finally:
        stop_socket_server()
        logging.info("Worker server stopped")


def setup_logging(log_level: str = "INFO", log_file: str = None):
    """Setup logging configuration."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Configure logging format
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Setup console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # Setup root logger
    logger = logging.getLogger()
    logger.setLevel(level)
    logger.addHandler(console_handler)
    
    # Setup file handler if specified
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            print(f"Logging to file: {log_file}")
        except PermissionError:
            print(f"Warning: Cannot write to log file: {log_file}")


def ensure_system_database():
    """Ensure system database directory exists with proper permissions."""
    db_path = config.get_multi_user_database_path()
    db_dir = os.path.dirname(db_path)
    
    # Create directory if it doesn't exist
    if not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir, mode=0o755, exist_ok=True)
            print(f"Created system database directory: {db_dir}")
        except PermissionError:
            print(f"Error: Cannot create system database directory: {db_dir}")
            print("Please run this script with appropriate permissions or manually create the directory:")
            sys.exit(1)
    
    # Ensure database file has proper permissions
    if not os.path.exists(db_path):
        try:
            # Create empty database file
            with open(db_path, 'w') as f:
                f.write('{"jobs": [], "logs": [], "worker_status": null, "next_job_id": 1}')
            # Set permissions so all users can read/write
            os.chmod(db_path, 0o666)
            print(f"Created system database file: {db_path}")
        except PermissionError:
            print(f"Error: Cannot create database file: {db_path}")
            print("Please ensure the directory has write permissions for this user")
            sys.exit(1)


def main():
    """Main entry point for the multi-user worker daemon."""
    parser = argparse.ArgumentParser(
        description="Multi-user Spack Installer Worker Daemon"
    )
    parser.add_argument(
        "--log-level", 
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set the logging level"
    )
    parser.add_argument(
        "--log-file",
        help="Path to log file (optional)"
    )
    parser.add_argument(
        "--check-interval",
        type=float,
        default=None,
        help="Seconds between job queue checks (default from config)"
    )
    parser.add_argument(
        "--mode",
        choices=["server", "worker"],
        default="server",
        help="Run mode: server (socket server + worker) or worker (worker only)"
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run as a daemon (detach from terminal)"
    )
    parser.add_argument(
        "--validate-setup",
        action="store_true",
        help="Validate system setup and exit"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.log_level, args.log_file)
    
    print("Spack Installer Multi-User Worker Daemon")
    print("=" * 50)
    
    # Validate system setup
    print("Validating system setup...")
    
    # Check Spack configuration
    if config.validate_spack_setup():
        print(f"✓ Spack setup script found: {config.get_spack_setup_script()}")
    else:
        print(f"✗ Spack setup script not found: {config.get_spack_setup_script()}")
        print("  Please set SPACK_SETUP_SCRIPT environment variable")
        if not args.validate_setup:
            print("  Warning: Worker will skip spack commands if setup script is missing")
    
    # Ensure system database setup
    try:
        ensure_system_database()
        print(f"✓ System database ready: {config.get_multi_user_database_path()}")
    except Exception as e:
        print(f"✗ Database setup failed: {e}")
        sys.exit(1)
    
    # Check permissions
    db_path = config.get_multi_user_database_path()
    if os.access(db_path, os.R_OK | os.W_OK):
        print("✓ Database file is readable and writable")
    else:
        print("✗ Database file is not accessible")
        sys.exit(1)
    
    if args.validate_setup:
        print("\nSystem validation complete. Exiting.")
        sys.exit(0)
    
    # Start in appropriate mode
    if args.mode == "server":
        print(f"\nStarting worker server mode...")
        print(f"Socket type: {'Unix socket' if config.USE_UNIX_SOCKET else 'TCP'}")
        if config.USE_UNIX_SOCKET:
            print(f"Socket path: {config.SERVER_SOCKET_PATH}")
        else:
            print(f"Server address: {config.SERVER_HOST}:{config.SERVER_PORT}")
        
        start_worker_server(args)
    else:
        print(f"\nStarting worker-only mode...")
        
        # Create and start worker
        try:
            worker = InstallationWorker(
                check_interval=args.check_interval,
                use_system_database=True
            )
            
            # Check if another worker is running
            if worker.is_running():
                print("Another worker is already running. Exiting.")
                sys.exit(1)
            
            # Start the worker
            worker.start()
            
        except KeyboardInterrupt:
            print("\nShutdown requested by user")
        except Exception as e:
            print(f"Worker error: {e}")
            sys.exit(1)
        
        print("Worker daemon stopped")


if __name__ == "__main__":
    main()
