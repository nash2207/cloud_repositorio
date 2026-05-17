import logging
from models import Slice

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
    
    def create_slice(self, username, slice_name, topology_type="linear"):
        user = self.db.get_user(username)
        if not user:
            return False, "User not found"
        
        try:
            slice_id = self.db.get_next_vm_id()
            vlan_ids = [self.db.get_next_vlan_id(), self.db.get_next_vlan_id()]
            slice_obj = Slice(slice_id, username, vlan_ids, topology_type)
            slice_obj.status = "active"
            
            self.db.add_slice(slice_obj.to_dict())
            
            if "slices" not in user:
                user["slices"] = []
            user["slices"].append(slice_id)
            self.db.update_user(username, user)
            
            logger.info(f"Slice {slice_id} created for {username}")
            return True, {"slice_id": slice_id, "name": slice_name}
        except Exception as e:
            logger.error(f"Slice creation error: {e}")
            return False, str(e)
    
    def add_vm_to_slice(self, username, slice_id, vm_name, base_image_path=None, internet_enabled=False):
        user = self.db.get_user(username)
        slice_data = self.db.get_slice(str(slice_id))
        
        if not user or not slice_data:
            return False, "User or Slice not found"
        
        if slice_data.get("owner") != username:
            return False, "Not authorized"
        
        if (user.get("used_vms", 0) + 1) > user.get("quota_vms", 10):
            return False, "Quota exceeded"
        
        try:
            vm_id = self.db.get_next_vm_id()
            worker_ip = self.get_next_worker()
            vlan_ids = slice_data.get("vlan_ids", [])
            
            success, vm = self.deployment_api.create_vm_with_qcow(
                slice_id, vm_id, vm_name, username, worker_ip, vlan_ids, 
                base_image_path=base_image_path,
                internet_enabled=internet_enabled
            )
            if not success:
                return False, "VM creation failed"
            
            if "vms" not in slice_data:
                slice_data["vms"] = []
            slice_data["vms"].append(vm.to_dict())
            self.db.update_slice(slice_id, slice_data)
            
            user["used_vms"] = user.get("used_vms", 0) + 1
            self.db.update_user(username, user)
            
            logger.info(f"VM {vm_id} added to slice {slice_id}")
            return True, vm.to_dict()
        except Exception as e:
            logger.error(f"VM creation error: {e}")
            return False, str(e)
    
    def delete_slice(self, username, slice_id):
        try:
            slice_data = self.db.get_slice(slice_id)
            if not slice_data or slice_data.get("owner") != username:
                return False, "Slice not found or not authorized"
            
            user = self.db.get_user(username)
            vm_count = len(slice_data.get("vms", []))
            
            for vm_dict in slice_data.get("vms", []):
                self.deployment_api.delete_vm_dict(vm_dict)
            
            self.db.delete_slice(slice_id)
            
            if "slices" in user and slice_id in user["slices"]:
                user["slices"].remove(slice_id)
            user["used_vms"] = max(0, user.get("used_vms", 0) - vm_count)
            self.db.update_user(username, user)
            
            logger.info(f"Slice {slice_id} deleted")
            return True, "Slice deleted"
        except Exception as e:
            logger.error(f"Delete error: {e}")
            return False, str(e)
