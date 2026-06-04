"""Remote Executor - SSH command execution with improved error handling"""
import subprocess
import logging

logger = logging.getLogger(__name__)


class RemoteExecutor:
    """Execute commands on remote workers via SSH"""
    
    def __init__(self, remote_user="ubuntu"):
        self.remote_user = remote_user
    
    def execute(self, remote_ip, script_path, args=None, timeout=30):
        """Execute a script on remote host"""
        try:
            cmd = f"ssh {self.remote_user}@{remote_ip} 'bash -s"
            if args:
                cmd += " " + " ".join(f"'{arg}'" for arg in args)
            cmd += "' < " + script_path
            
            result = subprocess.run(
                cmd, shell=True, capture_output=True, 
                text=True, timeout=timeout
            )
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown SSH error"
                logger.error(f"SSH Error on {remote_ip}: {error_msg}")
                return False, error_msg
            
            return True, result.stdout
            
        except subprocess.TimeoutExpired:
            logger.error(f"SSH timeout on {remote_ip} after {timeout}s")
            return False, f"Timeout after {timeout}s"
        except Exception as e:
            logger.error(f"Execute error on {remote_ip}: {e}")
            return False, str(e)
    
    def execute_direct(self, remote_ip, command, timeout=30):
        """Execute a command directly on remote host"""
        try:
            # Add BatchMode to avoid password prompts
            ssh_cmd = f"ssh -o StrictHostKeyChecking=no -o BatchMode=yes {self.remote_user}@{remote_ip}"
            full_cmd = f"{ssh_cmd} '{command}'"
            
            result = subprocess.run(
                full_cmd, shell=True, capture_output=True, 
                text=True, timeout=timeout
            )
            
            if result.returncode != 0:
                # Sometimes stderr is empty but stdout has the error
                error_msg = result.stderr.strip() or result.stdout.strip() or f"Command failed with code {result.returncode}"
                logger.error(f"SSH Error on {remote_ip}: {error_msg}")
                logger.debug(f"Failed command: {command[:100]}...")
                return False, error_msg
            
            return True, result.stdout
            
        except subprocess.TimeoutExpired:
            logger.error(f"SSH timeout on {remote_ip} after {timeout}s")
            logger.debug(f"Timed out command: {command[:100]}...")
            return False, f"Timeout after {timeout}s"
        except Exception as e:
            logger.error(f"Execute error on {remote_ip}: {e}")
            logger.debug(f"Exception on command: {command[:100]}...")
            return False, str(e)
