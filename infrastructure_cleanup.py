"""
Infrastructure Cleanup Utility
Detects and removes orphaned network configurations
"""
import logging
from database import Database
from remote_executor import RemoteExecutor
from vlan_trunk_manager import VLANTrunkManager

logger = logging.getLogger(__name__)


class InfrastructureCleanup:
    """
    Cleanup orphaned infrastructure resources
    
    Responsibilities:
    - Detect orphaned VLAN ports on network node
    - Detect orphaned TAP interfaces on workers
    - Sync physical switch and worker trunk configurations
    """
    
    def __init__(self, db, executor, vlan_manager):
        self.db = db
        self.executor = executor
        self.vlan_manager = vlan_manager
        
        # Cluster configuration
        clusters = db.data.get("clusters", {})
        self.linux_cluster = clusters.get("linux", {})
        self.network_node = self.linux_cluster.get("network_node")
        self.workers = self.linux_cluster.get("workers", [])
    
    def cleanup_all(self):
        """Run complete cleanup of orphaned resources"""
        logger.info("Starting infrastructure cleanup...")
        
        # Get active VLANs from database
        active_vlans = self._get_active_vlans()
        logger.info(f"Active VLANs from deployed slices: {sorted(active_vlans)}")
        
        # Cleanup network node
        self._cleanup_network_node(active_vlans)
        
        # Cleanup workers
        for worker_ip in self.workers:
            self._cleanup_worker(worker_ip)
        
        # Sync trunk configurations
        self._sync_trunk_configurations(active_vlans)
        
        logger.info("Infrastructure cleanup completed")
    
    def _get_active_vlans(self):
        """
        Get all VLANs currently in use by deployed slices
        
        Returns:
            set: Set of active VLAN IDs
        """
        active_vlans = {100, 400}  # Always keep management and internet VLANs
        
        for slice_id, slice_data in self.db.data.get('slices', {}).items():
            if slice_data.get('status') == 'deployed':
                # Get VLANs from links
                for link in slice_data.get('links', []):
                    vlan_id = link.get('vlan_id')
                    if vlan_id:
                        active_vlans.add(vlan_id)
                
                # Get VLANs from VM interfaces
                for vm in slice_data.get('vms', []):
                    for iface in vm.get('interfaces', []):
                        vlan_id = iface.get('vlan_id')
                        if vlan_id:
                            active_vlans.add(vlan_id)
        
        return active_vlans
    
    def _cleanup_network_node(self, active_vlans):
        """
        Cleanup orphaned VLAN configurations on network node
        
        Args:
            active_vlans: Set of VLANs that should be kept
        """
        if not self.network_node:
            return
        
        logger.info(f"Cleaning up network node {self.network_node}")
        
        # Get all DHCP ports
        cmd = "sudo ovs-vsctl list-ports br-provider | grep '^dhcp_v'"
        success, output = self.executor.execute_direct(self.network_node, cmd, timeout=10)
        
        if success and output.strip():
            dhcp_ports = output.strip().split('\n')
            for port_name in dhcp_ports:
                port_name = port_name.strip()
                if port_name.startswith('dhcp_v'):
                    # Extract VLAN ID
                    vlan_id = int(port_name.replace('dhcp_v', ''))
                    
                    # If VLAN is not active, remove it
                    if vlan_id not in active_vlans:
                        logger.info(f"Removing orphaned VLAN {vlan_id} from network node")
                        self.vlan_manager.cleanup_network_node_vlans(self.network_node, [vlan_id])
        
        # Configure network node uplink to allow active VLANs
        self._configure_network_node_uplink(active_vlans)
    
    def _configure_network_node_uplink(self, active_vlans):
        """
        Configure network node's br-provider uplink port (ens4) to allow active VLANs
        
        Args:
            active_vlans: Set of VLANs to allow
        """
        if not self.network_node:
            return
        
        logger.info(f"Configuring network node uplink with VLANs: {sorted(active_vlans)}")
        
        # Get current trunks
        cmd = "sudo ovs-vsctl get port ens4 trunks"
        success, output = self.executor.execute_direct(self.network_node, cmd, timeout=10)
        
        if success:
            vlans_str = ','.join(map(str, sorted(active_vlans)))
            cmd = f"sudo ovs-vsctl set port ens4 trunks={vlans_str}"
            success, _ = self.executor.execute_direct(self.network_node, cmd, timeout=10)
            
            if success:
                logger.info(f"Network node uplink configured with VLANs: {sorted(active_vlans)}")
    
    def _cleanup_worker(self, worker_ip):
        """
        Cleanup orphaned TAP interfaces on a worker
        
        Args:
            worker_ip: Worker IP address
        """
        logger.info(f"Cleaning up worker {worker_ip}")
        
        # Get all TAP interfaces
        cmd = "sudo ovs-vsctl list-ports br-provider | grep '^tap_'"
        success, output = self.executor.execute_direct(worker_ip, cmd, timeout=10)
        
        if success and output.strip():
            tap_interfaces = output.strip().split('\n')
            
            # Get all active VM IDs
            active_vm_ids = set()
            for slice_id, slice_data in self.db.data.get('slices', {}).items():
                if slice_data.get('status') == 'deployed':
                    for vm in slice_data.get('vms', []):
                        if vm.get('worker_ip') == worker_ip:
                            active_vm_ids.add(vm.get('vm_id'))
            
            # Remove TAP interfaces for non-active VMs
            for tap_name in tap_interfaces:
                tap_name = tap_name.strip()
                if tap_name.startswith('tap_'):
                    # Extract VM ID from tap_VMID_interface
                    parts = tap_name.split('_')
                    if len(parts) >= 2:
                        try:
                            vm_id = int(parts[1])
                            if vm_id not in active_vm_ids:
                                logger.info(f"Removing orphaned TAP interface {tap_name} on {worker_ip}")
                                
                                # Delete from OVS
                                cmd = f"sudo ovs-vsctl --if-exists del-port br-provider {tap_name}"
                                self.executor.execute_direct(worker_ip, cmd)
                                
                                # Delete TAP device
                                cmd = f"sudo ip link del {tap_name} 2>/dev/null || true"
                                self.executor.execute_direct(worker_ip, cmd)
                        except ValueError:
                            pass
    
    def _sync_trunk_configurations(self, active_vlans):
        """
        Sync physical switch and worker trunk configurations
        
        Only add VLANs to workers that actually host VMs using those VLANs.
        Network node gets ALL active VLANs.
        
        Args:
            active_vlans: Set of active VLANs
        """
        logger.info("Syncing trunk configurations across infrastructure")
        
        # Get deployed slices to determine which workers need which VLANs
        worker_vlans = {}
        
        for slice_id, slice_data in self.db.data.get('slices', {}).items():
            if slice_data.get('status') == 'deployed':
                # Map VMs to workers and their VLANs
                for vm in slice_data.get('vms', []):
                    worker_ip = vm.get('worker_ip')
                    if worker_ip and worker_ip != "PENDING" and worker_ip in self.workers:
                        if worker_ip not in worker_vlans:
                            worker_vlans[worker_ip] = set()
                        
                        # Add VLANs from VM interfaces
                        for iface in vm.get('interfaces', []):
                            vlan_id = iface.get('vlan_id')
                            if vlan_id:
                                worker_vlans[worker_ip].add(vlan_id)
        
        # Configure physical switch trunk ports ONLY for workers with VMs
        for worker_ip in self.workers:
            port_name = self.vlan_manager._get_trunk_port_for_worker(worker_ip)
            if not port_name:
                continue
            
            # If worker has VMs, configure with its VLANs + management
            if worker_ip in worker_vlans:
                vlans_with_mgmt = worker_vlans[worker_ip] | {100, 400}
                vlans_str = ','.join(map(str, sorted(vlans_with_mgmt)))
                cmd = f"sudo ovs-vsctl set port {port_name} trunks={vlans_str}"
                success, _ = self.executor.execute_direct(
                    self.vlan_manager.physical_switch_ip, cmd, timeout=10
                )
                if success:
                    logger.info(f"Physical switch port {port_name} → worker {worker_ip}: VLANs {sorted(vlans_with_mgmt)}")
            else:
                # Worker has no VMs, only keep management VLANs
                vlans_str = '100,400'
                cmd = f"sudo ovs-vsctl set port {port_name} trunks={vlans_str}"
                success, _ = self.executor.execute_direct(
                    self.vlan_manager.physical_switch_ip, cmd, timeout=10
                )
                if success:
                    logger.info(f"Physical switch port {port_name} → worker {worker_ip}: VLANs [100, 400] (no VMs)")
        
        # Configure worker uplinks - only VLANs they need
        for worker_ip in self.workers:
            if worker_ip in worker_vlans:
                vlans_with_mgmt = worker_vlans[worker_ip] | {100, 400}
            else:
                vlans_with_mgmt = {100, 400}
            
            vlans_str = ','.join(map(str, sorted(vlans_with_mgmt)))
            cmd = f"sudo ovs-vsctl set port ens4 trunks={vlans_str}"
            success, _ = self.executor.execute_direct(worker_ip, cmd, timeout=10)
            if success:
                logger.info(f"Worker {worker_ip} uplink (ens4): VLANs {sorted(vlans_with_mgmt)}")
        
        # Configure network node uplink with ALL active VLANs
        self._configure_network_node_uplink(active_vlans)


def run_cleanup():
    """Standalone cleanup script"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    db = Database()
    executor = RemoteExecutor()
    vlan_manager = VLANTrunkManager(executor, "10.0.0.7")
    
    cleanup = InfrastructureCleanup(db, executor, vlan_manager)
    cleanup.cleanup_all()
    
    print("\nCleanup completed successfully!")


if __name__ == '__main__':
    run_cleanup()
