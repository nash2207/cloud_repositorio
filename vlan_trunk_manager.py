"""
VLAN Trunk Manager
Manages VLAN trunking on physical switch and worker nodes
"""
import logging

logger = logging.getLogger(__name__)


class VLANTrunkManager:
    """
    Manages VLAN trunk configuration on OVS bridges
    
    Responsibilities:
    - Add VLANs to trunk ports when slices are deployed
    - Remove VLANs from trunk ports when slices are deleted
    - Ensure network node uplink allows all necessary VLANs
    """
    
    def __init__(self, executor, physical_switch_ip):
        """
        Initialize VLAN trunk manager
        
        Args:
            executor: RemoteExecutor instance
            physical_switch_ip: IP of physical switch (ovs1)
        """
        self.executor = executor
        self.physical_switch_ip = physical_switch_ip
        
        # Physical switch trunk ports (connecting to workers and network node)
        self.trunk_ports = {
            'ens4': '10.0.0.1',  # Network node
            'ens5': '10.0.0.2',  # Worker 1
            'ens6': '10.0.0.3',  # Worker 2
            'ens7': '10.0.0.4'   # Worker 3
        }
        
        # Worker nodes (for configuring their uplink ports)
        self.worker_nodes = {
            '10.0.0.2': 'ens4',
            '10.0.0.3': 'ens4',
            '10.0.0.4': 'ens4'
        }
    
    def add_vlan_to_trunks(self, vlan_id):
        """
        Add VLAN to all trunk ports on physical switch
        
        Args:
            vlan_id: VLAN ID to add
        
        Returns:
            bool: Success status
        """
        try:
            for port_name in self.trunk_ports.keys():
                # Get current trunks
                cmd = f"sudo ovs-vsctl get port {port_name} trunks"
                success, output = self.executor.execute_direct(
                    self.physical_switch_ip, cmd, timeout=10
                )
                
                if not success:
                    logger.error(f"Failed to get trunks for {port_name}")
                    continue
                
                # Parse current VLANs
                current_vlans = self._parse_vlan_list(output)
                
                # Add new VLAN if not present
                if vlan_id not in current_vlans:
                    current_vlans.append(vlan_id)
                    current_vlans.sort()
                    
                    # Update trunk configuration
                    vlans_str = ','.join(map(str, current_vlans))
                    cmd = f"sudo ovs-vsctl set port {port_name} trunks={vlans_str}"
                    success, _ = self.executor.execute_direct(
                        self.physical_switch_ip, cmd, timeout=10
                    )
                    
                    if success:
                        logger.info(f"Added VLAN {vlan_id} to {port_name} trunk")
                    else:
                        logger.error(f"Failed to add VLAN {vlan_id} to {port_name}")
            
            return True
        except Exception as e:
            logger.error(f"Error adding VLAN {vlan_id} to trunks: {e}")
            return False
    
    def remove_vlan_from_trunks(self, vlan_id):
        """
        Remove VLAN from all trunk ports on physical switch
        
        Args:
            vlan_id: VLAN ID to remove
        
        Returns:
            bool: Success status
        """
        try:
            for port_name in self.trunk_ports.keys():
                # Get current trunks
                cmd = f"sudo ovs-vsctl get port {port_name} trunks"
                success, output = self.executor.execute_direct(
                    self.physical_switch_ip, cmd, timeout=10
                )
                
                if not success:
                    continue
                
                # Parse current VLANs
                current_vlans = self._parse_vlan_list(output)
                
                # Remove VLAN if present (keep VLAN 100 for management)
                if vlan_id in current_vlans and vlan_id != 100:
                    current_vlans.remove(vlan_id)
                    
                    # Update trunk configuration
                    vlans_str = ','.join(map(str, current_vlans))
                    cmd = f"sudo ovs-vsctl set port {port_name} trunks={vlans_str}"
                    success, _ = self.executor.execute_direct(
                        self.physical_switch_ip, cmd, timeout=10
                    )
                    
                    if success:
                        logger.info(f"Removed VLAN {vlan_id} from {port_name} trunk")
            
            return True
        except Exception as e:
            logger.error(f"Error removing VLAN {vlan_id} from trunks: {e}")
            return False
    
    def ensure_vlan_400_on_trunks(self):
        """
        Ensure VLAN 400 (internet) is always present on all trunks
        
        Returns:
            bool: Success status
        """
        return self.add_vlan_to_trunks(400)
    
    def add_slice_vlans_to_trunks(self, slice_data):
        """
        Add VLANs used by a slice to trunk ports (only for workers hosting VMs)
        
        Args:
            slice_data: Slice dictionary with VMs and links
        
        Returns:
            bool: Success status
        """
        try:
            # Collect which workers are used by which VLANs
            worker_vlans = {}  # {worker_ip: [vlan_ids]}
            
            # VLAN 400 (internet) - add to workers that have VMs
            for vm in slice_data.get('vms', []):
                worker_ip = vm.get('worker_ip')
                if worker_ip and worker_ip != "PENDING":
                    if worker_ip not in worker_vlans:
                        worker_vlans[worker_ip] = set()
                    # Check if VM has internet enabled
                    for iface in vm.get('interfaces', []):
                        vlan_id = iface.get('vlan_id')
                        if vlan_id:
                            worker_vlans[worker_ip].add(vlan_id)
            
            # Link VLANs - add to both workers hosting the connected VMs
            for link in slice_data.get('links', []):
                vlan_id = link.get('vlan_id')
                vm1_id = link.get('vm1_id')
                vm2_id = link.get('vm2_id')
                
                # Find workers for both VMs
                vm1 = next((v for v in slice_data.get('vms', []) if v['vm_id'] == vm1_id), None)
                vm2 = next((v for v in slice_data.get('vms', []) if v['vm_id'] == vm2_id), None)
                
                if vm1 and vm1.get('worker_ip') and vm1.get('worker_ip') != "PENDING":
                    if vm1['worker_ip'] not in worker_vlans:
                        worker_vlans[vm1['worker_ip']] = set()
                    worker_vlans[vm1['worker_ip']].add(vlan_id)
                
                if vm2 and vm2.get('worker_ip') and vm2.get('worker_ip') != "PENDING":
                    if vm2['worker_ip'] not in worker_vlans:
                        worker_vlans[vm2['worker_ip']] = set()
                    worker_vlans[vm2['worker_ip']].add(vlan_id)
            
            # Always add VLANs to network node (ens4)
            all_vlans = set()
            for vlans in worker_vlans.values():
                all_vlans.update(vlans)
            
            # Add VLANs to network node uplink trunk (on network node itself)
            if all_vlans:
                self._configure_network_node_uplink(all_vlans)
            
            # Add VLANs to network node trunk port on physical switch (ens4)
            for vlan_id in all_vlans:
                self._add_vlan_to_port('ens4', vlan_id)
            
            # Add VLANs to specific worker trunk ports (physical switch side)
            for worker_ip, vlans in worker_vlans.items():
                # Map worker IP to trunk port on physical switch
                port_name = self._get_trunk_port_for_worker(worker_ip)
                if port_name:
                    for vlan_id in vlans:
                        self._add_vlan_to_port(port_name, vlan_id)
                        logger.info(f"Added VLAN {vlan_id} to physical switch {port_name} (worker {worker_ip})")
                
                # Also configure worker's own uplink port
                self._configure_worker_uplink(worker_ip, vlans)
            
            return True
        except Exception as e:
            logger.error(f"Error adding slice VLANs to trunks: {e}")
            return False
    
    def _get_trunk_port_for_worker(self, worker_ip):
        """Get trunk port name for a worker IP"""
        for port_name, ip in self.trunk_ports.items():
            if ip == worker_ip:
                return port_name
        return None
    
    def _add_vlan_to_port(self, port_name, vlan_id):
        """Add VLAN to a specific trunk port"""
        try:
            # Get current trunks
            cmd = f"sudo ovs-vsctl get port {port_name} trunks"
            success, output = self.executor.execute_direct(
                self.physical_switch_ip, cmd, timeout=10
            )
            
            if not success:
                logger.error(f"Failed to get trunks for {port_name}")
                return False
            
            # Parse current VLANs
            current_vlans = self._parse_vlan_list(output)
            
            # Add new VLAN if not present
            if vlan_id not in current_vlans:
                current_vlans.append(vlan_id)
                current_vlans.sort()
                
                # Update trunk configuration
                vlans_str = ','.join(map(str, current_vlans))
                cmd = f"sudo ovs-vsctl set port {port_name} trunks={vlans_str}"
                success, _ = self.executor.execute_direct(
                    self.physical_switch_ip, cmd, timeout=10
                )
                
                return success
            return True
        except Exception as e:
            logger.error(f"Error adding VLAN {vlan_id} to {port_name}: {e}")
            return False
    
    def _configure_worker_uplink(self, worker_ip, vlans):
        """
        Configure worker's br-provider uplink port to allow VLANs
        
        Args:
            worker_ip: Worker IP address
            vlans: Set of VLAN IDs to allow
        
        Returns:
            bool: Success status
        """
        try:
            if worker_ip not in self.worker_nodes:
                return True
            
            uplink_port = self.worker_nodes[worker_ip]
            
            # Get current trunks on worker
            cmd = f"sudo ovs-vsctl get port {uplink_port} trunks"
            success, output = self.executor.execute_direct(worker_ip, cmd, timeout=10)
            
            if not success:
                logger.warning(f"Failed to get trunks for {uplink_port} on {worker_ip}")
                return False
            
            # Parse current VLANs
            current_vlans = self._parse_vlan_list(output)
            
            # Add new VLANs
            updated = False
            for vlan_id in vlans:
                if vlan_id not in current_vlans:
                    current_vlans.append(vlan_id)
                    updated = True
            
            if updated:
                current_vlans.sort()
                vlans_str = ','.join(map(str, current_vlans))
                cmd = f"sudo ovs-vsctl set port {uplink_port} trunks={vlans_str}"
                success, _ = self.executor.execute_direct(worker_ip, cmd, timeout=10)
                
                if success:
                    logger.info(f"Configured worker {worker_ip} uplink {uplink_port} with VLANs: {vlans}")
                
                return success
            
            return True
        except Exception as e:
            logger.error(f"Error configuring worker {worker_ip} uplink: {e}")
            return False
    
    def _configure_network_node_uplink(self, vlans):
        """
        Configure network node's br-provider uplink port (ens4) to allow VLANs
        
        Args:
            vlans: Set of VLAN IDs to allow
        
        Returns:
            bool: Success status
        """
        try:
            network_node_ip = self.trunk_ports.get('ens4')  # Get network node IP
            if not network_node_ip:
                return False
            
            # Get current trunks on network node
            cmd = "sudo ovs-vsctl get port ens4 trunks"
            success, output = self.executor.execute_direct(network_node_ip, cmd, timeout=10)
            
            if not success:
                logger.warning(f"Failed to get trunks for ens4 on network node {network_node_ip}")
                return False
            
            # Parse current VLANs
            current_vlans = self._parse_vlan_list(output)
            
            # Add new VLANs
            updated = False
            for vlan_id in vlans:
                if vlan_id not in current_vlans:
                    current_vlans.append(vlan_id)
                    updated = True
            
            if updated:
                current_vlans.sort()
                vlans_str = ','.join(map(str, current_vlans))
                cmd = f"sudo ovs-vsctl set port ens4 trunks={vlans_str}"
                success, _ = self.executor.execute_direct(network_node_ip, cmd, timeout=10)
                
                if success:
                    logger.info(f"Configured network node {network_node_ip} uplink ens4 with VLANs: {sorted(current_vlans)}")
                
                return success
            
            return True
        except Exception as e:
            logger.error(f"Error configuring network node uplink: {e}")
            return False
    
    def remove_slice_vlans_from_trunks(self, slice_data):
        """
        Remove VLANs used by a slice from trunk ports
        
        Args:
            slice_data: Slice dictionary with links
        
        Returns:
            bool: Success status
        """
        try:
            # Remove VLANs from slice links
            for link in slice_data.get('links', []):
                vlan_id = link.get('vlan_id')
                if vlan_id:
                    self.remove_vlan_from_trunks(vlan_id)
                    logger.info(f"Removed slice VLAN {vlan_id} from physical switch trunks")
            
            return True
        except Exception as e:
            logger.error(f"Error removing slice VLANs from trunks: {e}")
            return False
    
    def cleanup_network_node_vlans(self, network_node_ip, vlans_to_remove):
        """
        Cleanup orphaned VLAN configurations on network node
        
        Args:
            network_node_ip: Network node IP
            vlans_to_remove: List of VLAN IDs to remove
        
        Returns:
            bool: Success status
        """
        try:
            for vlan_id in vlans_to_remove:
                # Delete namespace
                cmd = f"sudo ip netns del ns-dhcp-vlan{vlan_id} 2>/dev/null || true"
                self.executor.execute_direct(network_node_ip, cmd)
                
                # Delete OVS ports
                cmd = f"sudo ovs-vsctl --if-exists del-port br-provider dhcp_v{vlan_id}"
                self.executor.execute_direct(network_node_ip, cmd)
                
                cmd = f"sudo ovs-vsctl --if-exists del-port br-provider gw_vlan{vlan_id}"
                self.executor.execute_direct(network_node_ip, cmd)
                
                logger.info(f"Cleaned up VLAN {vlan_id} on network node")
            
            return True
        except Exception as e:
            logger.error(f"Error cleaning up network node VLANs: {e}")
            return False
    
    def cleanup_worker_tap_interfaces(self, worker_ip, vm_id):
        """
        Cleanup TAP interfaces for a VM on a worker node
        
        Args:
            worker_ip: Worker node IP
            vm_id: VM ID
        
        Returns:
            bool: Success status
        """
        try:
            # List all TAP interfaces for this VM
            cmd = f"sudo ovs-vsctl list-ports br-provider | grep tap_{vm_id}_"
            success, output = self.executor.execute_direct(worker_ip, cmd, timeout=10)
            
            if success and output.strip():
                tap_interfaces = output.strip().split('\n')
                for tap_name in tap_interfaces:
                    tap_name = tap_name.strip()
                    if tap_name:
                        # Delete from OVS
                        cmd = f"sudo ovs-vsctl --if-exists del-port br-provider {tap_name}"
                        self.executor.execute_direct(worker_ip, cmd)
                        
                        # Delete TAP device
                        cmd = f"sudo ip link del {tap_name} 2>/dev/null || true"
                        self.executor.execute_direct(worker_ip, cmd)
                        
                        logger.info(f"Cleaned up TAP interface {tap_name} on {worker_ip}")
            
            return True
        except Exception as e:
            logger.error(f"Error cleaning up TAP interfaces for VM {vm_id}: {e}")
            return False
    
    def _parse_vlan_list(self, ovs_output):
        """
        Parse OVS trunk VLAN list output
        
        Args:
            ovs_output: Output from 'ovs-vsctl get port X trunks'
        
        Returns:
            list: List of VLAN IDs
        """
        try:
            # Output format: [100, 200, 300] or []
            output = ovs_output.strip()
            if output == '[]':
                return []
            
            # Remove brackets and parse
            output = output.strip('[]')
            vlans = [int(v.strip()) for v in output.split(',') if v.strip()]
            return vlans
        except Exception as e:
            logger.error(f"Error parsing VLAN list '{ovs_output}': {e}")
            return [100]  # Default to VLAN 100
