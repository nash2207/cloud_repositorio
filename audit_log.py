"""
Audit Log System
Tracks all administrative and user actions in the system
"""
import logging
import time
from datetime import datetime
from collections import deque
from threading import Lock

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Centralized audit logging system
    
    Tracks:
    - User creation/deletion
    - Slice lifecycle (create, deploy, delete, edit)
    - VM operations (create, deploy, reboot, delete)
    - Network operations (create, delete)
    - Administrative actions
    """
    
    def __init__(self, max_logs=1000):
        """
        Initialize audit logger
        
        Args:
            max_logs: Maximum number of logs to keep in memory
        """
        self.logs = deque(maxlen=max_logs)
        self.lock = Lock()
    
    def log_event(self, event_type, username, action, details=None, level="INFO"):
        """
        Log an audit event
        
        Args:
            event_type: Event category (USER, SLICE, VM, NETWORK, ADMIN)
            username: User who performed the action
            action: Action description
            details: Additional details (optional)
            level: Log level (INFO, WARNING, ERROR)
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        log_entry = {
            "timestamp": timestamp,
            "epoch": time.time(),
            "event_type": event_type,
            "username": username,
            "action": action,
            "details": details or {},
            "level": level
        }
        
        with self.lock:
            self.logs.append(log_entry)
        
        # Also log to Python logger
        log_msg = f"[AUDIT] {event_type} | {username} | {action}"
        if details:
            log_msg += f" | {details}"
        
        if level == "ERROR":
            logger.error(log_msg)
        elif level == "WARNING":
            logger.warning(log_msg)
        else:
            logger.info(log_msg)
    
    def get_logs(self, limit=100, event_type=None, username=None):
        """
        Retrieve audit logs with optional filtering
        
        Args:
            limit: Maximum number of logs to return
            event_type: Filter by event type (optional)
            username: Filter by username (optional)
        
        Returns:
            list: List of log entries (newest first)
        """
        with self.lock:
            # Convert to list and reverse (newest first)
            logs_list = list(self.logs)
            logs_list.reverse()
            
            # Apply filters
            if event_type:
                logs_list = [log for log in logs_list if log["event_type"] == event_type]
            
            if username:
                logs_list = [log for log in logs_list if log["username"] == username]
            
            # Apply limit
            return logs_list[:limit]
    
    def get_logs_summary(self):
        """
        Get summary statistics of audit logs
        
        Returns:
            dict: Summary statistics
        """
        with self.lock:
            logs_list = list(self.logs)
        
        event_counts = {}
        user_actions = {}
        
        for log in logs_list:
            # Count by event type
            event_type = log["event_type"]
            event_counts[event_type] = event_counts.get(event_type, 0) + 1
            
            # Count by user
            username = log["username"]
            user_actions[username] = user_actions.get(username, 0) + 1
        
        return {
            "total_logs": len(logs_list),
            "event_counts": event_counts,
            "user_actions": user_actions
        }


# Global audit logger instance
audit_logger = AuditLogger(max_logs=1000)


# Convenience functions
def log_user_action(username, action, details=None):
    """Log user-related action"""
    audit_logger.log_event("USER", username, action, details)


def log_slice_action(username, action, slice_id=None, details=None):
    """Log slice-related action"""
    if slice_id:
        details = details or {}
        details["slice_id"] = slice_id
    audit_logger.log_event("SLICE", username, action, details)


def log_vm_action(username, action, vm_id=None, details=None):
    """Log VM-related action"""
    if vm_id:
        details = details or {}
        details["vm_id"] = vm_id
    audit_logger.log_event("VM", username, action, details)


def log_network_action(username, action, details=None):
    """Log network-related action"""
    audit_logger.log_event("NETWORK", username, action, details)


def log_admin_action(username, action, details=None, level="INFO"):
    """Log administrative action"""
    audit_logger.log_event("ADMIN", username, action, details, level)
