"""Database models for the Spack installer queue system."""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from sqlalchemy import Column, Integer, String, DateTime, Text, Float, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator, VARCHAR
import json

Base = declarative_base()


class ChoiceType(TypeDecorator):
    """Custom SQLAlchemy type for Enum choices."""
    
    impl = VARCHAR
    cache_ok = True
    
    def __init__(self, choices, **kw):
        if hasattr(choices, '__members__'):
            # It's an Enum class
            self.choices = choices
        else:
            # It's a dict or list of tuples
            self.choices = dict(choices)
        super().__init__(**kw)
    
    def process_bind_param(self, value, dialect):
        return value.value if isinstance(value, Enum) else value
    
    def process_result_value(self, value, dialect):
        return value


class JobStatus(Enum):
    """Job status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPriority(Enum):
    """Job priority enumeration."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class InstallationJob(Base):
    """Model for installation jobs."""
    
    __tablename__ = "installation_jobs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    package_name = Column(String(255), nullable=False)
    status = Column(ChoiceType(JobStatus), default=JobStatus.PENDING, nullable=False)
    priority = Column(ChoiceType(JobPriority), default=JobPriority.MEDIUM, nullable=False)
    estimated_time = Column(Float, default=300.0)  # in seconds
    actual_time = Column(Float, nullable=True)
    dependencies = Column(Text, nullable=True)  # JSON string of dependency list
    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    submitted_by = Column(String(255), nullable=True)
    error_message = Column(Text, nullable=True)
    spack_command = Column(Text, nullable=True)
    resource_requirements = Column(Text, nullable=True)  # JSON string
    
    # Relationships
    logs = relationship("JobLog", back_populates="job", cascade="all, delete-orphan")
    
    @property
    def dependencies_list(self) -> List[str]:
        """Get dependencies as a list."""
        if not self.dependencies:
            return []
        try:
            return json.loads(self.dependencies)
        except (json.JSONDecodeError, TypeError):
            return []
    
    @dependencies_list.setter
    def dependencies_list(self, value: List[str]):
        """Set dependencies from a list."""
        self.dependencies = json.dumps(value) if value else None
    
    @property
    def resource_requirements_dict(self) -> dict:
        """Get resource requirements as a dictionary."""
        if not self.resource_requirements:
            return {}
        try:
            return json.loads(self.resource_requirements)
        except (json.JSONDecodeError, TypeError):
            return {}
    
    @resource_requirements_dict.setter
    def resource_requirements_dict(self, value: dict):
        """Set resource requirements from a dictionary."""
        self.resource_requirements = json.dumps(value) if value else None
    
    @property
    def duration(self) -> Optional[float]:
        """Calculate job duration if completed."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    def __repr__(self):
        return f"<InstallationJob(id={self.id}, package='{self.package_name}', status='{self.status.value}')>"


class JobLog(Base):
    """Model for job execution logs."""
    
    __tablename__ = "job_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("installation_jobs.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    level = Column(String(10), nullable=False)  # INFO, WARNING, ERROR
    message = Column(Text, nullable=False)
    
    # Relationship
    job = relationship("InstallationJob", back_populates="logs")
    
    def __repr__(self):
        return f"<JobLog(id={self.id}, job_id={self.job_id}, level='{self.level}')>"


class WorkerStatus(Base):
    """Model for tracking worker status."""
    
    __tablename__ = "worker_status"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    is_active = Column(String(10), default="false", nullable=False)  # "true" or "false"
    current_job_id = Column(Integer, ForeignKey("installation_jobs.id"), nullable=True)
    started_at = Column(DateTime, nullable=True)
    last_heartbeat = Column(DateTime, default=datetime.utcnow, nullable=False)
    process_id = Column(Integer, nullable=True)
    
    # Relationship
    current_job = relationship("InstallationJob")
    
    def __repr__(self):
        return f"<WorkerStatus(is_active={self.is_active}, current_job_id={self.current_job_id})>"
