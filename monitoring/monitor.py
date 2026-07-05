"""
Real-time Monitoring System with Welford's Algorithm
Collects metrics every 1s (CPU/RAM) and discovers VMs every 5s
Updates database with μ and σ using Welford's online algorithm
"""
import logging
import threading
import time
from monitoring.collector import MetricsCollector
from monitoring.welford_stats import WorkerMetrics

logger = logging.getLogger(__name__)


class MonitoringSystem:
    """
    Real-time monitoring system for VM placement algorithm
    - Discovers VMs every 5 seconds
    - Collects CPU/RAM metrics every 1 second
    - Calculates μ and σ using Welford's algorithm
    """
    
    def __init__(self, database, remote_executor, clusters_config):
        self.db = database
        self.collector = MetricsCollector(remote_executor)
        self.clusters_config = clusters_config
        
        # Worker metrics storage: {worker_ip: WorkerMetrics}
        self.workers = {}
        
        # Control threads
        self.running = False
        self.discovery_thread = None
        self.metrics_thread = None
        
        # Timing control
        self.discovery_interval = 5  # seconds
        self.metrics_interval = 1  # seconds
        
        self.lock = threading.Lock()
        
        logger.info("Monitoring system initialized")
    
    def start(self):
        """Start monitoring threads"""
        if self.running:
            logger.warning("Monitoring system already running")
            return
        
        self.running = True
        
        # Initialize workers from clusters config
        self._initialize_workers()
        
        # Start discovery thread (every 5s)
        self.discovery_thread = threading.Thread(target=self._discovery_loop, daemon=True)
        self.discovery_thread.start()
        
        # Start metrics collection thread (every 1s)
        self.metrics_thread = threading.Thread(target=self._metrics_loop, daemon=True)
        self.metrics_thread.start()
        
        logger.info("Monitoring system started")
    
    def stop(self):
        """Stop monitoring threads"""
        self.running = False
        
        if self.discovery_thread:
            self.discovery_thread.join(timeout=10)
        
        if self.metrics_thread:
            self.metrics_thread.join(timeout=10)
        
        logger.info("Monitoring system stopped")
    
    def _initialize_workers(self):
        """Initialize worker tracking from clusters config"""
        with self.lock:
            for cluster_name, cluster_config in self.clusters_config.items():
                workers = cluster_config.get("workers", [])
                for worker_ip in workers:
                    if worker_ip not in self.workers:
                        self.workers[worker_ip] = WorkerMetrics(worker_ip)
                        logger.info(f"Initialized worker tracking: {worker_ip} ({cluster_name})")
    
    def _discovery_loop(self):
        """Discovery loop - runs every 5 seconds to map VMs to workers"""
        logger.info("VM discovery loop started (interval: 5s)")
        
        while self.running:
            try:
                self._discover_all_vms()
                time.sleep(self.discovery_interval)
            except Exception as e:
                logger.error(f"Error in discovery loop: {e}")
                time.sleep(self.discovery_interval)
    
    def _metrics_loop(self):
        """Metrics collection loop - runs every 1 second for CPU/RAM"""
        logger.info("Metrics collection loop started (interval: 1s)")
        
        while self.running:
            try:
                self._collect_all_metrics()
                time.sleep(self.metrics_interval)
            except Exception as e:
                logger.error(f"Error in metrics loop: {e}")
                time.sleep(self.metrics_interval)
    
    def _discover_all_vms(self):
        """Discover VMs on all workers and update tracking"""
        with self.lock:
            for worker_ip, worker_metrics in self.workers.items():
                try:
                    # Get worker capacity (once per discovery)
                    capacity = self.collector.get_worker_capacity(worker_ip)
                    worker_metrics.set_capacity(
                        capacity['cores'],
                        capacity['ram_kb'],
                        capacity['disk_gb']
                    )
                    
                    # Discover running VMs
                    vms = self.collector.discover_vms_on_worker(worker_ip)
                    
                    # Get current tracked PIDs
                    current_pids = set(worker_metrics.vms.keys())
                    discovered_pids = set(vm['pid'] for vm in vms if vm['is_daemon'])
                    
                    # Remove VMs that no longer exist
                    removed_pids = current_pids - discovered_pids
                    for pid in removed_pids:
                        worker_metrics.remove_vm(pid)
                    
                    # Add new VMs (map PID to VM ID from database)
                    new_pids = discovered_pids - current_pids
                    for pid in new_pids:
                        vm_id = self._map_pid_to_vm_id(worker_ip, pid)
                        if vm_id:
                            worker_metrics.add_vm(vm_id, pid)
                        else:
                            # Orphaned VM - track with PID as ID
                            worker_metrics.add_vm(f"orphan_{pid}", pid)
                            logger.warning(f"Orphaned VM found: PID {pid} on {worker_ip}")
                    
                except Exception as e:
                    logger.error(f"Error discovering VMs on {worker_ip}: {e}")
    
    def _collect_all_metrics(self):
        """Collect CPU/RAM metrics for all tracked VMs"""
        with self.lock:
            for worker_ip, worker_metrics in self.workers.items():
                for pid, vm_metrics in worker_metrics.vms.items():
                    try:
                        # Collect CPU usage
                        cpu_percent = self.collector.get_vm_cpu_usage(worker_ip, pid)
                        vm_metrics.update_cpu(cpu_percent)
                        
                        # Collect RAM usage
                        ram_kb = self.collector.get_vm_ram_usage(worker_ip, pid)
                        vm_metrics.update_ram(ram_kb)
                        
                    except Exception as e:
                        logger.debug(f"Error collecting metrics for PID {pid} on {worker_ip}: {e}")
    
    def _map_pid_to_vm_id(self, worker_ip, pid):
        """
        Map PID to VM ID using database
        Matches worker_ip and looks for VMs in deployed state
        
        Returns:
            int: VM ID or None if not found
        """
        try:
            # Get all slices from database
            all_slices = self.db.data.get("slices", {})
            
            for slice_id, slice_data in all_slices.items():
                if slice_data.get("status") != "deployed":
                    continue
                
                for vm in slice_data.get("vms", []):
                    if vm.get("worker_ip") == worker_ip and str(vm.get("pid")) == str(pid):
                        return vm.get("vm_id")
            
            return None
            
        except Exception as e:
            logger.error(f"Error mapping PID {pid} to VM ID: {e}")
            return None
    
    def get_worker_stats(self, worker_ip):
        """
        Get aggregated statistics for a worker
        
        Returns:
            dict: Worker capacity, usage (μ and σ), and VM count
        """
        with self.lock:
            worker = self.workers.get(worker_ip)
            if not worker:
                return None
            
            return worker.get_aggregated_stats()
    
    def get_all_workers_stats(self):
        """
        Get statistics for all workers
        
        Returns:
            list: [{worker_ip, capacity, usage, vms_count}, ...]
        """
        with self.lock:
            stats = []
            for worker_ip, worker in self.workers.items():
                stats.append(worker.get_aggregated_stats())
            return stats
    
    def get_vm_stats(self, vm_id):
        """
        Get statistics for a specific VM
        
        Returns:
            dict: {vm_id, worker_ip, pid, cpu: {mean, std_dev}, ram: {mean, std_dev}}
        """
        with self.lock:
            for worker in self.workers.values():
                for vm_metrics in worker.vms.values():
                    if vm_metrics.vm_id == vm_id:
                        return vm_metrics.get_metrics()
            return None
    
    def get_all_vms_stats(self):
        """
        Get statistics for all VMs
        
        Returns:
            list: [{vm_id, worker_ip, pid, cpu, ram}, ...]
        """
        with self.lock:
            all_vms = []
            for worker in self.workers.values():
                all_vms.extend(worker.get_all_vms().values())
            return all_vms
    
    def get_cluster_stats(self, availability_zone):
        """
        Get aggregated statistics for an entire cluster
        
        Args:
            availability_zone: "linux" or "openstack"
        
        Returns:
            dict: {
                'cluster': availability_zone,
                'total_capacity': {cores, ram_mb, disk_gb},
                'total_usage': {cpu: {mean, std_dev}, ram: {mean, std_dev}, disk_gb},
                'workers': [{worker_stats}, ...],
                'vms_count': total VMs
            }
        """
        cluster_config = self.clusters_config.get(availability_zone, {})
        cluster_workers = cluster_config.get("workers", [])
        
        with self.lock:
            total_cores = 0
            total_ram_mb = 0
            total_disk_gb = 0
            
            total_cpu_mean = 0
            total_cpu_variance = 0
            total_ram_mean = 0
            total_ram_variance = 0
            total_disk_allocated = 0
            
            workers_stats = []
            total_vms = 0
            
            for worker_ip in cluster_workers:
                worker = self.workers.get(worker_ip)
                if not worker:
                    continue
                
                worker_stats = worker.get_aggregated_stats()
                workers_stats.append(worker_stats)
                
                # Aggregate capacity
                total_cores += worker_stats['capacity']['cores']
                total_ram_mb += worker_stats['capacity']['ram_mb']
                total_disk_gb += worker_stats['capacity']['disk_gb']
                
                # Aggregate usage
                total_cpu_mean += worker_stats['usage']['cpu']['mean']
                total_cpu_variance += worker_stats['usage']['cpu']['std_dev'] ** 2
                total_ram_mean += worker_stats['usage']['ram']['mean']
                total_ram_variance += worker_stats['usage']['ram']['std_dev'] ** 2
                total_disk_allocated += worker_stats['usage']['disk']['allocated_gb']
                
                total_vms += worker_stats['vms_count']
            
            return {
                'cluster': availability_zone,
                'total_capacity': {
                    'cores': total_cores,
                    'ram_mb': total_ram_mb,
                    'disk_gb': total_disk_gb
                },
                'total_usage': {
                    'cpu': {
                        'mean': total_cpu_mean,
                        'std_dev': total_cpu_variance ** 0.5
                    },
                    'ram': {
                        'mean': total_ram_mean,
                        'std_dev': total_ram_variance ** 0.5
                    },
                    'disk': {
                        'allocated_gb': total_disk_allocated
                    }
                },
                'workers': workers_stats,
                'vms_count': total_vms
            }
