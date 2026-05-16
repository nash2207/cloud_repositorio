"""Orchestrator API for R1C (Slice Manager) with concurrency"""
import logging, concurrent.futures
from models import Slice, Network
from database import Database
from vlan_manager import VLANManager
from routing_manager import RoutingManager
logger = logging.getLogger(__name__)

class OrchestratorAPI:
    def __init__(self, db, deployment_api, vlan_mgr, routing_mgr):
        self.db = db
        self.deployment_api = deployment_api
        self.vlan_mgr = vlan_mgr
        self.routing_mgr = routing_mgr
        self.round_robin_idx = 0
        self.workers = ["10.0.0.1", "10.0.0.2","10.0.0.3"]
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)
    
    def get_next_worker(self):
        worker = self.workers[self.round_robin_idx % len(self.workers)]
        self.round_robin_idx += 1
        return worker
    
    def create_slice_with_vlans(self, username, slice_name, num_vms, vlan_config, base_image_path=None):
        user = self.db.get_user(username)
        if not user or (user.get("used_vms", 0) + num_vms) > user.get("quota_vms", 10):
            return False, "Quota exceeded"
        
        slice_id = self.db.get_next_vlan_id() * 100
        slice_obj = Slice(slice_id, username, vlan_config.get("vlan_ids", []), topology_type=vlan_config.get("topology", "linear"))
        vms_created = []
        
        try:
            futures = []
            for i in range(num_vms):
                vm_id = self.db.get_next_vm_id()
                worker_ip = self.get_next_worker()
                future = self.executor.submit(
                    self.deployment_api.create_vm_with_qcow,
                    slice_id, vm_id, f"{slice_name}_vm{i}", username, worker_ip,
                    vlan_config.get("vlan_ids", []), base_image_path
                )
                futures.append((vm_id, worker_ip, future))
            
            for vm_id, worker_ip, future in futures:
                success, vm = future.result()
                if not success:
                    raise Exception(f"VM {vm_id} creation failed")
                slice_obj.add_vm(vm.to_dict())
                vms_created.append(vm)
            
            for vlan_config_item in vlan_config.get("vlans", []):
                vlan_id = vlan_config_item["id"]
                cidr = vlan_config_item["cidr"]
                gateway = vlan_config_item["gateway"]
                dhcp = vlan_config_item.get("dhcp", False)
                
                for worker in self.workers:
                    self.vlan_mgr.create_vlan_with_gateway(worker, vlan_id, cidr, gateway, dhcp)
                    if vlan_config_item.get("internet", False):
                        self.routing_mgr.enable_ip_forward(worker)
                        self.routing_mgr.setup_masquerade(worker, vlan_id, cidr)
            
            slice_obj.status = "active"
            self.db.add_slice(slice_obj.to_dict())
            user["used_vms"] = user.get("used_vms", 0) + num_vms
            user["slices"].append(slice_id)
            self.db.update_user(username, user)
            return True, slice_obj.to_dict()
        except Exception as e:
            logger.error(f"Rollback: {e}")
            for vm in vms_created:
                self.deployment_api.delete_vm(vm)
            return False, str(e)
    
    def delete_slice(self, username, slice_id):
        slice_dict = self.db.get_slice(slice_id)
        if not slice_dict or slice_dict.get("owner") != username:
            return False, "Slice not found"
        
        for vm_dict in slice_dict.get("vms", []):
            vm = type('VM', (), vm_dict)()
            self.deployment_api.delete_vm(vm)
        
        for vlan_id in slice_dict.get("vlan_ids", []):
            for worker in self.workers:
                self.vlan_mgr.delete_vlan(worker, vlan_id)
        
        self.db.delete_slice(slice_id)
        user = self.db.get_user(username)
        user["used_vms"] = max(0, user.get("used_vms", 0) - len(slice_dict.get("vms", [])))
        user["slices"].remove(slice_id)
        self.db.update_user(username, user)
        return True, "Slice deleted"
