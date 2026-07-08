import logging, subprocess

logger = logging.getLogger(__name__)

class WorkerDiscovery:
    def __init__(self, remote_executor, workers=None):
        self.executor = remote_executor
        self.workers = workers or []  # Must be provided by caller
    
    def discover_all(self, db):
        for worker_ip in self.workers:
            specs = self.get_worker_specs(worker_ip)
            if specs:
                db.data["workers"] = db.data.get("workers", {})
                db.data["workers"][worker_ip] = specs
                db.save()
                logger.info(f"Worker {worker_ip}: {specs}")
    
    def get_worker_specs(self, worker_ip):
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
        try:
            result = subprocess.run(f"ssh -o ConnectTimeout=10 ubuntu@{worker_ip} nproc", 
                                  shell=True, capture_output=True, text=True, timeout=5)
            return int(result.stdout.strip()) if result.returncode == 0 else 2
        except: return 2
    
    def _get_ram(self, worker_ip):
        try:
            result = subprocess.run(f"ssh ubuntu@{worker_ip} 'free -g | grep Mem | awk \"{{print \\$2}}\"'", 
                                  shell=True, capture_output=True, text=True, timeout=5)
            return int(result.stdout.strip()) if result.returncode == 0 else 1
        except: return 1
    
    def _get_disk(self, worker_ip):
        try:
            result = subprocess.run(f"ssh ubuntu@{worker_ip} 'df /tmp -B G | tail -1 | awk \"{{print \\$2}}\" | tr -d G'", 
                                  shell=True, capture_output=True, text=True, timeout=5)
            return int(result.stdout.strip()) if result.returncode == 0 else 500
        except: return 500
