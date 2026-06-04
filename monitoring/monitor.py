"""
Monitor Manager - Orchestrates metrics collection and statistical analysis
Updates database with real-time μ and σ using Welford's algorithm
"""
import logging
import threading
import time
from monitoring.collector import MetricsCollector
from monitoring.stats import OnlineStats

logger = logging.getLogger(__name__)


class MonitorManager:
    """
    Main monitoring orchestrator
    - Collects metrics every interval
    - Updates Welford statistics
    - Persists to database
    """
    
    def __init__(self, db, remote_executor, interval=5):
        self.db = db
        self.executor = remote_executor
        self.collector = MetricsCollector(remote_executor)
        self.interval = interval  # seconds between collections
        
        # In-memory stats objects: {vm_id: {'cpu': OnlineStats, 'memory': OnlineStats}}
        self.vm_stats = {}
        
        # Worker stats: {worker_ip: {'cpu': OnlineStats, 'memory': OnlineStats}}
        self.worker_stats = {}
        
        # Control
        self.running = False
        self.thread = None
        
        # Load existing stats from database
        self._load_stats_from_db()
    
    def _load_stats_from_db(self):
        """Load existing Welford stats from database"""
        try:
            vm_metrics = self.db.data.get('vm_metrics', {})
            for vm_id, metrics in vm_metrics.items():
                if 'stats' in metrics:
                    self.vm_stats[vm_id] = {
                        'cpu': OnlineStats.from_dict(metrics['stats'].get('cpu', {})),
                        'memory': OnlineStats.from_dict(metrics['stats'].get('memory', {})),
                        'disk_read': OnlineStats.from_dict(metrics['stats'].get('disk_read', {})),
                        'disk_write': OnlineStats.from_dict(metrics['stats'].get('disk_write', {}))
                    }
            
            worker_metrics = self.db.data.get('worker_metrics', {})
            for worker_ip, metrics in worker_metrics.items():
                if 'stats' in metrics:
                    self.worker_stats[worker_ip] = {
                        'cpu': OnlineStats.from_dict(metrics['stats'].get('cpu', {})),
                        'memory': OnlineStats.from_dict(metrics['stats'].get('memory', {}))
                    }
            
            logger.info(f"Loaded stats for {len(self.vm_stats)} VMs and {len(self.worker_stats)} workers")
            
        except Exception as e:
            logger.error(f"Error loading stats from DB: {e}")
    
    def start(self):
        """Start monitoring thread"""
        if self.running:
            logger.warning("Monitor already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.thread.start()
        logger.info(f"Monitor started (interval: {self.interval}s)")
    
    def stop(self):
        """Stop monitoring thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        logger.info("Monitor stopped")
    
    def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                # Collect VM metrics
                self._collect_all_vm_metrics()
                
                # Collect worker metrics
                self._collect_all_worker_metrics()
                
                # Persist to database
                self._persist_metrics()
                
                time.sleep(self.interval)
                
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                time.sleep(self.interval)
    
    def _collect_all_vm_metrics(self):
        """Collect metrics for all running VMs"""
        try:
            # Get all VMs from database
            slices = self.db.data.get('slices', {})
            
            for slice_id, slice_data in slices.items():
                for vm in slice_data.get('vms', []):
                    vm_id = vm.get('vm_id')
                    pid = vm.get('pid')
                    worker_ip = vm.get('worker_ip')
                    qcow_path = vm.get('qcow_image')
                    
                    # Only collect if VM is deployed
                    if vm.get('status') != 'deployed' or not pid:
                        continue
                    
                    # Collect metrics
                    metrics = self.collector.collect_vm_metrics(worker_ip, pid)
                    
                    if not metrics:
                        continue
                    
                    # Get QCOW2 size
                    if qcow_path:
                        metrics['qcow_size_mb'] = self.collector.get_qcow2_size(worker_ip, qcow_path)
                    else:
                        metrics['qcow_size_mb'] = 0.0
                    
                    # Update Welford statistics
                    self._update_vm_stats(vm_id, metrics)
                    
        except Exception as e:
            logger.error(f"Error collecting VM metrics: {e}")
    
    def _update_vm_stats(self, vm_id, metrics):
        """Update Welford stats for a VM"""
        if vm_id not in self.vm_stats:
            self.vm_stats[vm_id] = {
                'cpu': OnlineStats(),
                'memory': OnlineStats(),
                'disk_read': OnlineStats(),
                'disk_write': OnlineStats()
            }
        
        # Update with new measurements
        self.vm_stats[vm_id]['cpu'].update(metrics.get('cpu_percent', 0.0))
        self.vm_stats[vm_id]['memory'].update(metrics.get('memory_mb', 0.0))
        self.vm_stats[vm_id]['disk_read'].update(metrics.get('disk_read_mb', 0.0))
        self.vm_stats[vm_id]['disk_write'].update(metrics.get('disk_write_mb', 0.0))
    
    def _collect_all_worker_metrics(self):
        """Collect metrics for all workers"""
        try:
            workers = self.db.data.get('workers_list', [])
            
            for worker_ip in workers:
                metrics = self.collector.collect_worker_metrics(worker_ip)
                
                if not metrics:
                    continue
                
                # Update worker stats
                self._update_worker_stats(worker_ip, metrics)
                
        except Exception as e:
            logger.error(f"Error collecting worker metrics: {e}")
    
    def _update_worker_stats(self, worker_ip, metrics):
        """Update Welford stats for a worker"""
        if worker_ip not in self.worker_stats:
            self.worker_stats[worker_ip] = {
                'cpu': OnlineStats(),
                'memory': OnlineStats()
            }
        
        self.worker_stats[worker_ip]['cpu'].update(metrics.get('cpu_percent', 0.0))
        self.worker_stats[worker_ip]['memory'].update(metrics.get('memory_mb', 0.0))
    
    def _persist_metrics(self):
        """Save current metrics and stats to database"""
        try:
            # Prepare VM metrics for DB
            vm_metrics = {}
            for vm_id, stats_dict in self.vm_stats.items():
                vm_metrics[vm_id] = {
                    'current': {
                        'cpu_mean': stats_dict['cpu'].get_mean(),
                        'cpu_stddev': stats_dict['cpu'].get_stddev(),
                        'memory_mean': stats_dict['memory'].get_mean(),
                        'memory_stddev': stats_dict['memory'].get_stddev(),
                        'disk_read_mean': stats_dict['disk_read'].get_mean(),
                        'disk_write_mean': stats_dict['disk_write'].get_mean(),
                        'samples': stats_dict['cpu'].n
                    },
                    'stats': {
                        'cpu': stats_dict['cpu'].to_dict(),
                        'memory': stats_dict['memory'].to_dict(),
                        'disk_read': stats_dict['disk_read'].to_dict(),
                        'disk_write': stats_dict['disk_write'].to_dict()
                    }
                }
            
            # Prepare worker metrics for DB
            worker_metrics = {}
            for worker_ip, stats_dict in self.worker_stats.items():
                worker_metrics[worker_ip] = {
                    'current': {
                        'cpu_mean': stats_dict['cpu'].get_mean(),
                        'cpu_stddev': stats_dict['cpu'].get_stddev(),
                        'memory_mean': stats_dict['memory'].get_mean(),
                        'memory_stddev': stats_dict['memory'].get_stddev(),
                        'samples': stats_dict['cpu'].n
                    },
                    'stats': {
                        'cpu': stats_dict['cpu'].to_dict(),
                        'memory': stats_dict['memory'].to_dict()
                    }
                }
            
            # Update database
            self.db.data['vm_metrics'] = vm_metrics
            self.db.data['worker_metrics'] = worker_metrics
            self.db.save()
            
        except Exception as e:
            logger.error(f"Error persisting metrics: {e}")
    
    def get_vm_stats(self, vm_id):
        """Get current statistics for a VM"""
        if vm_id not in self.vm_stats:
            return None
        
        stats = self.vm_stats[vm_id]
        return {
            'cpu': stats['cpu'].get_stats(),
            'memory': stats['memory'].get_stats(),
            'disk_read': stats['disk_read'].get_stats(),
            'disk_write': stats['disk_write'].get_stats()
        }
    
    def get_worker_stats(self, worker_ip):
        """Get current statistics for a worker"""
        if worker_ip not in self.worker_stats:
            return None
        
        stats = self.worker_stats[worker_ip]
        return {
            'cpu': stats['cpu'].get_stats(),
            'memory': stats['memory'].get_stats()
        }
