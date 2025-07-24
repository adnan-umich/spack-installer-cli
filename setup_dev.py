#!/usr/bin/env python3
"""
Development setup script for Spack Installer API.
"""

import subprocess
import sys
import os

def run_command(cmd, description):
    """Run a command and print status."""
    print(f">>> {description}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"ERROR: {description} failed!")
        sys.exit(1)
    print()

def main():
    """Set up development environment."""
    print("=== Spack Installer API Development Setup ===\n")
    
    # Install package in development mode
    run_command("pip install -e .", "Installing package in development mode")
    
    # Install development dependencies
    run_command("pip install -r requirements-dev.txt", "Installing development dependencies")
    
    # Create database directory
    db_dir = os.path.expanduser("~/.spack_installer")
    os.makedirs(db_dir, exist_ok=True)
    print(f">>> Created database directory: {db_dir}\n")
    
    print("=== Setup Complete! ===")
    print("\nQuick start:")
    print("1. Submit a job: spack-installer submit my_package --priority high")
    print("2. Check status: spack-installer status")
    print("3. Start worker: spack-installer worker start")
    print("\nRun tests: python -m pytest")
    print("View help: spack-installer --help")

if __name__ == "__main__":
    main()
