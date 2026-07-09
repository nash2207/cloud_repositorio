"""
Telemetry Adapter - I/O Layer for Infrastructure State
Fetches metrics and normalizes to standard dictionaries
Zero mathematical logic - pure data fetching and normalization
"""
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class TelemetryAdapter:
    """
    Adapter pattern for fetching infrastructure state
    
    Responsibilities:
    - Fetch worker capacities (CPU, RAM, Disk)
    - Fetch worker current usage (μ, σ from Welford stats)
    - Normalize to standard dictionaries
    
    Does NOT contain:
    - Mathematical calculations
    - Optimization logic
    - Decision making
    
    Output Format (standard dict):
        {
            'worker_ip': str,
            'capacity': {'cores': int, 'ram_mb': float, 'disk_gb': float},
            'usage': {
                'cpu': {'mean': float, 'std_dev': float},
                'ram': {'mean': float, 'std_dev': float},
                'disk': {'allocated_gb': float}
            },
            'vms_count': int
        }
    """
    
    def __init__(self, monitoring_system):
        """
        Initialize telemetry adapter
        
        Args:
            monitoring_system: MonitoringSystem instance (I/O source)
        """
        self.monitoring = monitoring_system
    
    def get_workers_state(self, worker_ips: List[str]) -> Dict[str, Dict]:
        """
        Fetch current state for all workers
        
        I/O Operation: Queries monitoring system
        
        Args:
            worker_ips: List of worker IP addresses
        
        Returns:
            Dict[worker_ip, state_dict]: State for each worker
        """
        workers_state = {}
        
        for worker_ip in worker_ips:
            state = self._get_worker_state(worker_ip)
            if state:
                workers_state[worker_ip] = state
        
        return workers_state
    
    def _get_worker_state(self, worker_ip: str) -> Optional[Dict]:
        """
        Fetch state for a single worker
        
        I/O Operation: Queries monitoring system
        
        Args:
            worker_ip: Worker IP address
        
        Returns:
            Dict or None: Worker state (normalized format)
        """
        stats = self.monitoring.get_worker_stats(worker_ip)
        
        if stats:
            return stats
        else:
            # Worker not yet initialized - use default values
            logger.warning(f"Worker {worker_ip} not in monitoring, using defaults")
            return {
                'worker_ip': worker_ip,
                'capacity': {
                    'cores': 4,
                    'ram_mb': 8000,
                    'disk_gb': 10
                },
                'usage': {
                    'cpu': {'mean': 0, 'std_dev': 0},
                    'ram': {'mean': 0, 'std_dev': 0},
                    'disk': {'allocated_gb': 0}
                },
                'vms_count': 0
            }
    
    def get_vm_flavor_resources(self, flavor: str) -> Dict[str, float]:
        """
        Get resource requirements for a VM flavor
        
        Pure data lookup (no I/O, but separated for clarity)
        
        Args:
            flavor: Flavor name (e.g., "ubuntu")
        
        Returns:
            Dict: {'cores': float, 'ram_mb': float, 'disk_gb': float}
        """
        # Flavor specifications (from models.py)
        flavors = {
            'ubuntu': {
                'cores': 1,
                'ram_mb': 512,  # 0.5 GB
                'disk_gb': 2.5
            }
        }
        
        return flavors.get(flavor, flavors['ubuntu'])
    
    def get_vm_default_usage_stats(self, flavor: str) -> Dict[str, Dict]:
        """
        Get default usage statistics for new VMs (before actual metrics)
        
        Pure data lookup - assumptions for GA placement
        
        Args:
            flavor: Flavor name
        
        Returns:
            Dict: {
                'cpu': {'mean': float, 'std_dev': float},
                'ram': {'mean': float, 'std_dev': float}
            }
        
        Assumptions:
            - Ubuntu VM uses ~50% CPU on average, σ=15%
            - Ubuntu VM uses ~256 MB RAM on average, σ=64 MB
        """
        # Default usage patterns (statistical assumptions)
        defaults = {
            'ubuntu': {
                'cpu': {
                    'mean': 0.5,  # 50% of 1 vCPU
                    'std_dev': 0.15  # 15% variation
                },
                'ram': {
                    'mean': 256,  # 256 MB average
                    'std_dev': 64  # 64 MB variation
                }
            }
        }
        
        return defaults.get(flavor, defaults['ubuntu'])
