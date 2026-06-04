"""
Metrics Collector - Reads metrics from cgroups v1 and /proc
Supports QEMU VMs running in system.slice/qemu-kvm.service
"""
import logging
import os
import re

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects VM and worker metrics from cgroups and /proc"""
    
    def __init__(self, remote_executor):
        self.executor = remote_executor
        # cgroups v1 paths
        self.cpu_path = "/sys/fs/cgroup/cpu,cpuacct/system.slice/qemu-kvm.service"
        self.memory_path = "/sys/fs/cgroup/memory/system.slice/qemu-kvm.service"
        self.blkio_path = "/sys/fs/cgroup/blkio/system.slice/qemu-kvm.service"
    
    def collect_vm_metrics(self, worker_ip, vm_pid):
        """
        Collect metrics for a specific VM by PID
        
        Args:
            worker_ip: Worker node IP
            vm_pid: QEMU process PID
            
        Returns:
            dict with cpu_percent, memory_mb, disk_iops, disk_throughput
        """
        try:
            metrics = {}
            
            # CPU usage from /proc/[pid]/stat
            cpu_percent = self._get_cpu_usage(worker_ip, vm_pid)
            metrics['cpu_percent'] = cpu_percent
            
            # Memory usage from /proc/[pid]/status
            memory_mb = self._get_memory_usage(worker_ip, vm_pid)
            metrics['memory_mb'] = memory_mb
            
            # Disk stats from /proc/[pid]/io
            disk_stats = self._get_disk_stats(worker_ip, vm_pid)
            metrics.update(disk_stats)
            
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to collect metrics for VM PID {vm_pid} on {worker_ip}: {e}")
            return {}
    
    def _get_cpu_usage(self, worker_ip, pid):
        """
        Calculate CPU usage percentage from /proc/[pid]/stat
        
        Formula:
            cpu_percent = (utime + stime) / uptime * 100
        """
        try:
            # Read /proc/[pid]/stat
            cmd = f"cat /proc/{pid}/stat"
            success, output = self.executor.execute_direct(worker_ip, cmd, timeout=5)
            
            if not success or not output:
                return 0.0
            
            parts = output.split()
            utime = int(parts[13])  # User mode jiffies
            stime = int(parts[14])  # Kernel mode jiffies
            
            # Read system uptime
            cmd_uptime = "cat /proc/uptime"
            success_up, uptime_out = self.executor.execute_direct(worker_ip, cmd_uptime, timeout=5)
            
            if not success_up:
                return 0.0
            
            uptime_seconds = float(uptime_out.split()[0])
            
            # Calculate CPU percentage (approximation)
            # Note: This gives cumulative usage, not instantaneous
            # For real-time %, need to sample twice with time delta
            total_time = utime + stime
            hz = 100  # Typical USER_HZ value
            seconds = total_time / hz
            
            if uptime_seconds > 0:
                cpu_percent = (seconds / uptime_seconds) * 100
                return min(cpu_percent, 100.0)  # Cap at 100%
            
            return 0.0
            
        except Exception as e:
            logger.debug(f"CPU collection error for PID {pid}: {e}")
            return 0.0
    
    def _get_memory_usage(self, worker_ip, pid):
        """
        Get memory usage in MB from /proc/[pid]/status
        
        Reads VmRSS (Resident Set Size)
        """
        try:
            cmd = f"grep VmRSS /proc/{pid}/status"
            success, output = self.executor.execute_direct(worker_ip, cmd, timeout=5)
            
            if not success or not output:
                return 0.0
            
            # Output format: "VmRSS:     123456 kB"
            match = re.search(r'(\d+)\s+kB', output)
            if match:
                kb = int(match.group(1))
                return kb / 1024.0  # Convert to MB
            
            return 0.0
            
        except Exception as e:
            logger.debug(f"Memory collection error for PID {pid}: {e}")
            return 0.0
    
    def _get_disk_stats(self, worker_ip, pid):
        """
        Get disk I/O stats from /proc/[pid]/io
        
        Returns:
            dict with disk_read_mb, disk_write_mb
        """
        try:
            cmd = f"cat /proc/{pid}/io"
            success, output = self.executor.execute_direct(worker_ip, cmd, timeout=5)
            
            if not success or not output:
                return {'disk_read_mb': 0.0, 'disk_write_mb': 0.0}
            
            stats = {}
            for line in output.split('\n'):
                if 'read_bytes' in line:
                    bytes_read = int(line.split(':')[1].strip())
                    stats['disk_read_mb'] = bytes_read / (1024 * 1024)
                elif 'write_bytes' in line:
                    bytes_write = int(line.split(':')[1].strip())
                    stats['disk_write_mb'] = bytes_write / (1024 * 1024)
            
            return stats
            
        except Exception as e:
            logger.debug(f"Disk stats collection error for PID {pid}: {e}")
            return {'disk_read_mb': 0.0, 'disk_write_mb': 0.0}
    
    def get_qcow2_size(self, worker_ip, qcow_path):
        """
        Get actual disk usage of QCOW2 file
        
        Args:
            worker_ip: Worker IP
            qcow_path: Path to QCOW2 file
            
        Returns:
            float: Size in MB
        """
        try:
            cmd = f"du -m {qcow_path} | awk '{{print $1}}'"
            success, output = self.executor.execute_direct(worker_ip, cmd, timeout=5)
            
            if success and output.strip():
                return float(output.strip())
            
            return 0.0
            
        except Exception as e:
            logger.debug(f"QCOW2 size collection error: {e}")
            return 0.0
    
    def collect_worker_metrics(self, worker_ip):
        """
        Collect overall worker node metrics
        
        Returns:
            dict with cpu_percent, memory_mb, disk_used_gb
        """
        try:
            metrics = {}
            
            # CPU usage: average from /proc/stat
            cmd_cpu = "grep 'cpu ' /proc/stat"
            success, output = self.executor.execute_direct(worker_ip, cmd_cpu, timeout=5)
            
            if success and output:
                parts = output.split()
                user = int(parts[1])
                nice = int(parts[2])
                system = int(parts[3])
                idle = int(parts[4])
                total = user + nice + system + idle
                busy = total - idle
                metrics['cpu_percent'] = (busy / total) * 100 if total > 0 else 0.0
            else:
                metrics['cpu_percent'] = 0.0
            
            # Memory: from /proc/meminfo
            cmd_mem = "grep -E 'MemTotal|MemAvailable' /proc/meminfo"
            success_mem, mem_output = self.executor.execute_direct(worker_ip, cmd_mem, timeout=5)
            
            if success_mem and mem_output:
                mem_total = 0
                mem_available = 0
                for line in mem_output.split('\n'):
                    if 'MemTotal' in line:
                        mem_total = int(re.search(r'(\d+)', line).group(1))
                    elif 'MemAvailable' in line:
                        mem_available = int(re.search(r'(\d+)', line).group(1))
                
                mem_used_kb = mem_total - mem_available
                metrics['memory_mb'] = mem_used_kb / 1024.0
                metrics['memory_total_mb'] = mem_total / 1024.0
            else:
                metrics['memory_mb'] = 0.0
                metrics['memory_total_mb'] = 0.0
            
            # Disk usage of home directory
            cmd_disk = "df -BG /home/ubuntu/vm_images | tail -1 | awk '{print $3}'"
            success_disk, disk_output = self.executor.execute_direct(worker_ip, cmd_disk, timeout=5)
            
            if success_disk and disk_output:
                disk_str = disk_output.strip().replace('G', '')
                metrics['disk_used_gb'] = float(disk_str) if disk_str else 0.0
            else:
                metrics['disk_used_gb'] = 0.0
            
            return metrics
            
        except Exception as e:
            logger.error(f"Worker metrics collection error for {worker_ip}: {e}")
            return {'cpu_percent': 0.0, 'memory_mb': 0.0, 'disk_used_gb': 0.0}
