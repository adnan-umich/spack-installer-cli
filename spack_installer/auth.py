"""Authentication utilities for spack-installer.

This module provides functions to validate user authorization based on
Unix group membership and file access permissions.
"""

import os
import grp
import pwd
import sys
from typing import List, Optional
from pathlib import Path
from colorama import Fore, Style

from .config import config

# The required Unix group for authorization
REQUIRED_GROUP = "swinstaller"


def get_current_user() -> str:
    """Get the username of the current user.
    
    Returns:
        The current username
    """
    return pwd.getpwuid(os.getuid()).pw_name


def get_user_groups(username: Optional[str] = None) -> List[str]:
    """Get all groups a user belongs to.
    
    Args:
        username: The username to check (defaults to current user)
        
    Returns:
        List of group names the user belongs to
    """
    if username is None:
        username = get_current_user()
    
    # Get the user's primary group
    user_info = pwd.getpwnam(username)
    primary_gid = user_info.pw_gid
    primary_group = grp.getgrgid(primary_gid).gr_name
    
    # Get all groups the user belongs to
    groups = [primary_group]
    for group in grp.getgrall():
        if username in group.gr_mem and group.gr_name not in groups:
            groups.append(group.gr_name)
    
    return groups


def user_in_group(group_name: str, username: Optional[str] = None) -> bool:
    """Check if a user belongs to the specified Unix group.
    
    Args:
        group_name: The name of the group to check
        username: The username to check (defaults to current user)
        
    Returns:
        True if the user is in the group, False otherwise
    """
    try:
        return group_name in get_user_groups(username)
    except (KeyError, ValueError):
        return False


def user_has_db_access(username: Optional[str] = None) -> bool:
    """Check if the user has read/write access to the database.
    
    Args:
        username: The username to check (defaults to current user)
        
    Returns:
        True if the user has read/write access, False otherwise
    """
    db_path = Path(config.get_multi_user_database_path())
    
    # Check if the database file exists
    if not db_path.exists():
        # Check if the parent directory exists and is writable
        parent_dir = db_path.parent
        if not parent_dir.exists():
            return False
        return os.access(parent_dir, os.W_OK)
    
    # If the database file exists, check if it's readable and writable
    return os.access(db_path, os.R_OK | os.W_OK)


def authenticate_user() -> bool:
    """Authenticate the current user.
    
    Checks that the user is a member of the required group and has
    access to the database.
    
    Returns:
        True if the user is authenticated, False otherwise
    """
    username = get_current_user()
    
    # Check group membership
    if not user_in_group(REQUIRED_GROUP, username):
        print(f"{Fore.RED}Error:{Style.RESET_ALL} User '{username}' is not a member of the required group '{REQUIRED_GROUP}'")
        print(f"Please contact your system administrator to be added to the '{REQUIRED_GROUP}' group.")
        return False
    
    # Check database access
    if not user_has_db_access(username):
        db_path = config.get_multi_user_database_path()
        print(f"{Fore.RED}Error:{Style.RESET_ALL} User '{username}' does not have read/write access to the database:")
        print(f"  {db_path}")
        print("Please contact your system administrator to fix permissions.")
        return False
    
    return True
