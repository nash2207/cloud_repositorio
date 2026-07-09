"""
Welford's Online Algorithm for Computing Mean and Variance
Computes μ (mean) and σ² (variance) in O(1) space without storing historical data

NOTE: This is a STATEFUL WRAPPER around pure mathematical functions
Pure functions are in: math_functions.welford_pure
"""
import logging
import threading
from math_functions.welford_pure import welford_update, welford_get_variance, welford_get_std_dev

logger = logging.getLogger(__name__)


class WelfordStats:
    """
    Online statistics tracker using Welford's algorithm
    
    This is a STATEFUL WRAPPER that:
    - Manages state (n, mean, M2)
    - Provides thread-safety
    - Delegates calculations to pure functions
    
    Pure mathematical logic is in: math_functions.welford_pure
    """
    
    def __init__(self, metric_name):
        self.metric_name = metric_name
        self.n = 0  # Number of samples
        self.mean = 0.0  # μ (mean)
        self.M2 = 0.0  # Sum of squared differences (for variance)
        self.lock = threading.Lock()
    
    def update(self, value):
        """
        Update statistics with a new sample
        
        Delegates to pure function: welford_update()
        
        Args:
            value: New sample value (CPU % or RAM MB)
        """
        with self.lock:
            self.n, self.mean, self.M2 = welford_update(self.n, self.mean, self.M2, value)
    
    def get_stats(self):
        """
        Get current statistics
        
        Delegates to pure functions: welford_get_variance(), welford_get_std_dev()
        
        Returns:
            dict: {
                'mean': μ (mean),
                'variance': σ² (variance),
                'std_dev': σ (standard deviation),
                'samples': n (number of samples)
            }
        """
        with self.lock:
            variance = welford_get_variance(self.n, self.M2)
            std_dev = welford_get_std_dev(self.n, self.M2)
            
            return {
                'mean': self.mean,
                'variance': variance,
                'std_dev': std_dev,
                'samples': self.n
            }
    
    def reset(self):
        """Reset statistics to initial state"""
        with self.lock:
            self.n = 0
            self.mean = 0.0
            self.M2 = 0.0
    
    def __repr__(self):
        stats = self.get_stats()
        return f"WelfordStats({self.metric_name}: μ={stats['mean']:.2f}, σ={stats['std_dev']:.2f}, n={stats['samples']})"


class VMMetrics:
    """
    Metrics tracker for a single VM
    Tracks CPU and RAM using Welford's algorithm
    """
    
    def __init__(self, vm_id, worker_ip, pid):
        self.vm_id = vm_id
        self.worker_ip = worker_ip
        self.pid = pid
        self.cpu_stats = WelfordStats(f"VM{vm_id}_CPU")
        self.ram_stats = WelfordStats(f"VM{vm_id}_RAM")
        self.last_update = None
    
    def update_cpu(self, cpu_percent):
        """Update CPU usage (percentage)"""
        self.cpu_stats.update(cpu_percent)
    
    def update_ram(self, ram_kb):
        """Update RAM usage (convert KB to MB)"""
        ram_mb = ram_kb / 1024.0
        self.ram_stats.update(ram_mb)
    
    def get_metrics(self):
        """
        Get all metrics for this VM
        
        Returns:
            dict: {
                'vm_id': VM ID,
                'worker_ip': Worker IP,
                'pid': Process ID,
                'cpu': {mean, std_dev, variance, samples},
                'ram': {mean, std_dev, variance, samples} (in MB)
            }
        """
        return {
            'vm_id': self.vm_id,
            'worker_ip': self.worker_ip,
            'pid': self.pid,
            'cpu': self.cpu_stats.get_stats(),
            'ram': self.ram_stats.get_stats()
        }
    
    def __repr__(self):
        return f"VMMetrics(VM{self.vm_id} on {self.worker_ip}, PID={self.pid})"


