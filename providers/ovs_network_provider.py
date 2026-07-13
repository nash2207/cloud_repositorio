"""
OVS Network Provider - OpenVSwitch + dnsmasq implementation
"""
import logging
from providers.base_compute import BaseNetworkProvider

logger = logging.getLogger(__name__)


class OVSNetworkProvider(BaseNetworkProvider):
    """Network provider using OpenVSwitch and dnsmasq for DHCP"""
    
    def __init__(self, remote_executor, network_node_ip="10.0.0.1", bridge_name="br-int"):
        self.executor = remote_executor
        self.network_node_ip = network_node_ip
        self.bridge_name = bridge_name  # Configurable OVS bridge name
    
    def create_network(self, vlan_id, cidr, gateway_ip, dhcp_enabled=True, create_gateway=True):
        """Create VLAN with gateway and optional DHCP on network node"""
        try:
            # Create gateway interface on OVS
            if create_gateway:
                mask = cidr.split('/')[1]
                cmd = f"""
                sudo ovs-vsctl --may-exist add-port {self.bridge_name} gw_vlan{vlan_id} tag={vlan_id} -- set interface gw_vlan{vlan_id} type=internal
                sudo ip addr add {gateway_ip}/{mask} dev gw_vlan{vlan_id} 2>/dev/null || true
                sudo ip link set dev gw_vlan{vlan_id} up
                """
                success, output = self.executor.execute_direct(self.network_node_ip, cmd)
                
                if not success:
                    logger.error(f"Gateway creation failed for VLAN {vlan_id}: {output}")
                    return False
            
            # Setup DHCP server
            if dhcp_enabled:
                return self._setup_dhcp(vlan_id, cidr, gateway_ip)
            
            return True
        except Exception as e:
            logger.error(f"Network creation error for VLAN {vlan_id}: {e}")
            return False
    
    def delete_network(self, vlan_id):
        """Delete VLAN and cleanup DHCP namespace"""
        try:
            cmd = f"""
            sudo ip netns exec ns-dhcp-vlan{vlan_id} pkill dnsmasq 2>/dev/null || true
            sudo ip netns delete ns-dhcp-vlan{vlan_id} 2>/dev/null || true
            sudo ovs-vsctl --if-exists del-port {self.bridge_name} gw_vlan{vlan_id}
            sudo ovs-vsctl --if-exists del-port {self.bridge_name} dhcp_v{vlan_id}
            sudo ip link del gw_vlan{vlan_id} 2>/dev/null || true
            """
            success, _ = self.executor.execute_direct(self.network_node_ip, cmd)
            
            if success:
                logger.info(f"VLAN {vlan_id} deleted")
            return success
        except Exception as e:
            logger.error(f"Network deletion error for VLAN {vlan_id}: {e}")
            return False
    
    def create_interface(self, vm_id, interface_name, vlan_id):
        """Not needed for OVS - interfaces are created during VM launch"""
        return True
    
    def _setup_dhcp(self, vlan_id, cidr, gateway_ip):
        """Setup DHCP namespace with dnsmasq"""
        try:
            ns_name = f"ns-dhcp-vlan{vlan_id}"
            dhcp_port = f"dhcp_v{vlan_id}"
            base_ip = '.'.join(cidr.split('.')[0:3])
            mask = cidr.split('/')[1]
            
            # Special handling for VLAN 400 (internet)
            if vlan_id == 400:
                # VLAN 400: 10.60.8.128/25 range (.129 to .254)
                # Gateway: 10.60.8.254 (external)
                # DHCP server IP: 10.60.8.253 (internal on network node)
                # DHCP range: 10.60.8.129 - 10.60.8.252
                dhcp_ip = "10.60.8.253"
                dhcp_range = "10.60.8.129,10.60.8.252"
            else:
                # Other VLANs: use standard configuration
                # DHCP server on .254, range .10-.250
                dhcp_ip = f"{base_ip}.254"
                dhcp_range = f"{base_ip}.10,{base_ip}.250"
            
            # Create namespace
            logger.info(f"Creating namespace {ns_name}")
            cmd1 = f"sudo ip netns add {ns_name} 2>/dev/null || true"
            self.executor.execute_direct(self.network_node_ip, cmd1)
            
            # Create DHCP port on OVS
            logger.info(f"Creating DHCP port {dhcp_port} in VLAN {vlan_id}")
            cmd2 = f"sudo ovs-vsctl --may-exist add-port {self.bridge_name} {dhcp_port} tag={vlan_id} -- set interface {dhcp_port} type=internal"
            success, output = self.executor.execute_direct(self.network_node_ip, cmd2)
            if not success:
                logger.error(f"Failed to create DHCP port: {output}")
                return False
            
            # Wait for port creation
            import time
            time.sleep(1)
            
            # Verify port exists (check both default namespace and target namespace)
            verify_cmd = f"ip link show {dhcp_port} || sudo ip netns exec {ns_name} ip link show {dhcp_port}"
            success, output = self.executor.execute_direct(self.network_node_ip, verify_cmd)
            
            # If port already exists in the namespace, we can skip moving it
            if "does not exist" in output:
                logger.error(f"DHCP port {dhcp_port} was not created: {output}")
                return False
            elif ns_name in output or "netns" in output:
                logger.info(f"DHCP port {dhcp_port} already in namespace {ns_name}, skipping move")
            
            # Move port to namespace (only if not already moved)
            check_ns_cmd = f"sudo ip netns exec {ns_name} ip link show {dhcp_port} 2>/dev/null"
            success, check_output = self.executor.execute_direct(self.network_node_ip, check_ns_cmd)
            
            if not success or dhcp_port not in check_output:
                # Port not in namespace yet, move it
                logger.info(f"Moving {dhcp_port} to namespace {ns_name}")
                cmd3 = f"sudo ip link set {dhcp_port} netns {ns_name}"
                success, output = self.executor.execute_direct(self.network_node_ip, cmd3)
                if not success:
                    logger.error(f"Failed to move port to namespace: {output}")
                    return False
            else:
                logger.info(f"Port {dhcp_port} already in namespace {ns_name}")
            
            # Configure IP on DHCP port
            logger.info(f"Configuring IP {dhcp_ip}/{mask} on {dhcp_port}")
            cmd4 = f"""
            sudo ip netns exec {ns_name} ip addr add {dhcp_ip}/{mask} dev {dhcp_port} 2>/dev/null || true
            sudo ip netns exec {ns_name} ip link set dev lo up
            sudo ip netns exec {ns_name} ip link set dev {dhcp_port} up
            """
            self.executor.execute_direct(self.network_node_ip, cmd4)
            
            # Start dnsmasq (disable DNS on port 53, only DHCP on port 67/68)
            logger.info(f"Starting dnsmasq in {ns_name} (range: {dhcp_range})")
            cmd5 = f"sudo ip netns exec {ns_name} pkill dnsmasq 2>/dev/null || true"
            self.executor.execute_direct(self.network_node_ip, cmd5)
            
            # Run dnsmasq as a proper daemon using nohup and disown
            # --port=0: Disable DNS server (no port 53 conflict)
            # --dhcp-range: DHCP range and lease time
            # --dhcp-option=3: Default gateway
            # --dhcp-option=6: DNS server (Google DNS)
            # --keep-in-foreground: Prevent double-fork (incompatible with netns)
            # --log-dhcp: Enable DHCP transaction logging
            # --log-facility=-: Log to stderr
            # nohup + setsid: Properly daemonize to survive SSH session close
            cmd6 = f"sudo ip netns exec {ns_name} bash -c 'nohup dnsmasq --port=0 --interface={dhcp_port} --bind-interfaces --dhcp-range={dhcp_range},24h --dhcp-option=3,{gateway_ip} --dhcp-option=6,8.8.8.8 --log-dhcp --log-facility=- > /var/log/dnsmasq-vlan{vlan_id}.log 2>&1 &'"
            success, output = self.executor.execute_direct(self.network_node_ip, cmd6, timeout=10)
            
            if not success:
                logger.error(f"Failed to start dnsmasq command: {output}")
            
            # Wait a moment for dnsmasq to start
            import time
            time.sleep(2)
            
            # Verify dnsmasq is running
            verify_cmd = f"sudo ip netns exec {ns_name} pgrep dnsmasq"
            success, pid = self.executor.execute_direct(self.network_node_ip, verify_cmd, timeout=5)
            
            if success and pid.strip():
                logger.info(f"DHCP configured for VLAN {vlan_id} (dnsmasq PID: {pid.strip()})")
                return True
            else:
                logger.error(f"dnsmasq not running in {ns_name} after startup")
                # Try to read the log file to see what went wrong
                log_check = f"sudo tail -20 /var/log/dnsmasq-vlan{vlan_id}.log 2>/dev/null || echo 'No log file'"
                _, log_output = self.executor.execute_direct(self.network_node_ip, log_check, timeout=5)
                logger.error(f"dnsmasq log for VLAN {vlan_id}: {log_output}")
                return False
                
        except Exception as e:
            logger.error(f"DHCP setup error for VLAN {vlan_id}: {e}")
            return False
