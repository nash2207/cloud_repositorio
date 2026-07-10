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
        Add all VLANs used by a slice to trunk ports
        
        Args:
            slice_data: Slice dictionary with links
        
        Returns:
            bool: Success status
        """
        try:
            # Always add VLAN 400 for internet
            self.add_vlan_to_trunks(400)
            
            # Add VLANs from slice links
            for link in slice_data.get('links', []):
                vlan_id = link.get('vlan_id')
                if vlan_id:
                    self.add_vlan_to_trunks(vlan_id)
                    logger.info(f"Added slice VLAN {vlan_id} to physical switch trunks")
            
            return True
        except Exception as e:
            logger.error(f"Error adding slice VLANs to trunks: {e}")
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
