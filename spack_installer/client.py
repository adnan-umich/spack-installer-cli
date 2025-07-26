"""Socket client module for the Spack Installer."""

import os
import socket
import json
import logging
from typing import Dict, Any, Optional, List

from .config import config

# Set up logging
logger = logging.getLogger(__name__)

class SpackInstallerClient:
    """Client for communicating with the Spack Installer server via sockets."""
    
    def __init__(self):
        """Initialize the client."""
        self.use_unix_socket = config.USE_UNIX_SOCKET
        self.server_socket_path = config.SERVER_SOCKET_PATH
        self.server_host = config.SERVER_HOST
        self.server_port = config.SERVER_PORT
        # Default socket timeout of 30 seconds if not configured
        self.socket_timeout = getattr(config, 'SOCKET_TIMEOUT', 30.0)
    
    def _send_request(self, action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send a request to the server and get the response.
        
        Args:
            action: The action to perform
            params: Parameters for the action
            
        Returns:
            Dict[str, Any]: The server response
            
        Raises:
            ConnectionError: If unable to connect to the server
            RuntimeError: If the server returns an error
        """
        if params is None:
            params = {}
        
        request = {
            "action": action,
            "params": params
        }
        
        try:
            if self.use_unix_socket:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                if not os.path.exists(self.server_socket_path):
                    raise ConnectionError(f"Unix socket {self.server_socket_path} does not exist")
                sock.connect(self.server_socket_path)
            else:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((self.server_host, self.server_port))
            
            sock.settimeout(self.socket_timeout)
            
            # Send the request
            request_json = json.dumps(request).encode('utf-8')
            sock.sendall(request_json)
            
            # Signal end of request by shutting down the write side
            sock.shutdown(socket.SHUT_WR)
            
            # Receive the response
            response_data = b''
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response_data += chunk
            
            sock.close()
            
            # Parse the complete response
            try:
                response = json.loads(response_data.decode('utf-8'))
            except json.JSONDecodeError:
                raise RuntimeError("Received invalid JSON response from server")
            
            if not response.get("success", False):
                error_msg = response.get("error", "Unknown error")
                raise RuntimeError(f"Server error: {error_msg}")
            
            return response.get("data", {})
            
        except socket.timeout:
            raise RuntimeError("Server did not respond within the timeout period")
        except json.JSONDecodeError:
            raise RuntimeError("Received invalid JSON response from server")
        except (socket.error, ConnectionError) as e:
            raise ConnectionError(f"Failed to connect to server: {e}")
    
    def is_server_running(self) -> bool:
        """Check if the server is running and responding.
        
        Returns:
            bool: True if the server is running and responding, False otherwise
        """
        try:
            # Try to create a socket and connect to the server
            if self.use_unix_socket:
                if not os.path.exists(self.server_socket_path):
                    return False
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(self.server_socket_path)
            else:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((self.server_host, self.server_port))
            
            sock.close()
            return True
        except Exception:
            return False
    
    def submit_job(self, package_name: str, priority: str = "medium", 
                   dependencies: Optional[List[str]] = None,
                   estimated_time: float = 7200.0,
                   spack_command: Optional[str] = None) -> Dict[str, Any]:
        """Submit a job to the server.
        
        Args:
            package_name: Name of the package to install
            priority: Job priority (high, medium, low)
            dependencies: List of package dependencies
            estimated_time: Estimated time in seconds
            spack_command: Custom spack command
            
        Returns:
            Dict containing job information
        """
        params = {
            'package_name': package_name,
            'priority': priority,
            'dependencies': dependencies or [],
            'estimated_time': estimated_time
        }
        if spack_command:
            params['spack_command'] = spack_command
        
        return self._send_request("submit_job", params)
    
    def get_status(self) -> Dict[str, Any]:
        """Get queue status from the server.
        
        Returns:
            Dict containing queue status information
        """
        return self._send_request("get_status")
    
    def get_jobs(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get jobs from the server.
        
        Args:
            status_filter: Optional status filter (pending, running, completed, failed, cancelled)
            
        Returns:
            List of job dictionaries
        """
        params = {}
        if status_filter:
            params['status'] = status_filter
        
        response = self._send_request("get_jobs", params)
        return response.get('jobs', [])
    
    def cancel_job(self, job_id: int) -> bool:
        """Cancel a job.
        
        Args:
            job_id: ID of the job to cancel
            
        Returns:
            bool: True if successfully cancelled
        """
        params = {'job_id': job_id}
        response = self._send_request("cancel_job", params)
        return response.get('cancelled', False)
    
    def get_job_logs(self, job_id: int) -> List[Dict[str, Any]]:
        """Get logs for a job.
        
        Args:
            job_id: ID of the job
            
        Returns:
            List of log entries
        """
        params = {'job_id': job_id}
        response = self._send_request("get_job_logs", params)
        return response.get('logs', [])
