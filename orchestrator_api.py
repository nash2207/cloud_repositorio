import logging
from models import Slice, Link, Flavor

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
    
    def create_slice(self, username, slice_name, topology_type="custom"):
        user = self.db.get_user(username)
        if not user:
            return False, "User not found"
        
        try:
            slice_id = self.db.get_next_vm_id()
            slice_obj = Slice(slice_id, username, topology_type)
            slice_obj.status = "design"
            
            self.db.add_slice(slice_obj.to_dict())
            
            if "slices" not in user:
                user["slices"] = []
            user["slices"].append(slice_id)
            self.db.update_user(username, user)
            
            logger.info(f"Slice {slice_id} created for {username} (VLAN pool: {slice_obj.vlan_pool_start}-{slice_obj.vlan_pool_end})")
            return True, {"slice_id": slice_id, "name": slice_name}
        except Exception as e:
            logger.error(f"Slice creation error: {e}")
            return False, str(e)
    
    def add_vm_to_slice(self, username, slice_id, vm_name, flavor_name, data_interfaces_count, internet_enabled=False):
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
            flavor_spec = Flavor.get(flavor_name)
            
            if not flavor_spec:
                return False, "Invalid flavor"
            
            success, vm = self.deployment_api.create_vm_with_qcow(
                slice_id, vm_id, vm_name, username, worker_ip, flavor_spec,
                data_interfaces_count, internet_enabled
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
    
    def create_link(self, username, slice_id, vm1_id, vm1_interface, vm2_id, vm2_interface):
        """Create L2 link between two VM interfaces"""
        slice_data = self.db.get_slice(str(slice_id))
        
        if not slice_data or slice_data.get("owner") != username:
            return False, "Slice not found or not authorized"
        
        try:
            # Reconstruct Slice object to use get_next_vlan()
            slice_obj = Slice(slice_data["slice_id"], slice_data["owner"])
            slice_obj.vlan_pool_used = slice_data.get("vlan_pool_used", [])
            slice_obj.vlan_pool_start = slice_data.get("vlan_pool_start")
            slice_obj.vlan_pool_end = slice_data.get("vlan_pool_end")
            
            vlan_id = slice_obj.get_next_vlan()
            if not vlan_id:
                return False, "VLAN pool exhausted"
            
            link_id = len(slice_data.get("links", [])) + 1
            link = Link(link_id, vlan_id, vm1_id, vm1_interface, vm2_id, vm2_interface)
            
            # Update interfaces in VMs
            for vm_dict in slice_data.get("vms", []):
                if vm_dict["vm_id"] == vm1_id:
                    for iface in vm_dict["interfaces"]:
                        if iface["name"] == vm1_interface:
                            iface["vlan_id"] = vlan_id
                            iface["link_id"] = link_id
                elif vm_dict["vm_id"] == vm2_id:
                    for iface in vm_dict["interfaces"]:
                        if iface["name"] == vm2_interface:
                            iface["vlan_id"] = vlan_id
                            iface["link_id"] = link_id
            
            if "links" not in slice_data:
                slice_data["links"] = []
            slice_data["links"].append(link.to_dict())
            slice_data["vlan_pool_used"] = slice_obj.vlan_pool_used
            
            self.db.update_slice(slice_id, slice_data)
            
            logger.info(f"Link {link_id} created: VM{vm1_id}.{vm1_interface} <-> VM{vm2_id}.{vm2_interface} (VLAN {vlan_id})")
            return True, link.to_dict()
        except Exception as e:
            logger.error(f"Link creation error: {e}")
            return False, str(e)
    
    def deploy_slice(self, username, slice_id):
        """Deploy slice: configure VLANs on workers and start VMs"""
        slice_data = self.db.get_slice(str(slice_id))
        
        if not slice_data or slice_data.get("owner") != username:
            return False, "Slice not found or not authorized"
        
        try:
            # TODO: Configure VLANs on workers using vlan_manager
            # TODO: Start QEMU processes with proper TAP interfaces
            
            slice_data["status"] = "running"
            self.db.update_slice(slice_id, slice_data)
            
            logger.info(f"Slice {slice_id} deployed")
            return True, "Slice deployed successfully"
        except Exception as e:
            logger.error(f"Deploy error: {e}")
            return False, str(e)
    
    def delete_slice(self, username, slice_id):
        try:
            slice_data = self.db.get_slice(str(slice_id))
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
