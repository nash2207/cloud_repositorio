"""Orchestrator API - High-level slice management with pluggable providers"""
import logging
import json
from models import Slice, Link, Flavor, VM, Interface
from providers.base_compute import BaseComputeProvider, BaseNetworkProvider
from topology_generator import TopologyGenerator
from vm_placement import VMPlacementGA
from vlan_trunk_manager import VLANTrunkManager

logger = logging.getLogger(__name__)


class OrchestratorAPI:
    """
    Orchestrator with pluggable compute and network providers (Hexagonal Architecture)
    
    Responsibilities:
    - Slice lifecycle management (create, deploy, delete)
    - VM placement optimization via GA
    - Topology generation
    - Provider orchestration (delegates infrastructure operations to injected providers)
    
    Compliance:
    - Uses dependency injection for ALL infrastructure providers
    - Depends only on abstract interfaces (BaseComputeProvider, BaseNetworkProvider)
    - Zero knowledge of concrete provider implementations (BareMetalComputeProvider, etc.)
    """
    
    def __init__(self, 
                 db, 
                 deployment_api, 
                 monitoring_system=None,
                 compute_provider: BaseComputeProvider = None,
                 network_provider: BaseNetworkProvider = None,
                 vlan_trunk_manager=None,
                 clusters_config=None):
        """
        Initialize orchestrator with injected dependencies
        
        Args:
            db: Database instance
            deployment_api: Deployment API instance
            monitoring_system: Optional monitoring system for telemetry
            compute_provider: Injected compute provider (BareMetalComputeProvider, OpenStackComputeProvider, etc.)
            network_provider: Injected network provider (OVSNetworkProvider, NeutronNetworkProvider, etc.)
            vlan_trunk_manager: Optional VLAN trunk manager for physical switch configuration
            clusters_config: Optional cluster configuration dict (defaults to database config)
        """
        self.db = db
        self.deployment_api = deployment_api
        self.monitoring_system = monitoring_system
        
        # Injected providers (Hexagonal Architecture compliance)
        self.compute_provider = compute_provider
        self.network_provider = network_provider
        self.vlan_trunk_manager = vlan_trunk_manager
        
        # Provider registry for multi-cluster support
        self._provider_registry = {}
        
        # Cluster configuration
        self.clusters = clusters_config or db.data.get("clusters", {
            "linux": {
                "bind_address": "10.0.0.6",
                "network_node": "10.0.0.1",
                "workers": ["10.0.0.2", "10.0.0.3", "10.0.0.4"]
            }
        })
        
        # Only include enabled clusters
        self.clusters = {k: v for k, v in self.clusters.items() if v is not None and isinstance(v, dict)}
        
        # Initialize VM Placement GA if monitoring is available
        if monitoring_system and "linux" in self.clusters:
            self.linux_placement_ga = VMPlacementGA(
                monitoring_system, 
                self.clusters["linux"],
                "linux"
            )
            logger.info("VM Placement GA initialized for Linux cluster")
        else:
            self.linux_placement_ga = None
            logger.warning("Monitoring system not provided - using fallback round-robin")
        
        # Round-robin state per cluster (fallback if GA not available)
        self.round_robin_idx = {"linux": 0}
    
    def register_providers(self, availability_zone, compute_provider, network_provider):
        """
        Register providers for a specific availability zone
        
        This allows supporting multiple clusters (linux, openstack, etc.) with different providers
        
        Args:
            availability_zone: Zone identifier (e.g., "openstack")
            compute_provider: Compute provider instance for this zone
            network_provider: Network provider instance for this zone
        """
        self._provider_registry[availability_zone] = {
            "compute": compute_provider,
            "network": network_provider
        }
        logger.info(f"Registered providers for availability zone: {availability_zone}")
    
    def _get_cluster_config(self, availability_zone):
        """Get cluster configuration for given AZ"""
        return self.clusters.get(availability_zone, self.clusters.get("linux", {}))
    
    def _get_compute_provider(self, availability_zone):
        """Get compute provider for given AZ"""
        # Check provider registry first (for multi-cluster support)
        if availability_zone in self._provider_registry:
            return self._provider_registry[availability_zone]["compute"]
        
        # Fallback to injected default provider
        return self.compute_provider
    
    def _get_network_provider(self, availability_zone):
        """Get network provider for given AZ"""
        # Check provider registry first (for multi-cluster support)
        if availability_zone in self._provider_registry:
            return self._provider_registry[availability_zone]["network"]
        
        # Fallback to injected default provider
        return self.network_provider
    
    def _set_bind_address(self, availability_zone):
        """Set RemoteExecutor bind address for cluster"""
        cluster_config = self._get_cluster_config(availability_zone)
        bind_address = cluster_config.get("bind_address")
        if bind_address and availability_zone == "linux":
            # Access executor from deployment_api
            if hasattr(self.deployment_api, 'executor'):
                self.deployment_api.executor.set_bind_address(bind_address)
    
    def get_next_worker(self, availability_zone="linux"):
        """Round-robin worker selection for given cluster"""
        cluster_config = self._get_cluster_config(availability_zone)
        workers = cluster_config.get("workers", [])
        
        if not workers:
            logger.error(f"No workers defined for AZ: {availability_zone}")
            return None
        
        idx = self.round_robin_idx.get(availability_zone, 0)
        worker = workers[idx % len(workers)]
        self.round_robin_idx[availability_zone] = idx + 1
        return worker
    
    def create_slice(self, username, slice_name, topology_type="custom", availability_zone="linux"):
        from audit_log import log_slice_action
        
        user = self.db.get_user(username)
        if not user:
            return False, "User not found"
        
        # Validate availability zone
        if availability_zone not in ["linux", "openstack"]:
            return False, f"Invalid availability zone: {availability_zone}. Choose 'linux' or 'openstack'"
        
        try:
            slice_id = self.db.get_next_vm_id()
            slice_obj = Slice(slice_id, username, topology_type, availability_zone)
            slice_obj.status = "design"
            
            self.db.add_slice(slice_obj.to_dict())
            
            if "slices" not in user:
                user["slices"] = []
            user["slices"].append(slice_id)
            self.db.update_user(username, user)
            
            log_slice_action(
                username,
                f"Created slice '{slice_name}'",
                slice_id,
                {"availability_zone": availability_zone, "vlan_pool": f"{slice_obj.vlan_pool_start}-{slice_obj.vlan_pool_end}"}
            )
            
            logger.info(f"Slice {slice_id} created for {username} in AZ '{availability_zone}' (VLAN pool: {slice_obj.vlan_pool_start}-{slice_obj.vlan_pool_end})")
            return True, {"slice_id": slice_id, "name": slice_name, "availability_zone": availability_zone}
        except Exception as e:
            logger.error(f"Slice creation error: {e}")
            return False, str(e)
    
    def _place_single_vm(self, slice_id, flavor_name, availability_zone):
        """
        Place a single VM on a worker (for live editing)
        
        Returns:
            str: Worker IP or None if placement fails
        """
        try:
            from models import Flavor
            flavor_spec = Flavor.get(flavor_name)
            if not flavor_spec:
                logger.error(f"Unknown flavor: {flavor_name}")
                return None
            
            # Get available workers
            cluster_config = self.clusters.get(availability_zone, {})
            workers = cluster_config.get("workers", [])
            
            if not workers:
                logger.error(f"No workers found in cluster {availability_zone}")
                return None
            
            # Simple round-robin placement for single VM
            # TODO: Use monitoring data for better placement
            slice_data = self.db.get_slice(str(slice_id))
            existing_vms = slice_data.get("vms", [])
            
            # Find worker with fewest VMs from this slice
            worker_vm_count = {w: 0 for w in workers}
            for vm in existing_vms:
                worker = vm.get("worker_ip")
                if worker and worker in worker_vm_count:
                    worker_vm_count[worker] += 1
            
            # Choose worker with minimum VMs
            selected_worker = min(worker_vm_count.items(), key=lambda x: x[1])[0]
            
            logger.info(f"Single VM placement: selected worker {selected_worker}")
            return selected_worker
            
        except Exception as e:
            logger.error(f"Single VM placement error: {e}")
            return None
    
    def _deploy_single_vm(self, slice_id, vm_dict):
        """
        Deploy a single VM (for live editing)
        
        Returns:
            bool: True if deployment successful
        """
        try:
            vm_id = vm_dict["vm_id"]
            worker_ip = vm_dict["worker_ip"]
            
            logger.info(f"Deploying single VM {vm_id} on {worker_ip}")
            
            # Deploy using compute provider
            success = self.compute_provider.launch_vm(worker_ip, vm_dict)
            
            if success:
                # Update VM status
                slice_data = self.db.get_slice(str(slice_id))
                for vm in slice_data.get("vms", []):
                    if vm["vm_id"] == vm_id:
                        vm["status"] = "deployed"
                        break
                self.db.update_slice(slice_id, slice_data)
                logger.info(f"VM {vm_id} deployed successfully")
                return True
            else:
                logger.error(f"Failed to deploy VM {vm_id}")
                return False
                
        except Exception as e:
            logger.error(f"Single VM deployment error: {e}")
            return False
    
    def _reboot_vm(self, vm_dict):
        """
        Reboot a VM to apply new configuration (for live editing)
        
        Args:
            vm_dict: VM dictionary containing vm_id, worker_ip, interfaces, etc.
        
        Returns:
            bool: True if reboot successful
        """
        import time
        
        try:
            vm_id = vm_dict["vm_id"]
            vm_name = vm_dict["name"]
            worker_ip = vm_dict["worker_ip"]
            interfaces = vm_dict.get("interfaces", [])
            
            logger.info(f"LIVE EDIT: Rebooting VM {vm_id} ({vm_name}) on {worker_ip}")
            
            # Step 1: Stop the VM
            logger.info(f"Stopping VM {vm_id}...")
            stop_success = self.compute_provider.stop_vm(worker_ip, vm_dict)
            
            if not stop_success:
                logger.error(f"Failed to stop VM {vm_id} during reboot")
                return False
            
            # Step 2: Wait briefly for cleanup
            logger.info(f"Waiting 3 seconds for VM {vm_id} cleanup...")
            time.sleep(3)
            
            # Step 3: Regenerate cloud-init seed ISO with updated interfaces
            logger.info(f"Regenerating cloud-init seed for VM {vm_id} with updated interfaces...")
            from cloudinit_seed import CloudInitSeedGenerator
            seed_generator = CloudInitSeedGenerator(self.compute_provider.executor)
            success, seed_iso = seed_generator.generate_seed_iso(
                worker_ip, vm_id, vm_name, interfaces
            )
            if success:
                vm_dict["seed_iso"] = seed_iso
                logger.info(f"Cloud-init seed regenerated: {seed_iso}")
            else:
                logger.warning(f"Failed to regenerate cloud-init seed for VM {vm_id}")
            
            # Step 4: Restart the VM
            logger.info(f"Restarting VM {vm_id}...")
            start_success, pid = self.compute_provider.launch_vm(worker_ip, vm_dict)
            
            if start_success:
                # Update VM status in database
                vm_dict["status"] = "deployed"
                if pid:
                    vm_dict["pid"] = pid
                logger.info(f"VM {vm_id} rebooted successfully with PID {pid}")
                return True
            else:
                logger.error(f"Failed to restart VM {vm_id} during reboot")
                vm_dict["status"] = "error"
                return False
                
        except Exception as e:
            logger.error(f"VM reboot error: {e}")
            return False
    
    def _get_next_vm_name(self, slice_data, base_name):
        """
        Get next available VM name in a slice by finding existing names with the same base
        
        Args:
            slice_data: Slice dict
            base_name: Base name for VM (e.g., "vm", "router", "server")
        
        Returns:
            str: Next available name (e.g., "vm4" if vm1, vm2, vm3 exist)
        
        Example:
            If slice has: vm1, vm2, vm3
            _get_next_vm_name(slice, "vm") returns "vm4"
        """
        import re
        
        existing_vms = slice_data.get("vms", [])
        
        # Find all VMs with names matching the pattern: base_name + number
        pattern = re.compile(f"^{re.escape(base_name)}(\\d+)$")
        existing_numbers = []
        
        for vm in existing_vms:
            vm_name = vm.get("name", "")
            match = pattern.match(vm_name)
            if match:
                existing_numbers.append(int(match.group(1)))
        
        # Find the next available number
        if not existing_numbers:
            next_number = 1
        else:
            next_number = max(existing_numbers) + 1
        
        return f"{base_name}{next_number}"
    
    def add_vm_to_slice(self, username, slice_id, vm_name, flavor_name, internet_enabled=False, auto_name=False):
        """
        Add VM to slice with only management interface (dynamic interfaces added via links)
        Worker placement deferred until deployment (batch placement via GA)
        
        Args:
            auto_name: If True, automatically find next available name using vm_name as base
        
        NEW BEHAVIOR: VMs added to deployed slices stay in "design" state
        User must click "Deploy Edition" button to deploy the new VMs
        """
        user = self.db.get_user(username)
        slice_data = self.db.get_slice(str(slice_id))
        
        if not user or not slice_data:
            return False, "User or Slice not found"
        
        if slice_data.get("owner") != username:
            return False, "Not authorized"
        
        # Allow adding VMs to deployed slices (but don't deploy them automatically)
        is_deployed = slice_data.get("status") == "deployed"
        
        if (user.get("used_vms", 0) + 1) > user.get("quota_vms", 10):
            return False, "Quota exceeded"
        
        try:
            # Auto-generate next available name if requested
            if auto_name:
                vm_name = self._get_next_vm_name(slice_data, vm_name)
                logger.info(f"Auto-generated VM name: {vm_name}")
            
            vm_id = self.db.get_next_vm_id()
            availability_zone = slice_data.get("availability_zone", "linux")
            
            # Always defer placement - no immediate deployment
            worker_ip = "PENDING"
            
            # Create VM in design state
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
            
            logger.info(
                f"VM {vm_id} ({flavor_name}) added to slice {slice_id} (AZ: {availability_zone}) in design state"
                f"{' - use Deploy Edition to deploy new VMs' if is_deployed else ''}"
            )
            return True, vm.to_dict()
        except Exception as e:
            logger.error(f"VM creation error: {e}")
            return False, str(e)
    
    def create_link(self, username, slice_id, vm1_id, vm2_id):
        """
        Create L2 link between two VMs, automatically adding interfaces dynamically
        
        NEW BEHAVIOR (Live Editing):
        - Links created in deployed slices stay in "design" state
        - VMs are NOT rebooted immediately
        - User must click "Deploy Edition" to apply pending links
        """
        slice_data = self.db.get_slice(str(slice_id))
        
        if not slice_data or slice_data.get("owner") != username:
            return False, "Slice not found or not authorized"
        
        # Check if slice is deployed
        is_deployed = slice_data.get("status") == "deployed"
        
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
            
            # NEW: Create link in "design" state if slice is deployed
            link_status = "design" if is_deployed else "design"  # Always design initially
            link = Link(link_id, vlan_id, vm1_id, vm1_iface_name, vm2_id, vm2_iface_name, status=link_status)
            
            # Add new interfaces to VMs with generated MAC addresses
            from deployment_api import DeploymentAPI
            macs = self.deployment_api.generate_unique_macs(vm1_id, 1)
            vm1_new_iface = Interface(vm1_iface_name, vlan_id=vlan_id, link_id=link_id, mac=macs[0])
            
            macs = self.deployment_api.generate_unique_macs(vm2_id, 1)
            vm2_new_iface = Interface(vm2_iface_name, vlan_id=vlan_id, link_id=link_id, mac=macs[0])
            
            vm1_dict["interfaces"].append(vm1_new_iface.to_dict())
            vm2_dict["interfaces"].append(vm2_new_iface.to_dict())
            
            # Save link
            if "links" not in slice_data:
                slice_data["links"] = []
            slice_data["links"].append(link.to_dict())
            slice_data["vlan_pool_used"] = slice_obj.vlan_pool_used
            
            self.db.update_slice(slice_id, slice_data)
            
            if is_deployed:
                logger.info(f"Link {link_id} created in DESIGN state: VM{vm1_id}.{vm1_iface_name} <-> VM{vm2_id}.{vm2_iface_name} (VLAN {vlan_id}) - use Deploy Edition to apply")
            else:
                logger.info(f"Link {link_id} created: VM{vm1_id}.{vm1_iface_name} <-> VM{vm2_id}.{vm2_iface_name} (VLAN {vlan_id})")
            
            # NEW BEHAVIOR: Do NOT reboot VMs immediately in deployed slices
            # Links stay in "design" state until user clicks "Deploy Edition"
            
            return True, link.to_dict()
        except Exception as e:
            logger.error(f"Link creation error: {e}")
            return False, str(e)
    
    def delete_link(self, username, slice_id, link_id):
        """
        Delete a link between two VMs, removing interfaces and rebooting VMs if deployed
        
        Args:
            username: Owner username
            slice_id: Slice ID
            link_id: Link ID to delete
        
        Returns:
            tuple: (success: bool, message: str or dict)
        """
        slice_data = self.db.get_slice(str(slice_id))
        
        if not slice_data or slice_data.get("owner") != username:
            return False, "Slice not found or not authorized"
        
        # LIVE EDIT: Allow deleting links in deployed slices (will reboot affected VMs)
        is_deployed = slice_data.get("status") == "deployed"
        
        try:
            # Find the link
            link_to_delete = None
            link_index = None
            for idx, link in enumerate(slice_data.get("links", [])):
                if link.get("link_id") == link_id:
                    link_to_delete = link
                    link_index = idx
                    break
            
            if not link_to_delete:
                return False, "Link not found"
            
            vm1_id = link_to_delete.get("vm1_id")
            vm2_id = link_to_delete.get("vm2_id")
            vm1_iface_name = link_to_delete.get("vm1_interface")
            vm2_iface_name = link_to_delete.get("vm2_interface")
            vlan_id = link_to_delete.get("vlan_id")
            
            # Find VMs
            vm1_dict = next((v for v in slice_data.get("vms", []) if v["vm_id"] == vm1_id), None)
            vm2_dict = next((v for v in slice_data.get("vms", []) if v["vm_id"] == vm2_id), None)
            
            if not vm1_dict or not vm2_dict:
                return False, "VMs not found"
            
            # Remove interfaces from both VMs
            vm1_dict["interfaces"] = [iface for iface in vm1_dict["interfaces"] if iface.get("name") != vm1_iface_name]
            vm2_dict["interfaces"] = [iface for iface in vm2_dict["interfaces"] if iface.get("name") != vm2_iface_name]
            
            # Remove link from slice
            slice_data["links"].pop(link_index)
            
            # Return VLAN to pool
            if vlan_id in slice_data.get("vlan_pool_used", []):
                slice_data["vlan_pool_used"].remove(vlan_id)
            
            # Save changes
            self.db.update_slice(slice_id, slice_data)
            
            logger.info(f"Link {link_id} deleted: VM{vm1_id}.{vm1_iface_name} <-> VM{vm2_id}.{vm2_iface_name} (VLAN {vlan_id})")
            
            # LIVE EDIT: Reboot VMs to apply configuration changes
            if is_deployed:
                logger.info(f"LIVE EDIT: Rebooting VMs {vm1_id} and {vm2_id} to remove link")
                
                # Reboot VM1
                reboot1_success = self._reboot_vm(vm1_dict)
                if not reboot1_success:
                    logger.warning(f"LIVE EDIT: VM {vm1_id} reboot had issues, but continuing...")
                
                # Reboot VM2
                reboot2_success = self._reboot_vm(vm2_dict)
                if not reboot2_success:
                    logger.warning(f"LIVE EDIT: VM {vm2_id} reboot had issues, but continuing...")
                
                # Save updated slice data with new VM statuses
                self.db.update_slice(slice_id, slice_data)
                
                logger.info(f"LIVE EDIT: VMs rebooted without deleted link")
                
                # Clean up network infrastructure if no other VMs use this VLAN
                network_provider = self._get_network_provider(slice_data.get("availability_zone", "linux"))
                network_provider.delete_network(vlan_id)
                logger.info(f"VLAN {vlan_id} infrastructure cleaned up")
            
            return True, {"link_id": link_id, "message": "Link deleted successfully"}
        except Exception as e:
            logger.error(f"Link deletion error: {e}")
            return False, str(e)
    
    def deploy_slice(self, username, slice_id):
        """Deploy slice using pluggable providers based on availability zone"""
        slice_data = self.db.get_slice(str(slice_id))
        
        if not slice_data or slice_data.get("owner") != username:
            return False, "Slice not found or not authorized"
        
        if slice_data.get("status") == "deployed":
            return False, "Slice already deployed"
        
        try:
            availability_zone = slice_data.get("availability_zone", "linux")
            compute_provider = self._get_compute_provider(availability_zone)
            network_provider = self._get_network_provider(availability_zone)
            
            # Set bind address for SSH connections
            self._set_bind_address(availability_zone)
            
            logger.info(f"Deploying slice {slice_id} to availability zone: {availability_zone}")
            
            # === PHASE 1: Calculate VM Placement using Genetic Algorithm ===
            vms_to_place = []
            for vm_dict in slice_data.get("vms", []):
                if vm_dict.get("worker_ip") == "PENDING":
                    vms_to_place.append({
                        'vm_id': vm_dict['vm_id'],
                        'flavor': vm_dict['flavor']
                    })
            
            if vms_to_place:
                # OpenStack uses Nova scheduler - skip GA placement
                if availability_zone == "openstack":
                    logger.info(f"OpenStack cluster: Nova scheduler will handle placement for {len(vms_to_place)} VMs")
                    # For OpenStack, worker_ip stays as "PENDING" - Nova decides during deployment
                else:
                    # Linux cluster: Use GA for placement
                    logger.info(f"Calculating placement for {len(vms_to_place)} VMs using GA...")
                    
                    if self.linux_placement_ga and self.monitoring_system:
                        # Use Genetic Algorithm for optimal placement
                        placement, explanation = self.linux_placement_ga.calculate_placement(vms_to_place)
                        logger.info(f"GA Placement result: {placement}")
                        logger.info(explanation)
                        
                        # Apply placement to VMs
                        for vm_dict in slice_data.get("vms", []):
                            if vm_dict['vm_id'] in placement:
                                vm_dict['worker_ip'] = placement[vm_dict['vm_id']]
                                logger.info(f"VM {vm_dict['vm_id']} assigned to worker {vm_dict['worker_ip']}")
                    else:
                        # Fallback to round-robin if GA not available
                        logger.warning("GA not available, using round-robin fallback")
                        for vm_dict in slice_data.get("vms", []):
                            if vm_dict.get("worker_ip") == "PENDING":
                                vm_dict['worker_ip'] = self.get_next_worker(availability_zone)
                    
                    # Save updated placement
                    self.db.update_slice(slice_id, slice_data)
            
            # === PHASE 2: Deploy Infrastructure ===
            # LINUX CLUSTER DEPLOYMENT
            if availability_zone == "linux":
                # 1. Configure VLAN 400 DHCP for internet access (gateway already exists)
                has_internet = any(
                    any(iface.get("vlan_id") == 400 for iface in vm.get("interfaces", []))
                    for vm in slice_data.get("vms", [])
                )
                
                if has_internet:
                    logger.info("Configuring DHCP for VLAN 400 (IP range: 10.60.8.129-254, gateway: 10.60.8.254)")
                    network_provider.delete_network(400)  # Cleanup previous
                    success = network_provider.create_network(
                        400, "10.60.8.128/25", "10.60.8.254", 
                        dhcp_enabled=True, create_gateway=False  # Gateway already exists externally
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
                    success = network_provider.create_network(
                        vlan_id, cidr, gateway_ip, dhcp_enabled=True
                    )
                    
                    if not success:
                        logger.error(f"Failed to configure VLAN {vlan_id}")
                        return False, f"Failed to configure VLAN {vlan_id}"
                
                # 2.5. Add VLANs to trunk ports (only for workers hosting VMs)
                logger.info("Configuring VLAN trunk ports for active workers")
                self.vlan_trunk_manager.add_slice_vlans_to_trunks(slice_data)
                
                # 3. Create QCOW2 images and cloud-init seeds for all VMs
                from cloudinit_seed import CloudInitSeedGenerator
                seed_generator = CloudInitSeedGenerator(self.compute_provider.executor)
                
                for vm_dict in slice_data.get("vms", []):
                    worker_ip = vm_dict.get("worker_ip")
                    vm_name = vm_dict.get("name")
                    vm_id = vm_dict.get("vm_id")
                    flavor = vm_dict.get("flavor")
                    interfaces = vm_dict.get("interfaces", [])
                    
                    # Create QCOW2 image if not created yet
                    if not vm_dict.get("qcow_image"):
                        from models import Flavor
                        flavor_spec = Flavor.get(flavor)
                        image_path = flavor_spec.get("image") if flavor_spec else None
                        
                        if image_path:
                            logger.info(f"Creating QCOW2 image for VM {vm_id} ({vm_name}) on {worker_ip}")
                            from qcow_manager import QCOWManager
                            qcow_mgr = QCOWManager(self.compute_provider.executor)
                            success, qcow_img = qcow_mgr.create_backing_image(
                                worker_ip, slice_id, vm_id, vm_name, image_path, []
                            )
                            if success:
                                vm_dict["qcow_image"] = qcow_img
                                logger.info(f"QCOW2 image created: {qcow_img}")
                            else:
                                logger.error(f"Failed to create QCOW2 image for VM {vm_id}")
                                return False, f"Failed to create QCOW2 image for VM {vm_id}"
                    
                    # Generate cloud-init seed ISO for automatic network configuration
                    logger.info(f"Generating cloud-init seed for VM {vm_id} ({vm_name})")
                    success, seed_iso = seed_generator.generate_seed_iso(
                        worker_ip, vm_id, vm_name, interfaces
                    )
                    if success:
                        vm_dict["seed_iso"] = seed_iso
                        logger.info(f"Cloud-init seed created: {seed_iso}")
                    else:
                        logger.warning(f"Failed to create cloud-init seed for VM {vm_id}, continuing without it")
                
                # 4. Launch all VMs using compute provider
                for vm_dict in slice_data.get("vms", []):
                    worker_ip = vm_dict.get("worker_ip")
                    logger.info(f"Deploying VM {vm_dict['vm_id']} on {worker_ip}")
                    
                    success, pid = compute_provider.launch_vm(worker_ip, vm_dict)
                    if success:
                        vm_dict["status"] = "deployed"
                        vm_dict["pid"] = pid
                        logger.info(f"VM {vm_dict['vm_id']} started with PID {pid}")
                    else:
                        logger.error(f"Failed to start VM {vm_dict['vm_id']}")
                        return False, f"Failed to start VM {vm_dict['vm_id']}"
            
            # OPENSTACK CLUSTER DEPLOYMENT
            elif availability_zone == "openstack":
                logger.info("=== OPENSTACK DEPLOYMENT ===")
                logger.info(f"Using OpenStack APIs for parallel deployment")
                
                # OpenStack uses its own Nova scheduler - no manual placement needed
                # VMs will be placed automatically by Nova based on available resources
                
                # === PHASE 1: Parallel Network Creation ===
                logger.info("PHASE 1: Creating networks in parallel...")
                
                # Prepare network specifications for all links
                network_specs = []
                for link in slice_data.get("links", []):
                    vlan_id = link.get("vlan_id")
                    
                    # Allocate subnet from pool (similar to Neutron's own allocation)
                    subnets = network_provider.allocate_subnets(count=1)
                    if not subnets:
                        logger.error(f"Failed to allocate subnet for VLAN {vlan_id}")
                        return False, f"Failed to allocate subnet for link"
                    
                    subnet_network = subnets[0]
                    gateway_ip = str(list(subnet_network.hosts())[0])  # First usable IP
                    
                    network_specs.append({
                        "vlan_id": vlan_id,
                        "cidr": str(subnet_network),
                        "gateway_ip": gateway_ip,
                        "dhcp_enabled": True,
                    })
                
                # Create all networks in parallel
                if network_specs:
                    network_results = network_provider.create_networks_parallel(network_specs)
                    
                    # Check for failures
                    failed_networks = [
                        vlan_id for vlan_id, (success, _, _) in network_results.items()
                        if not success
                    ]
                    
                    if failed_networks:
                        logger.error(f"Failed to create networks for VLANs: {failed_networks}")
                        return False, f"Failed to create networks: {failed_networks}"
                    
                    # Store network/subnet IDs in links
                    for link in slice_data.get("links", []):
                        vlan_id = link.get("vlan_id")
                        if vlan_id in network_results:
                            success, network_id, subnet_id = network_results[vlan_id]
                            link["network_id"] = network_id
                            link["subnet_id"] = subnet_id
                    
                    logger.info(f"Created {len(network_specs)} networks in parallel")
                
                # === PHASE 2: Prepare Network Information for VMs ===
                logger.info("PHASE 2: Preparing network configurations for VMs...")
                
                # For OpenStack, we'll let Nova auto-create ports during VM creation
                # This avoids port binding race conditions
                
                for vm_dict in slice_data.get("vms", []):
                    vm_name = vm_dict.get("name")
                    vm_id = vm_dict.get("vm_id")
                    interfaces = vm_dict.get("interfaces", [])
                    
                    # Build network list for Nova (network IDs, not ports)
                    vm_networks = []
                    
                    for iface in interfaces:
                        vlan_id = iface.get("vlan_id")
                        link_id = iface.get("link_id")
                        
                        # Internet network (VLAN 400)
                        if vlan_id == 400:
                            # Use external network ID directly
                            internet_net_id = network_provider.get_internet_network_id()
                            if internet_net_id:
                                vm_networks.append({
                                    "network_id": internet_net_id,
                                    "interface_name": iface.get("name")
                                })
                                logger.info(f"VM {vm_name}: Will attach to external network (internet)")
                            else:
                                logger.warning(f"VM {vm_name}: Internet network not found, skipping")
                            continue
                        
                        # Topology network (inter-VM links)
                        link = next((l for l in slice_data.get("links", []) if l.get("link_id") == link_id), None)
                        if not link:
                            logger.warning(f"Link {link_id} not found for interface {iface.get('name')}")
                            continue
                        
                        network_id = link.get("network_id")
                        
                        if not network_id:
                            logger.error(f"Network not found for VLAN {vlan_id}")
                            return False, f"Network not ready for VLAN {vlan_id}"
                        
                        vm_networks.append({
                            "network_id": network_id,
                            "interface_name": iface.get("name")
                        })
                        logger.info(f"VM {vm_name}: Will attach to network {network_id}")
                    
                    # Store network list in VM dict for use during creation
                    vm_dict["openstack_networks"] = vm_networks
                    logger.info(f"VM {vm_name}: Prepared {len(vm_networks)} network attachment(s)")
                
                # Save updated slice data with ports
                self.db.update_slice(slice_id, slice_data)
                
                # === PHASE 3: Parallel VM Creation ===
                logger.info("PHASE 3: Launching VMs in parallel...")
                
                # Initialize resource mapper for image/flavor ID resolution
                from openstack_clients.resource_mapper import OpenStackResourceMapper
                resource_mapper = OpenStackResourceMapper(compute_provider.connection)
                
                # Prepare VM assignments for parallel deployment
                vm_assignments = []
                for vm_dict in slice_data.get("vms", []):
                    # OpenStack: worker_ip is ignored, Nova scheduler decides placement
                    # Map local flavor name to OpenStack Glance image ID and Nova flavor ID
                    local_flavor_name = vm_dict.get("flavor")
                    
                    # Get Glance image ID
                    image_id = resource_mapper.get_image_id(local_flavor_name)
                    if not image_id:
                        logger.error(f"Could not find Glance image for flavor '{local_flavor_name}'")
                        return False, f"No Glance image available for flavor '{local_flavor_name}'"
                    
                    # Get Nova flavor ID
                    flavor_id = resource_mapper.get_flavor_id(local_flavor_name)
                    if not flavor_id:
                        logger.error(f"Could not find Nova flavor for '{local_flavor_name}'")
                        return False, f"No Nova flavor available for '{local_flavor_name}'"
                    
                    vm_dict["image_id"] = image_id
                    vm_dict["flavor_id"] = flavor_id
                    
                    logger.info(f"VM {vm_dict.get('name')}: Using image {image_id}, flavor {flavor_id}")
                    
                    vm_assignments.append(("nova", vm_dict))  # "nova" is placeholder for worker
                
                # Launch all VMs in parallel
                deployment_results = compute_provider.launch_vms_parallel(vm_assignments)
                
                # Process results
                failed_vms = []
                for vm_id, (success, server_id) in deployment_results.items():
                    vm_dict = next((v for v in slice_data.get("vms", []) if v["vm_id"] == vm_id), None)
                    if not vm_dict:
                        continue
                    
                    if success:
                        vm_dict["status"] = "deployed"
                        vm_dict["server_id"] = server_id
                        vm_dict["worker_ip"] = "openstack"  # Placeholder - actual host determined by Nova
                        logger.info(f"VM {vm_dict['name']} deployed successfully: {server_id}")
                    else:
                        vm_dict["status"] = "error"
                        failed_vms.append(vm_dict["name"])
                        logger.error(f"VM {vm_dict['name']} deployment failed")
                
                if failed_vms:
                    logger.warning(f"Some VMs failed to deploy: {failed_vms}")
                    # Don't fail entire deployment - partial deployment is acceptable
                    # This is part of the "error isolation" design
                
                logger.info(f"OpenStack deployment completed: {len(deployment_results) - len(failed_vms)}/{len(deployment_results)} VMs deployed")
            
            else:
                return False, f"Unknown availability zone: {availability_zone}"
            
            slice_data["status"] = "deployed"
            self.db.update_slice(slice_id, slice_data)
            
            logger.info(f"Slice {slice_id} deployed successfully on {availability_zone} cluster")
            return True, f"Slice deployed successfully on {availability_zone} cluster"
        except Exception as e:
            logger.error(f"Deploy error: {e}")
            return False, str(e)
    
    def deploy_slice_edition(self, username, slice_id):
        """
        Deploy only the pending VMs in an already deployed slice (Deploy Edition)
        This is used when users add new VMs/topologies to a deployed slice
        
        NEW: Also applies pending links (in "design" state) by:
        1. Configuring DHCP networks for design-state links FIRST
        2. Deploying/rebooting VMs so they get IPs on new interfaces
        3. Marking links as "deployed"
        """
        slice_data = self.db.get_slice(str(slice_id))
        
        if not slice_data or slice_data.get("owner") != username:
            return False, "Slice not found or not authorized"
        
        if slice_data.get("status") != "deployed":
            return False, "Slice must be deployed to use Deploy Edition"
        
        try:
            availability_zone = slice_data.get("availability_zone", "linux")
            compute_provider = self._get_compute_provider(availability_zone)
            network_provider = self._get_network_provider(availability_zone)
            
            # Set bind address for SSH connections
            self._set_bind_address(availability_zone)
            
            logger.info(f"Deploy Edition: deploying pending VMs and links in slice {slice_id}")
            
            # Find VMs that need deployment (status != deployed OR worker_ip == PENDING)
            pending_vms = [vm for vm in slice_data.get("vms", []) 
                          if vm.get("status") != "deployed" or vm.get("worker_ip") == "PENDING"]
            
            # Find links in design state
            pending_links = [link for link in slice_data.get("links", [])
                           if link.get("status") == "design"]
            
            # Find VMs affected by pending links (need reboot to get IPs)
            vms_needing_reboot = set()
            for link in pending_links:
                vms_needing_reboot.add(link.get("vm1_id"))
                vms_needing_reboot.add(link.get("vm2_id"))
            
            if not pending_vms and not pending_links:
                logger.info(f"No pending VMs or links found in slice {slice_id}")
                return True, "No pending VMs or links to deploy"
            
            logger.info(f"Found {len(pending_vms)} pending VMs and {len(pending_links)} pending links to deploy")
            logger.info(f"{len(vms_needing_reboot)} VMs will be rebooted to apply new links")
            
            # === PHASE 1: Configure DHCP networks for pending links FIRST ===
            if pending_links and availability_zone == "linux":
                logger.info("PHASE 1: Configuring DHCP networks for pending links...")
                
                for link in pending_links:
                    vlan_id = link.get("vlan_id")
                    cidr = f"192.168.{vlan_id % 256}.0/24"
                    gateway_ip = f"192.168.{vlan_id % 256}.1"
                    
                    logger.info(f"Configuring VLAN {vlan_id} for Link {link.get('link_id')} (BEFORE VM deployment)")
                    success = network_provider.create_network(
                        vlan_id, cidr, gateway_ip, dhcp_enabled=True
                    )
                    
                    if not success:
                        logger.error(f"Failed to configure VLAN {vlan_id} for link {link.get('link_id')}")
                        return False, f"Failed to configure VLAN {vlan_id}"
                
                # Update VLAN trunk ports for new VLANs
                logger.info("Updating VLAN trunk ports for new links...")
                self.vlan_trunk_manager.add_slice_vlans_to_trunks(slice_data)
            
            # === PHASE 2: Calculate VM Placement for pending VMs only ===
            vms_to_place = []
            for vm_dict in pending_vms:
                if vm_dict.get("worker_ip") == "PENDING":
                    vms_to_place.append({
                        'vm_id': vm_dict['vm_id'],
                        'flavor': vm_dict['flavor']
                    })
            
            if vms_to_place:
                logger.info(f"Calculating placement for {len(vms_to_place)} VMs...")
                
                placement_ga = self.linux_placement_ga if availability_zone == "linux" else None
                
                if placement_ga and self.monitoring_system:
                    # Use Genetic Algorithm
                    placement, explanation = placement_ga.calculate_placement(vms_to_place)
                    logger.info(f"GA Placement result: {placement}")
                    
                    # Apply placement
                    for vm_dict in pending_vms:
                        if vm_dict['vm_id'] in placement:
                            vm_dict['worker_ip'] = placement[vm_dict['vm_id']]
                            logger.info(f"VM {vm_dict['vm_id']} assigned to worker {vm_dict['worker_ip']}")
                else:
                    # Fallback to round-robin
                    logger.warning("GA not available, using round-robin fallback")
                    for vm_dict in pending_vms:
                        if vm_dict.get("worker_ip") == "PENDING":
                            vm_dict['worker_ip'] = self.get_next_worker(availability_zone)
                
                # Save updated placement
                self.db.update_slice(slice_id, slice_data)
            
            # === PHASE 3: Deploy pending VMs ===
            if pending_vms and availability_zone == "linux":
                logger.info("PHASE 3: Deploying pending VMs...")
                # Create QCOW2 images and cloud-init seeds
                from cloudinit_seed import CloudInitSeedGenerator
                seed_generator = CloudInitSeedGenerator(self.compute_provider.executor)
                
                for vm_dict in pending_vms:
                    worker_ip = vm_dict.get("worker_ip")
                    vm_name = vm_dict.get("name")
                    vm_id = vm_dict.get("vm_id")
                    flavor = vm_dict.get("flavor")
                    interfaces = vm_dict.get("interfaces", [])
                    
                    # Create QCOW2 if not exists
                    if not vm_dict.get("qcow_image"):
                        from models import Flavor
                        flavor_spec = Flavor.get(flavor)
                        image_path = flavor_spec.get("image") if flavor_spec else None
                        
                        if image_path:
                            logger.info(f"Creating QCOW2 image for VM {vm_id} ({vm_name}) on {worker_ip}")
                            from qcow_manager import QCOWManager
                            qcow_mgr = QCOWManager(self.compute_provider.executor)
                            success, qcow_img = qcow_mgr.create_backing_image(
                                worker_ip, slice_id, vm_id, vm_name, image_path, []
                            )
                            if success:
                                vm_dict["qcow_image"] = qcow_img
                            else:
                                logger.error(f"Failed to create QCOW2 for VM {vm_id}")
                                continue
                    
                    # Generate cloud-init seed
                    logger.info(f"Generating cloud-init seed for VM {vm_id} ({vm_name})")
                    success, seed_iso = seed_generator.generate_seed_iso(
                        worker_ip, vm_id, vm_name, interfaces
                    )
                    if success:
                        vm_dict["seed_iso"] = seed_iso
                    
                    # Launch VM
                    logger.info(f"Deploying VM {vm_id} on {worker_ip}")
                    success, pid = compute_provider.launch_vm(worker_ip, vm_dict)
                    
                    if success:
                        vm_dict["status"] = "deployed"
                        vm_dict["pid"] = pid
                        logger.info(f"VM {vm_id} started with PID {pid}")
                    else:
                        logger.error(f"Failed to start VM {vm_id}")
                        return False, f"Failed to start VM {vm_id}"
            
            # === PHASE 4: Reboot VMs affected by pending links (so they get IPs) ===
            if pending_links and vms_needing_reboot:
                logger.info(f"PHASE 4: Rebooting {len(vms_needing_reboot)} VMs to apply new links...")
                
                for vm_id in vms_needing_reboot:
                    # Find VM dict
                    vm_dict = next((v for v in slice_data.get("vms", []) if v["vm_id"] == vm_id), None)
                    if vm_dict and vm_dict.get("status") == "deployed" and vm_dict.get("worker_ip") != "PENDING":
                        logger.info(f"Rebooting VM {vm_id} to apply new link interfaces...")
                        reboot_success = self._reboot_vm(vm_dict)
                        if not reboot_success:
                            logger.warning(f"VM {vm_id} reboot had issues, but continuing...")
                
                # Mark all pending links as deployed
                for link in pending_links:
                    link["status"] = "deployed"
                    logger.info(f"Link {link.get('link_id')} marked as deployed (VLAN {link.get('vlan_id')})")
            
            # Save final state
            self.db.update_slice(slice_id, slice_data)
            
            result_msg = []
            if pending_vms:
                result_msg.append(f"{len(pending_vms)} VMs deployed")
            if pending_links:
                result_msg.append(f"{len(pending_links)} links applied")
            
            final_msg = " and ".join(result_msg) + " successfully"
            logger.info(f"Deploy Edition completed: {final_msg}")
            return True, final_msg
            
        except Exception as e:
            logger.error(f"Deploy Edition error: {e}")
            return False, str(e)
    
    def delete_slice(self, username, slice_id):
        """Delete slice using pluggable providers based on availability zone"""
        try:
            slice_data = self.db.get_slice(str(slice_id))
            if not slice_data or slice_data.get("owner") != username:
                return False, "Slice not found or not authorized"
            
            user = self.db.get_user(username)
            vm_count = len(slice_data.get("vms", []))
            availability_zone = slice_data.get("availability_zone", "linux")
            
            compute_provider = self._get_compute_provider(availability_zone)
            network_provider = self._get_network_provider(availability_zone)
            
            # Set bind address for SSH connections
            self._set_bind_address(availability_zone)
            
            # Stop VMs if deployed
            if slice_data.get("status") == "deployed":
                if availability_zone == "linux":
                    for vm_dict in slice_data.get("vms", []):
                        worker_ip = vm_dict.get("worker_ip")
                        vm_id = vm_dict.get("vm_id")
                        
                        # Stop VM
                        compute_provider.stop_vm(worker_ip, vm_dict)
                        
                        # Cleanup TAP interfaces on worker
                        self.vlan_trunk_manager.cleanup_worker_tap_interfaces(worker_ip, vm_id)
                    
                    # Cleanup VLANs on network node
                    vlan_list = []
                    for link in slice_data.get("links", []):
                        vlan_id = link.get("vlan_id")
                        network_provider.delete_network(vlan_id)
                        vlan_list.append(vlan_id)
                    
                    # Cleanup orphaned VLAN ports on network node
                    network_node_ip = self.clusters[availability_zone].get("network_node")
                    self.vlan_trunk_manager.cleanup_network_node_vlans(network_node_ip, vlan_list)
                    
                    # Remove VLANs from physical switch trunks
                    self.vlan_trunk_manager.remove_slice_vlans_from_trunks(slice_data)
                
                elif availability_zone == "openstack":
                    logger.warning("OpenStack cleanup - STUB NOT IMPLEMENTED")
                    # TODO: Delete instances, ports, networks via OpenStack APIs
            
            # Delete QCOW images (Linux cluster only)
            if availability_zone == "linux":
                for vm_dict in slice_data.get("vms", []):
                    self.deployment_api.delete_vm_dict(vm_dict)
            
            self.db.delete_slice(slice_id)
            
            if "slices" in user and slice_id in user["slices"]:
                user["slices"].remove(slice_id)
            user["used_vms"] = max(0, user.get("used_vms", 0) - vm_count)
            self.db.update_user(username, user)
            
            # Run infrastructure cleanup to sync VLAN trunks
            logger.info("Running infrastructure cleanup after slice deletion...")
            try:
                from infrastructure_cleanup import InfrastructureCleanup
                cleanup = InfrastructureCleanup(self.db, self.compute_provider.executor, self.vlan_trunk_manager)
                cleanup.cleanup_all()
                logger.info("Infrastructure cleanup completed")
            except Exception as e:
                logger.warning(f"Infrastructure cleanup error: {e}")
            
            logger.info(f"Slice {slice_id} deleted from {availability_zone} cluster")
            return True, "Slice deleted"
        except Exception as e:
            logger.error(f"Delete error: {e}")
            return False, str(e)
    
    def update_vm(self, username, slice_id, vm_id, updates):
        """
        Update VM properties
        
        LIVE EDIT: In deployed state, only internet_enabled can be changed (triggers VM reboot)
        In design state, all properties can be changed
        """
        try:
            slice_data = self.db.get_slice(str(slice_id))
            if not slice_data or slice_data.get("owner") != username:
                return False, "Slice not found or not authorized"
            
            is_deployed = slice_data.get("status") == "deployed"
            
            vm_dict = next((v for v in slice_data.get("vms", []) if v["vm_id"] == vm_id), None)
            if not vm_dict:
                return False, "VM not found"
            
            # In deployed state, only allow internet changes
            if is_deployed:
                if "internet_enabled" not in updates:
                    return False, "Only internet settings can be changed in deployed state"
                
                if "vm_name" in updates or "flavor" in updates:
                    return False, "Cannot change VM name or flavor in deployed state"
            
            # Update allowed fields
            if "vm_name" in updates and not is_deployed:
                vm_dict["name"] = updates["vm_name"]
            
            if "flavor" in updates and not is_deployed:
                vm_dict["flavor"] = updates["flavor"]
            
            if "internet_enabled" in updates:
                # Update internet interface (VLAN 400)
                mgmt_iface = vm_dict["interfaces"][0]
                
                if updates["internet_enabled"]:
                    # Enable internet on VLAN 400
                    mgmt_iface["vlan_id"] = 400
                    # Note: IP will be assigned by DHCP, no static config needed
                    mgmt_iface["ip_config"] = None
                else:
                    # Disable internet (no VLAN)
                    mgmt_iface["vlan_id"] = None
                    mgmt_iface["ip_config"] = None
                
                # LIVE EDIT: Reboot VM to apply internet changes if deployed
                if is_deployed:
                    logger.info(f"LIVE EDIT: Rebooting VM {vm_id} to apply internet configuration change")
                    reboot_success = self._reboot_vm(vm_dict)
                    
                    if not reboot_success:
                        logger.warning(f"LIVE EDIT: VM {vm_id} reboot had issues")
            
            self.db.update_slice(slice_id, slice_data)
            logger.info(f"VM {vm_id} updated in slice {slice_id}")
            return True, vm_dict
        except Exception as e:
            logger.error(f"Update VM error: {e}")
            return False, str(e)
    
    def create_topology_preset(self, username, slice_id, topology_type, num_vms, flavor, internet, base_name):
        """Create predefined topology (ring, bus, star, mesh) - supports live editing"""
        try:
            slice_data = self.db.get_slice(str(slice_id))
            if not slice_data or slice_data.get("owner") != username:
                return False, "Slice not found or not authorized"
            
            # Allow topology creation in deployed slices (VMs will be in "design" state)
            # User must click "Deploy Edition" to deploy the new topology
            
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
            
            # Create VMs with auto-naming to continue sequence
            created_vms = []
            for vm_cfg in vms_config:
                success, vm_dict = self.add_vm_to_slice(
                    username, slice_id, vm_cfg['name'], vm_cfg['flavor'], vm_cfg['internet_enabled'], auto_name=True
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
