import subprocess, logging
logger = logging.getLogger(__name__)
class RemoteExecutor:
    def __init__(self, remote_user="ubuntu"):
        self.remote_user = remote_user
    
    def execute(self, remote_ip, script_path, args=None, timeout=30):
        try:
            cmd = f"ssh {self.remote_user}@{remote_ip} 'bash -s"
            if args:
                cmd += " " + " ".join(f"'{arg}'" for arg in args)
            cmd += "' < " + script_path
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            if result.returncode != 0:
                logger.error(f"SSH Error: {result.stderr}")
                return False, result.stderr
            return True, result.stdout
        except Exception as e:
            logger.error(f"Execute error: {e}")
            return False, str(e)
    
    def execute_direct(self, remote_ip, command, timeout=30):
        try:
            cmd = f"ssh -o StrictHostKeyChecking=no {self.remote_user}@{remote_ip} '{command}'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            if result.returncode != 0:
                logger.error(f"SSH Error: {result.stderr}")
                return False, result.stderr
            return True, result.stdout
        except Exception as e:
            logger.error(f"Execute error: {e}")
            return False, str(e)
