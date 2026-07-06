"""
Metrics Collector - Extract resource usage from QEMU VMs via SSH
Uses Welford's algorithm for real-time statistical analysis
"""
import logging
import re

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Collect CPU, RAM, and Disk metrics from worker nodes
    Discovers VMs dynamically by scanning QEMU processes
    """
    
    def __init__(self, remote_executor):
        self.executor = remote_executor
    
    def discover_vms_on_worker(self, worker_ip):
        """
        Discover all running QEMU VMs on a worker
        Command: ps -eo pid,cmd | grep qemu-system | awk '{print $1, $NF}'
        
        Returns:
            list: [{'pid': '12345', 'is_daemon': True}, ...]
        """
        try:
            # Get all QEMU processes
            cmd = "ps -eo pid,cmd | grep qemu-system | grep -v grep"
            success, output = self.executor.execute_direct(worker_ip, cmd, timeout=10)
            
            if not success or not output.strip():
                logger.debug(f"No QEMU VMs found on {worker_ip}")
                return []
            
            vms = []
            for line in output.strip().split('\n'):
                # Parse: "132387 /usr/bin/qemu-system-x86_64 ... -daemonize"
                parts = line.split()
                if len(parts) >= 2:
                    pid = parts[0]
                    # Check if it's a daemonized VM (not just qemu-system command)
                    if '-daemonize' in line or 'qemu-system-x86_64' in line:
                        vms.append({
                            'pid': pid,
                            'is_daemon': '-daemonize' in line
                        })
            
            logger.debug(f"Discovered {len(vms)} VMs on {worker_ip}: {[vm['pid'] for vm in vms]}")
            return vms
            
        except Exception as e:
            logger.error(f"Error discovering VMs on {worker_ip}: {e}")
            return []
    
    def get_vm_cpu_usage(self, worker_ip, pid):
        """
        Get CPU usage for a VM process
        Command: ps -p <pid> -o %cpu=
        
        Returns:
            float: CPU percentage (e.g., 0.5 for 0.5%)
        """
        try:
            cmd = f"ps -p {pid} -o %cpu= 2>/dev/null"
            success, output = self.executor.execute_direct(worker_ip, cmd, timeout=5)
            
            if not success or not output.strip():
                return 0.0
            
            cpu_percent = float(output.strip())
            return cpu_percent
            
        except Exception as e:
            logger.debug(f"Error getting CPU for PID {pid} on {worker_ip}: {e}")
            return 0.0
    
    def get_vm_ram_usage(self, worker_ip, pid):
        """
        Get RAM usage for a VM process
        Command: ps -p <pid> -o rss=
        
        Returns:
            int: RAM usage in KB
        """
        try:
            cmd = f"ps -p {pid} -o rss= 2>/dev/null"
            success, output = self.executor.execute_direct(worker_ip, cmd, timeout=5)
            
            if not success or not output.strip():
                return 0
            
            ram_kb = int(output.strip())
            return ram_kb
            
        except Exception as e:
            logger.debug(f"Error getting RAM for PID {pid} on {worker_ip}: {e}")
            return 0
    
    def get_worker_capacity(self, worker_ip):
        """
        Get worker physical capacity
        Commands:
            - grep -c ^processor /proc/cpuinfo (CPU cores)
            - grep MemTotal /proc/meminfo (RAM in KB)
            - df -h / (Disk space)
        
        Returns:
            dict: {'cores': int, 'ram_kb': int, 'disk_gb': float}
        """
        try:
            # CPU cores
            cpu_cmd = "grep -c ^processor /proc/cpuinfo"
            success, cpu_output = self.executor.execute_direct(worker_ip, cpu_cmd, timeout=5)
            cores = int(cpu_output.strip()) if success and cpu_output.strip() else 0
            
            # RAM (KB) - Using awk with single quotes inside double quotes
            ram_cmd = """grep MemTotal /proc/meminfo | awk '{print $2}'"""
            success, ram_output = self.executor.execute_direct(worker_ip, ram_cmd, timeout=5)
            ram_kb = int(ram_output.strip()) if success and ram_output.strip() else 0
            
            # Disk space on / - Using awk with single quotes inside double quotes
            disk_cmd = """df / | tail -1 | awk '{print $2}'"""
            success, disk_output = self.executor.execute_direct(worker_ip, disk_cmd, timeout=5)
            
            # Parse disk size (e.g., "9.6G" -> 9.6)
            disk_gb = 0.0
            if success and disk_output.strip():
                disk_str = disk_output.strip()
                # Remove unit letter (G, M, T)
                if disk_str[-1].isalpha():
                    unit = disk_str[-1].upper()
                    size = float(disk_str[:-1])
                    if unit == 'G':
                        disk_gb = size
                    elif unit == 'M':
                        disk_gb = size / 1024.0
                    elif unit == 'T':
                        disk_gb = size * 1024.0
                else:
                    # Assume KB
                    disk_gb = float(disk_str) / (1024.0 * 1024.0)
            
            logger.debug(
                f"Worker {worker_ip} capacity: {cores} cores, "
                f"{ram_kb / 1024:.0f} MB RAM, {disk_gb:.1f} GB disk"
            )
            
            return {
                'cores': cores,
                'ram_kb': ram_kb,
                'disk_gb': disk_gb
            }
            
        except Exception as e:
            logger.error(f"Error getting capacity for {worker_ip}: {e}")
            return {
                'cores': 0,
                'ram_kb': 0,
                'disk_gb': 0.0
            }
