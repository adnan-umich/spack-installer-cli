"""Configuration settings for the Spack Installer API."""

import os
from typing import Optional


class Config:
    """Configuration settings for the application."""
    
    # Database settings
    DATABASE_TYPE: str = os.getenv("SPACK_INSTALLER_DB_TYPE", "json")  # "json" or "sqlite"
    DATABASE_URL: Optional[str] = os.getenv("SPACK_INSTALLER_DB_URL")
    DATABASE_PATH: str = os.getenv("SPACK_INSTALLER_DB_PATH", os.path.expanduser("~/.spack_installer/jobs.json"))
    
    # Spack configuration
    SPACK_SETUP_SCRIPT: str = os.getenv("SPACK_SETUP_SCRIPT", "/opt/spack/setup-env.sh")
    
    # Worker settings
    WORKER_CHECK_INTERVAL: float = float(os.getenv("WORKER_CHECK_INTERVAL", "10.0"))
    WORKER_HEARTBEAT_INTERVAL: float = float(os.getenv("WORKER_HEARTBEAT_INTERVAL", "30.0"))
    
    # Job settings
    DEFAULT_JOB_TIMEOUT_MULTIPLIER: float = float(os.getenv("JOB_TIMEOUT_MULTIPLIER", "2.0"))
    MAX_WORKER_HEARTBEAT_AGE: float = float(os.getenv("MAX_WORKER_HEARTBEAT_AGE", "60.0"))
    
    # Server settings (for multi-user mode)
    SERVER_HOST: str = os.getenv("SPACK_INSTALLER_SERVER_HOST", "localhost")
    SERVER_PORT: int = int(os.getenv("SPACK_INSTALLER_SERVER_PORT", "8080"))
    SERVER_SOCKET_PATH: str = os.getenv("SPACK_INSTALLER_SERVER_SOCKET", "/tmp/spack_installer.sock")
    USE_UNIX_SOCKET: bool = os.getenv("SPACK_INSTALLER_USE_UNIX_SOCKET", "true").lower() == "true"
    MULTI_USER_DATABASE_PATH: str = os.getenv("SPACK_INSTALLER_MULTI_USER_DB", "/tmp/jobs.json")
    
    @classmethod
    def get_database_path(cls) -> str:
        """Get the path to the database file."""
        return cls.DATABASE_PATH
    
    @classmethod
    def get_database_type(cls) -> str:
        """Get the database type (json or sqlite)."""
        return cls.DATABASE_TYPE.lower()
    
    @classmethod
    def get_database_url(cls) -> Optional[str]:
        """Get the database URL (for SQLite/PostgreSQL/etc.)."""
        return cls.DATABASE_URL
    
    @classmethod
    def get_spack_setup_script(cls) -> str:
        """Get the path to the spack setup script."""
        return cls.SPACK_SETUP_SCRIPT
    
    @classmethod
    def validate_spack_setup(cls) -> bool:
        """Check if the spack setup script exists."""
        setup_script = cls.get_spack_setup_script()
        return os.path.isfile(setup_script)
    
    @classmethod
    def get_server_host(cls) -> str:
        """Get the server host."""
        return cls.SERVER_HOST
    
    @classmethod
    def get_server_port(cls) -> int:
        """Get the server port."""
        return cls.SERVER_PORT
    
    @classmethod
    def get_server_socket_path(cls) -> str:
        """Get the Unix socket path for the server."""
        return cls.SERVER_SOCKET_PATH
    
    @classmethod
    def get_use_unix_socket(cls) -> bool:
        """Check if Unix socket should be used."""
        return cls.USE_UNIX_SOCKET
    
    @classmethod
    def get_multi_user_database_path(cls) -> str:
        """Get the path for multi-user database."""
        return cls.MULTI_USER_DATABASE_PATH


# Global config instance
config = Config()