class WorkerMetrics:
    """
    Metrics tracker for a single worker node
    Stores capacity and current VMs
    """
    
    def __init__(self, worker_ip):
        self.worker_ip = worker_ip
        self.total_cores = 0
        self.total_ram_mb = 0
        self.total_disk_gb = 0
        self.vms = {}  # {pid: VMMetrics}
        self.lock = threading.Lock()
    
    def set_capacity(self, cores, ram_kb, disk_gb):
        """Set worker physical capacity"""
        with self.lock:
            self.total_cores = cores
            self.total_ram_mb = ram_kb / 1024.0
            self.total_disk_gb = disk_gb
            logger.info(
                f"Worker {self.worker_ip} capacity: {cores} cores, "
                f"{self.total_ram_mb:.0f} MB RAM, {disk_gb:.1f} GB disk"
            )
    
    def add_vm(self, vm_id, pid):
        """Add VM to worker tracking"""
        with self.lock:
            if pid not in self.vms:
                self.vms[pid] = VMMetrics(vm_id, self.worker_ip, pid)
                logger.debug(f"Added VM {vm_id} (PID {pid}) to worker {self.worker_ip}")
    
    def remove_vm(self, pid):
        """Remove VM from worker tracking"""
        with self.lock:
            if pid in self.vms:
                vm_id = self.vms[pid].vm_id
                del self.vms[pid]
                logger.debug(f"Removed VM {vm_id} (PID {pid}) from worker {self.worker_ip}")
    
    def get_vm(self, pid):
        """Get VM metrics by PID"""
        with self.lock:
            return self.vms.get(pid)
    
    def get_all_vms(self):
        """Get all VM metrics on this worker"""
        with self.lock:
            return {pid: vm.get_metrics() for pid, vm in self.vms.items()}
    
    def get_aggregated_stats(self):
        """
        Calculate aggregated resource usage using Welford statistics
        
        Uses pure function: welford_combine_variances()
        
        Returns:
            dict: {
                'worker_ip': Worker IP,
                'capacity': {cores, ram_mb, disk_gb},
                'usage': {
                    'cpu': {mean, std_dev},
                    'ram': {mean, std_dev},
                    'disk': {allocated_gb}
                },
                'vms_count': Number of VMs
            }
        """
        from math_functions.welford_pure import welford_combine_std_dev
        
        with self.lock:
            total_cpu_mean = sum(vm.cpu_stats.get_stats()['mean'] for vm in self.vms.values())
            total_ram_mean = sum(vm.ram_stats.get_stats()['mean'] for vm in self.vms.values())
            
            # Variance of sum = sum of variances (independent variables)
            # Use pure function for combining variances
            cpu_variances = [vm.cpu_stats.get_stats()['variance'] for vm in self.vms.values()]
            ram_variances = [vm.ram_stats.get_stats()['variance'] for vm in self.vms.values()]
            
            total_cpu_std = welford_combine_std_dev(cpu_variances)
            total_ram_std = welford_combine_std_dev(ram_variances)
            
            # Disk is deterministic (2.5 GB per VM)
            total_disk_allocated = len(self.vms) * 2.5
            
            return {
                'worker_ip': self.worker_ip,
                'capacity': {
                    'cores': self.total_cores,
                    'ram_mb': self.total_ram_mb,
                    'disk_gb': self.total_disk_gb
                },
                'usage': {
                    'cpu': {
                        'mean': total_cpu_mean,
                        'std_dev': total_cpu_std
                    },
                    'ram': {
                        'mean': total_ram_mean,
                        'std_dev': total_ram_std
                    },
                    'disk': {
                        'allocated_gb': total_disk_allocated
                    }
                },
                'vms_count': len(self.vms)
            }
    
    def __repr__(self):
        return f"WorkerMetrics({self.worker_ip}: {len(self.vms)} VMs, {self.total_cores} cores, {self.total_ram_mb:.0f} MB)"
