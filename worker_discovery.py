"""Worker Discovery - Auto-detect worker specs via SSH"""
import logging
from remote_executor import RemoteExecutor

logger = logging.getLogger(__name__)

class WorkerDiscovery:
    def __init__(self, remote_executor):
        self.executor = remote_executor
        self.workers = ["10.0.0.1", "10.0.0.2", "10.0.0.3"]
    
    def discover_all(self, db):
        """Discover specs for all workers and update DB"""
        for worker_ip in self.workers:
            specs = self.get_worker_specs(worker_ip)
            if specs:
                db.data["workers"] = db.data.get("workers", {})
                db.data["workers"][worker_ip] = specs
                db.save()
                logger.info(f"Worker {worker_ip} discovered: {specs}")
    
    def get_worker_specs(self, worker_ip):
        """Get RAM, cores, disk via SSH"""
        try:
            specs = {
                "ip": worker_ip,
                "max_vms": 10,
                "max_cores": self._get_cores(worker_ip),
                "max_ram_gb": self._get_ram(worker_ip),
                "max_disk_gb": self._get_disk(worker_ip),
                "used_cores": 0,
                "used_ram_gb": 0,
                "used_disk_gb": 0
            }
            return specs
        except Exception as e:
            logger.error(f"Discovery error for {worker_ip}: {e}")
            return None
    
    def _get_cores(self, worker_ip):
        success, output = self.executor.execute(worker_ip, "", args=["nproc"])
        return int(output.strip()) if success else 16
    
    def _get_ram(self, worker_ip):
        success, output = self.executor.execute(worker_ip, "", args=["free -g | grep Mem | awk '{print $2}'"])
        return int(output.strip()) if success else 32
    
    def _get_disk(self, worker_ip):
        success, output = self.executor.execute(worker_ip, "", args=["df /tmp -B G | tail -1 | awk '{print $2}'"])
        return int(output.strip().replace('G', '')) if success else 500
