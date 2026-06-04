"""Orchestrator API - High-level slice management with pluggable providers"""
import logging
import json
from models import Slice, Link, Flavor, VM, Interface
from providers.baremetal_provider import BareMetalComputeProvider
from providers.ovs_network_provider import OVSNetworkProvider
from topology_generator import TopologyGenerator

logger = logging.getLogger(__name__)


class OrchestratorAPI:
    """
    Orchestrator with pluggable compute and network providers
    Can be extended to support OpenStack or other backends
    """
    
    def __init__(self, db, deployment_api, compute_provider=None, network_provider=None):
        self.db = db
        self.deployment_api = deployment_api
        
        # Use provided providers or default to bare-metal
        self.compute_provider = compute_provider or BareMetalComputeProvider(deployment_api.executor)
        self.network_provider = network_provider or OVSNetworkProvider(deployment_api.executor)
        
        self.round_robin_idx = 0
        self.workers = db.data.get("workers_list", ["10.0.10.1", "10.0.10.2", "10.0.10.3"])
    
    def get_next_worker(self):
        """Round-robin worker selection"""
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
    
    def add_vm_to_slice(self, username, slice_id, vm_name, flavor_name, internet_enabled=False):
        """Add VM to slice with only management interface (dynamic interfaces added via links)"""
        user = self.db.get_user(username)
        slice_data = self.db.get_slice(str(slice_id))
        
        if not user or not slice_data:
            return False, "User or Slice not found"
        
        if slice_data.get("owner") != username:
            return False, "Not authorized"
        
        if slice_data.get("status") != "design":
            return False, "Cannot add VMs to deployed slice"
        
        if (user.get("used_vms", 0) + 1) > user.get("quota_vms", 10):
            return False, "Quota exceeded"
        
        try:
            vm_id = self.db.get_next_vm_id()
            worker_ip = self.get_next_worker()
            
            # Create VM with only management interface
            success, vm = self.deployment_api.create_vm_with_qcow(
                slice_id, vm_id, vm_name, username, worker_ip, flavor_name, internet_enabled
            )
            if not success:
                return False, "VM creation failed"
            
            if "vms" not in slice_data:
                slice_data["vms"] = []
            slice_data["vms"].append(vm.to_dict())
            self.db.update_slice(slice_id, slice_data)
            
            user["used_vms"] = user.get("used_vms", 0) + 1
            self.db.update_user(username, user)
            
            logger.info(f"VM {vm_id} ({flavor_name}) added to slice {slice_id}")
            return True, vm.to_dict()
        except Exception as e:
            logger.error(f"VM creation error: {e}")
            return False, str(e)
    
    def create_link(self, username, slice_id, vm1_id, vm2_id):
        """Create L2 link between two VMs, automatically adding interfaces dynamically"""
        slice_data = self.db.get_slice(str(slice_id))
        
        if not slice_data or slice_data.get("owner") != username:
            return False, "Slice not found or not authorized"
        
        if slice_data.get("status") != "design":
            return False, "Cannot create links in deployed slice"
        
        try:
            # Find VMs
            vm1_dict = next((v for v in slice_data.get("vms", []) if v["vm_id"] == vm1_id), None)
            vm2_dict = next((v for v in slice_data.get("vms", []) if v["vm_id"] == vm2_id), None)
            
            if not vm1_dict or not vm2_dict:
                return False, "VMs not found"
            
            # Reconstruct VM objects to use get_next_interface_name()
            from models import VM, Interface
            vm1 = VM(vm1_dict["vm_id"], vm1_dict["name"], vm1_dict["owner"], 
                    vm1_dict["worker_ip"], vm1_dict["vnc_port"], 
                    [Interface(**iface) for iface in vm1_dict["interfaces"]],
                    flavor=vm1_dict["flavor"], qcow_image=vm1_dict.get("qcow_image"))
            
            vm2 = VM(vm2_dict["vm_id"], vm2_dict["name"], vm2_dict["owner"], 
                    vm2_dict["worker_ip"], vm2_dict["vnc_port"], 
                    [Interface(**iface) for iface in vm2_dict["interfaces"]],
                    flavor=vm2_dict["flavor"], qcow_image=vm2_dict.get("qcow_image"))
            
            # Get next available interface names
            vm1_iface_name = vm1.get_next_interface_name()
            vm2_iface_name = vm2.get_next_interface_name()
            
            if not vm1_iface_name or not vm2_iface_name:
                return False, "Failed to generate interface names"
            
            # Get VLAN from slice pool
            slice_obj = Slice(slice_data["slice_id"], slice_data["owner"])
            slice_obj.vlan_pool_used = slice_data.get("vlan_pool_used", [])
            slice_obj.vlan_pool_start = slice_data.get("vlan_pool_start")
            slice_obj.vlan_pool_end = slice_data.get("vlan_pool_end")
            
            vlan_id = slice_obj.get_next_vlan()
            if not vlan_id:
                return False, "VLAN pool exhausted"
            
            link_id = len(slice_data.get("links", [])) + 1
            link = Link(link_id, vlan_id, vm1_id, vm1_iface_name, vm2_id, vm2_iface_name)
            
            # Add new interfaces to VMs
            vm1_new_iface = Interface(vm1_iface_name, vlan_id=vlan_id, link_id=link_id)
            vm2_new_iface = Interface(vm2_iface_name, vlan_id=vlan_id, link_id=link_id)
            
            vm1_dict["interfaces"].append(vm1_new_iface.to_dict())
            vm2_dict["interfaces"].append(vm2_new_iface.to_dict())
            
            # Save link
            if "links" not in slice_data:
                slice_data["links"] = []
            slice_data["links"].append(link.to_dict())
            slice_data["vlan_pool_used"] = slice_obj.vlan_pool_used
            
            self.db.update_slice(slice_id, slice_data)
            
            logger.info(f"Link {link_id} created: VM{vm1_id}.{vm1_iface_name} <-> VM{vm2_id}.{vm2_iface_name} (VLAN {vlan_id})")
            return True, link.to_dict()
        except Exception as e:
            logger.error(f"Link creation error: {e}")
            return False, str(e)
    
    def deploy_slice(self, username, slice_id):
        """Deploy slice using pluggable providers"""
        slice_data = self.db.get_slice(str(slice_id))
        
        if not slice_data or slice_data.get("owner") != username:
            return False, "Slice not found or not authorized"
        
        if slice_data.get("status") == "deployed":
            return False, "Slice already deployed"
        
        try:
            # 1. Configure VLAN 400 DHCP for internet access (gateway already exists)
            has_internet = any(
                any(iface.get("vlan_id") == 400 for iface in vm.get("interfaces", []))
                for vm in slice_data.get("vms", [])
            )
            
            if has_internet:
                logger.info("Configuring DHCP for VLAN 400 (gateway 10.60.7.1 already exists)")
                self.network_provider.delete_network(400)  # Cleanup previous
                success = self.network_provider.create_network(
                    400, "10.60.7.0/24", "10.60.7.1", 
                    dhcp_enabled=True, create_gateway=False
                )
                if not success:
                    logger.error("Failed to configure DHCP for VLAN 400")
                    return False, "Failed to configure DHCP for VLAN 400"
            
            # 2. Configure VLANs for each Link (L2 connections between VMs)
            for link in slice_data.get("links", []):
                vlan_id = link.get("vlan_id")
                cidr = f"192.168.{vlan_id % 256}.0/24"
                gateway_ip = f"192.168.{vlan_id % 256}.1"
                
                logger.info(f"Configuring VLAN {vlan_id} for Link {link.get('link_id')}")
                success = self.network_provider.create_network(
                    vlan_id, cidr, gateway_ip, dhcp_enabled=True
                )
                
                if not success:
                    logger.error(f"Failed to configure VLAN {vlan_id}")
                    return False, f"Failed to configure VLAN {vlan_id}"
            
            # 3. Launch all VMs using compute provider
            for vm_dict in slice_data.get("vms", []):
                worker_ip = vm_dict.get("worker_ip")
                logger.info(f"Deploying VM {vm_dict['vm_id']} on {worker_ip}")
                
                success, pid = self.compute_provider.launch_vm(worker_ip, vm_dict)
                if success:
                    vm_dict["status"] = "deployed"
                    vm_dict["pid"] = pid
                    logger.info(f"VM {vm_dict['vm_id']} started with PID {pid}")
                else:
                    logger.error(f"Failed to start VM {vm_dict['vm_id']}")
                    return False, f"Failed to start VM {vm_dict['vm_id']}"
            
            slice_data["status"] = "deployed"
            self.db.update_slice(slice_id, slice_data)
            
            logger.info(f"Slice {slice_id} deployed successfully")
            return True, "Slice deployed successfully"
        except Exception as e:
            logger.error(f"Deploy error: {e}")
            return False, str(e)
    
    def delete_slice(self, username, slice_id):
        """Delete slice using pluggable providers"""
        try:
            slice_data = self.db.get_slice(str(slice_id))
            if not slice_data or slice_data.get("owner") != username:
                return False, "Slice not found or not authorized"
            
            user = self.db.get_user(username)
            vm_count = len(slice_data.get("vms", []))
            
            # Stop VMs if deployed
            if slice_data.get("status") == "deployed":
                for vm_dict in slice_data.get("vms", []):
                    worker_ip = vm_dict.get("worker_ip")
                    self.compute_provider.stop_vm(worker_ip, vm_dict)
                
                # Cleanup VLANs on network node
                for link in slice_data.get("links", []):
                    vlan_id = link.get("vlan_id")
                    self.network_provider.delete_network(vlan_id)
            
            # Delete QCOW images
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
    
    def update_vm(self, username, slice_id, vm_id, updates):
        """Update VM properties (only in design state)"""
        try:
            slice_data = self.db.get_slice(str(slice_id))
            if not slice_data or slice_data.get("owner") != username:
                return False, "Slice not found or not authorized"
            
            if slice_data.get("status") != "design":
                return False, "Cannot update deployed VM"
            
            vm_dict = next((v for v in slice_data.get("vms", []) if v["vm_id"] == vm_id), None)
            if not vm_dict:
                return False, "VM not found"
            
            # Update allowed fields
            if "vm_name" in updates:
                vm_dict["name"] = updates["vm_name"]
            if "flavor" in updates:
                vm_dict["flavor"] = updates["flavor"]
            if "internet_enabled" in updates:
                # Update internet interface (VLAN 400)
                mgmt_iface = vm_dict["interfaces"][0]
                if updates["internet_enabled"]:
                    mgmt_iface["vlan_id"] = 400
                    mgmt_iface["ip_config"] = {
                        "ip": f"10.60.7.{100 + vm_id % 100}",
                        "cidr": "10.60.7.0/24",
                        "gateway": "10.60.7.1"
                    }
                else:
                    mgmt_iface["vlan_id"] = None
                    mgmt_iface["ip_config"] = None
            
            self.db.update_slice(slice_id, slice_data)
            logger.info(f"VM {vm_id} updated in slice {slice_id}")
            return True, vm_dict
        except Exception as e:
            logger.error(f"Update VM error: {e}")
            return False, str(e)
    
    def create_topology_preset(self, username, slice_id, topology_type, num_vms, flavor, internet, base_name):
        """Create predefined topology (ring, bus, star, mesh)"""
        try:
            slice_data = self.db.get_slice(str(slice_id))
            if not slice_data or slice_data.get("owner") != username:
                return False, "Slice not found or not authorized"
            
            if slice_data.get("status") != "design":
                return False, "Cannot modify deployed slice"
            
            # Generate topology
            if topology_type == "ring":
                vms_config, links_config = TopologyGenerator.generate_ring(num_vms, base_name, flavor, internet)
            elif topology_type == "bus":
                vms_config, links_config = TopologyGenerator.generate_bus(num_vms, base_name, flavor, internet)
            elif topology_type == "star":
                vms_config, links_config = TopologyGenerator.generate_star(num_vms, base_name, flavor, internet)
            elif topology_type == "mesh":
                vms_config, links_config = TopologyGenerator.generate_full_mesh(num_vms, base_name, flavor, internet)
            else:
                return False, f"Unknown topology type: {topology_type}"
            
            # Create VMs
            created_vms = []
            for vm_cfg in vms_config:
                success, vm_dict = self.add_vm_to_slice(
                    username, slice_id, vm_cfg['name'], vm_cfg['flavor'], vm_cfg['internet_enabled']
                )
                if not success:
                    return False, f"Failed to create VM: {vm_dict}"
                created_vms.append(vm_dict)
            
            # Create links
            for link_cfg in links_config:
                vm1_id = created_vms[link_cfg['vm1_index']]['vm_id']
                vm2_id = created_vms[link_cfg['vm2_index']]['vm_id']
                
                success, link_dict = self.create_link(username, slice_id, vm1_id, vm2_id)
                if not success:
                    return False, f"Failed to create link: {link_dict}"
            
            logger.info(f"Topology {topology_type} created in slice {slice_id}: {num_vms} VMs, {len(links_config)} links")
            return True, {"vms": len(created_vms), "links": len(links_config)}
        except Exception as e:
            logger.error(f"Create topology error: {e}")
            return False, str(e)
    
    def export_slice_json(self, username, slice_id):
        """Export slice to JSON format"""
        try:
            slice_data = self.db.get_slice(str(slice_id))
            if not slice_data or slice_data.get("owner") != username:
                return False, "Slice not found or not authorized"
            
            # Build export format with complete VM info including flavors
            export_data = {
                "slice_name": f"slice_{slice_id}",
                "topology_type": slice_data.get("topology_type", "custom"),
                "vms": [],
                "links": []
            }
            
            for vm in slice_data.get("vms", []):
                flavor_spec = Flavor.get(vm["flavor"])
                vm_export = {
                    "name": vm["name"],
                    "flavor": vm["flavor"],
                    "flavor_config": flavor_spec,  # Include full flavor specs
                    "internet_enabled": any(iface.get("vlan_id") == 400 for iface in vm["interfaces"])
                }
                export_data["vms"].append(vm_export)
            
            for link in slice_data.get("links", []):
                # Find VM indices
                vm1_idx = next((i for i, v in enumerate(slice_data.get("vms", [])) if v["vm_id"] == link["vm1_id"]), None)
                vm2_idx = next((i for i, v in enumerate(slice_data.get("vms", [])) if v["vm_id"] == link["vm2_id"]), None)
                
                export_data["links"].append({
                    "vm1_index": vm1_idx,
                    "vm2_index": vm2_idx,
                    "description": f"Link between {link['vm1_interface']} and {link['vm2_interface']}"
                })
            
            logger.info(f"Slice {slice_id} exported to JSON")
            return True, export_data
        except Exception as e:
            logger.error(f"Export error: {e}")
            return False, str(e)
    
    def import_slice_json(self, username, json_data):
        """Import slice from JSON format"""
        try:
            # Create new slice
            slice_name = json_data.get("slice_name", "imported_slice")
            topology_type = json_data.get("topology_type", "custom")
            
            success, slice_result = self.create_slice(username, slice_name, topology_type)
            if not success:
                return False, slice_result
            
            slice_id = slice_result["slice_id"]
            
            # Create VMs
            created_vms = []
            for vm_cfg in json_data.get("vms", []):
                success, vm_dict = self.add_vm_to_slice(
                    username, slice_id, vm_cfg["name"], vm_cfg["flavor"], vm_cfg.get("internet_enabled", False)
                )
                if not success:
                    return False, f"Failed to create VM: {vm_dict}"
                created_vms.append(vm_dict)
            
            # Create links
            for link_cfg in json_data.get("links", []):
                vm1_id = created_vms[link_cfg['vm1_index']]['vm_id']
                vm2_id = created_vms[link_cfg['vm2_index']]['vm_id']
                
                success, link_dict = self.create_link(username, slice_id, vm1_id, vm2_id)
                if not success:
                    return False, f"Failed to create link: {link_dict}"
            
            logger.info(f"Slice {slice_id} imported from JSON")
            return True, {"slice_id": slice_id, "vms": len(created_vms), "links": len(json_data.get("links", []))}
        except Exception as e:
            logger.error(f"Import error: {e}")
            return False, str(e)
