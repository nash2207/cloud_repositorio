import logging
from database import Database

logger = logging.getLogger(__name__)

class OrchestratorAPI:
    def __init__(self, db, deployment_api):
        self.db = db
        self.deployment_api = deployment_api
        self.round_robin_idx = 0
        self.workers = db.data.get("workers_list", ["10.0.10.1", "10.0.10.2", "10.0.10.3"])
    
    def get_next_worker(self):
        worker = self.workers[self.round_robin_idx % len(self.workers)]
        self.round_robin_idx += 1
        return worker
    
    def create_vm(self, username, vm_name, vlan_ids, base_image_path=None):
        user = self.db.get_user(username)
        if not user or (user.get("used_vms", 0) + 1) > user.get("quota_vms", 10):
            return False, "Quota exceeded"
        
        try:
            vm_id = self.db.get_next_vm_id()
            worker_ip = self.get_next_worker()
            success, vm = self.deployment_api.create_vm_with_qcow(
                vm_id, vm_name, username, worker_ip, vlan_ids, base_image_path
            )
            if not success:
                return False, "VM creation failed"
            user["used_vms"] = user.get("used_vms", 0) + 1
            self.db.update_user(username, user)
            return True, vm.to_dict()
        except Exception as e:
            logger.error(f"Error: {e}")
            return False, str(e)
    
    def delete_vm(self, username, vm_id):
        try:
            user = self.db.get_user(username)
            user["used_vms"] = max(0, user.get("used_vms", 0) - 1)
            self.db.update_user(username, user)
            return True, "VM deleted"
        except Exception as e:
            return False, str(e)
