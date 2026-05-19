"""VLAN Manager - Create/delete VLANs, gateways, DHCP namespaces"""
import subprocess, logging
logger = logging.getLogger(__name__)

class VLANManager:
    def __init__(self, remote_executor, network_node_ip="10.0.10.3"):
        self.executor = remote_executor
        self.network_node_ip = network_node_ip
    
    def create_vlan_with_gateway(self, vlan_id, cidr, gateway_ip, dhcp_enabled=True, create_gateway=True):
        """Create VLAN with gateway on network node and optional DHCP"""
        try:
            if create_gateway:
                mask = cidr.split('/')[1]
                cmd = f"""
                sudo ovs-vsctl --may-exist add-port br-int gw_vlan{vlan_id} tag={vlan_id} -- set interface gw_vlan{vlan_id} type=internal
                sudo ip addr add {gateway_ip}/{mask} dev gw_vlan{vlan_id} 2>/dev/null || true
                sudo ip link set dev gw_vlan{vlan_id} up
                """
                success, output = self.executor.execute_direct(self.network_node_ip, cmd)
                
                if not success:
                    logger.error(f"Gateway creation failed: {output}")
                    return False
            
            if dhcp_enabled:
                return self._setup_dhcp(vlan_id, cidr, gateway_ip)
            return True
        except Exception as e:
            logger.error(f"VLAN creation error: {e}")
            return False
    
    def _setup_dhcp(self, vlan_id, cidr, gateway_ip):
        """Setup DHCP namespace with dnsmasq on network node"""
        try:
            ns_name = f"ns-dhcp-vlan{vlan_id}"
            dhcp_port = f"dhcp_v{vlan_id}"
            base_ip = '.'.join(cidr.split('.')[0:3])
            mask = cidr.split('/')[1]
            
            # Use .254 for DHCP server IP to avoid conflicts
            dhcp_ip = f"{base_ip}.254"
            dhcp_range = f"{base_ip}.10,{base_ip}.250"
            
            # Step by step to catch errors
            logger.info(f"Creating namespace {ns_name}")
            cmd1 = f"sudo ip netns add {ns_name} 2>/dev/null || true"
            self.executor.execute_direct(self.network_node_ip, cmd1)
            
            logger.info(f"Creating DHCP port {dhcp_port} in VLAN {vlan_id}")
            cmd2 = f"sudo ovs-vsctl --may-exist add-port br-int {dhcp_port} tag={vlan_id} -- set interface {dhcp_port} type=internal"
            success, output = self.executor.execute_direct(self.network_node_ip, cmd2)
            if not success:
                logger.error(f"Failed to create DHCP port: {output}")
                return False
            
            # Wait for port to be created
            import time
            time.sleep(1)
            
            # Verify port exists before moving to namespace
            verify_cmd = f"ip link show {dhcp_port}"
            success, output = self.executor.execute_direct(self.network_node_ip, verify_cmd)
            if not success:
                logger.error(f"DHCP port {dhcp_port} was not created: {output}")
                return False
            
            logger.info(f"Moving {dhcp_port} to namespace {ns_name}")
            cmd3 = f"sudo ip link set {dhcp_port} netns {ns_name}"
            success, output = self.executor.execute_direct(self.network_node_ip, cmd3)
            if not success:
                logger.error(f"Failed to move port to namespace: {output}")
                return False
            
            logger.info(f"Configuring IP {dhcp_ip}/{mask} on {dhcp_port}")
            cmd4 = f"""
            sudo ip netns exec {ns_name} ip addr add {dhcp_ip}/{mask} dev {dhcp_port} 2>/dev/null || true
            sudo ip netns exec {ns_name} ip link set dev lo up
            sudo ip netns exec {ns_name} ip link set dev {dhcp_port} up
            """
            self.executor.execute_direct(self.network_node_ip, cmd4)
            
            logger.info(f"Starting dnsmasq in {ns_name} (range: {dhcp_range})")
            cmd5 = f"sudo ip netns exec {ns_name} pkill dnsmasq 2>/dev/null || true"
            self.executor.execute_direct(self.network_node_ip, cmd5)
            
            cmd6 = f"sudo ip netns exec {ns_name} dnsmasq --interface={dhcp_port} --bind-interfaces --dhcp-range={dhcp_range},24h --dhcp-option=3,{gateway_ip} --dhcp-option=6,8.8.8.8 --log-facility=-"
            success, output = self.executor.execute_direct(self.network_node_ip, cmd6, timeout=10)
            
            if not success:
                logger.error(f"Failed to start dnsmasq: {output}")
                return False
            
            # Verify dnsmasq is running
            verify_cmd = f"sudo ip netns exec {ns_name} pgrep dnsmasq"
            success, pid = self.executor.execute_direct(self.network_node_ip, verify_cmd)
            
            if success and pid.strip():
                logger.info(f"DHCP configured for VLAN {vlan_id} (dnsmasq PID: {pid.strip()})")
                return True
            else:
                logger.error(f"dnsmasq not running in {ns_name}")
                return False
                
        except Exception as e:
            logger.error(f"DHCP setup error: {e}")
            return False
    
    def enable_internet_for_vlan(self, vlan_id, cidr, outgoing_iface="ens3"):
        """Enable internet access for VLAN via MASQUERADE"""
        try:
            cmd = f"""
            sudo sysctl -w net.ipv4.ip_forward=1
            sudo iptables -t nat -A POSTROUTING -s {cidr} -o {outgoing_iface} -j MASQUERADE 2>/dev/null || true
            sudo iptables -A FORWARD -i gw_vlan{vlan_id} -o {outgoing_iface} -j ACCEPT 2>/dev/null || true
            sudo iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || true
            """
            success, _ = self.executor.execute_direct(self.network_node_ip, cmd)
            if success:
                logger.info(f"Internet enabled for VLAN {vlan_id}")
            return success
        except Exception as e:
            logger.error(f"Internet setup error: {e}")
            return False
    
    def delete_vlan(self, vlan_id):
        """Delete VLAN and cleanup on network node"""
        try:
            cmd = f"""
            sudo ip netns exec ns-dhcp-vlan{vlan_id} pkill dnsmasq 2>/dev/null || true
            sudo ip netns delete ns-dhcp-vlan{vlan_id} 2>/dev/null || true
            sudo ovs-vsctl --if-exists del-port br-int gw_vlan{vlan_id}
            sudo ovs-vsctl --if-exists del-port br-int dhcp_v{vlan_id}
            sudo ip link del gw_vlan{vlan_id} 2>/dev/null || true
            """
            success, _ = self.executor.execute_direct(self.network_node_ip, cmd)
            if success:
                logger.info(f"VLAN {vlan_id} deleted")
            return success
        except Exception as e:
            logger.error(f"VLAN deletion error: {e}")
            return False
