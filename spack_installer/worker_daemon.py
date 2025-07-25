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
from pathlib import Path

# Add the package to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from spack_installer.worker import InstallationWorker
from spack_installer.config import config


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
    
    print("\nStarting multi-user worker daemon...")
    
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
