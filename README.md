# Spack Installer API

A Python CLI application for managing Spack package installations with intelligent queueing and job scheduling.

## Features

- **Queue Management**: Submit installation jobs that are queued and executed sequentially
- **Intelligent Scheduling**: Optimizes job order based on dependencies, estimated time, and resource requirements
- **Concurrent Safety**: Prevents multiple simultaneous installations
- **Priority System**: Support for different priority levels
- **Status Monitoring**: Track job progress and queue status
- **Persistent Storage**: Jobs survive application restarts

## Installation

```bash
pip install -e .
```

## Usage

### Check Configuration
```bash
spack-installer config-check
```

### Submit a new installation job
```bash
spack-installer submit package_name [--priority high|medium|low] [--dependencies dep1,dep2] [--estimated-time 60] [--spack-setup /path/to/setup-env.sh]
```

### Check queue status
```bash
spack-installer status
```

### Start the worker daemon
```bash
spack-installer worker start
```

### Stop the worker daemon
```bash
spack-installer worker stop
```

### Cancel a job
```bash
spack-installer cancel JOB_ID
```

### Clear completed jobs
```bash
spack-installer cleanup
```

## Configuration

The application can be configured using environment variables:

- `SPACK_SETUP_SCRIPT`: Path to spack setup script (default: `/opt/spack/setup-env.sh`)
- `SPACK_INSTALLER_DB_URL`: Database URL (default: SQLite in `~/.spack_installer/jobs.db`)
- `WORKER_CHECK_INTERVAL`: Seconds between queue checks (default: 10.0)
- `WORKER_HEARTBEAT_INTERVAL`: Seconds between heartbeats (default: 30.0)
- `JOB_TIMEOUT_MULTIPLIER`: Timeout multiplier for jobs (default: 2.0)
- `MAX_WORKER_HEARTBEAT_AGE`: Max age for worker heartbeat in seconds (default: 60.0)

## Architecture

- **CLI Interface**: User-facing command-line interface
- **Queue Manager**: Handles job submission and queue operations
- **Job Scheduler**: Implements intelligent job ordering algorithms
- **Worker**: Executes jobs sequentially
- **Database**: SQLite-based persistent storage

## Job Scheduling Algorithm

The scheduler optimizes job order based on:
1. **Priority**: High priority jobs are scheduled first
2. **Dependencies**: Jobs with fewer dependencies are prioritized
3. **Estimated Time**: Shorter jobs may be prioritized to improve throughput
4. **Resource Requirements**: Consider system resources and job requirements
5. **Dependency Chains**: Optimize the order of dependent packages
